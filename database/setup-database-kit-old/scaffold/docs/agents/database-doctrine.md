# Database schema — doctrine (the *why* behind `dbkit/`)

Reference for the reasoning that governs the `dbkit/` module. The operational "where do I
go" lives in `database-schema.md`; this file explains the principles the READMEs and
tools refer to by number, so the model can **conduct** decisions in the area, not just
follow steps. Read this when a situation isn't covered by a folder README, or when
deciding whether something is N1/N2/N3, which dialect tier applies, or whether a change
needs an ADR.

## Design principles (P1–P7)

| # | Principle | Practical consequence |
|---|---|---|
| P1 | **A single source of truth per fact** | `schema/` declares the desired state; everything else is generated or derived. Nothing generated is hand-maintained. |
| P2 | **SQL is the model's native language** | The agent writes SQL, not an invented DSL. Lower error rate, immediate validation, no generator to maintain. |
| P3 | **Verifiable → tool; judgment → short prose** | Style is SQLFluff's; transpilability is sqlglot's; coherence is CI's. Markdown instructions only for what needs judgment. |
| P4 | **Semantic loss is an explicit decision, never magic translation** | What doesn't transpile cleanly becomes a reviewable override — the build fails until it exists. |
| P5 | **One object per file** | PR diffs show exactly what changed in the domain. |
| P6 | **Per-task instructions, not a monolith** | Smaller models load only the current task's instruction (progressive disclosure). |
| P7 | **Migrations are immutable after merge** | A fix is a new migration. Never edit history. |

## Dialect strategy: families and tiers

"Support any DBMS" is a **non-goal**. The method is *dialect-pluggable*, but the
portability promise is bounded by what the engines guarantee.

**Families** (full portability only *within* a family):

| Family | Systems | Conceptual limit |
|---|---|---|
| **Relational OLTP** | Postgres, MySQL, MariaDB, SQLite, SQL Server, Oracle | The current design applies in full |
| **Columnar OLAP** | ClickHouse, DuckDB | ClickHouse: no real FK, no classic UPDATE; schema centered on ENGINE/ORDER BY |
| **Lakehouse** | Spark SQL, Hive, Databricks | Informational (unenforced) PK/FK; no triggers/procedures; partitioning is central |

Crossing families is not transpilation — it is **remodeling** (ADR + a family-specific
schema). The universal layer across families is the model docs — `dbkit/model/database.md`
and its `domains/` shards (growth contract in `dbkit/model/README.md`) — never the DDL.

**Support tiers** (target guarantees; lint, buildsql and doccheck run today —
dbverify and behavioral tests are *planned*):

| Tier | Guarantee | Dialects |
|---|---|---|
| **1 — Verified** | lint + transpile + dbverify in CI + behavioral tests | MySQL, Postgres |
| **2 — Validated** | lint + transpile check; no execution check in CI | MariaDB, SQLite, DuckDB; SQL Server (promoted 2026-07: canonical dialect of the first adopted real project); Databricks (ceiling — no container) |
| **3 — Recognized** | parse/lint only | Oracle, Hive, ClickHouse, Spark SQL — until a real project |

A per-dialect **capability profile** (`tools/dialects/<name>.yaml`, *not built yet*)
declares what the engine guarantees (`enforced_fk`, `triggers`, `procedures`, `check_constraints`,
`transactional_ddl`…). Tools will consult it and **refuse to generate** what the target
doesn't guarantee — P4 applied to engines, not just syntax. E.g. generating an FK for
Databricks requires an explicit `informational: true` flag in the override, recording
that the invariant becomes the application's responsibility. Dialects move up a tier
**on real-project demand**, never speculatively.

## Assumed risks

- **sqlglot as the N1/N2 judge**: false "transpiles cleanly" is possible; mitigated by
  dbverify + dual tests (the final truth is always a real database).
- **Model-docs discipline** (`database.md` and its `domains/` shards): the only
  artifact without full semantic verification (doccheck covers presence, not quality).
  Mitigation: focused human review, since the rest is mechanical.
