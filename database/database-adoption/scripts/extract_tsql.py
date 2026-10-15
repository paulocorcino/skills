#!/usr/bin/env python
"""extract_tsql.py — living introspection tool for brownfield adoption (SQL Server).

Read-only against the legacy database: the connection string pins
ApplicationIntent=ReadOnly and credentials come from .env at runtime — never
from code or from this file.

The subcommands form the adoption loop; each consumes the previous one's output:

  probe       fail-closed read-only check, run BEFORE anything else: records
              server version/edition (the source dialect), the account's
              effective database permissions (fn_my_permissions) and the
              non-system schemas into .scratch/adoption/probe.json. Exits 1 if
              the account holds ANY permission outside the read-safe whitelist
              — ApplicationIntent=ReadOnly does NOT prevent writes on a primary
              (it only routes/enforces on readable secondaries), so a
              write-capable account is a real risk, not a formality. Proceeding
              anyway is a HUMAN decision made explicit with
              --accept-write-risk "<reason>" and recorded in the ledger.
  inventory   snapshot the catalog into db-schema/baseline/inventory.<schema>.json
              (versioned; one file per adopted schema) — every object with a
              definition FINGERPRINT (short sha256 of its normalized shape) and
              its dependency edges, plus a content hash of every table listed
              in db-schema/baseline/watched-data.json (parameters of protected
              rules; rows never leave the process, only count + sha256 are
              kept). This file is the "as last absorbed" baseline reconcile
              diffs against; re-running it MOVES the baseline, so only do that
              deliberately — and never while a finding awaits a human.
  carve       render each object's DDL into the repo: tables ->
              db-schema/schema/tables/<name>.sql; views/functions/procedures/
              triggers and support objects (sequences, synonyms, table types) ->
              db-schema/schema/native/tsql/<kind>/<name>.sql.
              --objects name1,name2 restricts to a batch. carve re-reads the
              live catalog (it does not render from the baseline); if the DB
              changed since `inventory`, reconcile reports the drift.
  reconcile   prove coverage and detect drift: re-inventory the live catalog in
              memory (baseline stays untouched) and diff it against baseline
              AND repo files —
                DRIFT     fingerprint changed in the DB since extraction
                NEW/DROPPED  object appeared in / vanished from the live DB
                APPLIED   live object matching a carved file but absent from
                          the baseline — a repo migration landed; re-run
                          `inventory` to fold it in
                MISSING   inventory object with no carved file in the repo
                STALE     fingerprint stable but the carved file's content no
                          longer matches the live rendering — hand-edited,
                          corrupted, or the renderer evolved; re-carve after
                          deciding direction
                BLOCKED   object the tool cannot carve faithfully (encrypted
                          module, unsupported object class or index type,
                          unsafe filename) with no exceptions entry covering it
                DATA-DRIFT  a watched table's content hash changed — a
                          protected rule's parameter changed outside the repo
                UNDEPLOYED  repo file with no live object — a migration still
                          in flight (warning only, does not fail)
              Without --schema, reconcile covers every schema that has a
              baseline file.
              reconcile consumes db-schema/baseline/exceptions.json — the human
              decisions (objects `excluded` or `blocked`, each with a
              non-empty reason) — and exempts covered objects instead of
              reporting them; an entry without a reason is itself a finding.
              Every failing finding is a per-object DIRECTION decision, never
              an auto-fix (dynamics in verify.py's docstring): change came from
              outside -> re-carve the fact and update the model; change is
              intended by the repo -> that is a migration to apply, not drift.
              Run it at the start of any schema session (`verify.py --live`)
              while the live DB can still change outside the repo.
  census      reality numbers — row counts, implied-FK orphan counts, enum-ish
              cardinalities, tables without a declared PK (candidate-key
              duplicate/null counts). `--candidates <json>` adds FK edges from
              any provenance (code excavation, agent hypothesis) to the orphan
              count — the census tests candidates, it does not only generate
              them. Aggregates only, never row values; feeds the gap sections
              of docs/db-model/database.md.
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
discovers the tool by glob (`db-schema/tools/extract_*.py`) — no hardcoded name.

Stable contract (what every port must honor):
  - CLI: the six subcommands (probe / inventory / carve / reconcile / census /
    discover), `--schema`, `--objects` for carve batches;
    exit 0 = clean, exit 1 = findings (probe, reconcile) / failure.
  - Outputs: db-schema/baseline/inventory.<schema>.json (versioned, one per
    schema, deterministic: objects sorted by (type, name), no timestamp) with
    objects[] each carrying {schema, name, type, fingerprint, depends_on,
    target} (+ optional blocked reason) and watched_data {table: {rule, rows,
    sha256}} for the tables db-schema/baseline/watched-data.json lists;
    db-schema/baseline/exceptions.json read (human decisions, versioned);
    .scratch/adoption/probe.json (local) with version / permissions /
    write_capable / schemas; .scratch/adoption/census.json with row_counts /
    implied_fk_orphans / enumish_cardinality / tables_without_pk /
    candidate_fk_orphans (plus engine equivalents of untrusted constraints).
  - Object identity is (type, name) within a schema — never name alone
    (engines let a table and a table type share a name).
  - reconcile finding classes and their semantics: DRIFT, NEW, APPLIED,
    DROPPED, MISSING, STALE, BLOCKED, DATA-DRIFT (failures) and UNDEPLOYED
    (warning) —
    see cmd_reconcile; exceptions.json entries (excluded/blocked + reason)
    exempt objects mechanically.
  - Fingerprint semantics: hash of the normalized CATALOG shape, not of
    rendered DDL text (renderer evolution must never fake drift; STALE is the
    separate file-vs-rendering check that catches tampered files).
  - Safety: probe is fail-closed — write-capable accounts stop the run unless
    the human overrides with a recorded reason; connection pinned read-only
    where the engine allows; credentials from .env only; census emits
    aggregates, never row values; catalog identifiers are engine-quoted before
    interpolation into dynamic SQL.
  - Coverage honesty: object classes or features the renderer cannot carve
    faithfully become BLOCKED findings, never silent omissions.
  - Carve targets follow the repo layout, whose rules live in the READMEs:
    db-schema/schema/tables/README.md (one table per file, comments preserved),
    db-schema/schema/native/README.md (N3: one subfolder per dialect, one per
    kind), db-schema/schema/README.md (N1/N2/N3 split), and the model docs the
    adoption populates per docs/db-model/README.md (skeleton, materiality rule).

Engine layer (rewrite per engine, everything else stays):
  connect(), the read_* catalog functions, render_* / normalize_expr / ident
  (DDL rendering and quoting), and the census queries. Object-class coverage
  must sweep EVERYTHING the engine supports (the SKILL's rule) — e.g. Oracle
  adds packages; SQLite drops procedures; analytical engines (DuckDB, Spark,
  Databricks) lack enforced FKs/triggers entirely, so the adoption model
  itself needs rethinking there before any port makes sense.

VERSIONING — `__version__` below and this changelog move together: bump both on
every behavior change. A reference copy of this file ships with the
database-adoption skill (`.claude/skills/database-adoption/scripts/`). That
reference is READ-ONLY while an adoption runs: the run evolves only the repo
copy. At the start of an adoption the skill compares versions name-to-name:
  repo copy newer  -> keep using the repo copy; report the divergence so a
                      maintainer harvests it into the reference OUTSIDE any
                      adoption run (the skill learns across projects);
  skill newer      -> upgrade the repo copy;
  equal            -> nothing to do.
The changelog is what makes that merge informed — a version number says THAT
something diverged, the changelog says WHAT.

CHANGELOG:
  2.4.0  objects outside the default schema (dbo) carve to schema-prefixed
         files — db-schema/schema/tables/<schema>.<name>.sql, and the same
         under native/ — so two adopted schemas never share a file; objects in
         dbo keep their bare names (no existing repo changes). The file stem
         is the object's qualified name, which the kit tools read the same way.
         A name containing '.' is BLOCKED (ambiguous with the prefix).
         UNDEPLOYED is judged per schema from the file's prefix, by target
         path. Upgrading a repo that carved a non-dbo schema flat: re-carve
         those objects, then delete the old flat files (git mv keeps history).
  2.3.0  the baseline becomes versioned, per-schema governed state:
         - inventory writes db-schema/baseline/inventory.<schema>.json
           (was the single, gitignored .scratch/adoption/inventory.json): a
           second schema no longer overwrites the first's baseline, and a
           fresh clone or CI keeps the drift reference instead of re-running
           inventory over drift. Deterministic output (sorted, no timestamp)
           so a baseline move is a reviewable diff.
         - exceptions move to db-schema/baseline/exceptions.json (human
           decisions travel with the repo); an optional "schema" field
           narrows an entry, like "type".
         - watched data: tables listed in db-schema/baseline/watched-data.json
           ([{"schema", "table", "rule"}]) get a content hash (order-
           independent sha256 + row count; rows never printed or persisted);
           reconcile reports DATA-DRIFT when it changes — a protected rule's
           parameter edited in the live DB is no longer invisible.
         - reconcile without --schema covers every baselined schema; the
           pre-2.3.0 .scratch files are still read, with a note to move them.
         - carve targets colliding across schemas (same object name) become
           BLOCKED instead of overwriting each other's file.
  2.2.1  two false stops from the first SQL Server 2022 adoption with a plain
         read-only login (SELECT + VIEW DEFINITION):
         - probe: READ_SAFE_PERMS learns VIEW PERFORMANCE DEFINITION and VIEW
           CRYPTOGRAPHICALLY SECURED DEFINITION — 2022 splits VIEW DEFINITION
           into granular children, so a plain grant surfaced them and the
           write-risk gate fired on a read-only account.
         - census/discover: read_row_counts falls back to COUNT_BIG(*) per
           table when sys.dm_db_partition_stats is denied (VIEW DATABASE
           PERFORMANCE STATE missing), instead of failing the subcommand.
         - VERSIONING: the skill's reference is read-only during an adoption;
           harvesting a newer repo copy happens outside the run.
  2.2.0  the kit is `db-schema/` and the model docs left it for `docs/db-model/`
         (the old name, dbkit, is retired). Carve targets are persisted in
         inventory.json and resolved as REPO / target, so an inventory taken
         before this version still points at `dbkit/...`: reconcile would report
         every object as uncarved. Migrating an existing adoption means
         rewriting those target strings in inventory.json (or re-running
         `inventory` against the live database) — the fingerprints themselves
         are unaffected, since they describe catalog shape, not file location.
  2.1.3  gate message loses its last read-only-login suggestion (owner: the
         notification alone is the policy; the alternative is not the tool's
         to sell).
  2.1.2  module renderings normalize CRLF/CR to LF. write_text(newline="\n")
         keeps stray \r bytes while read_text() translates them away, so
         every CRLF module (most of them, on SQL Server) carved cleanly and
         then reconciled as a false STALE seconds later. Found by reconcile
         itself on the first full carve of bot_new. Also: the accept-path
         message no longer re-recommends a read-only login (owner policy).
  2.1.1  gate message follows the owner's policy: notify the elevated
         permissions and wait for acceptance — no unlock menu, no CREATE
         LOGIN script (the human adopts with the credential they chose to
         provide; acceptance = --accept-write-risk, which the agent fills
         with a factual reason once given). Fail-closed exit preserved: no
         flag, no advance.
  2.1.0  probe UX, after its first real fail-closed stop confused the human:
         - connection errors are diagnosed, not dumped: common engine errors
           (login 18456/28000, unknown DB 4060, unreachable HYT00/08001,
           missing driver IM002, TLS trust) map to WHICH .env variable to
           fix — several hints can apply at once; a missing variable is
           named too. Serves every subcommand, since all go through connect().
         - the write-capable stop reads as a decision, not a crash: the
           permission dump became headline perms + count (full list stays in
           probe.json), the message says the run is PAUSED for a human
           ("STOPPED ... NOT an error"), and unlock #1 ships ready-to-run
           T-SQL for the dedicated read-only login (db_datareader +
           VIEW DEFINITION). What deliberately did NOT change: the gate still
           never resolves itself — auto-accepting write risk would delete
           the safety property the gate exists to hold.
  2.0.0  safety + fidelity hardening after external review (major: CLI and
         finding classes grew, identity semantics changed):
         - `probe` subcommand: fail-closed effective-permission check
           (fn_my_permissions vs a read-safe whitelist), server version/
           edition, non-system schema list -> probe.json; write-capable
           accounts stop the run unless --accept-write-risk "<reason>".
         - renderers honor the object's schema (dbo was hardcoded: carving
           --schema sales produced dbo DDL — silent wrong output).
         - object identity is (type, name) everywhere (a table and a table
           type may share a name; reconcile used to collapse them).
         - `]` doubled in bracket quoting (ident); census/orphan dynamic SQL
           quotes every catalog identifier via bq() (QUOTENAME semantics).
         - module with NULL definition (WITH ENCRYPTION) is a BLOCKED
           finding, not an AttributeError.
         - coverage honesty: uncovered sys.objects classes (CLR, rules,
           standalone defaults, ...), alias UDTs, index types beyond
           (NON)CLUSTERED, unsafe/colliding filenames -> BLOCKED findings,
           never silent omissions or wrong DDL.
         - reconcile: new STALE finding (stable fingerprint but carved file
           differs from live rendering); consumes exceptions.json
           (excluded/blocked + mandatory reason) so the skill's
           done-criterion is mechanical, not a hand cross-check.
  1.2.0  census learns the two adverse-legacy findings: (a) tables WITHOUT a
         declared PK become a census entry — candidate key picked by declared
         single-column unique index, else id-ish column name, else first
         ordinal position (PKs overwhelmingly sit first), with duplicate and
         null COUNTs only, never values; whether the candidate IS the
         identity stays a grill decision. (b) `census --candidates <json>`
         counts orphans for FK edges of ANY provenance — code-excavated ORM
         joins, agent hypotheses over cryptic names — so a semantic candidate
         reaches the grill sized ("violated by N rows"), never as a bare
         guess. Orphan counting factored into count_orphans() (now supports
         ref_column != column); name-implied behavior unchanged.
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

__version__ = "2.4.0"

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SCRATCH = REPO / ".scratch" / "adoption"      # local working state (gitignored)
BASELINE = ROOT / "baseline"                  # versioned governed state
EXCEPTIONS = BASELINE / "exceptions.json"
WATCHED = BASELINE / "watched-data.json"
LEGACY_INVENTORY = SCRATCH / "inventory.json"  # pre-2.3.0 location
LEGACY_EXCEPTIONS = SCRATCH / "exceptions.json"  # pre-2.3.0 location
PROBE = SCRATCH / "probe.json"
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
    try:
        conn_str = (
            f"DRIVER={{{os.environ['DB_ODBC_DRIVER']}}};"
            f"SERVER={os.environ['DB_HOST']},{os.environ['DB_PORT']};"
            f"DATABASE={os.environ['DB_NAME']};"
            f"UID={os.environ['DB_USER']};PWD={os.environ['DB_PASSWORD']};"
            f"Encrypt={os.environ.get('DB_ENCRYPT', 'yes')};"
            f"TrustServerCertificate={os.environ.get('DB_TRUST_SERVER_CERTIFICATE', 'no')};"
            "ApplicationIntent=ReadOnly;"
        )
    except KeyError as exc:
        sys.exit(f"connection failed: {exc.args[0]} is missing from .env — "
                 "fill it and re-run")
    try:
        conn = pyodbc.connect(conn_str, timeout=15)
    except pyodbc.Error as exc:
        sys.exit(connection_diagnosis(str(exc)))
    conn.timeout = 60
    return conn


def connection_diagnosis(msg: str) -> str:
    """Translate the engine's connection error into WHICH .env variable to fix
    — nobody should have to decode an ODBC traceback mid-adoption. Every hint
    names its variable; several can apply at once (a wrong DB_NAME and a wrong
    password fail together); unrecognized errors fall back to the raw text."""
    hints = []
    if "IM002" in msg:
        hints.append("ODBC driver not found -> DB_ODBC_DRIVER (e.g. "
                     "'ODBC Driver 18 for SQL Server'; install it if absent)")
    if "18456" in msg or "28000" in msg:
        hints.append("login rejected -> DB_USER / DB_PASSWORD")
    if "4060" in msg:
        hints.append("database refused -> DB_NAME (typo, or this login has no "
                     "access to that database)")
    if "HYT00" in msg or "08001" in msg:
        hints.append("server unreachable -> DB_HOST / DB_PORT (also check "
                     "firewall and that the instance accepts TCP)")
    if "certificate" in msg.lower():
        hints.append("TLS trust failed -> DB_TRUST_SERVER_CERTIFICATE=yes for "
                     "a dev server, or fix the server certificate")
    fixes = ("\n".join(f"  fix: {h}" for h in hints) if hints else
             "  fix: error not recognized — correct one .env variable at a time")
    return f"connection failed:\n  {msg}\n{fixes}"


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


def render_sequence(schema: str, name: str, sq: dict) -> str:
    lines = [f"CREATE SEQUENCE {ident(schema)}.{ident(name)}",
             f"    AS {sq['type'].upper()}",
             f"    START WITH {sq['start']}",
             f"    INCREMENT BY {sq['increment']}",
             f"    MINVALUE {sq['min']}",
             f"    MAXVALUE {sq['max']}",
             f"    {'CYCLE' if sq['cycle'] else 'NO CYCLE'};"]
    return "\n".join(lines) + "\n"


def render_synonym(schema: str, name: str, base: str) -> str:
    return f"CREATE SYNONYM {ident(schema)}.{ident(name)} FOR {base};\n"


def render_table_type(schema: str, name: str, cols: list[dict]) -> str:
    body = ",\n".join(f"    {ident(c['name'])} {render_type(c)}"
                      f"{' NULL' if c['nullable'] else ' NOT NULL'}" for c in cols)
    return f"CREATE TYPE {ident(schema)}.{ident(name)} AS TABLE (\n{body}\n);\n"


def read_object_list(cur, schema: str) -> list[dict]:
    rows = fetch_rows(cur, """
        SELECT o.name, o.type
        FROM sys.objects AS o
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ? AND o.type IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR')
        ORDER BY o.name
    """, schema)
    return [{"name": r[0], "type": r[1].strip()} for r in rows]


KNOWN_INDEX_TYPES = {"CLUSTERED", "NONCLUSTERED"}


def read_uncovered(cur, schema: str) -> list[dict]:
    """Object classes this tool does NOT carve — reported, never silently
    omitted (coverage honesty in the PORTING CONTRACT). Two sweeps:
    sys.objects types outside the covered set (CLR modules, rules, standalone
    defaults, service queues, external tables, ...; table-bound constraints
    and internal tables are covered through their tables), and alias UDTs
    (sys.types), which columns reference by name — a table using one cannot
    be recreated without its CREATE TYPE."""
    rows = fetch_rows(cur, """
        SELECT o.type_desc, o.name FROM sys.objects AS o
        JOIN sys.schemas AS s ON s.schema_id = o.schema_id
        WHERE s.name = ? AND o.is_ms_shipped = 0
            AND o.type NOT IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR',
                               'SN', 'SO', 'C', 'F', 'PK', 'UQ', 'IT')
            AND NOT (o.type = 'D' AND o.parent_object_id <> 0)
        ORDER BY o.type_desc, o.name
    """, schema)
    out = [{"name": r[1], "kind": r[0]} for r in rows]
    alias = fetch_rows(cur, """
        SELECT ty.name FROM sys.types AS ty
        JOIN sys.schemas AS s ON s.schema_id = ty.schema_id
        WHERE s.name = ? AND ty.is_user_defined = 1 AND ty.is_table_type = 0
        ORDER BY ty.name
    """, schema)
    out.extend({"name": r[0], "kind": "ALIAS_TYPE"} for r in alias)
    return out


# ---------------------------------------------------------------- DDL rendering

import re

PLAIN_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def ident(name: str) -> str:
    """Bracket-quote only when the identifier demands it (RF06); ']' doubles
    inside brackets (QUOTENAME semantics — [a]b] is the WRONG quoting of a]b)."""
    return name if PLAIN_IDENT.match(name) else "[" + name.replace("]", "]]") + "]"


def bq(name: str) -> str:
    """ALWAYS bracket-quote — for catalog identifiers interpolated into dynamic
    SQL (census/orphan queries). Catalog-sourced names are still untrusted input
    to a query string; unconditional QUOTENAME-style quoting is the guard."""
    return "[" + name.replace("]", "]]") + "]"


SAFE_FILENAME = re.compile(r"^(?!\.)[A-Za-z0-9 ._\-]+(?<![ .])$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL",
                    *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}


def filename_block_reason(name: str) -> str | None:
    """Object names go straight into repo paths; a name the filesystem would
    mangle (path separators, traversal, trailing dot/space, Windows reserved
    words) surfaces as BLOCKED for a human call — an encoding scheme would
    hide exactly the weirdness worth seeing."""
    if not SAFE_FILENAME.match(name):
        return "name unsafe as a filename"
    if name.split(".")[0].upper() in WINDOWS_RESERVED:
        return "Windows-reserved filename"
    if "." in name:
        return "name contains '.', ambiguous with the <schema>.<name> file prefix"
    return None


DEFAULT_SCHEMA = "dbo"


def qualified_name(schema: str, name: str) -> str:
    """The carve file stem: the bare name in the default schema,
    <schema>.<name> elsewhere — the same rule the kit tools apply to DDL."""
    return name if schema.lower() == DEFAULT_SCHEMA else f"{schema}.{name}"


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


def render_table(schema: str, name: str, cols: list[dict], keys: list[dict],
                 fks: list[dict], checks: list[dict], idxs: list[dict],
                 description: str | None) -> str:
    lines: list[str] = []
    if description:
        for text_line in description.splitlines():
            lines.append(f"-- {text_line}".rstrip())
    lines.append(f"CREATE TABLE {ident(schema)}.{ident(name)} (")
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
                    f"    ON {ident(schema)}.{ident(name)} ({collist}){include}\n"
                    f"    WHERE {normalize_expr(idx['filter'])}")
        else:
            stmt = (f"\nCREATE {uniq}{kind}INDEX {ident(idx['name'])} "
                    f"ON {ident(schema)}.{ident(name)} ({collist}){include}")
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

# Effective database permissions that cannot write. EXECUTE is deliberately
# NOT here — procedures write. Anything outside this set fails the probe.
READ_SAFE_PERMS = {
    "CONNECT", "SELECT", "SHOWPLAN", "AUTHENTICATE",
    "VIEW DEFINITION", "VIEW DATABASE STATE",
    "VIEW DATABASE PERFORMANCE STATE", "VIEW DATABASE SECURITY STATE",
    "VIEW DATABASE SECURITY AUDIT", "VIEW SECURITY DEFINITION",
    # SQL Server 2022 split VIEW DEFINITION into granular children; a plain
    # GRANT VIEW DEFINITION now surfaces these too — metadata reads only.
    "VIEW PERFORMANCE DEFINITION", "VIEW CRYPTOGRAPHICALLY SECURED DEFINITION",
    "VIEW ANY COLUMN ENCRYPTION KEY DEFINITION",
    "VIEW ANY COLUMN MASTER KEY DEFINITION",
}


def cmd_probe(args) -> int:
    """Fail-closed preflight: prove what the account CAN do before reading
    anything else. ApplicationIntent=ReadOnly is routing, not protection — on
    a primary it does not stop INSERT/UPDATE/DDL — so the only honest
    read-only guarantee is an account whose effective permissions cannot
    write. fn_my_permissions is diffed against READ_SAFE_PERMS; any surplus
    fails the run. Proceeding anyway is a HUMAN decision made explicit with
    --accept-write-risk "<reason>" — recorded in probe.json and belonging in
    the ledger next to the standing recommendation: get a dedicated read-only
    login. An empty/failed permission read also fails: inconclusive = failed."""
    conn = connect()
    cur = conn.cursor()
    version, edition, database = fetch_rows(cur, """
        SELECT CONVERT(NVARCHAR(128), SERVERPROPERTY('ProductVersion')),
               CONVERT(NVARCHAR(128), SERVERPROPERTY('Edition')), DB_NAME()
    """)[0]
    perms = sorted({r[0].upper() for r in fetch_rows(
        cur, "SELECT permission_name FROM fn_my_permissions(NULL, 'DATABASE')")})
    schemas = fetch_rows(cur, """
        SELECT s.name, COUNT(o.object_id) FROM sys.schemas AS s
        LEFT JOIN sys.objects AS o
            ON o.schema_id = s.schema_id AND o.is_ms_shipped = 0
        WHERE s.name NOT IN ('sys', 'guest', 'INFORMATION_SCHEMA')
            AND s.name NOT LIKE 'db[_]%'
        GROUP BY s.name ORDER BY COUNT(o.object_id) DESC, s.name
    """)
    conn.close()

    write_capable = [p for p in perms if p not in READ_SAFE_PERMS]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "server_version": version, "edition": edition, "database": database,
        "permissions": perms, "write_capable": write_capable,
        "schemas": {name: count for name, count in schemas},
    }
    if args.accept_write_risk:
        out["write_risk_accepted"] = args.accept_write_risk
    SCRATCH.mkdir(parents=True, exist_ok=True)
    PROBE.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"probe: SQL Server {version} ({edition}), database [{database}] "
          f"-> {PROBE.relative_to(REPO)}")
    print("non-system schemas (by object count):")
    for name, count in schemas:
        print(f"  {count:5d}  {name}")
    if not perms:
        print("probe: FAIL — could not read effective permissions "
              "(inconclusive probe = failed probe)")
        return 1
    if write_capable:
        # summarize, don't dump: 90 permissions in one line bury the story.
        # The headline perms tell it; the full list is in probe.json.
        headline = [p for p in ("CONTROL", "TAKE OWNERSHIP", "INSERT", "UPDATE",
                                "DELETE", "ALTER", "EXECUTE", "CREATE TABLE",
                                "BACKUP DATABASE") if p in write_capable]
        if not headline:
            headline = write_capable[:5]
        rest = len(write_capable) - len(headline)
        print(f"probe: this account can WRITE — {len(write_capable)} "
              f"permission(s) outside the read-safe set, e.g. "
              + ", ".join(headline)
              + (f" (+{rest} more, full list in probe.json)" if rest else ""))
        if args.accept_write_risk:
            print(f"  proceeding on explicit override: {args.accept_write_risk}")
            print("  record the reason in the ledger")
            return 0
        print('probe: PAUSED — the provided credential is write-capable. '
              'Acceptance unlocks it: re-run with --accept-write-risk '
              '"<reason>" (recorded in probe.json; note it in the ledger).')
        return 1
    print(f"probe: OK — read-only account ({len(perms)} permission(s))")
    return 0


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
    uncovered = read_uncovered(cur, schema)
    watched = {}
    for w in read_watch_list(schema):
        try:
            fp = data_fingerprint(cur, schema, w["table"])
        except Exception as exc:  # missing table, unreadable type, permission
            fp = {"unavailable": type(exc).__name__}
        watched[w["table"]] = {"rule": w.get("rule"), **fp}
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
        blocked = filename_block_reason(name)
        if otype == "U":
            fp = table_fingerprint(name, cols.get(name, []), keys.get(name, []),
                                   fks.get(name, []), checks.get(name, []),
                                   idxs.get(name, []), descriptions.get(name))
            depends = sorted({fk["ref_table"] for fk in fks.get(name, [])
                              if fk["ref_table"] != name})
            target = f"db-schema/schema/tables/{qualified_name(schema, name)}.sql"
            odd = [i for i in idxs.get(name, [])
                   if i["type"] not in KNOWN_INDEX_TYPES]
            if blocked is None and odd:
                blocked = (f"index {odd[0]['name']} is {odd[0]['type']} — the "
                           "renderer only carves (NON)CLUSTERED; extend it or "
                           "record an exception")
        elif otype in ("SO", "SN", "TT"):
            fp = sha(json.dumps(obj["_payload"], sort_keys=True, default=str))
            depends = []
            target = (f"db-schema/schema/native/tsql/{MODULE_KIND_DIR[otype]}/"
                      f"{qualified_name(schema, name)}.sql")
        else:
            definition = modules[name]["definition"]
            if definition is None:
                # sys.sql_modules.definition is NULL for WITH ENCRYPTION —
                # unfaithful to carve, wrong to crash, worse to skip silently
                fp = "unavailable"
                blocked = blocked or "definition unavailable (WITH ENCRYPTION?)"
            else:
                fp = sha(definition)
            depends = deps.get(name, [])
            if otype == "TR":
                parent = trigger_parents.get(name)
                if parent and parent not in depends:
                    depends = [parent] + depends
            kind = MODULE_KIND_DIR[otype]
            target = f"db-schema/schema/native/tsql/{kind}/{qualified_name(schema, name)}.sql"
        entry = {"schema": schema, "name": name, "type": otype,
                 "fingerprint": fp, "depends_on": depends, "target": target}
        if blocked:
            entry["blocked"] = blocked
        inv_objects.append(entry)

    # case-insensitive target collisions: on a case-preserving filesystem
    # (Windows/macOS) two such files silently merge into one — every party
    # to a collision becomes BLOCKED for a human naming decision
    by_folded: dict[str, list[dict]] = {}
    for entry in inv_objects:
        by_folded.setdefault(entry["target"].lower(), []).append(entry)
    for group in by_folded.values():
        if len(group) > 1:
            names = ", ".join(f"{e['type']} {e['name']}" for e in group)
            for e in group:
                e.setdefault("blocked",
                             f"target collides case-insensitively ({names})")
    # carve targets carry no schema, so the same name in two adopted schemas
    # would share one file — block it for a human naming decision instead
    for other, targets in other_schema_targets(schema).items():
        for entry in inv_objects:
            if entry["target"].lower() in targets:
                entry.setdefault("blocked", f"target {entry['target']} is already "
                                 f"carved for schema [{other}]")
    inv_objects.sort(key=lambda e: (e["type"], e["name"]))
    uncovered = sorted(uncovered, key=lambda u: (u.get("kind", ""), u.get("name", "")))
    # "_catalog" carries the full column/constraint/module payloads so carve can
    # render without reconnecting. inventory/reconcile pop it before persisting:
    # the persisted baseline needs only fingerprints, and definitions may hold
    # things that don't belong in a JSON dump kept around (routine source bulk).
    # The baseline is versioned (db-schema/baseline/): it holds only names and
    # fingerprints — the names are already in git through the carved DDL — and
    # losing it, or keeping it on one machine, means re-running `inventory`,
    # which MOVES the drift reference over whatever drift exists. No timestamp:
    # git records when the baseline moved, and a stable file diffs cleanly.
    return {
        "schema": schema,
        "objects": inv_objects,
        "uncovered": uncovered,
        "watched_data": dict(sorted(watched.items())),
        "_catalog": {"cols": cols, "keys": keys, "fks": fks, "checks": checks,
                     "idxs": idxs, "descriptions": descriptions,
                     "modules": modules, "sequences": sequences,
                     "synonyms": synonyms, "table_types": table_types},
    }


def cmd_inventory(args) -> int:
    inv = build_inventory(args.schema)
    inv.pop("_catalog")
    path = inventory_path(args.schema)
    write_json(path, inv)
    counts: dict[str, int] = {}
    for obj in inv["objects"]:
        counts[obj["type"]] = counts.get(obj["type"], 0) + 1
    print(f"inventory: {len(inv['objects'])} objects in [{args.schema}] "
          f"-> {path.relative_to(REPO)} (versioned drift baseline — it belongs in the next commit)")
    if inv["watched_data"]:
        print(f"  watched data: {len(inv['watched_data'])} table(s) hashed")
    if LEGACY_INVENTORY.exists():
        print(f"  note: {LEGACY_INVENTORY.relative_to(REPO)} is the pre-2.3.0 "
              "baseline location — delete it once this file is versioned")
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t}: {n}")
    for obj in inv["objects"]:
        if "blocked" in obj:
            print(f"  BLOCKED {obj['type']} {obj['name']}: {obj['blocked']}")
    for u in inv["uncovered"]:
        print(f"  UNCOVERED {u['kind']} {u['name']} — object class this tool "
              "does not carve")
    return 0


def render_object(obj: dict, cat: dict) -> str:
    """One object's DDL as carve would write it — shared by carve (to write the
    file) and reconcile (to tell an APPLIED migration from a truly NEW object
    by comparing this rendering with the carved file's content)."""
    name, otype, schema = obj["name"], obj["type"], obj["schema"]
    if otype == "U":
        return render_table(schema, name, cat["cols"].get(name, []),
                            cat["keys"].get(name, []), cat["fks"].get(name, []),
                            cat["checks"].get(name, []), cat["idxs"].get(name, []),
                            cat["descriptions"].get(name))
    if otype == "SO":
        return render_sequence(schema, name, cat["sequences"][name])
    if otype == "SN":
        return render_synonym(schema, name, cat["synonyms"][name])
    if otype == "TT":
        return render_table_type(schema, name, cat["table_types"][name])
    # normalize CRLF/CR to LF: repo files are LF, and the STALE comparison
    # reads files with universal newlines — a CRLF rendering can never match
    definition = cat["modules"][name]["definition"]
    definition = definition.replace("\r\n", "\n").replace("\r", "\n")
    if not definition.endswith("\n"):
        definition += "\n"
    return definition


SAFE_SCHEMA = re.compile(r"[A-Za-z0-9_$#@-]+")


def note(msg: str) -> None:
    print(f"note: {msg}", file=sys.stderr)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def inventory_path(schema: str) -> Path:
    if not SAFE_SCHEMA.fullmatch(schema):
        sys.exit(f"schema name {schema!r} is not filename-safe for the baseline "
                 "file — extend inventory_path() with an explicit mapping")
    return BASELINE / f"inventory.{schema}.json"


def baseline_schemas() -> list[str]:
    found = sorted(p.name[len("inventory."):-len(".json")]
                   for p in BASELINE.glob("inventory.*.json"))
    if not found and LEGACY_INVENTORY.exists():
        found = [json.loads(LEGACY_INVENTORY.read_text(encoding="utf-8"))["schema"]]
    return found


def load_baseline(schema: str) -> dict | None:
    path = inventory_path(schema)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if LEGACY_INVENTORY.exists():
        legacy = json.loads(LEGACY_INVENTORY.read_text(encoding="utf-8"))
        if legacy.get("schema") == schema:
            note(f"baseline read from the pre-2.3.0 location "
                 f"{LEGACY_INVENTORY.relative_to(REPO)} — MOVE it to "
                 f"{path.relative_to(REPO)} (versioned); moving keeps the drift "
                 "reference, re-running inventory would absorb any drift")
            return legacy
    return None


def other_schema_targets(schema: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for other in baseline_schemas():
        if other == schema:
            continue
        base = load_baseline(other) or {}
        # a blocked object never claimed its file — counting it would make two
        # schemas block each other on every re-run
        out[other] = {o["target"].lower() for o in base.get("objects", [])
                      if "blocked" not in o}
    return out


def read_watch_list(schema: str) -> list[dict]:
    """db-schema/baseline/watched-data.json — tables whose DATA is part of a
    protected rule (rates, reference prices): [{"schema": ..., "table": ...,
    "rule": "ROY-01"}]; an entry without "schema" applies to every schema."""
    if not WATCHED.exists():
        return []
    return [w for w in json.loads(WATCHED.read_text(encoding="utf-8"))
            if w.get("schema", schema) == schema]


def data_fingerprint(cur, schema: str, table: str) -> dict:
    """Order-independent content hash of a watched table. The rows never leave
    this process: each is serialized, the lines are sorted, hashed, and
    dropped — only the row count and the sha256 are persisted or printed (the
    census rule: aggregates, never values)."""
    rows = fetch_rows(cur, f"SELECT * FROM {bq(schema)}.{bq(table)}")
    lines = sorted(json.dumps([None if v is None else str(v) for v in row],
                              ensure_ascii=False) for row in rows)
    return {"rows": len(lines),
            "sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()}


def load_exceptions() -> list[dict]:
    """db-schema/baseline/exceptions.json — the HUMAN decisions carve/reconcile
    consume, versioned with the repo: [{"name": ..., "status":
    "excluded"|"blocked", "reason": ...}, ...]; optional "type" and "schema"
    narrow an entry. This is the mechanized half of the skill's exception
    rule: a reasoned entry exempts the object from reconcile findings, and
    reconcile flags malformed entries (missing reason, unknown status)
    instead of honoring them."""
    path = EXCEPTIONS if EXCEPTIONS.exists() else (
        LEGACY_EXCEPTIONS if LEGACY_EXCEPTIONS.exists() else None)
    if path is None:
        return []
    if path == LEGACY_EXCEPTIONS:
        note(f"exceptions read from the pre-2.3.0 location "
             f"{LEGACY_EXCEPTIONS.relative_to(REPO)} — move it to "
             f"{EXCEPTIONS.relative_to(REPO)} (versioned)")
    return json.loads(path.read_text(encoding="utf-8"))


def exception_for(exceptions: list[dict], otype: str, name: str,
                  schema: str) -> dict | None:
    for e in exceptions:
        if (e.get("name") == name and e.get("type", otype) == otype
                and e.get("schema", schema) == schema):
            return e
    return None


def cmd_carve(args) -> int:
    inv = build_inventory(args.schema)
    cat = inv.pop("_catalog")
    exceptions = load_exceptions()
    only = set(args.objects.split(",")) if args.objects else None
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for obj in inv["objects"]:
        if only and obj["name"] not in only:
            continue
        exc = exception_for(exceptions, obj["type"], obj["name"], args.schema)
        if "blocked" in obj or (exc and exc.get("status") in ("excluded", "blocked")):
            reason = obj.get("blocked") or exc.get("reason", "(no reason)")
            print(f"  skip {obj['type']} {obj['name']}: {reason}")
            skipped += 1
            continue
        path = REPO / obj["target"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_object(obj, cat), encoding="utf-8", newline="\n")
        written += 1
    print(f"carved {written} object(s)"
          + (f", skipped {skipped} (blocked/excepted)" if skipped else ""))
    return 0


def cmd_reconcile(args) -> int:
    schemas = [args.schema] if args.schema else baseline_schemas()
    if not schemas:
        sys.exit(f"no baseline in {BASELINE.relative_to(REPO)}/ — run "
                 "`extract_tsql.py --schema <schema> inventory` first (adoption)")
    exceptions = load_exceptions()
    bad = [e for e in exceptions
           if e.get("status") not in ("excluded", "blocked") or not e.get("reason")]
    for e in bad:
        print(f"  exceptions.json entry {e.get('name')!r}: needs "
              'status "excluded"|"blocked" and a non-empty reason')
    rc = 1 if bad else 0
    for schema in schemas:
        rc |= reconcile_schema(schema, exceptions)
    return rc


def reconcile_schema(schema: str, exceptions: list[dict]) -> int:
    # Three-way diff: committed baseline (inventory.<schema>.json) × live catalog (read
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
    #   STALE       fingerprint stable but the carved file's content differs
    #               from the live rendering -> hand-edited, corrupted, or the
    #               renderer evolved; "file exists" is not "file faithful"
    #   BLOCKED     object the tool cannot carve faithfully (encrypted module,
    #               unsupported class or index type, unsafe filename) and no
    #               exceptions entry covers it -> extend the tool or decide
    #   UNDEPLOYED  repo file with no live object and no baseline -> designed
    #               here, migration not applied yet. Expected intermediate
    #               state -> reported as a warning, does NOT fail the run
    #               (verifying deployment is dbverify's future job).
    # Objects covered by a well-formed exceptions.json entry (excluded/blocked
    # + non-empty reason) are exempted and counted; malformed entries are
    # themselves problems. Identity is (type, name) — a table and a table
    # type may legally share a name.
    baseline = load_baseline(schema)
    if baseline is None:
        print(f"reconcile [{schema}]: no baseline {inventory_path(schema).relative_to(REPO)} "
              "— restore it from the repo; re-running inventory would absorb drift")
        return 1
    recorded = {(o["type"], o["name"]): o for o in baseline["objects"]}
    live = build_inventory(schema)
    cat = live.pop("_catalog")
    live_objs = {(o["type"], o["name"]): o for o in live["objects"]}

    problems: list[str] = []
    warnings: list[str] = []
    exempt = 0

    for (otype, name), obj in live_objs.items():
        exc = exception_for(exceptions, otype, name, schema)
        if exc and exc.get("status") in ("excluded", "blocked") and exc.get("reason"):
            exempt += 1
            continue
        if "blocked" in obj:
            problems.append(f"BLOCKED {otype} {name}: {obj['blocked']}")
            continue
        rec = recorded.get((otype, name))
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
        drifted = rec["fingerprint"] != obj["fingerprint"]
        if drifted:
            problems.append(f"DRIFT since extraction: {name}")
        target = REPO / rec["target"]
        if not target.exists():
            problems.append(f"MISSING carved file: {rec['target']} ({name})")
        elif (not drifted
                and target.read_text(encoding="utf-8") != render_object(obj, cat)):
            # only meaningful under a stable fingerprint: with drift the live
            # rendering legitimately left the file behind — DRIFT already fired
            problems.append(f"STALE carved file: {rec['target']} — content "
                            "differs from the live rendering (hand-edited, "
                            "corrupted, or renderer evolved); decide direction, "
                            "then re-carve")
    for (otype, name) in recorded:
        if ((otype, name) not in live_objs
                and not exception_for(exceptions, otype, name, schema)):
            problems.append(f"DROPPED from source since inventory: {name}")

    # watched data: a protected rule's parameters live in rows, which the
    # catalog fingerprint cannot see
    recorded_data = baseline.get("watched_data", {})
    for table, now in live.get("watched_data", {}).items():
        before = recorded_data.get(table)
        label = table + (f" (rule {now['rule']})" if now.get("rule") else "")
        if "unavailable" in now:
            problems.append(f"DATA-WATCH unavailable: {label} — {now['unavailable']}")
        elif not before or "sha256" not in before:
            warnings.append(f"DATA-WATCH unbaselined: {label} — run `inventory` "
                            "once no finding awaits a human")
        elif before["sha256"] != now["sha256"]:
            problems.append(f"DATA-DRIFT: {label} — content changed since the "
                            f"baseline (rows {before['rows']} -> {now['rows']}); a "
                            "protected rule's parameter changed outside the repo")

    # object classes the tool does not carve: honest coverage means each one
    # is either an exceptions entry (human decision) or a failing finding
    for u in live.get("uncovered", []):
        if not exception_for(exceptions, u["kind"], u["name"], schema):
            problems.append(f"BLOCKED {u['kind']} {u['name']}: object class not "
                            "carved by this tool — extend it or record an "
                            "exception")

    # repo -> DB direction: a carved/designed file of this schema (its prefix,
    # or no prefix for the default schema) whose target exists nowhere in the
    # live catalog nor in the baseline is a migration still in flight
    known = ({o["target"].lower() for o in live["objects"]}
             | {o["target"].lower() for o in baseline["objects"]})
    for path in sorted(list(TABLES_DIR.glob("*.sql")) + list(NATIVE_DIR.rglob("*.sql"))):
        stem = path.stem
        file_schema = stem.split(".", 1)[0] if "." in stem else DEFAULT_SCHEMA
        if file_schema.lower() != schema.lower():
            continue
        if path.relative_to(REPO).as_posix().lower() not in known:
            warnings.append(f"UNDEPLOYED: {path.relative_to(REPO)} — no live object "
                            "(pending migration?)")

    for w in warnings:
        print(f"  warn  {w}")
    if problems:
        print(f"reconcile [{schema}]: {len(problems)} problem(s)"
              + (f", {len(warnings)} warning(s)" if warnings else ""))
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"reconcile [{schema}]: OK — {len(live_objs)} objects, every fingerprint stable, "
          "every carved file present and faithful"
          + (f"; {exempt} exception(s) honored" if exempt else "")
          + (f"; {len(warnings)} undeployed file(s) pending" if warnings else ""))
    return 0


ENUMISH = re.compile(
    r"(status|tipo|type|flag|situacao|estado|state|nivel|level|categoria)",
    re.IGNORECASE)


PERMISSION_DENIED = re.compile(r"\((229|262|297|300)\)|permission", re.IGNORECASE)


def read_row_counts(cur, schema: str) -> dict[str, int]:
    """Row counts from sys.dm_db_partition_stats (cheap, metadata only). That
    DMV needs VIEW DATABASE PERFORMANCE STATE; a plain read-only login (SELECT
    + VIEW DEFINITION) lacks it, so a denial falls back to COUNT_BIG(*) per
    table — exact and still an aggregate, but a full scan on large tables."""
    try:
        rows = fetch_rows(cur, """
            SELECT t.name, SUM(ps.row_count)
            FROM sys.dm_db_partition_stats AS ps
            JOIN sys.tables AS t ON t.object_id = ps.object_id
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            WHERE s.name = ? AND ps.index_id IN (0, 1)
            GROUP BY t.name ORDER BY t.name
        """, schema)
        return {r[0]: int(r[1]) for r in rows}
    except Exception as exc:
        if not PERMISSION_DENIED.search(str(exc)):
            raise
    print("note: sys.dm_db_partition_stats denied (VIEW DATABASE PERFORMANCE "
          "STATE missing) — counting rows with COUNT_BIG(*) per table instead",
          file=sys.stderr)
    tables = fetch_rows(cur, """
        SELECT t.name FROM sys.tables AS t
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ? ORDER BY t.name
    """, schema)
    return {t: int(fetch_rows(cur, f"SELECT COUNT_BIG(*) FROM {bq(schema)}.{bq(t)}")[0][0])
            for (t,) in tables}


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


def count_orphans(cur, schema: str, tbl: str, col: str, ref: str, ref_col: str):
    """COUNT of child rows whose non-null value misses the referenced column.
    Returns int, or the error text when uncountable (type mismatch etc. — a
    finding to record, not a crash)."""
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM {bq(schema)}.{bq(tbl)} AS c "
            f"LEFT JOIN {bq(schema)}.{bq(ref)} AS p ON p.{bq(ref_col)} = c.{bq(col)} "
            f"WHERE c.{bq(col)} IS NOT NULL AND p.{bq(ref_col)} IS NULL")
        return int(cur.fetchone()[0])
    except Exception as exc:
        return f"uncountable: {exc}"


def parse_candidate_edges(path: Path) -> list[tuple[str, str, str, str]]:
    """JSON array of "table.column -> ref_table[.ref_column]" strings — FK
    candidates from OUTSIDE the tool's own name matching: ORM joins excavated
    from application code, or agent hypotheses over cryptic names that defeat
    name-implication. ref_column defaults to column. The census only COUNTS
    these; deciding what a violated candidate means stays with the grill."""
    edges = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        left, _, right = entry.partition("->")
        tbl, _, col = left.strip().partition(".")
        ref, _, ref_col = right.strip().partition(".")
        if not (tbl and col and ref):
            raise SystemExit(f"bad candidate edge: {entry!r} "
                             '(want "table.column -> ref_table[.ref_column]")')
        edges.append((tbl, col, ref, ref_col or col))
    return edges


def census_tables_without_pk(cur, schema: str, row_counts: dict[str, int]) -> dict:
    """Tables whose identity is undeclared — the classic legacy adversity
    ("PK declarations dropped during bulk-load optimizations"). Without this,
    a heap sails through adoption and its per-table block cannot state
    identity, the first invariant of any table. For each such table, name ONE
    candidate key — a declared single-column unique index wins; else an id-ish
    column name; else the first ordinal column (PKs overwhelmingly sit at
    position 1) — and count its duplicates and nulls. Counts size the gap;
    whether the candidate IS the identity is a grill decision."""
    with_pk = {r[0] for r in fetch_rows(cur, """
        SELECT t.name FROM sys.key_constraints AS kc
        JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ? AND kc.type = 'PK'
    """, schema)}
    unique_single = fetch_rows(cur, """
        SELECT t.name, c.name FROM sys.indexes AS i
        JOIN sys.tables AS t ON t.object_id = i.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.index_columns AS ic
            ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns AS c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE s.name = ? AND i.is_unique = 1 AND ic.is_included_column = 0
            AND (SELECT COUNT(*) FROM sys.index_columns AS ic2
                 WHERE ic2.object_id = i.object_id AND ic2.index_id = i.index_id
                     AND ic2.is_included_column = 0) = 1
    """, schema)
    uniq_by_tbl: dict[str, str] = {}
    for tbl, col in unique_single:
        uniq_by_tbl.setdefault(tbl, col)

    ordered = fetch_rows(cur, """
        SELECT t.name, c.name FROM sys.columns AS c
        JOIN sys.tables AS t ON t.object_id = c.object_id
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        WHERE s.name = ? ORDER BY t.name, c.column_id
    """, schema)
    by_tbl: dict[str, list[str]] = {}
    for tbl, col in ordered:
        by_tbl.setdefault(tbl, []).append(col)

    out: dict = {}
    for tbl, columns in by_tbl.items():
        if tbl in with_pk:
            continue
        unique_col = uniq_by_tbl.get(tbl)
        cand = (unique_col
                or next((c for c in columns if c.upper().startswith("ID")
                         or c.upper().endswith("ID")), columns[0]))
        entry: dict = {"rows": row_counts.get(tbl, 0),
                       "unique_index_on": unique_col, "candidate": cand}
        if entry["rows"]:
            try:
                cur.execute(
                    f"SELECT COUNT({bq(cand)}) - COUNT(DISTINCT {bq(cand)}), "
                    f"COUNT(*) - COUNT({bq(cand)}) FROM {bq(schema)}.{bq(tbl)}")
                dup, nul = cur.fetchone()
                entry["candidate_duplicates"] = int(dup)
                entry["candidate_nulls"] = int(nul)
            except Exception as exc:
                entry["candidate_duplicates"] = f"uncountable: {exc}"
        out[tbl] = entry
    return out


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

    orphans: dict[str, int | str] = {}
    for tbl, col, ref in implied:
        orphans[f"{tbl}.{col} -> {ref}"] = count_orphans(cur, schema, tbl, col, ref, col)
    out["implied_fk_orphans"] = orphans
    violated = {k: v for k, v in orphans.items() if isinstance(v, int) and v > 0}
    print(f"implied FKs with orphans: {len(violated)}")

    if getattr(args, "candidates", None):
        supplied = parse_candidate_edges(Path(args.candidates))
        ext: dict[str, int | str] = {}
        for tbl, col, ref, ref_col in supplied:
            ext[f"{tbl}.{col} -> {ref}.{ref_col}"] = count_orphans(
                cur, schema, tbl, col, ref, ref_col)
        out["candidate_fk_orphans"] = ext
        ext_violated = {k: v for k, v in ext.items() if isinstance(v, int) and v > 0}
        print(f"supplied candidate edges: {len(supplied)}, "
              f"{len(ext_violated)} with orphans")

    no_pk = census_tables_without_pk(cur, schema, out["row_counts"])
    out["tables_without_pk"] = no_pk
    print(f"tables without a declared PK: {len(no_pk)}")

    enumish = [(t, c) for t, c in candidates if ENUMISH.search(c)]
    cards: dict[str, int] = {}
    for tbl, col in enumish:
        if out["row_counts"].get(tbl, 0) == 0:
            continue
        try:
            cur.execute(f"SELECT COUNT(DISTINCT {bq(col)}) FROM {bq(schema)}.{bq(tbl)}")
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
    parser.add_argument("--schema", help="default dbo; reconcile without it "
                        "covers every baselined schema")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument(
        "--accept-write-risk", metavar="REASON",
        help="explicit human override for a write-capable account; the reason "
             "is recorded in probe.json and belongs in the ledger")
    sub.add_parser("inventory")
    carve = sub.add_parser("carve")
    carve.add_argument("--objects", help="comma-separated object names (a batch)")
    sub.add_parser("reconcile")
    census = sub.add_parser("census")
    census.add_argument(
        "--candidates",
        help='JSON file: ["table.column -> ref_table[.ref_column]", ...] — '
             "extra FK candidates (code-excavated, agent-hypothesized) to "
             "orphan-count alongside the name-implied ones")
    sub.add_parser("discover")
    args = parser.parse_args()
    if args.schema is None and args.command != "reconcile":
        args.schema = "dbo"
    return {"probe": cmd_probe, "inventory": cmd_inventory, "carve": cmd_carve,
            "reconcile": cmd_reconcile, "census": cmd_census,
            "discover": cmd_discover}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
