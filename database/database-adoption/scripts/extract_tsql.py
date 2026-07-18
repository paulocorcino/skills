#!/usr/bin/env python
"""extract_tsql.py — living introspection tool for brownfield adoption (SQL Server).

Read-only against the legacy database: the connection string pins
ApplicationIntent=ReadOnly and credentials come from .env at runtime — never
from code or from this file.

The subcommands form the adoption loop; each consumes the previous one's output:

  inventory   snapshot the catalog into .scratch/adoption/inventory.json — every
              object in the adopted schema with a definition FINGERPRINT (short
              sha256 of its normalized shape) and its dependency edges. This
              file is the "as extracted" baseline that reconcile diffs against;
              re-running it MOVES the baseline, so only do that deliberately.
  carve       render each object's DDL into the repo: tables ->
              dbkit/schema/tables/<name>.sql; views/functions/procedures/
              triggers and support objects (sequences, synonyms, table types) ->
              dbkit/schema/native/tsql/<kind>/<name>.sql.
              --objects name1,name2 restricts to a batch.
  reconcile   prove coverage and detect drift: re-inventory the live catalog in
              memory (baseline stays untouched) and diff it against baseline
              AND repo files —
                DRIFT     fingerprint changed in the DB since extraction
                NEW/DROPPED  object appeared in / vanished from the live DB
                APPLIED   live object matching a carved file but absent from
                          the baseline — a repo migration landed; re-run
                          `inventory` to fold it in
                MISSING   inventory object with no carved file in the repo
                UNDEPLOYED  repo file with no live object — a migration still
                          in flight (warning only, does not fail)
              Every failing finding is a per-object DIRECTION decision, never
              an auto-fix (dynamics in verify.py's docstring): change came from
              outside -> re-carve the fact and update the model; change is
              intended by the repo -> that is a migration to apply, not drift.
              Run it at the start of any schema session (`verify.py --live`)
              while the live DB can still change outside the repo.
  census      reality numbers — row counts, implied-FK orphan counts, enum-ish
              cardinalities. Aggregates only, never row values; feeds the gap
              sections of dbkit/model/database.md.
  discover    DB-to-Domain discovery — rank tables by structural relevance
              (referencing tables + referencing modules dominate; row count is
              tiebreaker only), classify their structural role (junction,
              lookup, log, core, elimination candidate, unreferenced), and
              cluster the FK graph (declared + implied edges) into candidate
              domain areas. Everything it emits is a CANDIDATE for the
              database-modeling grill, never a fact — naming a domain is a
              human decision. Adoption-time tool: runs once to order the grill.

Grown per-adoption: extend it when this engine or this database demands
something it doesn't cover yet. This is code MEANT to be adjusted — when you
change behavior, update these comments so the next reader still gets the why.

PORTING CONTRACT — this file is SQL Server-only ON PURPOSE (living tool, not a
universal extractor). Porting to another engine means a sibling implementation
named `extract_<source-dialect>.py` (the engine of the adopted database) that
keeps the contract below and rewrites the engine layer; extract the common
interface only when a second engine exists, never before. `verify.py --live`
discovers the tool by glob (`dbkit/tools/extract_*.py`) — no hardcoded name.

Stable contract (what every port must honor):
  - CLI: the four subcommands, `--schema`, `--objects` for carve batches;
    exit 0 = clean, exit 1 = findings (reconcile) / failure.
  - Outputs: .scratch/adoption/inventory.json with objects[] each carrying
    {schema, name, type, fingerprint, depends_on, target};
    .scratch/adoption/census.json with row_counts / implied_fk_orphans /
    enumish_cardinality (plus engine equivalents of untrusted constraints).
  - reconcile finding classes and their semantics: DRIFT, NEW, APPLIED,
    DROPPED, MISSING (failures) and UNDEPLOYED (warning) — see cmd_reconcile.
  - Fingerprint semantics: hash of the normalized CATALOG shape, not of
    rendered DDL text (renderer evolution must never fake drift).
  - Safety: connection pinned read-only where the engine allows; credentials
    from .env only; census emits aggregates, never row values.
  - Carve targets follow the repo layout, whose rules live in the READMEs:
    dbkit/schema/tables/README.md (one table per file, comments preserved),
    dbkit/schema/native/README.md (N3: one subfolder per dialect, one per
    kind), dbkit/schema/README.md (N1/N2/N3 split), and the model docs the
    adoption populates per dbkit/model/README.md (skeleton, materiality rule).

Engine layer (rewrite per engine, everything else stays):
  connect(), the read_* catalog functions, render_* / normalize_expr / ident
  (DDL rendering and quoting), and the census queries. Object-class coverage
  must sweep EVERYTHING the engine supports (the SKILL's rule) — e.g. Oracle
  adds packages; SQLite drops procedures; analytical engines (DuckDB, Spark,
  Databricks) lack enforced FKs/triggers entirely, so the adoption model
  itself needs rethinking there before any port makes sense.

VERSIONING — `__version__` below and this changelog move together: bump both on
every behavior change. A reference copy of this file ships with the
database-adoption skill (`.claude/skills/database-adoption/scripts/`); at the
start of an adoption the skill compares versions name-to-name:
  repo copy newer  -> harvest the evolution back into the skill's reference
                      (the skill learns across projects);
  skill newer      -> upgrade the repo copy;
  equal            -> nothing to do.
The changelog is what makes that merge informed — a version number says THAT
something diverged, the changelog says WHAT.

CHANGELOG:
  1.1.0  add `discover` (DB-to-Domain discovery): per-table relevance score
         (3×referencing tables + 2×referencing modules + log10(rows) as
         tiebreaker), structural-role candidates (junction / lookup / log /
         core / elimination candidate / unreferenced / shared entity),
         connected-component clustering over declared+implied FK edges into
         candidate domain areas, with adaptive hub peeling (universal
         entities glue every domain into one blob; they are removed
         iteratively until no component exceeds ~20% of tables and reported
         as cross-domain shared entities) -> .scratch/adoption/discovery.json.
         Factored
         read_row_counts / find_implied_fks out of census (shared reads,
         census behavior unchanged).
  1.0.0  first versioned reference: inventory / carve / reconcile / census;
         catalog-shape fingerprints (renderer evolution never fakes drift);
         reconcile finding classes DRIFT / NEW / APPLIED / DROPPED / MISSING
         (fail) + UNDEPLOYED (warn); census emits aggregates only; read-only
         connection pinned; PORTING CONTRACT for sibling engines.
"""
from __future__ import annotations

__version__ = "1.1.0"

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRATCH = REPO / ".scratch" / "adoption"
INVENTORY = SCRATCH / "inventory.json"
TABLES_DIR = ROOT / "schema" / "tables"
NATIVE_DIR = ROOT / "schema" / "native" / "tsql"

MODULE_TYPES = {"V", "P", "FN", "IF", "TF", "TR"}
OBJECT_TYPES = MODULE_TYPES | {"U"}
# native/<dialect>/<kind>/ layout, per schema/native/README.md
MODULE_KIND_DIR = {"V": "views", "P": "procedures", "TR": "triggers",
                   "FN": "functions", "IF": "functions", "TF": "functions",
                   "SO": "sequences", "SN": "synonyms", "TT": "types"}


def connect():
    try:
        import pyodbc
        from dotenv import load_dotenv
    except ImportError as exc:
        sys.exit(f"missing dependency: {exc.name} (pip install pyodbc python-dotenv)")
    import os

    load_dotenv(REPO / ".env")
    conn_str = (
        f"DRIVER={{{os.environ['DB_ODBC_DRIVER']}}};"
        f"SERVER={os.environ['DB_HOST']},{os.environ['DB_PORT']};"
        f"DATABASE={os.environ['DB_NAME']};"
        f"UID={os.environ['DB_USER']};PWD={os.environ['DB_PASSWORD']};"
        f"Encrypt={os.environ.get('DB_ENCRYPT', 'yes')};"
        f"TrustServerCertificate={os.environ.get('DB_TRUST_SERVER_CERTIFICATE', 'no')};"
        "ApplicationIntent=ReadOnly;"
    )
    conn = pyodbc.connect(conn_str, timeout=15)
    conn.timeout = 60
    return conn


def fetch_rows(cur, sql: str, *params) -> list[tuple]:
    cur.execute(sql, *params)
    return cur.fetchall()


# ---------------------------------------------------------------- catalog reads

def read_columns(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT t.name, c.column_id, c.name, ty.name, c.max_length, c.precision,
               c.scale, c.is_nullable, c.is_identity, CONVERT(BIGINT, ic.seed_value),
               CONVERT(BIGINT, ic.increment_value), cc.definition, cc.is_persisted,
               df.definition, df.name, c.collation_name,
               CONVERT(NVARCHAR(4000), ep.value)
        FROM sys.tables AS t
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.columns AS c ON c.object_id = t.object_id
        JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
        LEFT JOIN sys.identity_columns AS ic
            ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        LEFT JOIN sys.computed_columns AS cc
            ON cc.object_id = c.object_id AND cc.column_id = c.column_id
        LEFT JOIN sys.default_constraints AS df
            ON df.parent_object_id = c.object_id AND df.parent_column_id = c.column_id
        LEFT JOIN sys.extended_properties AS ep
            ON ep.major_id = c.object_id AND ep.minor_id = c.column_id
            AND ep.class = 1 AND ep.name = 'MS_Description'
        WHERE s.name = ?
        ORDER BY t.name, c.column_id
    """, schema)
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r[0], []).append({
            "name": r[2], "type": r[3], "max_length": r[4], "precision": r[5],
            "scale": r[6], "nullable": bool(r[7]), "identity": bool(r[8]),
            "seed": r[9], "increment": r[10], "computed": r[11],
            "persisted": bool(r[12]) if r[12] is not None else False,
            "default": r[13], "default_name": r[14], "collation": r[15],
            "description": r[16],
        })
    return out


def read_key_constraints(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT t.name, kc.name, kc.type, i.type_desc, c.name, ic.key_ordinal,
               ic.is_descending_key
        FROM sys.key_constraints AS kc
        JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.indexes AS i
            ON i.object_id = kc.parent_object_id AND i.index_id = kc.unique_index_id
        JOIN sys.index_columns AS ic
            ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns AS c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE s.name = ? AND ic.key_ordinal > 0
        ORDER BY t.name, kc.name, ic.key_ordinal
    """, schema)
    out: dict[str, list[dict]] = {}
    for tbl, cname, ctype, idx_desc, col, _, desc in rows:
        cons = out.setdefault(tbl, [])
        if not cons or cons[-1]["name"] != cname:
            cons.append({"name": cname, "type": ctype.strip(),
                         "clustered": idx_desc == "CLUSTERED", "columns": []})
        cons[-1]["columns"].append(col + (" DESC" if desc else ""))
    return out


def read_foreign_keys(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT t.name, fk.name, rs.name, rt.name, pc.name, rc.name,
               fk.delete_referential_action_desc, fk.update_referential_action_desc,
               fkc.constraint_column_id
        FROM sys.foreign_keys AS fk
        JOIN sys.tables AS t ON t.object_id = fk.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.tables AS rt ON rt.object_id = fk.referenced_object_id
        JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
        JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.columns AS pc
            ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        JOIN sys.columns AS rc
            ON rc.object_id = fkc.referenced_object_id
            AND rc.column_id = fkc.referenced_column_id
        WHERE s.name = ?
        ORDER BY t.name, fk.name, fkc.constraint_column_id
    """, schema)
    out: dict[str, list[dict]] = {}
    for tbl, fname, rschema, rtable, pcol, rcol, on_del, on_upd, _ in rows:
        fks = out.setdefault(tbl, [])
        if not fks or fks[-1]["name"] != fname:
            fks.append({"name": fname, "ref_schema": rschema, "ref_table": rtable,
                        "columns": [], "ref_columns": [],
                        "on_delete": on_del, "on_update": on_upd})
        fks[-1]["columns"].append(pcol)
        fks[-1]["ref_columns"].append(rcol)
    return out


def read_check_constraints(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT t.name, ck.name, ck.definition
        FROM sys.check_constraints AS ck
        JOIN sys.tables AS t ON t.object_id = ck.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ?
        ORDER BY t.name, ck.name
    """, schema)
    out: dict[str, list[dict]] = {}
    for tbl, name, definition in rows:
        out.setdefault(tbl, []).append({"name": name, "definition": definition})
    return out


def read_indexes(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT t.name, i.name, i.type_desc, i.is_unique, i.filter_definition,
               c.name, ic.key_ordinal, ic.is_descending_key, ic.is_included_column
        FROM sys.indexes AS i
        JOIN sys.tables AS t ON t.object_id = i.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.index_columns AS ic
            ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns AS c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE s.name = ? AND i.type > 0
            AND i.is_primary_key = 0 AND i.is_unique_constraint = 0
        ORDER BY t.name, i.name, ic.is_included_column, ic.key_ordinal
    """, schema)
    out: dict[str, list[dict]] = {}
    for tbl, name, tdesc, uniq, filt, col, _, desc, incl in rows:
        idxs = out.setdefault(tbl, [])
        if not idxs or idxs[-1]["name"] != name:
            idxs.append({"name": name, "type": tdesc, "unique": bool(uniq),
                         "filter": filt, "columns": [], "include": []})
        if incl:
            idxs[-1]["include"].append(col)  # INCLUDE columns carry no direction
        else:
            idxs[-1]["columns"].append(col + (" DESC" if desc else ""))
    return out


def read_table_descriptions(cur, schema: str) -> dict[str, str]:
    rows = fetch_rows(cur, """
        SELECT t.name, CONVERT(NVARCHAR(4000), ep.value)
        FROM sys.tables AS t
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.extended_properties AS ep
            ON ep.major_id = t.object_id AND ep.minor_id = 0
            AND ep.class = 1 AND ep.name = 'MS_Description'
        WHERE s.name = ?
    """, schema)
    return {r[0]: r[1] for r in rows}


def read_modules(cur, schema: str) -> dict[str, dict]:
    rows = fetch_rows(cur, """
        SELECT o.name, o.type, m.definition
        FROM sys.sql_modules AS m
        JOIN sys.objects AS o ON o.object_id = m.object_id
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ?
        ORDER BY o.name
    """, schema)
    return {r[0]: {"type": r[1].strip(), "definition": r[2]} for r in rows}


def read_trigger_parents(cur, schema: str) -> dict[str, str]:
    rows = fetch_rows(cur, """
        SELECT tr.name, t.name FROM sys.triggers AS tr
        JOIN sys.tables AS t ON t.object_id = tr.parent_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ?
    """, schema)
    return {r[0]: r[1] for r in rows}


def read_dependencies(cur, schema: str) -> dict[str, list[str]]:
    rows = fetch_rows(cur, """
        SELECT o.name, d.referenced_entity_name
        FROM sys.sql_expression_dependencies AS d
        JOIN sys.objects AS o ON o.object_id = d.referencing_id
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ? AND d.referenced_id IS NOT NULL
            AND d.referenced_id <> d.referencing_id
        ORDER BY o.name, d.referenced_entity_name
    """, schema)
    out: dict[str, list[str]] = {}
    for name, ref in rows:
        deps = out.setdefault(name, [])
        if ref not in deps:
            deps.append(ref)
    return out


def read_sequences(cur, schema: str) -> dict[str, dict]:
    rows = fetch_rows(cur, """
        SELECT sq.name, TYPE_NAME(sq.user_type_id), CONVERT(BIGINT, sq.start_value),
               CONVERT(BIGINT, sq.increment), CONVERT(BIGINT, sq.minimum_value),
               CONVERT(BIGINT, sq.maximum_value), sq.is_cycling
        FROM sys.sequences AS sq
        JOIN sys.schemas AS s ON s.schema_id = sq.schema_id
        WHERE s.name = ? ORDER BY sq.name
    """, schema)
    return {r[0]: {"type": r[1], "start": r[2], "increment": r[3], "min": r[4],
                   "max": r[5], "cycle": bool(r[6])} for r in rows}


def read_synonyms(cur, schema: str) -> dict[str, str]:
    rows = fetch_rows(cur, """
        SELECT sn.name, sn.base_object_name FROM sys.synonyms AS sn
        JOIN sys.schemas AS s ON s.schema_id = sn.schema_id
        WHERE s.name = ? ORDER BY sn.name
    """, schema)
    return {r[0]: r[1] for r in rows}


def read_table_types(cur, schema: str) -> dict[str, list[dict]]:
    rows = fetch_rows(cur, """
        SELECT tt.name, c.name, ty.name, c.max_length, c.precision, c.scale,
               c.is_nullable
        FROM sys.table_types AS tt
        JOIN sys.schemas AS s ON s.schema_id = tt.schema_id
        JOIN sys.columns AS c ON c.object_id = tt.type_table_object_id
        JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
        WHERE s.name = ?
        ORDER BY tt.name, c.column_id
    """, schema)
    out: dict[str, list[dict]] = {}
    for tname, cname, ctype, maxlen, prec, scale, nullable in rows:
        out.setdefault(tname, []).append({
            "name": cname, "type": ctype, "max_length": maxlen,
            "precision": prec, "scale": scale, "nullable": bool(nullable),
            "identity": False, "computed": None, "default": None,
            "collation": None,
        })
    return out


def render_sequence(name: str, sq: dict) -> str:
    lines = [f"CREATE SEQUENCE dbo.{ident(name)}",
             f"    AS {sq['type'].upper()}",
             f"    START WITH {sq['start']}",
             f"    INCREMENT BY {sq['increment']}",
             f"    MINVALUE {sq['min']}",
             f"    MAXVALUE {sq['max']}",
             f"    {'CYCLE' if sq['cycle'] else 'NO CYCLE'};"]
    return "\n".join(lines) + "\n"


def render_synonym(name: str, base: str) -> str:
    return f"CREATE SYNONYM dbo.{ident(name)} FOR {base};\n"


def render_table_type(name: str, cols: list[dict]) -> str:
    body = ",\n".join(f"    {ident(c['name'])} {render_type(c)}"
                      f"{' NULL' if c['nullable'] else ' NOT NULL'}" for c in cols)
    return f"CREATE TYPE dbo.{ident(name)} AS TABLE (\n{body}\n);\n"


def read_object_list(cur, schema: str) -> list[dict]:
    rows = fetch_rows(cur, """
        SELECT o.name, o.type
        FROM sys.objects AS o
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ? AND o.type IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR')
        ORDER BY o.name
    """, schema)
    return [{"name": r[0], "type": r[1].strip()} for r in rows]


# ---------------------------------------------------------------- DDL rendering

import re

PLAIN_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def ident(name: str) -> str:
    """Bracket-quote only when the identifier demands it (RF06)."""
    return name if PLAIN_IDENT.match(name) else f"[{name}]"


TYPE_TOKEN = re.compile(
    r"\[(varchar|nvarchar|char|nchar|varbinary|binary|int|bigint|smallint|tinyint|"
    r"bit|decimal|numeric|float|real|money|smallmoney|datetime2?|smalldatetime|"
    r"date|time|datetimeoffset|uniqueidentifier|text|ntext|image|xml)\]",
    re.IGNORECASE)


def normalize_expr(expr: str) -> str:
    """Lint-normalize a catalog expression (default/check/computed/filter) without
    touching string literals: space after commas and around bare '=', bracketed
    lowercase type names uppercased. Splitting on quotes keeps literals verbatim."""
    parts = re.split(r"('(?:[^']|'')*')", expr)
    for i in range(0, len(parts), 2):  # even slots are outside string literals
        s = parts[i]
        s = re.sub(r",(?=\S)", ", ", s)
        s = re.sub(r"(?<=[^\s<>!=])=(?=[^\s=])", " = ", s)
        s = TYPE_TOKEN.sub(lambda m: m.group(1).upper(), s)
        parts[i] = s
    return "".join(parts)


def ident_dir(col: str) -> str:
    """Key/index column that may carry a trailing ' DESC' direction."""
    if col.endswith(" DESC"):
        return f"{ident(col[:-5])} DESC"
    return ident(col)


SIZED = {"varchar", "char", "varbinary", "binary", "nvarchar", "nchar"}
PRECISION = {"decimal", "numeric"}
SCALED = {"datetime2", "datetimeoffset", "time"}


def render_type(col: dict) -> str:
    t = col["type"]
    if t in SIZED:
        n = col["max_length"]
        if n == -1:
            return f"{t.upper()}(MAX)"
        if t.startswith("n"):
            n //= 2
        return f"{t.upper()}({n})"
    if t in PRECISION:
        return f"{t.upper()}({col['precision']}, {col['scale']})"
    if t in SCALED:
        return f"{t.upper()}({col['scale']})"
    return t.upper()


def render_column(col: dict) -> str:
    if col["computed"]:
        line = f"{ident(col['name'])} AS {normalize_expr(col['computed'])}"
        if col["persisted"]:
            line += " PERSISTED"
        return line
    line = f"{ident(col['name'])} {render_type(col)}"
    if col["collation"]:
        line += f" COLLATE {col['collation']}"
    if col["identity"]:
        line += f" IDENTITY ({col['seed']}, {col['increment']})"
    line += " NULL" if col["nullable"] else " NOT NULL"
    if col["default"]:
        line += (f" CONSTRAINT {ident(col['default_name'])} "
                 f"DEFAULT {normalize_expr(col['default'])}")
    return line


def render_table(name: str, cols: list[dict], keys: list[dict], fks: list[dict],
                 checks: list[dict], idxs: list[dict], description: str | None) -> str:
    lines: list[str] = []
    if description:
        for text_line in description.splitlines():
            lines.append(f"-- {text_line}".rstrip())
    lines.append(f"CREATE TABLE dbo.{ident(name)} (")
    body: list[str] = []
    for col in cols:
        if col["description"]:
            for text_line in col["description"].splitlines():
                body.append(f"    -- {text_line}".rstrip())
        body.append(f"    {render_column(col)},")
    for kc in keys:
        kind = "PRIMARY KEY" if kc["type"] == "PK" else "UNIQUE"
        clustered = "CLUSTERED" if kc["clustered"] else "NONCLUSTERED"
        collist = ", ".join(ident_dir(c) for c in kc["columns"])
        body.append(f"    CONSTRAINT {ident(kc['name'])} {kind} {clustered} ({collist}),")
    for ck in checks:
        body.append(f"    CONSTRAINT {ident(ck['name'])} "
                    f"CHECK {normalize_expr(ck['definition'])},")
    for fk in fks:
        cols_s = ", ".join(ident(c) for c in fk["columns"])
        refs_s = ", ".join(ident(c) for c in fk["ref_columns"])
        line = (f"    CONSTRAINT {ident(fk['name'])} FOREIGN KEY ({cols_s}) "
                f"REFERENCES {fk['ref_schema']}.{ident(fk['ref_table'])} ({refs_s})")
        if fk["on_delete"] != "NO_ACTION":
            line += f" ON DELETE {fk['on_delete'].replace('_', ' ')}"
        if fk["on_update"] != "NO_ACTION":
            line += f" ON UPDATE {fk['on_update'].replace('_', ' ')}"
        body.append(line + ",")
    if body and body[-1].endswith(","):
        body[-1] = body[-1][:-1]
    lines.extend(body)
    lines.append(");")
    for idx in idxs:
        uniq = "UNIQUE " if idx["unique"] else ""
        kind = "CLUSTERED " if idx["type"] == "CLUSTERED" else ""
        collist = ", ".join(ident_dir(c) for c in idx["columns"])
        include = ""
        if idx["include"]:
            include = " INCLUDE (" + ", ".join(ident_dir(c) for c in idx["include"]) + ")"
        if idx["filter"]:
            # filtered indexes go multi-line: lint expects ON/WHERE each indented
            stmt = (f"\nCREATE {uniq}{kind}INDEX {ident(idx['name'])}\n"
                    f"    ON dbo.{ident(name)} ({collist}){include}\n"
                    f"    WHERE {normalize_expr(idx['filter'])}")
        else:
            stmt = (f"\nCREATE {uniq}{kind}INDEX {ident(idx['name'])} "
                    f"ON dbo.{ident(name)} ({collist}){include}")
        lines.append(stmt + ";")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- fingerprints
#
# A fingerprint hashes an object's NORMALIZED shape, not its rendered DDL text:
# for tables, the sorted JSON of columns/keys/FKs/checks/indexes/description;
# for modules, the sys.sql_modules definition verbatim. Consequence: any
# structural change in the DB (including a column comment) changes the
# fingerprint and shows up as DRIFT in reconcile; re-rendering style in this
# tool does NOT, which is exactly what lets the renderer evolve without faking
# drift. 16 hex chars is plenty for a few hundred objects.

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def table_fingerprint(name, cols, keys, fks, checks, idxs, description) -> str:
    payload = json.dumps(
        {"c": cols, "k": keys, "f": fks, "ck": checks, "i": idxs, "d": description},
        sort_keys=True, default=str)
    return sha(payload)


# ---------------------------------------------------------------- subcommands

def build_inventory(schema: str) -> dict:
    conn = connect()
    cur = conn.cursor()
    objects = read_object_list(cur, schema)
    cols = read_columns(cur, schema)
    keys = read_key_constraints(cur, schema)
    fks = read_foreign_keys(cur, schema)
    checks = read_check_constraints(cur, schema)
    idxs = read_indexes(cur, schema)
    descriptions = read_table_descriptions(cur, schema)
    modules = read_modules(cur, schema)
    deps = read_dependencies(cur, schema)
    trigger_parents = read_trigger_parents(cur, schema)
    sequences = read_sequences(cur, schema)
    synonyms = read_synonyms(cur, schema)
    table_types = read_table_types(cur, schema)
    conn.close()

    # object classes outside sys.objects' module/table types
    for sname, sq in sequences.items():
        objects.append({"name": sname, "type": "SO", "_payload": sq})
    for sname, base in synonyms.items():
        objects.append({"name": sname, "type": "SN", "_payload": base})
    for tname, tcols in table_types.items():
        objects.append({"name": tname, "type": "TT", "_payload": tcols})

    inv_objects = []
    for obj in objects:
        name, otype = obj["name"], obj["type"]
        if otype == "U":
            fp = table_fingerprint(name, cols.get(name, []), keys.get(name, []),
                                   fks.get(name, []), checks.get(name, []),
                                   idxs.get(name, []), descriptions.get(name))
            depends = sorted({fk["ref_table"] for fk in fks.get(name, [])
                              if fk["ref_table"] != name})
            target = f"dbkit/schema/tables/{name}.sql"
        elif otype in ("SO", "SN", "TT"):
            fp = sha(json.dumps(obj["_payload"], sort_keys=True, default=str))
            depends = []
            target = f"dbkit/schema/native/tsql/{MODULE_KIND_DIR[otype]}/{name}.sql"
        else:
            fp = sha(modules[name]["definition"])
            depends = deps.get(name, [])
            if otype == "TR":
                parent = trigger_parents.get(name)
                if parent and parent not in depends:
                    depends = [parent] + depends
            kind = MODULE_KIND_DIR[otype]
            target = f"dbkit/schema/native/tsql/{kind}/{name}.sql"
        inv_objects.append({"schema": schema, "name": name, "type": otype,
                            "fingerprint": fp, "depends_on": depends,
                            "target": target})
    # "_catalog" carries the full column/constraint/module payloads so carve can
    # render without reconnecting. inventory/reconcile pop it before persisting:
    # the committed baseline needs only fingerprints, and definitions may hold
    # things that don't belong in a JSON dump kept around (routine source bulk).
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "objects": inv_objects,
        "_catalog": {"cols": cols, "keys": keys, "fks": fks, "checks": checks,
                     "idxs": idxs, "descriptions": descriptions,
                     "modules": modules, "sequences": sequences,
                     "synonyms": synonyms, "table_types": table_types},
    }


def cmd_inventory(args) -> int:
    inv = build_inventory(args.schema)
    inv.pop("_catalog")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    INVENTORY.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    counts: dict[str, int] = {}
    for obj in inv["objects"]:
        counts[obj["type"]] = counts.get(obj["type"], 0) + 1
    print(f"inventory: {len(inv['objects'])} objects in [{args.schema}] "
          f"-> {INVENTORY.relative_to(REPO)}")
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t}: {n}")
    return 0


def render_object(obj: dict, cat: dict) -> str:
    """One object's DDL as carve would write it — shared by carve (to write the
    file) and reconcile (to tell an APPLIED migration from a truly NEW object
    by comparing this rendering with the carved file's content)."""
    name, otype = obj["name"], obj["type"]
    if otype == "U":
        return render_table(name, cat["cols"].get(name, []),
                            cat["keys"].get(name, []), cat["fks"].get(name, []),
                            cat["checks"].get(name, []), cat["idxs"].get(name, []),
                            cat["descriptions"].get(name))
    if otype == "SO":
        return render_sequence(name, cat["sequences"][name])
    if otype == "SN":
        return render_synonym(name, cat["synonyms"][name])
    if otype == "TT":
        return render_table_type(name, cat["table_types"][name])
    definition = cat["modules"][name]["definition"]
    if not definition.endswith("\n"):
        definition += "\n"
    return definition


def cmd_carve(args) -> int:
    inv = build_inventory(args.schema)
    cat = inv.pop("_catalog")
    only = set(args.objects.split(",")) if args.objects else None
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for obj in inv["objects"]:
        if only and obj["name"] not in only:
            continue
        path = REPO / obj["target"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_object(obj, cat), encoding="utf-8", newline="\n")
        written += 1
    print(f"carved {written} object(s)")
    return 0


def cmd_reconcile(args) -> int:
    # Three-way diff: committed baseline (inventory.json) × live catalog (read
    # now, in memory) × carved files on disk. Nothing is written — reconcile
    # only reports; fixing a finding is a human direction decision (see module
    # docstring). Exit 1 on any problem so `verify.py --live` fails loudly.
    #
    # Finding classes and what to do with each:
    #   DRIFT       fingerprint changed in the DB -> decide direction (re-carve
    #               the fact, or it regressed an intended repo change)
    #   NEW         live object, no baseline, no matching file -> born outside
    #               the repo; adopt it (carve + inventory + model docs)
    #   APPLIED     live object, no baseline, but the carved file matches the
    #               live rendering -> a repo-designed migration landed; run
    #               `extract_tsql.py inventory` to fold it into the baseline
    #   DROPPED     baseline object gone from the DB -> dropped outside the repo
    #               (or by an applied contract migration); align repo + model
    #   MISSING     baseline object with no carved file -> extraction hole
    #   UNDEPLOYED  repo file with no live object and no baseline -> designed
    #               here, migration not applied yet. Expected intermediate
    #               state -> reported as a warning, does NOT fail the run
    #               (verifying deployment is dbverify's future job).
    if not INVENTORY.exists():
        sys.exit(f"no {INVENTORY.relative_to(REPO)} — run `extract_tsql.py inventory` first")
    recorded = {o["name"]: o for o in
                json.loads(INVENTORY.read_text(encoding="utf-8"))["objects"]}
    live = build_inventory(args.schema)
    cat = live.pop("_catalog")
    live_objs = {o["name"]: o for o in live["objects"]}

    problems: list[str] = []
    warnings: list[str] = []
    for name, obj in live_objs.items():
        rec = recorded.get(name)
        if rec is None:
            target = REPO / obj["target"]
            if (target.exists()
                    and target.read_text(encoding="utf-8") == render_object(obj, cat)):
                problems.append(f"APPLIED but baseline stale: {name} — live object "
                                f"matches {obj['target']}; run `extract_tsql.py inventory` "
                                "to fold it into the baseline")
            else:
                problems.append(f"NEW in source, absent from inventory: {name}")
            continue
        if rec["fingerprint"] != obj["fingerprint"]:
            problems.append(f"DRIFT since extraction: {name}")
        target = REPO / rec["target"]
        if not target.exists():
            problems.append(f"MISSING carved file: {rec['target']} ({name})")
    for name in recorded:
        if name not in live_objs:
            problems.append(f"DROPPED from source since inventory: {name}")

    # repo -> DB direction: a carved/designed file whose object exists nowhere
    # in the live catalog nor in the baseline is a migration still in flight
    for path in sorted(list(TABLES_DIR.glob("*.sql")) + list(NATIVE_DIR.rglob("*.sql"))):
        name = path.stem
        if name not in live_objs and name not in recorded:
            warnings.append(f"UNDEPLOYED: {path.relative_to(REPO)} — no live object "
                            "(pending migration?)")

    for w in warnings:
        print(f"  warn  {w}")
    if problems:
        print(f"reconcile: {len(problems)} problem(s)"
              + (f", {len(warnings)} warning(s)" if warnings else ""))
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"reconcile: OK — {len(live_objs)} objects, every fingerprint stable, "
          "every carved file present"
          + (f"; {len(warnings)} undeployed file(s) pending" if warnings else ""))
    return 0


ENUMISH = re.compile(
    r"(status|tipo|type|flag|situacao|estado|state|nivel|level|categoria)",
    re.IGNORECASE)


def read_row_counts(cur, schema: str) -> dict[str, int]:
    rows = fetch_rows(cur, """
        SELECT t.name, SUM(ps.row_count)
        FROM sys.dm_db_partition_stats AS ps
        JOIN sys.tables AS t ON t.object_id = ps.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ? AND ps.index_id IN (0, 1)
        GROUP BY t.name ORDER BY t.name
    """, schema)
    return {r[0]: int(r[1]) for r in rows}


def read_column_pairs(cur, schema: str) -> list[tuple[str, str]]:
    rows = fetch_rows(cur, """
        SELECT t.name, c.name FROM sys.columns AS c
        JOIN sys.tables AS t ON t.object_id = c.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ?
    """, schema)
    return [(t, c) for t, c in rows]


def find_implied_fks(cur, schema: str,
                     column_pairs: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """(table, column, referenced_table) triples where a column named exactly
    like another table's single-column, non-generic PK column carries no
    declared FK — legacy schemas often keep relationships only by naming.
    census counts their orphans; discover uses them as graph edges."""
    pk_cols = fetch_rows(cur, """
        SELECT t.name, c.name FROM sys.key_constraints AS kc
        JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.index_columns AS ic
            ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
        JOIN sys.columns AS c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE s.name = ? AND kc.type = 'PK' AND ic.key_ordinal = 1
            AND NOT EXISTS (
                SELECT 1 FROM sys.index_columns AS ic2
                WHERE ic2.object_id = kc.parent_object_id
                    AND ic2.index_id = kc.unique_index_id AND ic2.key_ordinal = 2)
    """, schema)
    pk_by_col = {}
    for tbl, col in pk_cols:
        if col.upper() in ("ID", "CODIGO", "CODE"):
            continue
        pk_by_col.setdefault(col, []).append(tbl)
    pk_by_col = {c: ts[0] for c, ts in pk_by_col.items() if len(ts) == 1}

    declared = fetch_rows(cur, """
        SELECT t.name, pc.name FROM sys.foreign_key_columns AS fkc
        JOIN sys.tables AS t ON t.object_id = fkc.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.columns AS pc
            ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        WHERE s.name = ?
    """, schema)
    declared_set = {(t, c) for t, c in declared}

    implied = []
    for tbl, col in column_pairs:
        ref = pk_by_col.get(col)
        if ref and ref != tbl and (tbl, col) not in declared_set:
            implied.append((tbl, col, ref))
    return implied


def cmd_census(args) -> int:
    """Reality census — read-only aggregates only. Counts and cardinalities expose
    scale, never values (raw values require classification first — see the skill)."""
    conn = connect()
    cur = conn.cursor()
    schema = args.schema
    out: dict = {"generated_at": datetime.now(timezone.utc).isoformat()}

    out["row_counts"] = read_row_counts(cur, schema)
    print(f"row counts: {len(out['row_counts'])} tables, "
          f"{sum(out['row_counts'].values()):,} rows total")

    untrusted = fetch_rows(cur, """
        SELECT t.name, fk.name FROM sys.foreign_keys AS fk
        JOIN sys.tables AS t ON t.object_id = fk.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ? AND fk.is_not_trusted = 1
    """, schema)
    out["untrusted_fks"] = [f"{t}.{n}" for t, n in untrusted]
    print(f"untrusted (NOCHECK) FKs: {len(untrusted)}")

    candidates = read_column_pairs(cur, schema)
    implied = find_implied_fks(cur, schema, candidates)
    print(f"implied FK candidates (no constraint behind them): {len(implied)}")

    orphans: dict[str, int] = {}
    for tbl, col, ref in implied:
        try:
            cur.execute(
                f"SELECT COUNT(*) FROM {schema}.[{tbl}] AS c "
                f"LEFT JOIN {schema}.[{ref}] AS p ON p.[{col}] = c.[{col}] "
                f"WHERE c.[{col}] IS NOT NULL AND p.[{col}] IS NULL")
            n = cur.fetchone()[0]
        except Exception as exc:  # type mismatch etc. — a finding, not a crash
            orphans[f"{tbl}.{col} -> {ref}"] = f"uncountable: {exc}"
            continue
        orphans[f"{tbl}.{col} -> {ref}"] = int(n)
    out["implied_fk_orphans"] = orphans
    violated = {k: v for k, v in orphans.items() if isinstance(v, int) and v > 0}
    print(f"implied FKs with orphans: {len(violated)}")

    enumish = [(t, c) for t, c in candidates if ENUMISH.search(c)]
    cards: dict[str, int] = {}
    for tbl, col in enumish:
        if out["row_counts"].get(tbl, 0) == 0:
            continue
        try:
            cur.execute(f"SELECT COUNT(DISTINCT [{col}]) FROM {schema}.[{tbl}]")
            cards[f"{tbl}.{col}"] = int(cur.fetchone()[0])
        except Exception:
            continue
    out["enumish_cardinality"] = cards
    print(f"enum-ish columns (cardinality only, no values): {len(cards)}")

    conn.close()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "census.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"census -> {(SCRATCH / 'census.json').relative_to(REPO)}")
    return 0


LOGISH = re.compile(r"(^|_)(log|logs|hist|historico|history|audit|auditoria|"
                    r"bkp|backup|bak|old|tmp|temp)($|_|s?$)|_(log|hist|bak|old|bkp)$",
                    re.IGNORECASE)


def cmd_discover(args) -> int:
    """DB-to-Domain discovery. Relevance is dominated by reference structure
    (who points at the table: other tables via FK, modules via dependencies);
    row count enters only as a log-scale tiebreaker — the biggest tables in a
    legacy DB are usually logs, the most central ones can be tiny lookups.
    Every classification and cluster here is a CANDIDATE for the modeling
    grill; the human names the domains. Runs once, at adoption time."""
    conn = connect()
    cur = conn.cursor()
    schema = args.schema

    objects = read_object_list(cur, schema)
    tables = {o["name"] for o in objects if o["type"] == "U"}
    module_names = {o["name"] for o in objects if o["type"] in MODULE_TYPES}
    fks = read_foreign_keys(cur, schema)
    deps = read_dependencies(cur, schema)
    keys = read_key_constraints(cur, schema)
    rows = read_row_counts(cur, schema)
    column_pairs = read_column_pairs(cur, schema)
    implied = find_implied_fks(cur, schema, column_pairs)
    conn.close()

    ncols = {t: 0 for t in tables}
    for tbl, _ in column_pairs:
        if tbl in ncols:
            ncols[tbl] += 1

    # edges: declared FKs + implied (name-matched) FKs, both directions tracked.
    # Implied edges matter because legacy schemas keep half the graph in naming
    # conventions only — without them clustering fractures into fragments.
    ref_in: dict[str, set[str]] = {t: set() for t in tables}
    ref_out: dict[str, set[str]] = {t: set() for t in tables}
    edges: set[tuple[str, str]] = set()
    fk_cols: dict[str, set[str]] = {t: set() for t in tables}
    for tbl, fklist in fks.items():
        for fk in fklist:
            ref = fk["ref_table"]
            fk_cols[tbl].update(fk["columns"])
            if ref in tables and ref != tbl:
                ref_in[ref].add(tbl)
                ref_out[tbl].add(ref)
                edges.add(tuple(sorted((tbl, ref))))
    implied_in: dict[str, set[str]] = {t: set() for t in tables}
    for tbl, col, ref in implied:
        if tbl in tables and ref in tables:
            implied_in[ref].add(tbl)
            edges.add(tuple(sorted((tbl, ref))))

    # modules touching each table, per sys.sql_expression_dependencies (reads
    # AND writes look the same there — this measures participation, not traffic)
    routine_refs: dict[str, set[str]] = {t: set() for t in tables}
    for mod in module_names:
        for ref in deps.get(mod, []):
            if ref in tables:
                routine_refs[ref].add(mod)

    def score(t: str) -> float:
        structural = (3 * (len(ref_in[t]) + len(implied_in[t]))
                      + 2 * len(routine_refs[t]))
        return structural + math.log10(rows.get(t, 0) + 1)

    def role(t: str) -> str:
        n_in = len(ref_in[t]) + len(implied_in[t])
        n_rows = rows.get(t, 0)
        touched = len(routine_refs[t])
        if n_rows == 0 and n_in == 0 and touched == 0:
            return "elimination candidate"
        pk = next((k["columns"] for k in keys.get(t, []) if k["type"] == "PK"), [])
        pk_plain = {c[:-5] if c.endswith(" DESC") else c for c in pk}
        if (len(ref_out[t]) >= 2 and pk_plain and pk_plain <= fk_cols[t]
                and ncols[t] <= len(fk_cols[t]) + 2):
            return "junction candidate"
        if n_in >= 3 and ncols[t] <= 6 and 0 < n_rows <= 1000:
            return "lookup candidate"
        if n_in == 0 and LOGISH.search(t):
            return "log/history candidate"
        if n_in == 0 and touched == 0 and n_rows > 0:
            return "unreferenced (app-code only? gap)"
        if n_in >= 2 and touched >= 1:
            return "core candidate"
        return "regular"

    # candidate domain areas: connected components over the combined FK graph,
    # AFTER peeling hubs. Universal entities (user, form, tag …) are referenced
    # from every subsystem and glue all domains into one giant component;
    # domains are what remains when the shared entities are set aside. Peel
    # adaptively — remove the highest-in-degree table inside the largest
    # component until no component exceeds ~20% of the tables — so the
    # threshold tunes itself per database. Hubs are a finding of their own:
    # cross-domain shared entities the grill must place deliberately.
    def component_map(excluded: set[str]) -> dict[str, list[str]]:
        parent = {t: t for t in tables if t not in excluded}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in edges:
            if a in excluded or b in excluded:
                continue
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        comps: dict[str, list[str]] = {}
        for t in parent:
            comps.setdefault(find(t), []).append(t)
        return comps

    blob_limit = max(10, len(tables) // 5)
    hubs: set[str] = set()
    while len(hubs) < 15:
        components = component_map(hubs)
        biggest = max(components.values(), key=len, default=[])
        if len(biggest) <= blob_limit:
            break
        hubs.add(max(biggest,
                     key=lambda t: (len(ref_in[t]) + len(implied_in[t]), t)))
    components = component_map(hubs)
    clusters = sorted((sorted(m, key=score, reverse=True)
                       for m in components.values() if len(m) > 1),
                      key=len, reverse=True)
    isolated = sorted(t for m in components.values() if len(m) == 1 for t in m)

    ranked = sorted(tables, key=score, reverse=True)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "tables": {t: {
            "score": round(score(t), 2),
            "rows": rows.get(t, 0),
            "ref_in_declared": len(ref_in[t]),
            "ref_in_implied": len(implied_in[t]),
            "ref_out": len(ref_out[t]),
            "module_refs": len(routine_refs[t]),
            "columns": ncols[t],
            "role": "shared entity (hub)" if t in hubs else role(t),
        } for t in ranked},
        "hubs": sorted(hubs, key=score, reverse=True),
        "clusters": [{"id": i + 1, "size": len(m), "anchors": m[:3], "members": m}
                     for i, m in enumerate(clusters)],
        "isolated": isolated,
    }
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / "discovery.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    role_counts: dict[str, int] = {}
    for t in ranked:
        r = out["tables"][t]["role"]
        role_counts[r] = role_counts.get(r, 0) + 1
    print(f"discover: {len(tables)} tables in [{schema}] -> {path.relative_to(REPO)}")
    print("\nstructural roles (candidates, not facts):")
    for r, n in sorted(role_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {r}")
    print(f"\ntop {min(20, len(ranked))} by relevance "
          "(score = 3*tables_in + 2*modules + log10(rows)):")
    print(f"  {'score':>7}  {'rows':>10}  {'in':>3}  {'imp':>3}  {'mod':>3}  table [role]")
    for t in ranked[:20]:
        m = out["tables"][t]
        print(f"  {m['score']:7.2f}  {m['rows']:>10,}  {m['ref_in_declared']:>3}  "
              f"{m['ref_in_implied']:>3}  {m['module_refs']:>3}  {t} [{m['role']}]")
    if hubs:
        print(f"\nshared entities (hubs) — referenced across domains, "
              "peeled before clustering:")
        for t in out["hubs"]:
            m = out["tables"][t]
            print(f"  {t} (referenced by "
                  f"{m['ref_in_declared'] + m['ref_in_implied']} tables)")
    print(f"\ncandidate domain areas ({len(clusters)} clusters, "
          f"{len(isolated)} isolated tables):")
    for c in out["clusters"]:
        print(f"  #{c['id']}: {c['size']} tables — anchors: {', '.join(c['anchors'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="dbo")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    carve = sub.add_parser("carve")
    carve.add_argument("--objects", help="comma-separated object names (a batch)")
    sub.add_parser("reconcile")
    sub.add_parser("census")
    sub.add_parser("discover")
    args = parser.parse_args()
    return {"inventory": cmd_inventory, "carve": cmd_carve,
            "reconcile": cmd_reconcile, "census": cmd_census,
            "discover": cmd_discover}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
