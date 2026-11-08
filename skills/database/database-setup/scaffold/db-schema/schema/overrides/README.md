# schema/overrides/ — explicit N2 implementations per dialect

When an object in `schema/tables/` uses something that **does not transpile cleanly**
across dialects (N2), automatic transpilation is forbidden: you declare the correct
implementation for each dialect here, in a file with the **same name as the object**.
The build **fails** while an override is missing for a target dialect — semantic loss
is always an explicit decision, never magic translation (principle P4).

```
overrides/
└── <dialect>/          # e.g. mysql/, postgres/
    └── <object>.sql    # same filename as in tables/
```

## When to create an override

`levelcheck.py` (not built yet) will classify each table. If it
flags **N2**, create the override for each target dialect. Typical candidates: ENUM, SET, JSON, UUID,
autoincrement/identity, timestamp with timezone, computed column, partial index,
collation, sequence, UPSERT.

## Rules

- Filename = **same name** as the object in `../tables/`. Whatever is here replaces
  automatic transpilation to that dialect in the build.
- Keep the **same contract** as the other versions: same logical columns, same business
  semantics — only the dialect-specific syntax changes.
- Comment at the top **why** it is N2 (the feature that does not transpile).
- Every target dialect needs its own override; otherwise the build fails.

## Template

The template is MySQL-flavored; adapt the syntax to each target dialect.

```sql
-- <object>: MySQL override — N2 reason: <specific feature, e.g. native ENUM>.
CREATE TABLE <object> (
    <object>_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    status       ENUM('active','inactive') NOT NULL DEFAULT 'active',
    PRIMARY KEY (<object>_id)
);
```
