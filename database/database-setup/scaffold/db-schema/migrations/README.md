# migrations/ — executable, immutable history

Versioned step-by-step that takes an existing database from the previous state to the
state declared in `schema/`. Unlike `schema/` (desired state), this is **history**:
once merged, a migration is **never** edited.

## How it works

- **Data** migrations (backfill, fixes) are handwritten.
- **Schema** migrations: the target design generates them by *diff* against `schema/`
  (tooling **not built yet**). Until then, write them by hand: the migration must take
  the previous state exactly to the state declared in `schema/`, and `dbverify` (not
  built yet) is what will prove both tell the same truth.
- Name: `NNNN_<verb>_<object>.sql` (e.g. `0007_add_email_customer.sql`).

## Safety checklist (❌ → ✅) — expand/contract

Inspired by Strong Migrations. The automatable ones become a tool check.

- ❌ RENAME a column/table in one step → ✅ expand/contract: (1) create new,
  (2) backfill + dual-write, (3) drop old (next release)
- ❌ `ADD COLUMN NOT NULL` without `DEFAULT` on a populated table → ✅ default or 3 phases
- ❌ change a type in place → ✅ new column + backfill + swap
- ❌ DROP in the same release that removed its use → ✅ DROP only in the next release
- ❌ blocking `CREATE INDEX` on a large table (Postgres) → ✅ `CONCURRENTLY`
- ❌ edit an already-merged migration → ✅ a new corrective migration

Every migration must be **reversible** (have a clear path back).

An engine with a limited `ALTER TABLE` (SQLite cannot add or drop a constraint in place)
changes a table by **rebuilding** it, in one transaction: create the new table, copy the
rows, drop the old one, rename the new one, recreate its indexes and triggers — with
foreign-key enforcement suspended during the swap and `PRAGMA foreign_key_check` clean
before commit.

## Protected rules and effective-dated data

- A migration touching an object or a parameter of a rule tagged **[protected]** lands
  in the same change as the new memo version and the re-validated examples, through the
  change sequence in `docs/db-model/calc/README.md`.
- A changed rate, price, or threshold in an effective-dated table is a **data**
  migration that appends the new version with its `valid_from` and closes the previous
  version's open `valid_to` — the one edit an existing row receives; its value stays as
  it was, so past periods keep computing with the value they were computed under.

## Template

Write migrations in the canonical dialect.

```sql
-- 0007_add_email_customer.sql
-- Expand: adds an optional column; backfill in a separate migration.
ALTER TABLE customer
    ADD COLUMN email VARCHAR(<domain_size>) NULL;

-- rollback:
-- ALTER TABLE customer DROP COLUMN email;
```
