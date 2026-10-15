# Common problems

The closed checklist for steps 2–4 of [`SKILL.md`](SKILL.md): the problems that cost the most, most often. Each row names its default severity and how to find it; the evidence adjusts the severity (step 4). **Correctness** rows are swept across all the code; the rest across the hot code first.

## Severity rules

- **High** — a measured share of ≥ 20% of CPU or reads in the window, or any correctness row.
- **Medium** — a measured share of 5–20%, or a structural problem on a hot path.
- **Low** — under 5%, hygiene, or a problem on cold code.
- A speculative performance finding is never High. Report the thresholds used.
- **Reads far above rows returned** is the general signal behind most rows below: a statement that examines thousands of rows per execution to return a handful is worth a plan, whatever its name turns out to be.

## Correctness — swept across all the code

| Problem | Default | Static signal | Live signal | Typical change |
|---|---|---|---|---|
| **SQL built by concatenating input** | High | string formatting or concatenation into a statement (`f"... {x}"`, `+ id +`) | many single-use ad-hoc plans with the same shape | parameters — also removes the injection risk (security, not only cost) |
| **A dirty read deciding a write** | High | `NOLOCK` / `READ UNCOMMITTED` followed by an `UPDATE` / `INSERT` | negative or impossible values counted by an aggregate | the guarantee in a named constraint; committed reads for decisions |
| **Read-then-update in separate statements** | High | a `SELECT` of a quantity, a condition in code or SQL, then an `UPDATE` of it | lost updates, oversell counts | a conditional single-statement update guarded by a constraint |
| **A value in the wrong type** | High | money or a regulated quantity in `FLOAT` / `REAL` / `DOUBLE`; dates or numbers stored as text | totals that miss by cents; text dates sorting wrong (`'10/02'` before `'9/02'`); implicit conversions | exact decimal (integers in the smallest unit where the engine has none, e.g. SQLite), a date type, a numeric type — a migration with backfill |
| **`NOT IN` over a subquery that can return `NULL`** | High | `NOT IN (SELECT col …)` where `col` is nullable | — | `NOT EXISTS` — a single `NULL` makes `NOT IN` return no rows, silently |
| **A constraint declared but not enforced** | High | SQLite connections opened without `PRAGMA foreign_keys = ON` (off by default, per connection); SQL Server constraints added `WITH NOCHECK`, or marked `NOT FOR REPLICATION` on a copy that also takes local writes; PostgreSQL triggers and foreign keys on a logical-replication subscriber that takes local writes; MySQL tables on an engine that ignores foreign keys (MyISAM) | `PRAGMA foreign_key_check` rows; untrusted constraints (`is_not_trusted`); `is_not_for_replication`; orphans counted by the census | clean the violations, then enforce: the pragma in every connection, `WITH CHECK CHECK CONSTRAINT`, a transactional engine |
| **A protected rule without its guard** | High | a `[protected]` rule whose memo, examples, or header comment is missing | — | the change sequence in `docs/db-model/calc/README.md` |

## Cost — hot code first

| Problem | Default | Static signal | Live signal | Typical change |
|---|---|---|---|---|
| **N+1** | Medium | a query inside a loop over another query's rows; ORM lazy loading in a loop | one cheap statement with a huge execution count | one set-based query, or eager loading |
| **Predicate that defeats an index** | Medium | a function on an indexed column in `WHERE` (`YEAR(col)`, `UPPER(col)`, `col + 0`) | a scan where a seek fits; reads far above rows returned | a range predicate (`col >= start AND col < next`), a computed indexed column |
| **Leading wildcard search** | Medium | `LIKE '%x%'` or `LIKE '%x'` on a hot path — a prefix `LIKE 'x%'` uses the index and is fine | a scan on the searched table; reads grow with the table, not the result | full-text search (or trigram indexes where the engine has them), a reversed-value index for suffix search, or a search service when the volume demands it |
| **Catch-all filter** | Medium | optional filters written as `(@p IS NULL OR col = @p)` — search screens | one plan serving every filter combination; scans; wide duration spread | build the predicate from the filters actually supplied (parameterized), or a per-execution recompile |
| **Deep `OFFSET` pagination** | Medium | `OFFSET n` with `n` growing with the page number | reads per execution growing with the page | keyset pagination (`WHERE key > last_seen ORDER BY key`) |
| **Implicit conversion** | Medium | a parameter or variable typed differently from the column (`nvarchar` vs `varchar`) | plan warning `PlanAffectingConvert`; a scan on an indexed column | match the parameter type to the column |
| **FK without an index** | Medium | a foreign-key column with no index leading on it | scans on the child table in joins and deletes | an index on the FK column — weighed against write cost |
| **Key lookups** | Medium | a frequent query reading columns its index does not carry | `Key Lookup` / `RID Lookup` among the costliest operators of the plan | add the columns as included columns of the index the query already seeks — weighed against write cost |
| **Missing index on a hot predicate** | Medium | — | missing-index suggestion with a high score, confirmed by the costly statement's plan | an index — the suggestion is a lead, never a verdict: check overlap with existing indexes and write cost |
| **Unbounded query** | Medium | a list or export with no `TOP` / `LIMIT` / pagination | high rows per execution | pagination or a bounded window |
| **Single-use plans (compile CPU)** | Medium | ad-hoc literals instead of parameters | single-use ad-hoc plans a large share of the cache | parameters; at the database level, forced parameterization or "optimize for ad hoc workloads" — a DBA decision |
| **Plan instability** | Medium | — | several plans for one query with a wide duration spread | a stable plan (parameter-sensitive fixes, statistics, a hint as last resort) |
| **Spills and oversized memory grants** | Medium | large sorts and hashes (`ORDER BY` / `GROUP BY` / `DISTINCT` over big sets), often from bad estimates | spill warnings in actual plans; temp space or memory grant far above what the query uses (Query Store memory columns, `temp_blks_written` in `pg_stat_statements`) | better estimates (statistics, sargable predicates), an index that delivers the order, a smaller set before the sort |
| **Stale statistics** | Medium | — | estimated rows far from actual rows in the plan | statistics maintenance — a DBA decision |
| **Row-by-row processing** | Medium | cursors, `WHILE` loops over rows, scalar functions called per row in a `SELECT` | high CPU per execution for few rows | set-based rewrite |
| **Long transactions, blocking, deadlocks** | Medium | a transaction held open across a remote call, a user wait, or a long loop; tables touched in different orders by different paths | lock waits (`LCK_M_*`) among the top waits; deadlock graphs in the engine's health session | short transactions; one fixed table order per routine (the Consistency theme's lock-order rule) — High when deadlocks are measured |
| **Expensive aggregation repeated** | Medium | the same aggregate recomputed on every read (dashboards, reports) | a heavy aggregate statement with many executions | precompute (materialized view, summary table) with its staleness decided — the Derivation theme |
| **Bloat (MVCC engines, e.g. PostgreSQL)** | Medium | tables updated or deleted heavily | dead tuples a large share of live ones; autovacuum far behind; reads growing while rows stay flat | autovacuum tuned per table — a DBA decision; `pg_repack` over `VACUUM FULL`, which locks |
| **Connection churn** | Medium | a connection opened per query or per request, no pool | logins per second high; connection count near the limit | a connection pool in the application or a pooler in front of the database |
| **`SELECT *` on a hot path** | Low | `SELECT *` in a frequently executed statement | reads above what the columns need; no covering index possible | name the columns |
| **Index maintained but never read, or duplicated** | Low | two indexes whose leading columns repeat each other | writes counted, no seeks / scans / lookups since restart | drop it — after a full business cycle confirms it stays unused, or keep the wider of two overlapping indexes |
