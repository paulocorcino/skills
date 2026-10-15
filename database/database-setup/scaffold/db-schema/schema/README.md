# schema/ — desired database state (SOURCE)

Schema declared in plain SQL. This is not history (that's `migrations/`); it is the
**final state** the database must have. Each subfolder has its own README.

| Subfolder | What lives here | Level |
|---|---|---|
| `tables/` | one `CREATE TABLE` per file, canonical dialect | N1/N2 |
| `overrides/<dialect>/` | explicit implementation when transpilation loses semantics | N2 |
| `native/<dialect>/` | procedural routines and support objects, one subfolder per kind (`functions/`, `procedures/`, `triggers/`, `views/`, and — where the dialect has the object class — `sequences/`, `synonyms/`, `types/`) | N3 |

## Rules that apply to the whole folder

- **One object per file**, filename = the object's **qualified name**: the bare name in
  the dialect's default schema (`dbo`, `public`, …), `<schema>.<name>` outside it
  (`fin.invoice.sql`) — so two schemas never share a file, and the tools read the
  same name from the DDL. A table's own `CREATE INDEX` statements are the one
  exception to one-object-per-file — they live in the table's file.
- **No `DELIMITER`/`GO`** — those are client commands; the build/lint adds them.
- Dialect is **per folder** (the linter picks the dialect from the folder).
- Run `python db-schema/tools/lint.py db-schema/schema/<file>` and fix until it passes.
- When done: `python db-schema/tools/verify.py` green.

Pick the right subfolder by the object's level (see `docs/agents/database-schema.md`).
