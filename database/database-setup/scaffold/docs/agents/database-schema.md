# Database schema (`db-schema/`) — guide for agents

`db-schema/` is a **drop-in** module for governable schema: the desired state is declared
in plain SQL (one object per file), the domain is documented as source, diagrams are
generated, and validation is mechanical. This file is the entry point; **each folder
has a `README.md`** with the specific instruction and a template of what to put there.

## Golden rule

Finish every schema change with `python db-schema/tools/verify.py` green.
Every change follows the instruction of the folder where the work happens.

## Going to... → go to the folder (the instruction is in its README)

| Going to...                                | Folder                                            |
|--------------------------------------------|---------------------------------------------------|
| Create / alter a table                     | `db-schema/schema/tables/`                        |
| Function / procedure / trigger / view / support object (sequence, synonym, type) | `db-schema/schema/native/<dialect>/<kind>/` |
| Implement a dialect difference (N2)        | `db-schema/schema/overrides/<dialect>/`           |
| Decide or change the model (a modeling gap, a new concept, a rule) | `database-modeling` skill (grill → model docs, glossary, ADRs) |
| Change a rule tagged **[protected]** (its code, parameters, or examples) | `docs/db-model/calc/README.md` — its change sequence comes first |
| Adopt an existing/legacy database          | `database-adoption` skill (`db-schema/tools/extract_<dialect>.py`; it builds a port when no extractor covers the engine) |
| Sync repo with changes made in the live DB | `database-sync` skill (reconcile → import/retire) |
| Generate / record a migration              | `db-schema/migrations/`                           |
| Document the domain and business rules     | `docs/db-model/`                                  |
| Write a behavior test                      | `db-schema/tests/`                                |
| Reference / dev data                       | `db-schema/seeds/`                                |

> The two prose homes live **at the repo root**, outside the module: the model docs in
> `docs/db-model/` (where they live is declared in `db-schema/tools/_paths.py`; the
> specs of protected rules in its `calc/` subfolder) and the ADRs, one decision per
> file, in `docs/adr/`.

## Adopted live database — drift rule

While the live DB can still change outside the repo (app DDL, DBA hotfix), start
any schema session with `python db-schema/tools/verify.py --live` (offline pipeline
plus `extract_<dialect>.py reconcile`, discovered by glob, read-only, needs `.env`). Reconcile failures
(DRIFT / NEW / APPLIED / DROPPED / MISSING) are **per-object direction
decisions**, never auto-fixes: change came from outside → re-carve the fact and
update the model docs; change is intended by the repo → that is a migration to
apply, not drift. To act on findings end-to-end (import new/changed objects,
retire dropped ones, refresh baseline and model docs), invoke the
`database-sync` skill. A repo-designed object whose migration hasn't landed yet shows
as an `UNDEPLOYED` warning (doesn't fail); after the migration lands it flips to
`APPLIED` — re-run `extract_<dialect>.py inventory` to fold it into the baseline
(`db-schema/baseline/`, versioned — commit every move; a missing baseline is restored
from git, never rebuilt over drift).
When deploys start flowing only from the repo, the arrow inverts — drift becomes
an alarm that someone bypassed the process; record that flip as an ADR.

## The 3 levels (core mental model)

What separates "auto-generatable" from "needs human decision":

| Level | What it is | Where | Verification |
|---|---|---|---|
| **N1 — Portable** | transpiles cleanly across all dialects | `schema/tables/` | sqlglot generates the rest |
| **N2 — Dialect-sensitive** | transpilation loses/alters semantics | `schema/tables/` + `schema/overrides/<dialect>/` | `buildsql` fails on a lossy transpile without an override; `levelcheck` (classification) *not built yet* |
| **N3 — Native** | procedural / DBMS-specific | `schema/native/<dialect>/` | test against a real database (lint is best-effort) |

N2 examples: ENUM, SET, UUID, JSON, autoincrement, timestamp with timezone,
computed columns, partial/expression index, collation, sequence, UPSERT.

## How to review a schema change (PR)

1. `docs/db-model/erd.mmd` renders in the PR — does the structural change make sense?
2. `db-schema/schema/` — is the diff small and focused? (one concept per PR)
3. `db-schema/migrations/` — does it follow expand/contract? Is it reversible? Never edits a merged migration?
4. `docs/db-model/database.md` (or the owning `domains/` shard) — was the intent updated alongside and does it match the DDL?
5. `docs/adr/` — does a new decision have an ADR explaining the rejected alternatives?
6. Is `python db-schema/tools/verify.py` green?

> Today `verify.py` runs **lint + erd-check + buildsql + doccheck**. Steps that need
> `dbverify`, `levelcheck` and capability profiles are **not built yet** — where this
> guide describes them in the present tense, read them as the target design. A green
> `verify.py` therefore still does not prove behavior (that is `dbverify` + tests).

## Commands (from the repo root)

```
python db-schema/tools/verify.py        # pipeline: lint + erd-check + buildsql + doccheck
python db-schema/tools/verify.py --live # + extract_<dialect>.py reconcile (drift vs adopted DB)
python db-schema/tools/lint.py [path]   # SQLFluff, dialect per folder, split DELIMITER/GO
python db-schema/tools/erdgen.py        # regenerate diagrams; --check for CI
python db-schema/tools/buildsql.py      # assemble generated/<dialect>/schema.sql
python db-schema/tools/doccheck.py      # schema ↔ model docs presence coherence
```

## Facts that save time

- SQL style is SQLFluff's job (config in `db-schema/.sqlfluff`) — don't argue style in
  review, run the linter.
- `schema/native/` is linted best-effort: SQLFluff doesn't parse all procedural
  SQL (official gap sqlfluff#901). An "N3 gap" in the lint is **expected**.
- `DELIMITER`/`GO` are client commands, not SQL — never put them in `schema/`
  files; the build/lint slices them on its own when applying/validating.
- The scaffold is **dialect-agnostic**: the canonical dialect is read from
  `db-schema/.sqlfluff` (`dialect = …`), with **no hardcoded default** — tools fail loudly if
  it is unset. Choosing it is a project decision — bootstrap steps in `db-schema/README.md`;
  the `database-modeling` skill walks the decision when it is still open.

## The *why* behind the rules

The doctrine — design principles P1–P9, the dialect families/tiers strategy, and the
assumed risks — lives in `database-doctrine.md`. Read it when a case isn't covered by a
folder README, or when you must decide N1/N2/N3, a dialect tier, or whether a change
needs an ADR.