# Adopting behind an ORM

The disclosed branch of [`SKILL.md`](SKILL.md), reached when an application maps the database through an ORM: its schema or entity definitions, and a migrations folder it generates or applies. The steps run as written; this file adds what each one gains.

## The mode — before step 3

The repo's agent instructions file declares the mode (**source** or **mirror**, doctrine P1 in `docs/agents/database-doctrine.md`). Undeclared → put the decision to the user as the `database-setup` preflight frames it, and record it as setup does: the mode line in the agent instructions file and an ADR. Record in the ledger the ORM, its schema path, and its migrations path.

In **mirror mode** the adoption carves the first mirror:

- **Which database.** Carve from a private database the ORM's migrations built at the repo's head: reproducible, and what the repo claims. Then, with the user's read-only credential, reconcile the deployed database against that baseline: every finding is a divergence between the deployed state and the migrations, put to the user, and a deployed object no migration creates is drift from outside the repo.
- **The ORM's bookkeeping.** The ORM's migration-tracking table (`__drizzle_migrations`, `_prisma_migrations`, `django_migrations`, `alembic_version`, `__EFMigrationsHistory`, `flyway_schema_history`, `SequelizeMeta`, …) is tooling, not domain: propose its `exceptions.json` entry, `excluded`, with that reason, so `discover` never ranks it.

## The hand-written layer — step 4

What the ORM's schema cannot express (routines, triggers, row-level security policies, grants, storage settings) lives only in hand-written migrations, so the live catalog is its only complete record. Hold the extractor to the **behavior-bearing attributes** [`PORTING.md`](PORTING.md) step 2 lists: an attribute the repo copy does not read is an extraction hole. Fix it in the repo copy, or put it to the user as `BLOCKED`.

## The mapping — a third fact source, steps 5 and 6

The ORM's mapping is enumerable like the catalog: every entity, property, relation, and enum. Dump it through the ORM's own metadata API (Drizzle's `getTableConfig`, Prisma's DMMF, Django's `_meta`, SQLAlchemy's `MetaData`, EF Core's model) into a scratch script, so the diff is a script's output rather than a reading of the source. Diff it against the carved DDL, and record each mismatch as a gap:

- an entity or property with no column; a column no property maps (another writer's, or dead)
- nullability, type, length, precision, or default that differs; a default the application computes is invisible to every other writer
- a relation the mapping declares with no foreign key behind it (some ORMs' relation helpers create no constraint): feed it to `census --candidates`
- an enum stored by ordinal position: reordering its values in code changes the meaning of every stored row (a type smell)
- a uniqueness rule, cascade, or validation the ORM enforces in the application with no constraint behind it: every other writer bypasses it (an invariant candidate)
- a soft-delete filter the ORM applies globally: uniqueness rules and readers that query the table directly still see the deleted rows

In mirror mode, the mapping and the catalog both come from the same migrations, so a mismatch is the repo contradicting itself: record it as a ticket candidate too.

Step 6 starts from the mapping. The **table anchor** goes from table to entity to the entity's call sites. The **value anchor** follows the property the code assigns before a save, wherever the column name never appears. Sweep the statements that bypass the mapping by their own names: raw-SQL helpers (`sql.raw`, `$queryRawUnsafe`, `FromSqlRaw`, `.raw()`, `text()`) with input interpolated, and bulk updates that skip the ORM's validations and hooks. Under *unguarded decisions*, add the entity loaded, changed, and saved with no version column guarding the save: a contested-quantity candidate.
