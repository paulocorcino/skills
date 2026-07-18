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

## Template

```sql
-- 0007_add_email_customer.sql
-- Expand: adds an optional column; backfill in a separate migration.
ALTER TABLE customer
    ADD COLUMN email VARCHAR(255) NULL AFTER last_name;

-- rollback:
-- ALTER TABLE customer DROP COLUMN email;
```
