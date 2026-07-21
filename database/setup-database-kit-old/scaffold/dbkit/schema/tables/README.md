# schema/tables/ — tables (desired state, SOURCE)

One file per table: `<table_name>.sql`, containing **a single** `CREATE TABLE` in the
canonical dialect, optionally followed by that table's own `CREATE INDEX` statements
(non-constraint indexes travel with their table — never in a separate file). This is
the source that generates diagrams and transpiles to other dialects.

## Steps to create/alter a table

1. Write/edit `dbkit/schema/tables/<name>.sql` — a single `CREATE TABLE`.
2. `python dbkit/tools/lint.py dbkit/schema/tables/<name>.sql` — fix until it passes.
3. `python dbkit/tools/erdgen.py` — refresh the diagrams.
4. Document the table in `dbkit/model/database.md` (concept, invariants, relations).
5. If it materializes a domain decision → create an ADR in `docs/adr/`.
6. Write ≥1 test in `dbkit/tests/` proving the core invariant.
7. `python dbkit/tools/verify.py`. **Never finish with verify failing.**
8. Altering a table already in a database → generate a migration in `dbkit/migrations/`.

## Conventions

- Explicit PK; name your constraints (FK, UNIQUE) — anonymous constraints break migrations.
- FK with an explicit action (`RESTRICT`/`SET NULL`/`CASCADE`) — decide, don't rely on default.
- No magic dialect translation: a dialect-sensitive type/feature (ENUM, JSON,
  autoincrement…) is N2 → it needs an override (see `../overrides/`).

> **Adopted legacy tables:** the conventions and checklist below govern **new**
> tables. Tables carved from an existing database keep their legacy names, types
> and quirks **verbatim** — never "fix" them in place; every deviation is recorded
> in `model/database.md` and changes only through a refactoring ticket plus a
> migration.

## Checklist (❌ → ✅)

- ❌ plural table name → ✅ singular (`customer`, not `customers`)
- ❌ PK with no declared strategy → ✅ recorded decision (int/uuid + why)
- ❌ column without `NOT NULL` and no reason → ✅ nullable only with a reason in database.md
- ❌ FK without an index → ✅ every FK indexed
- ❌ `VARCHAR(255)` by habit → ✅ size derived from the domain
- ❌ implicit soft-delete/enum/status → ✅ invariant as a `CHECK` or a domain table
- ❌ reserved word as identifier in a new table → ✅ avoid keywords

## Template

Write it in the **canonical dialect** (`dbkit/.sqlfluff`); the placeholders below are
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
