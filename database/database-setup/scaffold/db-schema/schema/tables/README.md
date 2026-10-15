# schema/tables/ — tables (desired state, SOURCE)

One file per table: `<table_name>.sql` — `<schema>.<table_name>.sql` outside the dialect's
default schema (see `../README.md`) — containing **a single** `CREATE TABLE` in the
canonical dialect, optionally followed by that table's own `CREATE INDEX` statements
(non-constraint indexes travel with their table — never in a separate file). This is
the source that generates diagrams and transpiles to other dialects.

## Steps to create/alter a table

1. Write/edit `db-schema/schema/tables/<name>.sql` — a single `CREATE TABLE`.
2. `python db-schema/tools/lint.py db-schema/schema/tables/<name>.sql` — fix until it passes.
3. `python db-schema/tools/erdgen.py` — refresh the diagrams.
4. Document the table in `docs/db-model/database.md` (concept, invariants, relations).
5. If it materializes a domain decision → create an ADR in `docs/adr/`.
6. Write ≥1 test in `db-schema/tests/` proving the core invariant.
7. `python db-schema/tools/verify.py` — finish only when it is green.
8. Altering a table already in a database → generate a migration in `db-schema/migrations/`.

## Conventions

- Explicit PK; name your constraints (FK, UNIQUE) — anonymous constraints break migrations.
- FK with an explicit action (`RESTRICT`/`SET NULL`/`CASCADE`) — decide, don't rely on default.
- No magic dialect translation: a dialect-sensitive type/feature (ENUM, JSON,
  autoincrement…) is N2 → it needs an override (see `../overrides/`).

> **Adopted legacy tables:** the conventions and checklist below govern **new**
> tables. Tables carved from an existing database keep their legacy names, types
> and quirks **verbatim** — never "fix" them in place; every deviation is recorded
> in `docs/db-model/database.md` and changes only through a refactoring ticket plus a
> migration.

## Checklist (❌ → ✅)

- ❌ plural table name → ✅ singular (`customer`, not `customers`)
- ❌ PK with no declared strategy → ✅ recorded decision (int/uuid + why)
- ❌ column without `NOT NULL` and no reason → ✅ nullable only with a reason in database.md
- ❌ FK without an index → ✅ every FK indexed
- ❌ `updated_at` with only `DEFAULT now()` (fires on insert alone) → ✅ maintained on every update by a named trigger or by the one writer that owns the table
- ❌ `VARCHAR(255)` by habit → ✅ size derived from the domain
- ❌ implicit soft-delete/enum/status → ✅ invariant as a named `CHECK`/`UNIQUE`/FK constraint or a domain table — the guarantee lives in the schema, never in a locking hint (doctrine P8)
- ❌ money or a regulated quantity in binary floating point (`FLOAT`, `REAL`, `DOUBLE`) → ✅ exact decimal with a scale derived from the domain — integers in the smallest unit (cents) where the engine has no exact decimal (SQLite stores `DECIMAL` as floating point)
- ❌ date-time with no stated zone → ✅ the project's date-time convention (zone-aware type, or UTC by rule) recorded in the model docs
- ❌ reserved word as identifier in a new table → ✅ avoid keywords

## Template

Write it in the **canonical dialect** (`db-schema/.sqlfluff`); the placeholders below are
dialect-neutral. Note that an auto-generated PK (autoincrement/identity/sequence) is
**N2** — using one means an override per target dialect (see `../overrides/`).

```sql
-- <table>: <what a row represents, one line>.
CREATE TABLE <table> (
    <table>_id    <pk_type> NOT NULL,           -- PK strategy is a recorded decision
    <column>      VARCHAR(<domain_size>) NOT NULL,
    <fk>_id       <pk_type> NOT NULL,
    created_at    <timestamp_type> NOT NULL,
    PRIMARY KEY (<table>_id),
    CONSTRAINT uq_<table>_<column> UNIQUE (<column>),
    CONSTRAINT fk_<table>_<fk> FOREIGN KEY (<fk>_id)
        REFERENCES <other_table> (<other_table>_id) ON DELETE RESTRICT
);
```
