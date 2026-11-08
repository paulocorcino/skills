# seeds/ — reference and development data

Data loaded into the database, split by purpose and lifecycle:

| Subfolder | What it is | Applied in |
|---|---|---|
| `reference/` | data that is **part of the domain** (e.g. list of countries, languages, statuses) | all environments |
| `dev/` | local test data | **never** in production |

## Rules

- A seed must be **idempotent** — running it twice does not duplicate or break anything.
- `reference/` is part of the schema contract; changing it is a domain change
  (document it in `docs/db-model/database.md`).
- `dev/` may reference `reference/`, never the other way around.
- **Effective-dated tables are append-only.** Rates, reference prices, thresholds —
  above all the parameters of a rule tagged **[protected]** — carry `valid_from` /
  `valid_to`; a changed value is a **new row**, and a version's value never changes —
  closing its open `valid_to` is the one edit an existing row receives.
  Their seed inserts the versions that are missing and leaves existing rows exactly
  as they are; a change to a protected rule's parameter goes through
  `docs/db-model/calc/README.md` first.

## Templates (idempotent)

Write seeds in the canonical dialect; the idempotency mechanism is the dialect's own
(`ON CONFLICT`, `MERGE`, `ON DUPLICATE KEY`, `INSERT … WHERE NOT EXISTS`).

A plain reference list — an existing row may be corrected in place:

```sql
-- reference/language.sql — languages supported by the catalog.
-- (PostgreSQL syntax shown; use the canonical dialect's upsert)
INSERT INTO language (language_id, name) VALUES
    (1, 'English'),
    (2, 'Portuguese')
ON CONFLICT (language_id) DO UPDATE SET name = EXCLUDED.name;
```

An effective-dated parameter — insert missing versions only, never update:

```sql
-- reference/royalty_rate.sql — rate versions; a new rate is a new row.
INSERT INTO royalty_rate (field_code, rate, valid_from, valid_to)
SELECT v.field_code, v.rate, v.valid_from, v.valid_to
FROM (VALUES
    ('FLD-01', 0.1000, DATE '2026-01-01', DATE '2026-07-01'),
    ('FLD-01', 0.0500, DATE '2026-07-01', NULL)
) AS v (field_code, rate, valid_from, valid_to)
WHERE NOT EXISTS (
    SELECT 1 FROM royalty_rate AS r
    WHERE r.field_code = v.field_code AND r.valid_from = v.valid_from
);
```
