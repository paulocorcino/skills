# tests/ — proof of behavior

Where the business rules in `docs/db-model/database.md` become executable checks. The proof
that an N3 routine or an invariant works is the **test against a real database**
(dbverify + ephemeral Docker), not the linter.

> ⚠️ The runner (pytest wiring, the `db` fixture, dbverify) is **not built yet**.
> Write the tests now anyway, following the convention below: they are the executable
> spec the runner will pick up. Not being able to run them today is expected, not an
> error.

## What to test

- **Invariants**: every business rule in `database.md` has at least one test.
- **N3 routines**: functions/procedures/triggers proven by real execution.
- **Portability**: the same tests run on each Tier 1 dialect (MySQL, Postgres).

## Convention (Arrange–Act–Assert)

```python
def test_item_unavailable_with_open_rental(db):
    # Arrange: an open rental (return_date NULL) for item 1
    db.execute("INSERT INTO rental (...) VALUES (...)")

    # Act
    available = db.scalar("SELECT inventory_in_stock(1)")

    # Assert
    assert available == 0
```

One test = one invariant. The name describes the rule, not the implementation.

## Protected rules

A rule tagged **[protected]** has its cases in `docs/db-model/calc/<RULE-ID>.examples.yaml`
— the single copy; its test is parametrised over that file and holds no expected value
of its own (format and change sequence in `docs/db-model/calc/README.md`).

- A case with `validated_by` set is a hard assertion; a case without it is skipped as
  *awaiting validation*, so the gap shows in every run.
- A failing protected case means the code is wrong. Its expected value changes only
  through the change sequence, with the approver's sign-off recorded in the case.
- A case that states a concurrent load runs as real simultaneous sessions against a
  real database — a sequential test passes whether or not the race is handled.
- A protected rule implemented in application code is tested in the application's
  suite, reading the same examples file.
