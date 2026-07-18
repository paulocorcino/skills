# Database schema (`dbkit/`) — guide for agents

`dbkit/` is a **drop-in** module for governable schema: the desired state is declared
in plain SQL (one object per file), the domain is documented as source, diagrams are
generated, and validation is mechanical. This file is the entry point; **each folder
has a `README.md`** with the specific instruction and a template of what to put there.

## Golden rule

Never finish a schema change with `python dbkit/tools/verify.py` failing.
Every change follows the instruction of the folder where the work happens.

## Going to... → go to the folder (the instruction is in its README)

| Going to...                               | Folder                             |
|-------------------------------------------|------------------------------------|
| Create / alter a table                    | `dbkit/schema/tables/`                |
| Function / procedure / trigger / view / support object (sequence, synonym, type) | `dbkit/schema/native/<dialect>/<kind>/` |
| Implement a dialect difference (N2)       | `dbkit/schema/overrides/<dialect>/`   |
| Adopt an existing/legacy database         | `database-adoption` skill (`dbkit/tools/extract_<dialect>.py`) |
| Sync repo with changes made in the live DB | `database-sync` skill (reconcile → import/retire) |
| Generate / record a migration             | `dbkit/migrations/`                   |
| Document the domain and business rules    | `dbkit/model/`                        |
| Write a behavior test                     | `dbkit/tests/`                        |
| Reference / dev data                      | `dbkit/seeds/`                        |

> ADRs (decisions, one per file) live in `docs/adr/` **at the repo root**.

## Adopted live database — drift rule

While the live DB can still change outside the repo (app DDL, DBA hotfix), start
any schema session with `python dbkit/tools/verify.py --live` (offline pipeline
plus `extract_<dialect>.py reconcile`, discovered by glob, read-only, needs `.env`). Reconcile failures
(DRIFT / NEW / APPLIED / DROPPED / MISSING) are **per-object direction
decisions**, never auto-fixes: change came from outside → re-carve the fact and
update the model docs; change is intended by the repo → that is a migration to
apply, not drift. To act on findings end-to-end (import new/changed objects,
retire dropped ones, refresh baseline and model docs), invoke the
`database-sync` skill. A repo-designed object whose migration hasn't landed yet shows
as an `UNDEPLOYED` warning (doesn't fail); after the migration lands it flips to
`APPLIED` — re-run `extract_<dialect>.py inventory` to fold it into the baseline.
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

1. `dbkit/model/erd.mmd` renders in the PR — does the structural change make sense?
2. `dbkit/schema/` — is the diff small and focused? (one concept per PR)
3. `dbkit/migrations/` — does it follow expand/contract? Is it reversible? Never edits a merged migration?
4. `dbkit/model/database.md` (or the owning `domains/` shard) — was the intent updated alongside and does it match the DDL?
5. `docs/adr/` — does a new decision have an ADR explaining the rejected alternatives?
6. Is `python dbkit/tools/verify.py` green?

> Today `verify.py` runs **lint + erd-check + buildsql + doccheck**. Steps that need
> `dbverify`, `levelcheck` and capability profiles are **not built yet** — where this
> guide describes them in the present tense, read them as the target design. A green
> `verify.py` therefore still does not prove behavior (that is `dbverify` + tests).

## Commands (from the repo root)

```
python dbkit/tools/verify.py        # pipeline: lint + erd-check + buildsql + doccheck
python dbkit/tools/verify.py --live # + extract_<dialect>.py reconcile (drift vs adopted DB)
python dbkit/tools/lint.py [path]   # SQLFluff, dialect per folder, split DELIMITER/GO
python dbkit/tools/erdgen.py        # regenerate diagrams; --check for CI
python dbkit/tools/buildsql.py      # assemble generated/<dialect>/schema.sql
python dbkit/tools/doccheck.py      # schema ↔ model docs presence coherence
```

## Facts that save time

- SQL style is SQLFluff's job (config in `dbkit/.sqlfluff`) — don't argue style in
  review, run the linter.
- `schema/native/` is linted best-effort: SQLFluff doesn't parse all procedural
  SQL (official gap sqlfluff#901). An "N3 gap" in the lint is **expected**.
- `DELIMITER`/`GO` are client commands, not SQL — never put them in `schema/`
  files; the build/lint slices them on its own when applying/validating.
- The scaffold is **dialect-agnostic**: the canonical dialect is read from
  `dbkit/.sqlfluff` (`dialect = …`), with **no hardcoded default** — tools fail loudly if
  it is unset. Choosing it is a project decision — bootstrap steps in `dbkit/README.md`;
  the `database-modeling` skill walks the decision when it is still open.

## The *why* behind the rules

The doctrine — design principles P1–P7, the dialect families/tiers strategy, and the
assumed risks — lives in `database-doctrine.md`. Read it when a case isn't covered by a
folder README, or when you must decide N1/N2/N3, a dialect tier, or whether a change
needs an ADR.