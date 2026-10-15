# Cost sources

The disclosed reference for step 1 of [`SKILL.md`](SKILL.md): where each engine records its own cost, what reading it needs, and the window the numbers cover. The measurement tool reads these; this file is what a port starts from when no reference in `scripts/` covers the engine. Examples, not the list — for an engine absent here, find the equivalent in its own documentation.

Three cautions apply to every engine:

- **Query text can carry data** — a literal email, document number, or name written into the SQL. Normalize before it leaves the tool: literals → `?`.
- **Windows differ.** Cumulative views reset on restart or when a plan leaves the cache; persisted stores keep days. Always say which window a number covers.
- **Measuring by executing is load.** Estimated plans never execute; an actual measurement runs the statement — on a copy, or in production with the user's authorization.

## SQL Server

| Source | Shows | Needs | Window |
|---|---|---|---|
| **Query Store** (`sys.query_store_*`) | per query and plan: executions, CPU, logical reads, duration, rows; plan history and regressions | `VIEW DATABASE STATE` (2022: `VIEW DATABASE PERFORMANCE STATE`); must be enabled per database | retention days (`stale_query_threshold_days`) |
| Plan-cache DMVs (`sys.dm_exec_query_stats`, `sys.dm_exec_cached_plans`) | the same totals for cached plans; single-use ad-hoc plans (CPU spent compiling) | `VIEW SERVER STATE` (2022: `VIEW SERVER PERFORMANCE STATE`) | since each plan was cached |
| `sys.dm_os_wait_stats` | what the server waits on (I/O, locks, CPU pressure) | `VIEW SERVER STATE` | since the server started |
| Missing-index DMVs, `sys.dm_db_index_usage_stats` | suggested indexes with an impact score; indexes maintained but never read | `VIEW SERVER STATE` | since the server started |
| Estimated plan (`SET SHOWPLAN_XML ON`) | the plan without executing | `SHOWPLAN` | — |
| `system_health` Extended Events session | recent deadlock graphs | `VIEW SERVER STATE` | ring buffer, recent only |

Turning Query Store on (`ALTER DATABASE … SET QUERY_STORE = ON`) is a change the database owner makes — recommend it when it is off; it is the cheapest way to have evidence next time.

## PostgreSQL

| Source | Shows | Needs | Window |
|---|---|---|---|
| `pg_stat_statements` | per normalized statement: calls, total and mean time, rows, shared blocks hit / read, temp blocks written (spills) | the extension in `shared_preload_libraries`; role `pg_read_all_stats` | since `pg_stat_statements_reset()` or restart |
| `pg_stat_user_tables` / `pg_stat_user_indexes` | sequential vs index scans per table; indexes never scanned; dead vs live tuples and last autovacuum (bloat) | `pg_read_all_stats` | since the statistics reset |
| `pg_stat_activity`, `pg_locks` | what sessions wait on now | `pg_read_all_stats` | now |
| `EXPLAIN` | the estimated plan, no execution | `SELECT` on the tables | — |
| `EXPLAIN (ANALYZE, BUFFERS)` | actual rows, time, buffers — **executes**: wrap it in `BEGIN READ ONLY … ROLLBACK` | same | — |
| `log_min_duration_statement`, `auto_explain` | slow statements in the server log | access to the log | the log's retention |

## MySQL / MariaDB

| Source | Shows | Needs | Window |
|---|---|---|---|
| `performance_schema.events_statements_summary_by_digest` | per digest: executions, total latency, rows examined vs sent, no-index-used counts | `SELECT` on `performance_schema` | since restart or truncation |
| `sys` schema views (`statement_analysis`, `schema_unused_indexes`) | the same, pre-digested | `SELECT` on `sys` | same |
| `EXPLAIN` / `EXPLAIN ANALYZE` (8.0.18+) | estimated plan / actual — **`ANALYZE` executes** | `SELECT` | — |
| slow query log | slow statements | access to the log | the log's retention |

## Others

Oracle records cost in `V$SQL` and, historically, in AWR / ASH — **AWR and ASH require the Diagnostics Pack license**; ask before reading them. Analytical engines (Snowflake, BigQuery, Databricks) expose a query history with bytes scanned and credits — cost is money there, measured per query.

## Porting the measurement tool

A new engine's `measure_<dialect>.py` keeps the reference's porting contract — the five subcommands, the output files, the numbers-only rule, and `run`'s guards — and rewrites the engine layer against the sources above. Build it by trial and error against the live database: `sources` first (it must report denials, never fail on them), then `top`, `plan`, `indexes`, and `run` last.
