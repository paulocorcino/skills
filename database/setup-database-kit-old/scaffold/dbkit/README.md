# dbkit/ — governable schema module (drop-in)

Self-contained schema method. Start here when dropping `dbkit/` into a new repo.
Per-folder instructions live in each subfolder's `README.md`.

The module travels with three companion files — copy them together with `dbkit/`:

- `docs/agents/database-schema.md` — the entry point: task → folder routing and the
  N1/N2/N3 mental model (folder READMEs point at it).
- `docs/agents/database-doctrine.md` — the *why*: principles P1–P7, dialect
  families/tiers, assumed risks.
- `.github/workflows/verify.yml` — CI backstop: runs `dbkit/tools/verify.py` on every
  push/PR, so the golden rule holds even when no instruction was read.

## Bootstrap: create `dbkit/.sqlfluff` (required, not generated)

`dbkit/.sqlfluff` is the **only** configuration file the tools read, and **no tool
recreates it** — `dbkit/tools/lint.py` only *reads* it. Without it, SQLFluff falls back
to defaults and the pipeline breaks (wrong dialect, `jinja` templater instead of
`raw`, lost rule exclusions). Create it once, per project, with **your canonical
dialect**.

## Steps

1. Pick the project's canonical dialect (the source-of-truth SQL dialect that
   `dbkit/schema/tables/` is written in): `mysql`, `postgres`, `tsql`, `sqlite`, …
2. Create `dbkit/.sqlfluff` from the template below with that `dialect`. This is the
   **single source** of the canonical dialect — the tools read it from here; there is
   no hardcoded default. Folder names still override the dialect per-dialect subfolders.
3. Keep `templater = raw` and `large_file_skip_byte_limit = 0` — the tools assume both.
4. `exclude_rules` — start empty; add a rule only with a one-line reason next to it
   (traceable to an ADR). The commented lines below are just examples.
5. `python dbkit/tools/verify.py` — must be green before you commit.

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
- Style is the linter's job: never argue SQL style in review, run `dbkit/tools/lint.py`.
```
