#!/usr/bin/env python
"""erdgen.py — generates erd.mmd (Mermaid) and schema.dbml in the model docs from schema/tables/.

Principle P1: diagrams are DERIVED — never edited by hand.
Deterministic output (sorted everywhere) so --check works in CI.

The diagrams are reading artifacts: they live beside the domain prose, in
`docs/db-model/` (path declared in `_paths.py`), not inside `db-schema/`.

What lands in the DBML, and from where — versioned sources only, every one optional:
  - columns, keys, FKs (name, composite, ON DELETE/UPDATE), table/column comments
      <- schema/tables/*.sql (`--` lines before CREATE TABLE / a column, inline
         COMMENT, COMMENT ON)
  - table note: Concept, model link, elimination candidate; TableGroup per `###` group;
    implied relations (`**Implied:**`, drawn in their own color / dotted in Mermaid)
      <- docs/db-model/database.md + domains/*.md (formats in docs/db-model/README.md)
  - routines touching the table <- db-schema/baseline/inventory.*.json (depends_on)
  - blocked/excluded + reason <- db-schema/baseline/exceptions.json
  - watched data <- db-schema/baseline/watched-data.json
  - protected-rule memos naming the table as `<table>` <- docs/db-model/calc/*.md
  - dialect overrides <- schema/overrides/<dialect>/<table>.sql
Editing any of these without re-running erdgen turns `--check` red.

Usage:
  python tools/erdgen.py           # regenerate erd.mmd and schema.dbml in the model docs
  python tools/erdgen.py --check   # fail (exit 1) when the committed ones diverge
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

from _dialect import canonical_dialect, qualified
from _model import Block, elimination_candidates, table_blocks
from _paths import KIT_ROOT, MODEL_DIR, display, link_to, model_path

ROOT = KIT_ROOT
TABLES_DIR = ROOT / "schema" / "tables"
OVERRIDES_DIR = ROOT / "schema" / "overrides"
BASELINE_DIR = ROOT / "baseline"
CALC_DIR = MODEL_DIR / "calc"
ERD_MMD = model_path("erd.mmd")
ERD_DBML = model_path("schema.dbml")
IMPLIED_COLOR = "#d97706"


@dataclass
class Column:
    name: str
    type: str
    not_null: bool = False
    pk: bool = False
    fk: bool = False
    comment: str | None = None


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    name: str | None = None
    on_delete: str | None = None
    on_update: str | None = None


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    fks: list[ForeignKey] = field(default_factory=list)
    comment: str | None = None


# ---------------------------------------------------------------- DDL parsing

_COMMENT_LINE = re.compile(r"^\s*--\s?(.*?)\s*$")
_LEAD_IDENT = re.compile(r"""^\s*[\["`]?([^\s\]"`(,]+)[\]"`]?\s""")
_TRAILING = re.compile(r",?\s*--\s?(.*?)\s*$")


def _comment_block(lines: list[str], i: int) -> str | None:
    """Contiguous `--` lines directly above line i, joined; None when there are none."""
    out: list[str] = []
    j = i - 1
    while j >= 0:
        m = _COMMENT_LINE.match(lines[j])
        if not m:
            break
        out.append(m[1])
        j -= 1
    text = " ".join(t for t in reversed(out) if t)
    return text or None


def _raw_comments(sql: str, columns: set[str]) -> tuple[str | None, dict[str, str]]:
    """Table and column comments written as `--` lines (the carve format)."""
    lines = sql.splitlines()
    table_comment = None
    col_comments: dict[str, str] = {}
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"^\s*CREATE\s+(\w+\s+)*TABLE\b", ln, re.IGNORECASE)), None)
    if start is None:
        return None, {}
    table_comment = _comment_block(lines, start)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if _COMMENT_LINE.match(ln):
            continue
        if re.match(r"^\s*\)\s*;?\s*$", ln):
            break
        m = _LEAD_IDENT.match(ln)
        if not m or m[1] not in columns or m[1] in col_comments:
            continue
        above = _comment_block(lines, i)
        trail = _TRAILING.search(ln) if "--" in ln else None
        text = above or (trail[1] if trail and trail[1] else None)
        if text:
            col_comments[m[1]] = text
    return table_comment, col_comments


def _options(ref: exp.Reference | None) -> tuple[str | None, str | None]:
    on_delete = on_update = None
    for opt in (ref.args.get("options") or []) if ref is not None else []:
        m = re.match(r"ON\s+(DELETE|UPDATE)\s+(.+)", str(opt).strip(), re.IGNORECASE)
        if not m:
            continue
        action = m[2].strip().lower()
        if action == "no action":
            continue
        if m[1].upper() == "DELETE":
            on_delete = action
        else:
            on_update = action
    return on_delete, on_update


def _fk(cols: list[str], ref: exp.Reference, name: str | None) -> ForeignKey:
    ref_schema = ref.this
    on_delete, on_update = _options(ref)
    return ForeignKey(
        columns=cols,
        ref_table=qualified(ref_schema.this.db, ref_schema.this.name),
        ref_columns=[c.name for c in ref_schema.expressions],
        name=name, on_delete=on_delete, on_update=on_update,
    )


def _literal(node: exp.Expression | None) -> str | None:
    if isinstance(node, exp.Literal):
        return node.this or None
    return None


def _colname(node: exp.Expression) -> str:
    """Column name from Identifier, Column, or Ordered(Column) (key column lists)."""
    return node.this.name if isinstance(node, exp.Ordered) else node.name


def parse_table(sql: str) -> Table | None:
    dialect = canonical_dialect()
    # A table file may carry CREATE INDEX / COMMENT ON statements after the CREATE
    # TABLE; only the CREATE TABLE and its comments feed the diagram.
    statements = sqlglot.parse(sql, read=dialect)
    tree = next(
        (s for s in statements if isinstance(s, exp.Create) and s.kind == "TABLE"),
        None,
    )
    if tree is None:
        return None
    schema = tree.this
    table = Table(name=qualified(schema.this.db, schema.this.name))

    for e in schema.expressions:
        if isinstance(e, exp.ColumnDef):
            col = Column(name=e.name, type=e.args["kind"].sql(dialect=dialect))
            for c in e.args.get("constraints") or []:
                kind = c.kind
                if isinstance(kind, exp.NotNullColumnConstraint):
                    col.not_null = not kind.args.get("allow_null")  # explicit NULL
                if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                    col.pk = True
                    table.pk.append(col.name)
                if isinstance(kind, exp.CommentColumnConstraint):
                    col.comment = _literal(kind.this)
                if isinstance(kind, exp.Reference):
                    table.fks.append(_fk([col.name], kind, None))
            table.columns.append(col)
        elif isinstance(e, exp.PrimaryKey):
            table.pk = [_colname(c) for c in e.expressions]
        elif isinstance(e, exp.ForeignKey):
            table.fks.append(_fk([c.name for c in e.expressions], e.args["reference"], None))
        elif isinstance(e, exp.Constraint):
            cname = e.this.name if e.this is not None else None
            subs = e.expressions
            if isinstance(e.this, exp.Identifier) and any(
                    isinstance(s, exp.PrimaryKeyColumnConstraint) for s in subs):
                # T-SQL: CONSTRAINT pk PRIMARY KEY [NON]CLUSTERED (cols)
                for s in subs:
                    if isinstance(s, (exp.ClusteredColumnConstraint,
                                      exp.NonClusteredColumnConstraint)):
                        table.pk = [_colname(c) for c in s.this or []]
            for sub in subs:
                if isinstance(sub, exp.PrimaryKey):
                    table.pk = [_colname(c) for c in sub.expressions]
                if isinstance(sub, exp.ForeignKey):
                    table.fks.append(_fk([c.name for c in sub.expressions],
                                         sub.args["reference"], cname))

    # comments: inline COMMENT (above), table COMMENT property, COMMENT ON, `--` lines
    props = tree.args.get("properties")
    for p in (props.expressions if props else []):
        if isinstance(p, exp.SchemaCommentProperty):
            table.comment = _literal(p.this)
    for s in statements:
        if isinstance(s, exp.Comment) and isinstance(s.expression, exp.Literal):
            kind = (s.args.get("kind") or "").upper()
            if kind == "TABLE":
                table.comment = s.expression.this or table.comment
            elif kind == "COLUMN":
                for c in table.columns:
                    if c.name == s.this.name:
                        c.comment = s.expression.this or c.comment
    raw_table, raw_cols = _raw_comments(sql, {c.name for c in table.columns})
    table.comment = table.comment or raw_table
    for c in table.columns:
        c.comment = c.comment or raw_cols.get(c.name)

    for c in table.columns:
        if c.name in table.pk:
            c.pk = True
        if any(c.name in fk.columns for fk in table.fks):
            c.fk = True
    return table


# ---------------------------------------------------------- versioned context

@dataclass
class Context:
    blocks: dict[str, Block] = field(default_factory=dict)
    eliminations: set[str] = field(default_factory=set)
    routines: dict[str, list[tuple[str, str, Path]]] = field(default_factory=dict)
    exceptions: dict[str, str] = field(default_factory=dict)
    watched: dict[str, str] = field(default_factory=dict)
    calc: dict[str, list[Path]] = field(default_factory=dict)
    overrides: dict[str, list[Path]] = field(default_factory=dict)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gather_context(tables: list[Table]) -> Context:
    names = {t.name for t in tables}
    ctx = Context()
    ctx.blocks = table_blocks(names)
    ctx.eliminations = elimination_candidates(names)
    repo_root = KIT_ROOT.parent

    # routines touching a table: invert depends_on of every non-table object
    for inv in sorted(BASELINE_DIR.glob("inventory.*.json")):
        data = _load_json(inv) or {}
        objects = data.get("objects") or []
        table_qn: dict[tuple[str, str], str] = {}
        for o in objects:
            target = o.get("target") or ""
            if "/schema/tables/" in target:
                table_qn[(o.get("schema") or "", o.get("name") or "")] = Path(target).stem
        for o in objects:
            target = o.get("target") or ""
            if not target or "/schema/tables/" in target:
                continue
            kind = Path(target).parent.name
            for dep in o.get("depends_on") or []:
                if "." in dep:
                    sch, nm = dep.split(".", 1)
                else:
                    sch, nm = o.get("schema") or "", dep
                qn = table_qn.get((sch, nm))
                if qn in names:
                    ctx.routines.setdefault(qn, []).append(
                        (kind, Path(target).stem, repo_root / target))
    for qn in ctx.routines:
        ctx.routines[qn] = sorted(set(ctx.routines[qn]), key=lambda r: (r[0], r[1]))

    for e in _load_json(BASELINE_DIR / "exceptions.json") or []:
        qn = qualified(e.get("schema"), e.get("name") or "")
        if qn in names:
            ctx.exceptions[qn] = f"{e.get('status', 'exception')}: {e.get('reason', '')}".strip()

    for w in _load_json(BASELINE_DIR / "watched-data.json") or []:
        qn = qualified(w.get("schema"), w.get("table") or "")
        if qn in names:
            ctx.watched[qn] = w.get("rule") or "watched"

    if CALC_DIR.is_dir():
        for memo in sorted(CALC_DIR.glob("*.md")):
            if memo.name.lower() == "readme.md":
                continue
            text = memo.read_text(encoding="utf-8")
            for qn in names:
                if f"`{qn}`" in text:
                    ctx.calc.setdefault(qn, []).append(memo)

    if OVERRIDES_DIR.is_dir():
        for f in sorted(OVERRIDES_DIR.glob("*/*.sql")):
            if f.stem in names:
                ctx.overrides.setdefault(f.stem, []).append(f)
    return ctx


# ------------------------------------------------------------------- Mermaid

def _mermaid_type(t: str) -> str:
    """Mermaid does not accept comma/quote/space in an attribute type."""
    t = re.sub(r"\((?![\d, ]+\)).*\)", "", t)          # ENUM('G',...) -> ENUM
    t = t.replace(", ", ",").replace(",", "-")           # DECIMAL(4,2) -> DECIMAL(4-2)
    return t.replace(" ", "_")


def _mermaid_attr(name: str) -> str:
    """Mermaid attribute names take no spaces or '-': `Data de início` -> `Data_de_início`."""
    return re.sub(r"[^\w]", "_", name)


def _mermaid_id(name: str) -> str:
    # Mermaid entity ids take no '.', so a schema-qualified name becomes schema__name
    return name.replace(".", "__")


def to_mermaid(tables: list[Table], ctx: Context | None = None) -> str:
    out = ["erDiagram"]
    for t in sorted(tables, key=lambda x: x.name):
        for fk in sorted(t.fks, key=lambda f: (f.ref_table, f.columns)):
            nullable = any(
                (c.name in fk.columns and not c.not_null) for c in t.columns
            )
            card = "|o--o{" if nullable else "||--o{"
            label = "-".join(fk.columns)
            out.append(f"    {_mermaid_id(fk.ref_table)} {card} {_mermaid_id(t.name)} : \"{label}\"")
        block = ctx.blocks.get(t.name) if ctx else None
        for imp in sorted(block.implied if block else [], key=lambda i: (i.ref_table, i.columns)):
            # dotted = non-identifying in Mermaid; here: a relation with no FK behind it
            label = "implied " + "-".join(imp.columns)
            out.append(f"    {_mermaid_id(imp.ref_table)} |o..o{{ {_mermaid_id(t.name)} : \"{label}\"")
    out.append("")
    for t in sorted(tables, key=lambda x: x.name):
        out.append(f"    {_mermaid_id(t.name)} {{")
        for c in t.columns:
            keys = []
            if c.pk:
                keys.append("PK")
            if c.fk:
                keys.append("FK")
            key_marker = f" {','.join(keys)}" if keys else ""
            out.append(f"        {_mermaid_type(c.type)} {_mermaid_attr(c.name)}{key_marker}")
        out.append("    }")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------- DBML

def _dbml_type(t: str) -> tuple[str, str | None]:
    """ENUM/SET have no portable DBML equivalent → text + note with the original."""
    if t.upper().startswith(("ENUM(", "SET(")):
        return "varchar", t
    return f'"{t}"' if (" " in t or "," in t) else t.lower(), None


def _q(s: str) -> str:
    """A single-quoted DBML string."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ") + "'"


def _id(name: str) -> str:
    """A DBML identifier: bare when plain ASCII, double-quoted otherwise (spaces, accents, '-')."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else '"' + name.replace('"', '\\"') + '"'


def _tid(qualified_name: str) -> str:
    """A table reference: schema and name quoted separately."""
    return ".".join(_id(part) for part in qualified_name.split(".", 1))


def _ref_side(table: str, cols: list[str] | tuple[str, ...]) -> str:
    if len(cols) == 1:
        return f"{_tid(table)}.{_id(cols[0])}"
    return f"{_tid(table)}.({', '.join(_id(c) for c in cols)})"


def _table_note(t: Table, ctx: Context) -> list[str]:
    block = ctx.blocks.get(t.name)
    head: list[str] = []
    if block and block.concept:
        head.append(block.concept)
    elif t.comment:
        head.append(t.comment)
    if block and block.concept and t.comment and t.comment != block.concept:
        head.append(f"DDL comment: {t.comment}")
    if block is None or not block.concept:
        head.append("model block pending")
    if t.name in ctx.eliminations:
        head.append("ELIMINATION CANDIDATE")

    links: list[str] = []
    if block:
        links.append(f"[model]({link_to(block.file)}#{block.anchor})")
    links.append(f"[DDL]({link_to(TABLES_DIR / (t.name + '.sql'))})")
    for f in ctx.overrides.get(t.name, []):
        links.append(f"[override {f.parent.name}]({link_to(f)})")

    lines = [" · ".join(head), " · ".join(links)]
    routines = ctx.routines.get(t.name)
    if routines:
        lines.append("routines: " + ", ".join(
            f"[{kind} {name}]({link_to(path)})" for kind, name, path in routines))
    flags: list[str] = []
    for memo in ctx.calc.get(t.name, []):
        flags.append(f"[protected] rule [{memo.stem}]({link_to(memo)})")
    if t.name in ctx.exceptions:
        flags.append(ctx.exceptions[t.name])
    if t.name in ctx.watched:
        flags.append(f"watched data: {ctx.watched[t.name]}")
    for fk in t.fks:
        if _self_column_fk(t, fk):
            flags.append(f"FK {fk.name or ''} references its own column(s) "
                         f"{', '.join(fk.columns)} (not drawable)".replace("FK  ", "FK "))
    if flags:
        lines.append(" · ".join(flags))
    return lines


def _self_column_fk(t: Table, fk: ForeignKey) -> bool:
    """An FK from columns to those same columns — legal DDL, no relation to draw."""
    return fk.ref_table == t.name and list(fk.columns) == list(fk.ref_columns)


def to_dbml(tables: list[Table], ctx: Context | None = None) -> str:
    ctx = ctx or Context()
    out = ["// GENERATED by tools/erdgen.py — do not edit by hand (principle P1)", ""]
    for t in sorted(tables, key=lambda x: x.name):
        out.append(f"Table {_tid(t.name)} {{")
        for c in t.columns:
            typ, note = _dbml_type(c.type)
            attrs = []
            if c.pk and len(t.pk) == 1:
                attrs.append("pk")
            if c.not_null:
                attrs.append("not null")
            notes = [n for n in (note, c.comment) if n]
            if notes:
                attrs.append(f"note: {_q(' · '.join(notes))}")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            out.append(f"    {_id(c.name)} {typ}{suffix}")
        if len(t.pk) > 1:
            out.append("")
            out.append("    indexes {")
            out.append(f"        ({', '.join(_id(c) for c in t.pk)}) [pk]")
            out.append("    }")
        out.append("")
        out.append("    Note: '''")
        for line in _table_note(t, ctx):
            out.append("    " + line.replace("\\", "\\\\").replace("'''", "\\'''"))
        out.append("    '''")
        out.append("}")
        out.append("")

    names = {t.name for t in tables}
    for t in sorted(tables, key=lambda x: x.name):
        for fk in sorted(t.fks, key=lambda f: (f.ref_table, f.columns)):
            settings = []
            if fk.on_delete:
                settings.append(f"delete: {fk.on_delete}")
            if fk.on_update:
                settings.append(f"update: {fk.on_update}")
            label = f"Ref {fk.name}:" if fk.name and re.fullmatch(r"\w+", fk.name) else "Ref:"
            suffix = f" [{', '.join(settings)}]" if settings else ""
            line = (f"{label} {_ref_side(t.name, fk.columns)} > "
                    f"{_ref_side(fk.ref_table, fk.ref_columns)}{suffix}")
            # DBML rejects a Ref to the same column(s) or to a table it does not
            # declare: keep the fact as a comment instead of breaking the file
            if _self_column_fk(t, fk):
                line = f"// {line}  -- references its own column(s)"
            elif fk.ref_table not in names:
                line = f"// {line}  -- target table not in schema/tables/"
            out.append(line)
    for t in sorted(tables, key=lambda x: x.name):
        block = ctx.blocks.get(t.name)
        for imp in sorted(block.implied if block else [], key=lambda i: (i.ref_table, i.columns)):
            if imp.ref_table not in names:
                continue  # doccheck reports it; a dangling Ref would break the DBML
            note = f" // implied, no FK{': ' + imp.note if imp.note else ''}"
            out.append(f"Ref: {_ref_side(t.name, imp.columns)} > "
                       f"{_ref_side(imp.ref_table, imp.ref_columns)} [color: {IMPLIED_COLOR}]{note}")

    groups: dict[str, list[str]] = {}
    for name, block in ctx.blocks.items():
        if block.group:
            groups.setdefault(block.group, []).append(name)
    if groups:
        out.append("")
    for group in sorted(groups):
        out.append(f"TableGroup {_id(group)} {{")
        for name in sorted(groups[group]):
            out.append(f"    {_tid(name)}")
        out.append("}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    tables: list[Table] = []
    for f in sorted(TABLES_DIR.glob("*.sql")):
        t = parse_table(f.read_text(encoding="utf-8"))
        if t is None:
            print(f"ERROR: {f.name} does not contain a parseable CREATE TABLE.")
            return 1
        tables.append(t)

    if not tables:
        # A fresh drop-in module has no tables yet — nothing to generate/check, not an error.
        print("No tables in schema/tables/ — nothing to do.")
        return 0

    ctx = gather_context(tables)
    mmd = to_mermaid(tables, ctx)
    dbml = to_dbml(tables, ctx)

    if check:
        ok = True
        for path, new in ((ERD_MMD, mmd), (ERD_DBML, dbml)):
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if old != new:
                print(f"OUT OF DATE: {display(path)} — run: python tools/erdgen.py")
                ok = False
        if ok:
            print(f"OK: diagrams in sync with schema/tables/ and the model docs ({len(tables)} tables).")
        return 0 if ok else 1

    ERD_MMD.parent.mkdir(parents=True, exist_ok=True)
    ERD_MMD.write_text(mmd, encoding="utf-8", newline="\n")
    ERD_DBML.write_text(dbml, encoding="utf-8", newline="\n")
    print(f"Generated: {display(ERD_MMD)}, {display(ERD_DBML)} ({len(tables)} tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
