---
name: database-setup
description: Install the db-schema governance method (kit, model-docs home, agent docs, ADR seed, CI backstop) into a repo and prove it green.
disable-model-invocation: true
---

Install the schema method this skill travels with: desired state declared in plain SQL, domain documented as source, validation mechanical. The `scaffold/` folder beside this file is the versioned reference of the whole method — copy it, wire it, prove it green. The scaffold is read-only during a run; the copy in the target repo is the repo's own, and the repo grows it from there. What the scaffold deliberately leaves out matters as much as what it holds.

## 1. Preflight

- The target must be a git repository; when it is not, offer `git init` and wait for the user's answer.
- **An existing `db-schema/`** means this is not an install. Tell the user it exists and ask for authorization before going further; this skill installs only. With authorization, compare the repo's copy against `scaffold/` file by file and report each file the scaffold has moved past, with the change it would bring. A file the repo changed on its own is the repo's adaptation and stays as it is. Done when the user has the report; the repo and `scaffold/` stay as they were unless the user directs a change to the repo.
- **The agent instructions file.** Identify the file the project already uses for agent instructions (`AGENTS.md`, `CLAUDE.md`, or another the project's tooling reads) and name it to the user — that is where step 4 writes. When the project has none, propose creating `AGENTS.md` and create it only with the user's authorization.
- **The DDL's owner.** Look for an ORM that writes the schema: its schema or entity definitions and a migrations folder it generates or applies (Drizzle, Prisma, Django, Alembic, EF Core, Hibernate, Rails, …). Found one → the mode is the user's decision, put with its trade-off: **mirror mode** keeps the ORM as the DDL's owner and carves `db-schema/` from a database its migrations built (recommend it when those migrations already deploy); **source mode** moves ownership to `db-schema/`, and the ORM's mapping follows the declared schema. Found none → source mode, with nothing to ask. Done when the mode is settled — and, in mirror mode, the ORM, its schema path, and its migrations path are named.
- Python 3.11+ available. Tool dependencies have a single pinned source — `db-schema/tools/_deps.py` (no requirements file, by design); the CI workflow shows the one-liner that installs them.

## 2. Copy the scaffold

Copy every tracked file of `scaffold/` into the repo root **verbatim**, byte for byte — derived files such as `__pycache__/` stay behind. A file the repo already has at a target path (an ADR index, a workflow) stays as it is: report it to the user with what the scaffold's version would add, and merge that part only on their word. The files:

- `db-schema/` — folder skeleton with its per-folder READMEs (each one is the instruction set for work done in that folder) and `tools/` (`verify.py`, `lint.py`, `erdgen.py`, `buildsql.py`, `doccheck.py`, `_dialect.py`, `_deps.py`, `_paths.py`, `_model.py`)
- `docs/db-model/README.md` — the domain documentation lives **outside** the kit, in the repo's own docs tree: the DDL is code, the model is prose, and prose belongs where the rest of the project's prose lives. Only its `README.md` (skeleton and growth contract) ships; the model itself is grown from decisions or evidence
- `docs/agents/database-schema.md` — the entry point: task → folder routing, N1/N2/N3 mental model
- `docs/agents/database-doctrine.md` — the why: principles, dialect tiers, assumed risks
- `docs/adr/README.md` — the decision-record format
- `.github/workflows/verify.yml` — CI backstop; adjust its `branches:` to the repo's default branch, and leave it out only when the repo doesn't use GitHub Actions (the golden rule then has no mechanical net — tell the user)

The tools derive `db-schema/`'s own location from their file position, so the module travels anywhere. The **one** path they cannot derive is where the model docs live — a monorepo keeps its docs at the workspace root, several levels above the kit. It is declared once, in `db-schema/tools/_paths.py` (`MODEL_DIR`), and the default assumes `db-schema/` and `docs/` are siblings at the repo root. **When they are not, fix that constant now**, before step 5 — every tool reads it, so a wrong value surfaces as `doccheck` inventing a missing model doc rather than as a path error.

## 3. Deliberate absences

Each of these is a decision or an artifact another skill brings into existence; the install leaves the slot empty:

- **`db-schema/.sqlfluff`** — the canonical dialect is the project's first modeling decision. It lands via the routes in step 6; creation steps in `db-schema/README.md`.
- **`docs/db-model/database.md`** — the model doc is grown from decisions (greenfield) or evidence (brownfield).
- **`extract_*.py`** — live-database introspection ships with the `database-adoption` skill, which also builds a port when no extractor covers the engine.
- **The glossary** (`CONTEXT.md`, `GLOSSARY.md`, …) — it comes into existence through the modeling grill, one resolved term at a time; a glossary the project already has stays as it is.
- **`docs/db-model/calc/`** — the modeling grill creates it with the first protected rule.

Filling any of these during the install pre-empts a decision the method routes to a human.

## 4. Wire the repo

Append to `.gitignore` (create it if absent):

```gitignore
# db-schema build output (derived — never source); the folder's README stays tracked
db-schema/generated/*
!db-schema/generated/README.md
# tool bytecode (derived)
__pycache__/
# local work area (adoption ledger, inventories)
.scratch/
# local secrets (commit .env.example instead)
.env
```

Append to the agent instructions file identified in step 1, leaving what is already there untouched:

```markdown
## Database schema (`db-schema/`)

- Any schema work → read `docs/agents/database-schema.md` first, then the
  `README.md` of the folder where the work happens.
- DDL lives in `db-schema/`; the domain documentation lives in `docs/db-model/`.
- The why behind a rule → `docs/agents/database-doctrine.md`.
- Golden rule: finish every schema change with `python db-schema/tools/verify.py`
  green (run from the repo root).
```

In mirror mode, the block's `DDL lives in` line becomes the mode line below, filled from step 1, and the choice is recorded as an ADR in `docs/adr/` (the alternative rejected, and why):

```markdown
- Mode: **mirror**: <ORM> owns the DDL (schema `<path>`, migrations `<path>`);
  `db-schema/` is its carved mirror, written by `database-sync`; the domain
  documentation lives in `docs/db-model/`.
```

## 5. Prove it green

`python db-schema/tools/verify.py` from the repo root must pass on the virgin scaffold — empty pipeline steps report clean, and no tool invents a dialect. When it fails here, the installation is wrong; fix it before handing off.

## 6. Route the first decision

Setup gives structure; it decides nothing. Offer the next step:

- **Greenfield** (schema to be designed) → the `database-modeling` grill; its first theme settles the canonical dialect, which creates `db-schema/.sqlfluff`.
- **Brownfield** (existing database to govern) → the `database-adoption` skill; its probe records the source dialect and puts the canonical-dialect decision to the user.
- **Mirror mode** → the `database-adoption` skill, against a private database the ORM's migrations built: it carves the first mirror. The canonical dialect is the engine the migrations target.

## Maintenance: dependency pins

Outside any run. The pins in `scaffold/db-schema/tools/_deps.py` freeze while SQLFluff and sqlglot keep releasing, and every install copies them as they are; `check_deps` warns once `VALIDATED_ON` is older than `STALE_AFTER_DAYS`. To refresh:

1. `python scripts/check_pins.py` — pinned vs latest on PyPI, with changelog links. Exit 0 means current; stop.
2. For each pin behind, read the changelog from the pinned version to the candidate: renamed or removed rules, dialect parser changes, `.sqlfluff` keys that moved, sqlglot transpile changes.
3. In a scratch repo with the scaffold installed and a `.sqlfluff` per dialect the references cover, install the candidates and run `verify.py` green, along with the extractor references' fixtures where they exist. A candidate that fails stays out; pin the newest one that passes.
4. Update `REQUIRES` and `VALIDATED_ON` together in the scaffold. Repos already installed pick up the move through the `_deps.py` check in `database-sync` step 1.
