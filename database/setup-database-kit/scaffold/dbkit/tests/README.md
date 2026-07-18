# tests/ — proof of behavior

Where the business rules in `dbkit/model/database.md` become executable checks. The proof
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
