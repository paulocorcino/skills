#!/usr/bin/env python
"""erdgen.py — gera model/erd.mmd (Mermaid) e model/schema.dbml a partir de schema/tables/.

Principle P1: diagrams are DERIVED — never edited by hand.
Deterministic output (alphabetical order) so --check works in CI.

Uso:
  python tools/erdgen.py           # regenera model/erd.mmd e model/schema.dbml
  python tools/erdgen.py --check   # falha (exit 1) se os commitados divergirem
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import exp

from _dialect import canonical_dialect

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "schema" / "tables"
ERD_MMD = ROOT / "model" / "erd.mmd"
ERD_DBML = ROOT / "model" / "schema.dbml"


@dataclass
class Column:
    name: str
    type: str
    not_null: bool = False
    pk: bool = False
    fk: bool = False


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    pk: list[str] = field(default_factory=list)
    fks: list[ForeignKey] = field(default_factory=list)


def parse_table(sql: str) -> Table | None:
    dialect = canonical_dialect()
    # A table file may carry CREATE INDEX statements after the CREATE TABLE;
    # only the CREATE TABLE feeds the diagram.
    statements = sqlglot.parse(sql, read=dialect)
    tree = next(
        (s for s in statements if isinstance(s, exp.Create) and s.kind == "TABLE"),
        None,
    )
    if tree is None:
        return None
    schema = tree.this
    table = Table(name=schema.this.name)

    for e in schema.expressions:
        if isinstance(e, exp.ColumnDef):
            col = Column(name=e.name, type=e.args["kind"].sql(dialect=dialect))
            for c in e.args.get("constraints") or []:
                kind = c.kind
                if isinstance(kind, exp.NotNullColumnConstraint):
                    col.not_null = True
                if isinstance(kind, exp.PrimaryKeyColumnConstraint):
                    col.pk = True
                    table.pk.append(col.name)
            table.columns.append(col)
        elif isinstance(e, exp.PrimaryKey):
            table.pk = [c.name for c in e.expressions]
        elif isinstance(e, exp.ForeignKey):
            cols = [c.name for c in e.expressions]
            ref = e.args.get("reference")
            ref_schema = ref.this
            fk = ForeignKey(
                columns=cols,
                ref_table=ref_schema.this.name,
                ref_columns=[c.name for c in ref_schema.expressions],
            )
            table.fks.append(fk)
        elif isinstance(e, exp.Constraint):
            for sub in e.expressions:
                if isinstance(sub, exp.ForeignKey):
                    cols = [c.name for c in sub.expressions]
                    ref = sub.args.get("reference")
                    ref_schema = ref.this
                    table.fks.append(ForeignKey(
                        columns=cols,
                        ref_table=ref_schema.this.name,
                        ref_columns=[c.name for c in ref_schema.expressions],
                    ))

    for c in table.columns:
        if c.name in table.pk:
            c.pk = True
        if any(c.name in fk.columns for fk in table.fks):
            c.fk = True
    return table


def _mermaid_type(t: str) -> str:
    """Mermaid does not accept comma/quote/space in an attribute type."""
    t = re.sub(r"\((?![\d, ]+\)).*\)", "", t)          # ENUM('G',...) -> ENUM
    t = t.replace(", ", ",").replace(",", "-")           # DECIMAL(4,2) -> DECIMAL(4-2)
    return t.replace(" ", "_")


def to_mermaid(tables: list[Table]) -> str:
    out = ["erDiagram"]
    for t in sorted(tables, key=lambda x: x.name):
        for fk in sorted(t.fks, key=lambda f: (f.ref_table, f.columns)):
            nullable = any(
                (c.name in fk.columns and not c.not_null) for c in t.columns
            )
            card = "|o--o{" if nullable else "||--o{"
            label = "-".join(fk.columns)
            out.append(f"    {fk.ref_table} {card} {t.name} : \"{label}\"")
    out.append("")
    for t in sorted(tables, key=lambda x: x.name):
        out.append(f"    {t.name} {{")
        for c in t.columns:
            keys = []
            if c.pk:
                keys.append("PK")
            if c.fk:
                keys.append("FK")
            suffix = f" \"{','.join(keys)}\"" if keys else ""
            key_marker = f" {','.join(keys)}" if keys else ""
            out.append(f"        {_mermaid_type(c.type)} {c.name}{key_marker}")
            _ = suffix
        out.append("    }")
    return "\n".join(out) + "\n"


def _dbml_type(t: str) -> tuple[str, str | None]:
    """ENUM/SET have no portable DBML equivalent → text + note with the original."""
    if t.upper().startswith(("ENUM(", "SET(")):
        return "varchar", t
    return f'"{t}"' if (" " in t or "," in t) else t.lower(), None


def to_dbml(tables: list[Table]) -> str:
    out = ["// GENERATED by tools/erdgen.py — do not edit by hand (principle P1)", ""]
    for t in sorted(tables, key=lambda x: x.name):
        out.append(f"Table {t.name} {{")
        for c in t.columns:
            typ, note = _dbml_type(c.type)
            attrs = []
            if c.pk and len(t.pk) == 1:
                attrs.append("pk")
            if c.not_null:
                attrs.append("not null")
            if note:
                attrs.append(f"note: '{note}'")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            out.append(f"    {c.name} {typ}{suffix}")
        if len(t.pk) > 1:
            out.append("")
            out.append("    indexes {")
            out.append(f"        ({', '.join(t.pk)}) [pk]")
            out.append("    }")
        out.append("}")
        out.append("")
    for t in sorted(tables, key=lambda x: x.name):
        for fk in sorted(t.fks, key=lambda f: (f.ref_table, f.columns)):
            for col, ref_col in zip(fk.columns, fk.ref_columns):
                out.append(f"Ref: {t.name}.{col} > {fk.ref_table}.{ref_col}")
    return "\n".join(out) + "\n"


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

    mmd = to_mermaid(tables)
    dbml = to_dbml(tables)

    if check:
        ok = True
        for path, new in ((ERD_MMD, mmd), (ERD_DBML, dbml)):
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if old != new:
                print(f"OUT OF DATE: {path.relative_to(ROOT)} — run: python tools/erdgen.py")
                ok = False
        if ok:
            print(f"OK: diagrams in sync with schema/tables/ ({len(tables)} tables).")
        return 0 if ok else 1

    ERD_MMD.write_text(mmd, encoding="utf-8", newline="\n")
    ERD_DBML.write_text(dbml, encoding="utf-8", newline="\n")
    print(f"Generated: {ERD_MMD.relative_to(ROOT)}, {ERD_DBML.relative_to(ROOT)} ({len(tables)} tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
