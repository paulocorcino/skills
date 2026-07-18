# schema/ — desired database state (SOURCE)

Schema declared in plain SQL. This is not history (that's `migrations/`); it is the
**final state** the database must have. Each subfolder has its own README.

| Subfolder | What lives here | Level |
|---|---|---|
| `tables/` | one `CREATE TABLE` per file, canonical dialect | N1/N2 |
| `overrides/<dialect>/` | explicit implementation when transpilation loses semantics | N2 |
| `native/<dialect>/` | procedural routines and support objects, one subfolder per kind (`functions/`, `procedures/`, `triggers/`, `views/`, and — where the dialect has the object class — `sequences/`, `synonyms/`, `types/`) | N3 |

## Rules that apply to the whole folder

- **One object per file**, filename = object name (a table's own `CREATE INDEX`
  statements are the one exception — they live in the table's file).
- **No `DELIMITER`/`GO`** — those are client commands; the build/lint adds them.
- Dialect is **per folder** (the linter picks the dialect from the folder).
- Run `python dbkit/tools/lint.py dbkit/schema/<file>` and fix until it passes.
- When done: `python dbkit/tools/verify.py` green.

Pick the right subfolder by the object's level (see `docs/agents/database-schema.md`).
