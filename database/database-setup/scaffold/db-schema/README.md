# db-schema/ — governable schema module (drop-in)

Drop-in schema method. Start here when dropping `db-schema/` into a new repo.
Per-folder instructions live in each subfolder's `README.md`.

This folder holds the **DDL and the tooling**. The domain documentation is not here —
it lives in `docs/db-model/`, with the rest of the project's prose. `tools/_paths.py`
declares where, and is the one path to adjust in a monorepo.

The module travels with four companion files — copy them together with `db-schema/`:

- `docs/db-model/README.md` — the model docs' skeleton and growth contract; the model
  itself is grown from decisions or evidence, never templated.
- `docs/agents/database-schema.md` — the entry point: task → folder routing and the
  N1/N2/N3 mental model (folder READMEs point at it).
- `docs/agents/database-doctrine.md` — the *why*: principles P1–P9, dialect
  families/tiers, assumed risks.
- `.github/workflows/verify.yml` — CI backstop: runs `db-schema/tools/verify.py` on every
  push/PR, so the golden rule holds even when no instruction was read.

## Bootstrap: create `db-schema/.sqlfluff` (required, not generated)

`db-schema/.sqlfluff` is the **only** configuration file the tools read, and **no tool
recreates it** — `db-schema/tools/lint.py` only *reads* it. Without it, SQLFluff falls back
to defaults and the pipeline breaks (wrong dialect, `jinja` templater instead of
`raw`, lost rule exclusions). Create it once, per project, with **your canonical
dialect**.

## Steps

1. Pick the project's canonical dialect (the source-of-truth SQL dialect that
   `db-schema/schema/tables/` is written in): `mysql`, `postgres`, `tsql`, `sqlite`, …
2. Create `db-schema/.sqlfluff` from the template below with that `dialect`. This is the
   **single source** of the canonical dialect — the tools read it from here; there is
   no hardcoded default. Folder names still override the dialect per-dialect subfolders.
3. Keep `templater = raw` and `large_file_skip_byte_limit = 0` — the tools assume both.
4. `exclude_rules` — start empty; add a rule only with a one-line reason next to it
   (traceable to an ADR). The commented lines below are just examples.
5. `python db-schema/tools/verify.py` — must be green before you commit.

## Template

```ini
[sqlfluff]
dialect = <mysql|postgres|tsql|sqlite|...>
templater = raw
large_file_skip_byte_limit = 0
# Add exclusions only with a reason, linking an ADR when there is one. Examples:
# LT05: long line — irrelevant for generated/reviewed DDL in a diff
# RF04: keywords used as identifiers — only if a legacy schema forces it
exclude_rules =

[sqlfluff:indentation]
tab_space_size = 4
```

## Notes

- Per-dialect subfolders (`schema/native/<dialect>/`, `schema/overrides/<dialect>/`)
  override the dialect by folder name — this file only sets the **canonical** default.
- Style is the linter's job: never argue SQL style in review, run `db-schema/tools/lint.py`.
```
