# schema/native/ — N3 routines (procedural, per dialect)

Objects that **do not transpile** across DBMSs: functions, procedures, triggers and
complex views, RLS, partitioning, full-text, GIS, events. Because they are
DBMS-specific, they live in a subfolder **per dialect**, and equivalence across
dialects is guaranteed by **tests against a real database**, never by automatic
translation.

```
native/
└── <dialect>/          # e.g. mysql/, postgres/
    ├── functions/      # scalar, inline and table-valued
    ├── procedures/
    ├── triggers/
    ├── views/
    ├── sequences/      # support objects: engine-specific settings (cache, cycle)
    ├── synonyms/       #   → present only when the dialect has the object class
    └── types/          #   (user-defined/table types)
```

## Rules

- **One object per file**, **no `DELIMITER`** — the file is one statement; the build
  adds the delimiter when applying it to the database.
- Start with a `--` comment of 1–3 lines: what it does and which business rule it serves.
  **Exception — adopted legacy routines:** they enter **verbatim** from the source
  database, without a header comment. Never invent one: the comment is added when the
  routine's behavior is characterized (its ticket in `model/database.md` closes), and
  editing the file breaks verbatim traceability until then.
- Register the routine in `dbkit/model/database.md` ("Routines" section: what it
  guarantees, when it fires, what it returns).
- Linting here is **best-effort** (SQLFluff does not parse all procedural SQL —
  sqlfluff#901). An "N3 gap" is expected; fix only legitimate style warnings.
- The real proof is a test in `dbkit/tests/` (dbverify).
- Routine characteristics (`DETERMINISTIC`, `READS SQL DATA` vs `MODIFIES SQL DATA`,
  `SQL SECURITY`) are part of the contract — declare them explicitly.
- Prefer explicit `JOIN ... ON` over implicit joins (`FROM a, b`) — same plan, better
  readability and linting.

## Object types (templates)

Templates below are MySQL-flavored (the canonical pilot dialect); adapt the syntax to
each target dialect.

**Function** — returns a scalar, serves a business rule.

```sql
-- <name>: <what it computes and which rule it serves, 1-3 lines>.
CREATE FUNCTION <name>(<param> <type>)
    RETURNS <type>
    READS SQL DATA
    DETERMINISTIC
BEGIN
    DECLARE v_result <type>;
    SELECT <expr> INTO v_result FROM <table> WHERE <column> = <param>;
    RETURN v_result;
END
```

**Procedure** — performs an operation (multi-row query, maintenance, report). Mark
params `IN`/`OUT`/`INOUT`; use `MODIFIES SQL DATA` if it writes.

```sql
-- <name>: <what it does and which rule/report it serves, 1-3 lines>.
CREATE PROCEDURE <name>(IN p_<param> <type>, OUT p_<out> <type>)
    READS SQL DATA
BEGIN
    SELECT <columns> FROM <table> WHERE <column> = p_<param>;
END
```

**Trigger** — maintains an invariant automatically. Naming `<event>_<table>` (e.g.
`ins_film`); pick `BEFORE`/`AFTER` + event to match the invariant.

```sql
-- <name>: <invariant it maintains, and on which event, 1-3 lines>.
CREATE TRIGGER <name>
    AFTER INSERT ON <table>
    FOR EACH ROW
BEGIN
    INSERT INTO <derived_table> (<col>) VALUES (NEW.<col>);
END
```

**View** — simple views can be N1; those using DBMS-specific features are N3. Always
explicit `JOIN ... ON`; alias output columns for a stable contract.

```sql
-- <name>: <what the view exposes and for which consumer, 1-3 lines>.
CREATE VIEW <name> AS
SELECT <a>.<column> AS <alias>
FROM <table_a> AS <a>
INNER JOIN <table_b> AS <b> ON <a>.<fk>_id = <b>.<pk>_id;
```
