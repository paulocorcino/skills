# tools/ — the method's mechanical validation

Python scripts that do the verification (style, transpilability, coherence) so that
prose instructions only handle judgment. Tools are **deliberately dumb**: verification
and orchestration, never semantic translation. They fail loud, with an actionable
message. Run them from the **repo root**.

| Tool | What it does | Fails when |
|---|---|---|
| `verify.py` | orchestrates the pipeline (lint + erd-check + buildsql + doccheck) | any step fails |
| `lint.py` | SQLFluff; dialect per folder; slices `DELIMITER`/`GO` | strict error in `tables/` |
| `erdgen.py` | generates `docs/db-model/erd.mmd` + `docs/db-model/schema.dbml` from `tables/` | `--check`: committed diagram diverges |
| `buildsql.py` | assembles `generated/<dialect>/schema.sql` in FK dependency order; overrides replace, never magic translation | lossy transpile without an override (P4) |
| `doccheck.py` | presence coherence between `schema/` and `model/` docs | table/native object missing from model docs |
| `extract_<dialect>.py` | **living** adoption tool — engine-specific by nature, one per adopted source engine (versioned references ship with the `database-adoption` skill, which ports one when no reference covers the engine; porting contract in the docstring): `probe`/`inventory`/`carve`/`reconcile`/`census`/`discover`, read-only; writes the versioned drift baseline to `db-schema/baseline/` | probe: write-capable account; reconcile: source drift or missing carved file |

```
python db-schema/tools/verify.py        # before finishing any change
python db-schema/tools/lint.py [path]   # validate a file/folder
python db-schema/tools/erdgen.py        # regenerate diagrams (--check for CI)
python db-schema/tools/buildsql.py      # build generated/<dialect>/schema.sql
python db-schema/tools/doccheck.py      # schema ↔ model docs coherence
python db-schema/tools/extract_<dialect>.py …  # adoption: probe | inventory | carve | reconcile | census | discover
```

## Rules

- These tools are the source of truth for style/structure — don't reimplement the
  rules in prose; adjust the config (`db-schema/.sqlfluff`) if you need to change style.
- `native/` is linted best-effort (sqlfluff#901) — an "N3 gap" is expected, not an error.
- Don't put business rules in a tool; behavior is proven in `db-schema/tests/`.
- Dependencies are pinned in `_deps.py` (hardcoded, self-contained) and checked by
  `verify.py` — the module ships no repo-root requirements file. `verify` prints the
  exact `pip install` command when a package is missing or mismatched.

## Not yet built

The full pipeline adds `levelcheck`, `dbverify` and the behavioral `pytest` suite.
These are **designed but not implemented** — `verify.py` lists them as `not-built` in
its summary. When one is built, wire it into `verify.py`.
