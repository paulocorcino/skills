# seeds/ — reference and development data

Data loaded into the database, split by purpose and lifecycle:

| Subfolder | What it is | Applied in |
|---|---|---|
| `reference/` | data that is **part of the domain** (e.g. list of countries, languages, statuses) | all environments |
| `dev/` | local test data | **never** in production |

## Rules

- A seed must be **idempotent** — running it twice does not duplicate or break anything.
- `reference/` is part of the schema contract; changing it is a domain change
  (document it in `dbkit/model/database.md`).
- `dev/` may reference `reference/`, never the other way around.

## Template (idempotent)

```sql
-- reference/language.sql — languages supported by the catalog.
INSERT INTO language (language_id, name) VALUES
    (1, 'English'),
    (2, 'Portuguese')
ON DUPLICATE KEY UPDATE name = VALUES(name);
```
