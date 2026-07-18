---
name: setup-database-kit
description: Scaffold the dbkit schema-governance method into a repo — copy the dbkit/ module (tools, folder READMEs), the agent docs (database-schema, database-doctrine), the ADR seed, and the CI backstop; wire .gitignore and CLAUDE.md and prove verify.py green. Use when the user wants to install dbkit, bootstrap database governance in a new or existing repo, or start the schema method from scratch.
---

Install the schema method this skill travels with: desired state declared in plain SQL, domain documented as source, validation mechanical. The `scaffold/` folder beside this file is the versioned reference of the whole method — copy it, wire it, prove it green. What the scaffold deliberately does **not** contain matters as much as what it does.

## 1. Preflight

- The target must be a git repository (offer `git init` if not).
- If `dbkit/` already exists there, **stop** — this skill installs, it never upgrades. An existing installation means the work is a deliberate diff: compare the repo's copy against `scaffold/`, decide direction file by file, and harvest genuine improvements back into `scaffold/` (that is how the method learns across projects).
- Python 3.11+ available. Tool dependencies have a single pinned source — `dbkit/tools/_deps.py` (no requirements file, by design); the CI workflow shows the one-liner that installs them.

## 2. Copy the scaffold

Copy `scaffold/` into the repo root **verbatim** — every file, byte for byte:

- `dbkit/` — folder skeleton with its per-folder READMEs (each one is the instruction set for work done in that folder) and `tools/` (`verify.py`, `lint.py`, `erdgen.py`, `buildsql.py`, `doccheck.py`, `_dialect.py`, `_deps.py`)
- `docs/agents/database-schema.md` — the entry point: task → folder routing, N1/N2/N3 mental model
- `docs/agents/database-doctrine.md` — the why: principles, dialect tiers, assumed risks
- `docs/adr/README.md` — the decision-record format
- `.github/workflows/verify.yml` — CI backstop; adjust its `branches:` to the repo's default branch, and drop it only if the repo doesn't use GitHub Actions (the golden rule then has no mechanical net — say so)

## 3. Deliberate absences — do not fill them

- **`dbkit/.sqlfluff`** — the canonical dialect is the project's first modeling decision, never a default this skill ships. It lands via the routes in step 6; creation steps in `dbkit/README.md`.
- **`dbkit/model/database.md`** — the model doc is grown from decisions (greenfield) or evidence (brownfield), never from a template.
- **`extract_*.py`** — live-database introspection ships with the `database-adoption` skill, not with the scaffold.
- **`CONTEXT.md`** — the glossary comes into existence through the modeling grill, one resolved term at a time.

Creating any of these "to be helpful" pre-empts a decision the method routes to a human.

## 4. Wire the repo

Append to `.gitignore` (create it if absent):

```gitignore
# dbkit build output (derived — never source)
dbkit/generated/
# dbkit local work area (adoption ledger, inventories)
.scratch/
# local secrets (commit .env.example instead)
.env
```

Add to the repo's `CLAUDE.md` (create it if absent; if it exists, append without disturbing what's there):

```markdown
## Database schema (dbkit)

- Any schema work → read `docs/agents/database-schema.md` first, then the
  `README.md` of the folder where the work happens.
- The why behind a rule → `docs/agents/database-doctrine.md`.
- Golden rule: never finish a schema change with `python dbkit/tools/verify.py`
  failing (run from the repo root).
```

## 5. Prove it green

`python dbkit/tools/verify.py` from the repo root must pass on the virgin scaffold — empty pipeline steps report clean, and no tool invents a dialect. If it fails here, the installation is wrong; fix it before handing off.

## 6. Route the first decision

Setup gives structure; it decides nothing. Offer the next step:

- **Greenfield** (schema to be designed) → the `database-modeling` grill; its first theme settles the canonical dialect, which creates `dbkit/.sqlfluff`.
- **Brownfield** (existing database to govern) → the `database-adoption` skill; its probe records the source dialect and puts the canonical-dialect decision to me.
