---
name: database-adoption
description: Adopt a brownfield database into dbkit. Use when the user wants to import an existing database, reverse-engineer a legacy schema, or connect one and bring it under governance.
---

Bring an existing database under `dbkit/` governance. The live schema is the source of facts; the repo is where it becomes governable. Two standing rules:

- Work **read-only** against the legacy database — and make the connection itself incapable of writing where the engine allows: open read-only transactions (or the driver's read-only flag), set a statement timeout, and check at probe time that the account holds no write grants. "We intend to read" is weaker than "the connection cannot write".
- Keep the **ledger** current — `.scratch/adoption/ledger.md` (gitignored) holds only what no script can derive: the connection recipe (never credentials), source dialect, chosen schemas, and the exceptions — objects `excluded` or `blocked`, each with its reason. Per-object progress is **not hand-tracked**: `extract_<dialect>.py reconcile` computes the frontier (uncarved objects, drifted fingerprints, drops) from the live catalog, the committed inventory, and the carved files — evidence, not self-report. Every fresh session reads the ledger, runs reconcile, and resumes from what it reports.

## 1. Locate the connection

Search the project for how it already reaches the database: env files, `docker-compose`/Dockerfile, framework config (Django settings, Spring `application.yml`, Prisma, knexfile, …), docs. **Never read the values inside secret-bearing files** (`.env` and kin) — inspect filenames, variable names, and configuration structure only; the connection script reads secrets from the environment at runtime, so their values are never needed in context. Done when you hold a connection recipe — engine, host, port, database, credential source — or have established that none exists.

## 2. Wire the env

If none exists, create the project's native env convention (`.env` plus a committed `.env.example`, the real file gitignored) with placeholder variables, matching the project's language and stack. Tell me exactly which variables to fill; credentials live in the env file only — never in the chat. The env user needs read permission on the catalog and the target schemas — if the probe fails on permissions, name the exact missing grant. Wait until I confirm the env is filled.

## 3. Probe

Connect through a short Python script using the engine's driver, read-only. On failure, show the error and fix the recipe with me, one variable at a time. On success: record engine and version — that is the **source dialect**, not automatically the canonical one. If `dbkit/.sqlfluff` is missing, propose the source dialect as canonical and ask me to confirm or name a different target (steps in `dbkit/README.md`); if it exists and differs from the source, surface the difference — never overwrite it. Then list the non-system schemas and put the first decision to me: **which schemas to adopt**. Write the ledger — recipe, source dialect, schemas, and the full object inventory with a definition fingerprint per object, every object `pending`.

## 4. Extract and carve

Introspection is mechanical — script it, never transcribe by hand. The tool is `dbkit/tools/extract_<source-dialect>.py`, a **living tool** this skill ships as a versioned reference in its `scripts/` folder (today: `extract_tsql.py`). Before extracting, sync versions name-to-name — compare `__version__` in the repo copy against the skill's reference:

- no repo copy yet → copy the matching reference into `dbkit/tools/`; if no reference covers this engine, write a sibling honoring the **PORTING CONTRACT** in the reference's docstring (same CLI, outputs, finding classes, fingerprint semantics, safety rules; engine layer rewritten) and add it to `scripts/`
- repo copy **newer** → harvest the evolution back into the skill's reference (copy it over `scripts/`, changelog included) — this is how the skill learns across projects
- skill reference **newer** → upgrade the repo copy, reading the changelog for what changed
- equal → compare content too (a byte diff is enough): identical → proceed; different → someone changed behavior without bumping — diff, decide direction, bump the version, then sync

Adjust the tool whenever this engine or this database demands something it doesn't cover yet — and bump `__version__` + changelog with every behavior change, or the sync above goes blind. When the inventory is too large for one session, split it along dependency order into batches sized to fit one subagent's context (no batch needing another's output) and delegate each to a subagent that carves its objects and reports back, keeping the main window for orchestration; a small inventory is carved directly. Either way, the done-criterion below — not the tactic — is what guarantees coverage:

- tables → `dbkit/schema/tables/<table>.sql`, comments preserved
- functions, procedures, triggers, views → `dbkit/schema/native/<dialect>/<kind>/` — one subfolder per kind (`functions/`, `procedures/`, `triggers/`, `views/`), per that folder's README
- support objects the engine has — sequences, synonyms, user-defined types, and kin — → `dbkit/schema/native/<dialect>/<kind>/` too. The inventory must sweep **every object class the engine supports**, not just tables and routines: defaults and routines depend on these objects, and a schema carved without them cannot be recreated
- what doesn't transpile cleanly → `dbkit/schema/overrides/<dialect>/`

Done when the inventory **reconciles**: `extract_<dialect>.py reconcile` reports every source object carved (or listed in the ledger as `excluded`/`blocked` with its reason) and no fingerprint drifted since extraction — and `python dbkit/tools/verify.py` is green. A green `verify.py` alone is not evidence of extraction completeness; the reconciliation is what proves coverage.

## 5. Populate the model

Run `python dbkit/tools/erdgen.py`. Draft `dbkit/model/database.md` (skeleton and growth contract in `dbkit/model/README.md`) from evidence only: table/column comments, constraints, and column semantics become concepts and invariants. When a specific question survives the catalog evidence, a `SELECT … LIMIT 3` is allowed to inspect **shape** — record what the shape told you, never the sampled values (they may be personal or business-sensitive). Record what evidence cannot tell you — intent, business rules, vocabulary — as explicit gaps, and fill "Conscious divergences from the original dump" for anything deliberately changed while carving. Per-table blocks follow the materiality rule in `dbkit/model/README.md`: an empty table no routine touches and nothing references gets a one-line entry marked **elimination candidate** (an owner decision to confirm or drop), never a *pending* block.

Then run `extract_<dialect>.py discover` — **DB-to-Domain discovery**: it ranks every table by structural relevance (who references it — tables via FK, modules via dependencies; row count only breaks ties), classifies structural roles (junction, lookup, log, core, elimination candidate, unreferenced), and clusters the FK graph — declared *plus* name-implied edges — into candidate domain areas, peeling cross-domain hub entities first. Everything it emits is a **candidate, never a fact**: clusters suggest domain areas but naming them is a human decision for the grill; `unreferenced` tables and hub entities are gaps to record; its `elimination candidate` list mechanizes the materiality rule above. Use the ranking to order the model draft and the grill — human attention goes to core candidates first.

Then run the **reality census** — read-only aggregates, scripted like the extraction: row count per table, orphan count for every implied FK, violation count for every candidate invariant. Counts expose scale, not values. `DISTINCT` **does return values** — run it only on columns first classified as non-sensitive from catalog evidence (name, type, comment, cardinality); when in doubt, ask before querying. Attach each number to its gap ("candidate invariant: violated by N rows") — the numbers size the cleanup the refactoring tickets will carry. In the routines table, mark every non-trivial routine **behavior not characterized** — each mark becomes a characterization-test ticket before that routine may be refactored.

Done when every adopted table has its per-table block or one-line entry, every census number is attached to a gap, and every non-trivial routine carries its **behavior not characterized** mark.

## 6. Excavate the code

If the repo carries application code, excavate it for what the catalog cannot see: ORM associations and joins that imply relationships with **no FK behind them**, enums, state machines, and validations living only in the app layer. In a legacy refactoring these code-only rules are exactly what the model must make explicit — record each finding as a candidate relation or invariant, marked as a gap until confirmed. The same sampling guard as step 5 applies.

The repo is not the whole blast radius. Put to me the one question no excavation can answer: **who else reads or writes this database** — other systems, BI/ETL, replication, scheduled jobs, direct access? Record the answer with the gaps; an unknown consumer is itself a finding, never a silence.

## 7. Hand off the gaps

Extraction gives structure; it cannot give intent. Close by offering the `database-modeling` grill over the recorded gaps — the live schema and the excavated code are now fact sources its tracer reads. If no `CONTEXT.md` exists yet, the grill is what brings it into existence: each resolved gap lands a term in the glossary or a rule in the model.
