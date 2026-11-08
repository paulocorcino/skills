"""measure_tsql.py — cost measurement for a database audit, SQL Server edition.

Reads what the engine already records about its own cost and reports NUMBERS
ONLY: counts, times, reads, plan shapes. Row values, parameter values, and
literal-bearing query text never reach stdout or the JSON it writes — query
text is normalized (literals -> ?) before it leaves this process. That is the
point of the tool: an agent can audit cost without data entering its context.

Run from the repo root; connection from .env / environment (same variables as
the adoption extractor): DB_ODBC_DRIVER, DB_HOST, DB_PORT, DB_NAME, DB_USER,
DB_PASSWORD, DB_ENCRYPT (default yes), DB_TRUST_SERVER_CERTIFICATE (default no).
Outputs go to .scratch/audit/ (local working state).

Subcommands:
  sources     which cost sources this account can read (Query Store state and
              retention window, DMVs, plan cache, missing-index DMVs), with the
              permission each needs. Never fails on a denial — it reports it.
  top         the most expensive queries in the window: share of total CPU,
              executions, CPU / logical reads / duration per execution, average
              rows, memory used and tempdb per execution, plan count (a
              plan-regression hint), owning object, and the normalized text;
              from the DMVs also granted-vs-used memory and spill counts. Query Store when available (--days window), the
              plan-cache DMVs otherwise (window = since each plan was cached).
              Also: single-use ad-hoc plans (CPU spent compiling) and top waits.
  plan        estimated plan summary — the engine plans, nothing executes:
              --query-id N (latest Query Store plan) or --file q.sql (SHOWPLAN).
              Reports cost, estimated rows, costliest operators, scans, implicit
              conversions, missing-index suggestions. Parameter values compiled
              into the plan are never printed.
  indexes     missing-index suggestions (impact-scored) and nonclustered
              indexes with writes but no reads since the last restart.
  run         EXECUTES one SELECT and reports rows, server CPU, logical and
              physical reads, elapsed time — rows fetched and discarded. Guards:
              SELECT/WITH only (write keywords refused), inside a transaction
              that is always rolled back, and --confirm-execution "<where and
              why>" is mandatory (recorded): run it on a copy, or in production
              only with the user's authorization. --params-from-plan PLAN_ID
              binds the plan's compiled parameter values without printing them.

PORTING CONTRACT — SQL Server only on purpose; another engine gets a sibling
measure_<dialect>.py keeping: the five subcommands and their flags; the output
files .scratch/audit/{sources,top,indexes}.json, plan-*.json, run-*.json with
the same top-level keys; the numbers-only rule (normalize() before any text
leaves the process, never print row or parameter values); run's guards
(read-only statement check, rollback, mandatory confirmation). Engine layer to
rewrite: connect(), the source queries, plan retrieval and its parser.
"""
from __future__ import annotations

# CHANGELOG
#   1.1.0  top: memory used and tempdb per execution (Query Store), granted vs
#          used memory and spills (DMVs); --by memory|tempdb; oversized-grant
#          and spill lines in the summary.
#   1.0.0  sources / top / plan / indexes / run.

__version__ = "1.1.0"

import argparse
import json
import os
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.cwd()
OUT = REPO / ".scratch" / "audit"
NS = {"p": "http://schemas.microsoft.com/sqlserver/2004/07/showplan"}

# ---------------------------------------------------------------- plumbing


def connect(autocommit: bool = True):
    try:
        import pyodbc
        from dotenv import load_dotenv
    except ImportError as exc:
        sys.exit(f"missing dependency ({exc.name}) — pip install pyodbc python-dotenv")
    load_dotenv(REPO / ".env")
    missing = [v for v in ("DB_ODBC_DRIVER", "DB_HOST", "DB_PORT", "DB_NAME",
                           "DB_USER", "DB_PASSWORD") if not os.environ.get(v)]
    if missing:
        sys.exit(f"connection variables missing: {', '.join(missing)} (.env)")
    try:
        return pyodbc.connect(
            f"DRIVER={{{os.environ['DB_ODBC_DRIVER']}}};"
            f"SERVER={os.environ['DB_HOST']},{os.environ['DB_PORT']};"
            f"DATABASE={os.environ['DB_NAME']};"
            f"UID={os.environ['DB_USER']};PWD={os.environ['DB_PASSWORD']};"
            f"Encrypt={os.environ.get('DB_ENCRYPT', 'yes')};"
            f"TrustServerCertificate={os.environ.get('DB_TRUST_SERVER_CERTIFICATE', 'no')};",
            autocommit=autocommit, timeout=15)
    except pyodbc.Error as exc:
        sys.exit(f"connection failed: {str(exc)[:300]}")


def rows(cur, sql: str, *params) -> list[tuple]:
    cur.execute(sql, *params)
    return cur.fetchall()


def denied(exc: Exception) -> bool:
    return bool(re.search(r"\((229|262|297|300|916)\)|permission|denied", str(exc), re.I))


def save(name: str, data) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")
    return path


def normalize(sql: str | None, width: int = 0) -> str:
    """Literal-free shape of a statement: comments dropped, string / binary /
    numeric literals -> ?, IN lists collapsed, whitespace squeezed."""
    if not sql:
        return ""
    s = re.sub(r"--[^\n]*", " ", sql)
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"N?'(?:[^']|'')*'", "?", s)
    s = re.sub(r"(?<![\w@#$])0x[0-9A-Fa-f]+", "?", s)
    s = re.sub(r"(?<![\w@#$.\]])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w])", "?", s)
    s = re.sub(r"\(\s*\?(?:\s*,\s*\?)+\s*\)", "(?...)", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\((\w+)\(\?\)\)", r"(\1)", s)       # nvarchar(?) -> nvarchar
    s = re.sub(r"\b(n?varchar|n?char|varbinary|datetime2|decimal|numeric)\(\?(?:,\?)?\)", r"\1", s, flags=re.I)
    return s if not width or len(s) <= width else s[: width - 1] + "…"


def fmt(n, digits: int = 1) -> str:
    if n is None:
        return "-"
    return f"{n:,.{digits}f}" if isinstance(n, float) else f"{n:,}"

# ---------------------------------------------------------------- sources


def probe_source(cur, label: str, sql: str, needs: str) -> dict:
    try:
        rows(cur, sql)
        return {"source": label, "available": True}
    except Exception as exc:
        return {"source": label, "available": False, "needs": needs,
                "reason": "permission denied" if denied(exc) else str(exc)[:160]}


def cmd_sources(args) -> int:
    conn = connect()
    cur = conn.cursor()
    version = rows(cur, "SELECT CONVERT(NVARCHAR(128), SERVERPROPERTY('ProductVersion')), "
                        "CONVERT(NVARCHAR(128), SERVERPROPERTY('Edition')), DB_NAME()")[0]
    out = {"version": version[0], "edition": version[1], "database": version[2],
           "sources": []}
    try:
        qs = rows(cur, "SELECT actual_state_desc, stale_query_threshold_days, "
                       "max_storage_size_mb, current_storage_size_mb, query_capture_mode_desc "
                       "FROM sys.database_query_store_options")[0]
        window = rows(cur, "SELECT CONVERT(VARCHAR(33), MIN(start_time), 126), "
                           "CONVERT(VARCHAR(33), MAX(end_time), 126) FROM "
                           "sys.query_store_runtime_stats_interval")[0]
        out["sources"].append({
            "source": "Query Store", "available": qs[0] in ("READ_WRITE", "READ_ONLY"),
            "state": qs[0], "retention_days": qs[1], "capture_mode": qs[4],
            "storage_mb": f"{qs[3]}/{qs[2]}",
            "window": [str(window[0]), str(window[1])] if window[0] else None,
            "needs": "VIEW DATABASE STATE (2022: VIEW DATABASE PERFORMANCE STATE)"})
    except Exception as exc:
        out["sources"].append({"source": "Query Store", "available": False,
                               "needs": "VIEW DATABASE STATE",
                               "reason": "permission denied" if denied(exc) else str(exc)[:160]})
    out["sources"].append(probe_source(
        cur, "plan-cache DMVs (sys.dm_exec_query_stats)",
        "SELECT TOP (1) 1 FROM sys.dm_exec_query_stats",
        "VIEW SERVER STATE (2022: VIEW SERVER PERFORMANCE STATE)"))
    out["sources"].append(probe_source(
        cur, "wait stats (sys.dm_os_wait_stats)",
        "SELECT TOP (1) 1 FROM sys.dm_os_wait_stats", "VIEW SERVER STATE"))
    out["sources"].append(probe_source(
        cur, "missing-index DMVs", "SELECT TOP (1) 1 FROM sys.dm_db_missing_index_details",
        "VIEW SERVER STATE"))
    out["sources"].append(probe_source(
        cur, "estimated plans (SHOWPLAN)", "SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'SHOWPLAN')",
        "SHOWPLAN"))
    try:
        up = rows(cur, "SELECT sqlserver_start_time FROM sys.dm_os_sys_info")[0][0]
        out["server_started"] = str(up)
    except Exception:
        out["server_started"] = None
    try:
        showplan = rows(cur, "SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'SHOWPLAN')")[0][0]
        out["sources"][-1]["available"] = bool(showplan)
    except Exception:
        pass
    path = save("sources.json", out)
    print(f"SQL Server {out['version']} ({out['edition']}), database [{out['database']}]")
    for s in out["sources"]:
        flag = "yes" if s["available"] else "NO "
        extra = ""
        if s["source"] == "Query Store" and s.get("state"):
            extra = (f" — state {s['state']}, retention {s['retention_days']}d, "
                     f"window {s['window'][0][:16]} .. {s['window'][1][:16]}" if s.get("window")
                     else f" — state {s['state']}, no intervals captured yet")
        if not s["available"]:
            extra = (f" — needs {s['needs']}" if s.get("reason") in (None, "permission denied")
                     else f" — unreadable: {s['reason']}")
        print(f"  [{flag}] {s['source']}{extra}")
    if out.get("server_started"):
        print(f"  server started {out['server_started'][:19]} — plan-cache and wait "
              "numbers cover only the time since then")
    print(f"-> {path.relative_to(REPO)}")
    return 0

# ---------------------------------------------------------------- top

AUDIT_NOISE = re.compile(r"sys\.(query_store|dm_|database_query_store)|SHOWPLAN|"
                         r"HAS_PERMS_BY_NAME|SERVERPROPERTY|StatMan\(|plan_persist|oplsn_", re.I)

BENIGN_WAITS = {
    "SLEEP_TASK", "BROKER_TASK_STOP", "BROKER_TO_FLUSH", "SQLTRACE_BUFFER_FLUSH",
    "CLR_AUTO_EVENT", "CLR_MANUAL_EVENT", "LAZYWRITER_SLEEP", "SLEEP_SYSTEMTASK",
    "SLEEP_BPOOL_FLUSH", "BROKER_EVENTHANDLER", "XE_DISPATCHER_WAIT", "XE_TIMER_EVENT",
    "FT_IFTS_SCHEDULER_IDLE_WAIT", "LOGMGR_QUEUE", "CHECKPOINT_QUEUE",
    "REQUEST_FOR_DEADLOCK_SEARCH", "SP_SERVER_DIAGNOSTICS_SLEEP", "DIRTY_PAGE_POLL",
    "HADR_FILESTREAM_IOMGR_IOCOMPLETION", "QDS_PERSIST_TASK_MAIN_LOOP_SLEEP",
    "QDS_ASYNC_QUEUE", "QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP",
    "WAIT_XTP_OFFLINE_CKPT_NEW_LOG", "SOS_WORK_DISPATCHER", "PREEMPTIVE_XE_DISPATCHER",
    "WAITFOR", "BROKER_RECEIVE_WAITFOR", "ONDEMAND_TASK_QUEUE", "PWAIT_EXTENSIBILITY_CLEANUP_TASK",
    "SQLTRACE_INCREMENTAL_FLUSH_SLEEP", "WAIT_XTP_HOST_WAIT", "XE_LIVE_TARGET_TVF",
    "PARALLEL_REDO_DRAIN_WORKER", "PARALLEL_REDO_LOG_CACHE", "PARALLEL_REDO_TRAN_LIST",
    "PARALLEL_REDO_WORKER_SYNC", "PARALLEL_REDO_WORKER_WAIT_WORK", "VDI_CLIENT_OTHER",
    "DISPATCHER_QUEUE_SEMAPHORE", "STARTUP_DEPENDENCY_MANAGER", "SERVER_IDLE_CHECK",
    "KSOURCE_WAKEUP", "MEMORY_ALLOCATION_EXT", "PREEMPTIVE_OS_FLUSHFILEBUFFERS",
    "HADR_WORK_QUEUE", "HADR_CLUSAPI_CALL", "HADR_LOGCAPTURE_WAIT", "HADR_TIMER_TASK",
    "CXCONSUMER", "RESOURCE_QUEUE", "SNI_HTTP_ACCEPT", "WAIT_FOR_RESULTS",
}


def top_query_store(cur, days: int) -> list[dict]:
    # avg_tempdb_space_used exists from SQL Server 2017; older engines get 0
    sql = """
        SELECT q.query_id, OBJECT_NAME(q.object_id), qt.query_sql_text,
               SUM(rs.count_executions),
               SUM(rs.avg_cpu_time * rs.count_executions),
               SUM(rs.avg_logical_io_reads * rs.count_executions),
               SUM(rs.avg_duration * rs.count_executions),
               SUM(rs.avg_rowcount * rs.count_executions),
               COUNT(DISTINCT p.plan_id),
               MAX(rs.avg_duration), MIN(rs.avg_duration),
               SUM(rs.avg_query_max_used_memory * rs.count_executions),
               SUM(ISNULL(rs.avg_tempdb_space_used, 0) * rs.count_executions)
        FROM sys.query_store_runtime_stats AS rs
        JOIN sys.query_store_runtime_stats_interval AS i
          ON i.runtime_stats_interval_id = rs.runtime_stats_interval_id
        JOIN sys.query_store_plan AS p ON p.plan_id = rs.plan_id
        JOIN sys.query_store_query AS q ON q.query_id = p.query_id
        JOIN sys.query_store_query_text AS qt ON qt.query_text_id = q.query_text_id
        WHERE i.start_time >= DATEADD(day, -?, SYSUTCDATETIME())
        GROUP BY q.query_id, q.object_id, qt.query_sql_text
    """
    try:
        data = rows(cur, sql, days)
    except Exception as exc:
        if "avg_tempdb_space_used" not in str(exc):
            raise
        data = rows(cur, sql.replace("ISNULL(rs.avg_tempdb_space_used, 0)", "0"), days)
    out = []
    for qid, obj, text, execs, cpu, reads, dur, rws, plans, dmax, dmin, mem, tmp in data:
        if AUDIT_NOISE.search(text or ""):
            continue
        out.append({"id": f"qs:{qid}", "query_id": qid, "object": obj,
                    "executions": int(execs or 0), "cpu_ms": (cpu or 0) / 1000.0,
                    "logical_reads": float(reads or 0), "duration_ms": (dur or 0) / 1000.0,
                    "rows_total": float(rws or 0), "plans": int(plans or 0),
                    "duration_spread": (dmax / dmin) if dmin else None,
                    "memory_mb": float(mem or 0) * 8 / 1024, "tempdb_mb": float(tmp or 0) * 8 / 1024,
                    "grant_mb": None, "spills": None,
                    "text": normalize(text)})
    return out


def top_dmv(cur) -> list[dict]:
    # grant / spill columns exist from SQL Server 2016 SP2 / 2017; older get 0
    sql = """
        SELECT CONVERT(VARCHAR(18), qs.query_hash, 1),
               SUM(qs.execution_count), SUM(qs.total_worker_time),
               SUM(qs.total_logical_reads), SUM(qs.total_elapsed_time),
               SUM(qs.total_rows), COUNT(DISTINCT qs.plan_handle), MIN(qs.creation_time),
               MAX(OBJECT_NAME(st.objectid, st.dbid)),
               MAX(SUBSTRING(st.text, qs.statement_start_offset / 2 + 1,
                   ((CASE qs.statement_end_offset WHEN -1 THEN DATALENGTH(st.text)
                     ELSE qs.statement_end_offset END - qs.statement_start_offset) / 2) + 1)),
               SUM(qs.total_used_grant_kb), SUM(qs.total_grant_kb), SUM(qs.total_spills)
        FROM sys.dm_exec_query_stats AS qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
        WHERE st.dbid = DB_ID() OR st.dbid IS NULL
        GROUP BY qs.query_hash
    """
    try:
        data = rows(cur, sql)
    except Exception as exc:
        if not any(c in str(exc) for c in ("total_used_grant_kb", "total_grant_kb", "total_spills")):
            raise
        data = rows(cur, sql.replace("SUM(qs.total_used_grant_kb), SUM(qs.total_grant_kb), "
                                     "SUM(qs.total_spills)", "0, 0, 0"))
    out = []
    for qh, execs, cpu, reads, dur, rws, plans, since, obj, text, used, granted, spills in data:
        if AUDIT_NOISE.search(text or ""):
            continue
        out.append({"id": f"hash:{qh}", "object": obj, "executions": int(execs or 0),
                    "cpu_ms": (cpu or 0) / 1000.0, "logical_reads": float(reads or 0),
                    "duration_ms": (dur or 0) / 1000.0, "rows_total": float(rws or 0),
                    "plans": int(plans or 0), "cached_since": str(since),
                    "memory_mb": float(used or 0) / 1024, "tempdb_mb": 0.0,
                    "grant_mb": float(granted or 0) / 1024, "spills": int(spills or 0),
                    "text": normalize(text)})
    return out


def group_by_shape(queries: list[dict]) -> list[dict]:
    """Merge entries sharing one normalized shape and owner: the engine splits
    a statement by parameter length, and literal-built SQL arrives as one entry
    per literal. `variants` counts the merged entries — a high count on one
    shape is the signature of SQL built without parameters."""
    groups: dict[tuple, dict] = {}
    for q in queries:
        k = (q["text"], q.get("object"))
        g = groups.get(k)
        if g is None:
            g = groups[k] = {**q, "ids": [q["id"]], "variants": 1}
            continue
        g["variants"] += 1
        if len(g["ids"]) < 5:
            g["ids"].append(q["id"])
        for f in ("executions", "cpu_ms", "logical_reads", "duration_ms", "rows_total", "plans",
                  "memory_mb", "tempdb_mb"):
            g[f] += q[f]
        for f in ("grant_mb", "spills"):
            if q.get(f) is not None:
                g[f] = (g.get(f) or 0) + q[f]
        if q.get("duration_spread") and (g.get("duration_spread") or 0) < q["duration_spread"]:
            g["duration_spread"] = q["duration_spread"]
    return list(groups.values())


def cmd_top(args) -> int:
    conn = connect()
    cur = conn.cursor()
    source = None
    queries: list[dict] = []
    if args.source in ("auto", "querystore"):
        try:
            state = rows(cur, "SELECT actual_state_desc FROM sys.database_query_store_options")[0][0]
            if state in ("READ_WRITE", "READ_ONLY"):
                queries = top_query_store(cur, args.days)
                source = f"Query Store, last {args.days} day(s)"
        except Exception as exc:
            if args.source == "querystore":
                sys.exit(f"Query Store unreadable: {'permission denied' if denied(exc) else exc}")
    if source is None:
        try:
            queries = top_dmv(cur)
            source = "plan-cache DMVs (since each plan was cached)"
        except Exception as exc:
            sys.exit("no readable cost source — run `sources` "
                     f"({'permission denied' if denied(exc) else str(exc)[:160]})")
    queries = group_by_shape(queries)
    key = {"cpu": "cpu_ms", "reads": "logical_reads", "duration": "duration_ms",
           "executions": "executions", "memory": "memory_mb", "tempdb": "tempdb_mb"}[args.by]
    total_cpu = sum(q["cpu_ms"] for q in queries) or 1.0
    total_reads = sum(q["logical_reads"] for q in queries) or 1.0
    for q in queries:
        q["cpu_share_pct"] = 100.0 * q["cpu_ms"] / total_cpu
        q["reads_share_pct"] = 100.0 * q["logical_reads"] / total_reads
        n = q["executions"] or 1
        q["cpu_ms_per_exec"] = q["cpu_ms"] / n
        q["reads_per_exec"] = q["logical_reads"] / n
        q["duration_ms_per_exec"] = q["duration_ms"] / n
        q["rows_per_exec"] = q["rows_total"] / n
        q["memory_mb_per_exec"] = q["memory_mb"] / n
        q["tempdb_mb_per_exec"] = q["tempdb_mb"] / n
        if q.get("grant_mb"):
            q["grant_used_pct"] = round(100.0 * q["memory_mb"] / q["grant_mb"], 1)
    queries.sort(key=lambda q: q[key], reverse=True)
    ranked = queries[: args.limit]

    adhoc = None
    try:
        a = rows(cur, "SELECT COUNT(*), SUM(CAST(size_in_bytes AS BIGINT)) FROM "
                      "sys.dm_exec_cached_plans WHERE objtype = 'Adhoc' AND usecounts = 1")[0]
        t = rows(cur, "SELECT COUNT(*) FROM sys.dm_exec_cached_plans")[0][0]
        adhoc = {"single_use_adhoc_plans": int(a[0]), "single_use_mb": round((a[1] or 0) / 1048576, 1),
                 "all_cached_plans": int(t)}
    except Exception:
        pass
    waits = []
    try:
        for wt, ms, cnt in rows(cur, "SELECT TOP (40) wait_type, wait_time_ms, waiting_tasks_count "
                                     "FROM sys.dm_os_wait_stats WHERE wait_time_ms > 0 "
                                     "ORDER BY wait_time_ms DESC"):
            if wt not in BENIGN_WAITS and not wt.startswith(("SLEEP_", "QDS_", "XE_", "BROKER_")):
                waits.append({"wait_type": wt, "wait_ms": int(ms), "tasks": int(cnt)})
        waits = waits[:8]
    except Exception:
        pass

    out = {"source": source, "by": args.by, "total_cpu_ms": total_cpu,
           "queries_seen": len(queries), "top": ranked, "adhoc_plans": adhoc, "waits": waits}
    path = save("top.json", out)
    print(f"top {len(ranked)} of {len(queries)} queries by {args.by} — {source}")
    print(f"{'#':>2} {'id':<21} {'cpu%':>6} {'reads%':>6} {'execs':>9} {'cpu ms/ex':>10} "
          f"{'reads/ex':>10} {'ms/ex':>9} {'rows/ex':>9} {'memMB/ex':>8} {'tmpMB/ex':>8} "
          f"{'plans':>5} {'var':>5}  object / shape")
    for i, q in enumerate(ranked, 1):
        print(f"{i:>2} {q['id']:<21} {q['cpu_share_pct']:>6.1f} {q['reads_share_pct']:>6.1f} "
              f"{q['executions']:>9,} {q['cpu_ms_per_exec']:>10.2f} {q['reads_per_exec']:>10.1f} "
              f"{q['duration_ms_per_exec']:>9.2f} {q['rows_per_exec']:>9.1f} "
              f"{q['memory_mb_per_exec']:>8.2f} {q['tempdb_mb_per_exec']:>8.2f} {q['plans']:>5} "
              f"{q['variants']:>5}  "
              f"{(q['object'] + ': ') if q['object'] else ''}{normalize(q['text'], 90)}")
    if adhoc:
        print(f"plan cache: {adhoc['single_use_adhoc_plans']:,} single-use ad-hoc plans "
              f"({adhoc['single_use_mb']} MB) of {adhoc['all_cached_plans']:,} — each one CPU "
              "spent compiling a statement used once")
    wasteful = [q for q in ranked if q.get("grant_used_pct") is not None and q["grant_mb"] >= 1
                and q["grant_used_pct"] < 25]
    for q in wasteful[:5]:
        print(f"memory grant: {q['id']} used {q['grant_used_pct']}% of {q['grant_mb']:.1f} MB granted "
              "— an oversized grant holds memory other queries wait for")
    spilled = [q for q in ranked if q.get("spills")]
    for q in spilled[:5]:
        print(f"spills: {q['id']} spilled {q['spills']:,} time(s) to tempdb")
    if waits:
        print("top waits since server start: " + ", ".join(
            f"{w['wait_type']} {w['wait_ms']:,} ms" for w in waits[:5]))
    print(f"-> {path.relative_to(REPO)}")
    return 0

# ---------------------------------------------------------------- plan


def summarize_plan(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    stmts = []
    for st in root.iterfind(".//p:StmtSimple", NS):
        ops = []
        for rel in st.iterfind(".//p:RelOp", NS):
            sub = float(rel.get("EstimatedTotalSubtreeCost", 0) or 0)
            children = sum(float(c.get("EstimatedTotalSubtreeCost", 0) or 0)
                           for c in rel.findall("./*/p:RelOp", NS))
            obj = rel.find("./*/p:Object", NS)
            ops.append({"op": rel.get("PhysicalOp"), "self_cost": max(sub - children, 0.0),
                        "est_rows": float(rel.get("EstimateRows", 0) or 0),
                        "table_rows": float(rel.get("TableCardinality", 0) or 0) or None,
                        "object": ".".join(filter(None, [
                            (obj.get("Table") if obj is not None else None),
                            (obj.get("Index") if obj is not None else None)])) or None})
        total = float(st.get("StatementSubTreeCost", 0) or 0) or 1.0
        ops.sort(key=lambda o: o["self_cost"], reverse=True)
        for o in ops:
            o["cost_pct"] = round(100.0 * o["self_cost"] / total, 1)
        warnings = []
        for conv in st.iterfind(".//p:Warnings/p:PlanAffectingConvert", NS):
            warnings.append(f"implicit conversion ({conv.get('ConvertIssue')}): "
                            f"{normalize(conv.get('Expression'), 140)}")
        for w in st.iterfind(".//p:Warnings", NS):
            for attr in ("NoJoinPredicate", "UnmatchedIndexes"):
                if w.get(attr) == "true":
                    warnings.append(attr)
            if w.find("p:ColumnsWithNoStatistics", NS) is not None:
                warnings.append("columns with no statistics")
        missing = []
        for grp in st.iterfind(".//p:MissingIndexes/p:MissingIndexGroup", NS):
            for mi in grp.iterfind("p:MissingIndex", NS):
                cols = {u: [c.get("Name") for c in cg.iterfind("p:Column", NS)]
                        for cg in mi.iterfind("p:ColumnGroup", NS)
                        for u in [cg.get("Usage")]}
                missing.append({"impact_pct": float(grp.get("Impact", 0) or 0),
                                "table": f"{mi.get('Schema')}.{mi.get('Table')}",
                                "equality": cols.get("EQUALITY", []),
                                "inequality": cols.get("INEQUALITY", []),
                                "include": cols.get("INCLUDE", [])})
        scans = [o for o in ops if o["op"] in ("Table Scan", "Clustered Index Scan", "Index Scan")]
        params = [c.get("Column") for c in st.iterfind(".//p:ParameterList/p:ColumnReference", NS)]
        stmts.append({"statement": normalize(st.get("StatementText"), 200),
                      "est_cost": round(total, 4), "est_rows": float(st.get("StatementEstRows", 0) or 0),
                      "top_operators": ops[:6], "scans": scans, "warnings": warnings,
                      "missing_indexes": missing, "parameters": params})
    return {"statements": stmts}


def cmd_plan(args) -> int:
    conn = connect()
    cur = conn.cursor()
    plans: list[str] = []
    label = ""
    if args.query_id is not None:
        r = rows(cur, "SELECT TOP (1) plan_id, query_plan FROM sys.query_store_plan "
                      "WHERE query_id = ? ORDER BY last_execution_time DESC", args.query_id)
        if not r:
            sys.exit(f"no Query Store plan for query_id {args.query_id}")
        label = f"qs{args.query_id}-plan{r[0][0]}"
        plans = [r[0][1]]
    elif args.file:
        sql = Path(args.file).read_text(encoding="utf-8")
        label = Path(args.file).stem
        cur.execute("SET SHOWPLAN_XML ON")
        try:
            cur.execute(sql)
            while True:
                try:
                    plans += [row[0] for row in cur.fetchall()]
                except Exception:
                    pass
                if not cur.nextset():
                    break
        finally:
            cur.execute("SET SHOWPLAN_XML OFF")
    else:
        sys.exit("plan needs --query-id N or --file q.sql")
    summary = {"label": label, "statements": []}
    for xml_text in plans:
        if xml_text:
            summary["statements"] += summarize_plan(xml_text)["statements"]
    path = save(f"plan-{label}.json", summary)
    for st in summary["statements"]:
        print(f"statement: {st['statement']}")
        print(f"  estimated cost {st['est_cost']}, estimated rows {fmt(st['est_rows'])}"
              + (f", parameters {', '.join(st['parameters'])} (values not shown)" if st["parameters"] else ""))
        for o in st["top_operators"][:4]:
            print(f"  {o['cost_pct']:>5.1f}%  {o['op']}" + (f" on {o['object']}" if o["object"] else "")
                  + f" — est rows {fmt(o['est_rows'])}"
                  + (f" of {fmt(o['table_rows'])}" if o["table_rows"] else ""))
        for w in st["warnings"]:
            print(f"  WARNING {w}")
        for m in st["missing_indexes"]:
            print(f"  MISSING INDEX impact {m['impact_pct']:.0f}% on {m['table']}: "
                  f"eq {m['equality']} ineq {m['inequality']} include {m['include']}")
    print(f"-> {path.relative_to(REPO)}")
    return 0

# ---------------------------------------------------------------- indexes


def cmd_indexes(args) -> int:
    conn = connect()
    cur = conn.cursor()
    out = {"missing": [], "unused": []}
    try:
        for tbl, eq, ineq, inc, seeks, cost, impact in rows(cur, """
            SELECT d.statement, d.equality_columns, d.inequality_columns, d.included_columns,
                   s.user_seeks, s.avg_total_user_cost, s.avg_user_impact
            FROM sys.dm_db_missing_index_details AS d
            JOIN sys.dm_db_missing_index_groups AS g ON g.index_handle = d.index_handle
            JOIN sys.dm_db_missing_index_group_stats AS s ON s.group_handle = g.index_group_handle
            WHERE d.database_id = DB_ID()"""):
            out["missing"].append({"table": tbl, "equality": eq, "inequality": ineq,
                                   "include": inc, "seeks": int(seeks),
                                   "score": round(seeks * cost * impact, 1),
                                   "impact_pct": float(impact)})
        out["missing"].sort(key=lambda m: m["score"], reverse=True)
    except Exception as exc:
        out["missing_error"] = "permission denied (VIEW SERVER STATE)" if denied(exc) else str(exc)[:160]
    try:
        for sch, tbl, idx, writes in rows(cur, """
            SELECT s.name, t.name, i.name, ISNULL(u.user_updates, 0)
            FROM sys.indexes AS i
            JOIN sys.tables AS t ON t.object_id = i.object_id
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            LEFT JOIN sys.dm_db_index_usage_stats AS u
              ON u.object_id = i.object_id AND u.index_id = i.index_id AND u.database_id = DB_ID()
            WHERE i.type_desc = 'NONCLUSTERED' AND i.is_primary_key = 0
              AND i.is_unique_constraint = 0
              AND ISNULL(u.user_seeks, 0) + ISNULL(u.user_scans, 0) + ISNULL(u.user_lookups, 0) = 0"""):
            out["unused"].append({"index": f"{sch}.{tbl}.{idx}", "writes": int(writes)})
    except Exception as exc:
        out["unused_error"] = "permission denied (VIEW SERVER STATE)" if denied(exc) else str(exc)[:160]
    path = save("indexes.json", out)
    print(f"missing-index suggestions: {len(out['missing'])} (impact-scored; a suggestion, not a verdict)")
    for m in out["missing"][:10]:
        print(f"  score {m['score']:>12,.1f}  seeks {m['seeks']:>7,}  {m['table']}  "
              f"eq {m['equality']} ineq {m['inequality']} include {m['include']}")
    print(f"nonclustered indexes never read since restart: {len(out['unused'])}")
    for u in out["unused"][:10]:
        print(f"  {u['index']} — {u['writes']:,} writes maintained for no reads")
    for k in ("missing_error", "unused_error"):
        if k in out:
            print(f"  {k}: {out[k]}")
    print(f"-> {path.relative_to(REPO)}")
    return 0

# ---------------------------------------------------------------- run

WRITE_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|EXECUTE|INTO|DROP|ALTER|CREATE|TRUNCATE|GRANT|"
    r"DENY|REVOKE|DBCC|BACKUP|RESTORE|SHUTDOWN|KILL|WAITFOR|OPENROWSET|OPENQUERY|"
    r"OPENDATASOURCE|BULK|xp_\w+|sp_\w+)\b", re.I)


def compiled_params(cur, plan_id: int) -> list[tuple[str, str, str]]:
    r = rows(cur, "SELECT query_plan FROM sys.query_store_plan WHERE plan_id = ?", plan_id)
    if not r:
        sys.exit(f"no Query Store plan {plan_id}")
    root = ET.fromstring(r[0][0])
    out = []
    for c in root.iterfind(".//p:ParameterList/p:ColumnReference", NS):
        value = c.get("ParameterCompiledValue")
        if value is not None:
            if value.startswith("(") and value.endswith(")"):
                value = value[1:-1]
            out.append((c.get("Column"), c.get("ParameterDataType"), value))
    return out


def cmd_run(args) -> int:
    if not args.confirm_execution or not args.confirm_execution.strip():
        sys.exit('run executes the statement: --confirm-execution "<where and why>" is required '
                 "(a copy of the database, or production with the user's authorization)")
    sql = Path(args.file).read_text(encoding="utf-8")
    body = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    body = re.sub(r"N?'(?:[^']|'')*'", "''", body).strip()
    if not re.match(r"(?is)^(SELECT|WITH)\b", body):
        sys.exit("run measures one SELECT (or WITH … SELECT) — nothing else")
    bad = WRITE_WORDS.search(body)
    if bad:
        sys.exit(f"refused: {bad.group(0).upper()} is not allowed in a measured statement")
    conn = connect(autocommit=False)
    cur = conn.cursor()
    prelude = ""
    bound = 0
    if args.params_from_plan is not None:
        decls = [(n, t, v) for n, t, v in compiled_params(cur, args.params_from_plan)
                 if re.search(re.escape(n) + r"\b", sql)]
        prelude = "".join(f"DECLARE {n} {t} = {v};\n" for n, t, v in decls)
        bound = len(decls)
    stats_sql = ("SELECT cpu_time, logical_reads, reads FROM sys.dm_exec_sessions "
                 "WHERE session_id = @@SPID")
    runs = []
    try:
        for _ in range(max(args.repeat, 1)):
            before = rows(cur, stats_sql)[0]
            t0 = time.perf_counter()
            cur.execute(prelude + sql)
            n = 0
            while True:
                try:
                    while True:
                        chunk = cur.fetchmany(5000)
                        if not chunk:
                            break
                        n += len(chunk)
                except Exception:
                    pass
                if not cur.nextset():
                    break
            elapsed = (time.perf_counter() - t0) * 1000.0
            after = rows(cur, stats_sql)[0]
            runs.append({"rows": n, "elapsed_ms": round(elapsed, 2),
                         "cpu_ms": int(after[0] - before[0]),
                         "logical_reads": int(after[1] - before[1]),
                         "physical_reads": int(after[2] - before[2])})
    finally:
        conn.rollback()
        conn.close()
    warm = runs[1:] or runs
    out = {"file": args.file, "statement": normalize(sql, 200),
           "confirmed": args.confirm_execution, "parameters_bound": bound,
           "at": datetime.now(timezone.utc).isoformat(), "runs": runs,
           "first_run": runs[0],
           "warm_median": {k: statistics.median(r[k] for r in warm)
                           for k in ("elapsed_ms", "cpu_ms", "logical_reads", "physical_reads")}}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = save(f"run-{Path(args.file).stem}-{stamp}.json", out)
    print(f"measured: {out['statement']}")
    if bound:
        print(f"  {bound} parameter(s) bound from plan {args.params_from_plan} (values not shown)")
    f, w = out["first_run"], out["warm_median"]
    print(f"  rows {f['rows']:,} (fetched and discarded) — transaction rolled back")
    print(f"  first run: {f['elapsed_ms']:.1f} ms elapsed, {f['cpu_ms']} ms CPU, "
          f"{f['logical_reads']:,} logical / {f['physical_reads']:,} physical reads")
    if len(runs) > 1:
        print(f"  warm median of {len(warm)}: {w['elapsed_ms']:.1f} ms elapsed, {w['cpu_ms']} ms CPU, "
              f"{w['logical_reads']:,} logical / {w['physical_reads']:,} physical reads")
    print(f"-> {path.relative_to(REPO)}")
    return 0

# ---------------------------------------------------------------- cli


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sources")
    top = sub.add_parser("top")
    top.add_argument("--by", choices=["cpu", "reads", "duration", "executions", "memory", "tempdb"],
                     default="cpu")
    top.add_argument("--limit", type=int, default=15)
    top.add_argument("--days", type=int, default=7)
    top.add_argument("--source", choices=["auto", "querystore", "dmv"], default="auto")
    plan = sub.add_parser("plan")
    plan.add_argument("--query-id", type=int)
    plan.add_argument("--file")
    sub.add_parser("indexes")
    run = sub.add_parser("run")
    run.add_argument("--file", required=True)
    run.add_argument("--confirm-execution", metavar="WHERE_AND_WHY")
    run.add_argument("--params-from-plan", type=int, metavar="PLAN_ID")
    run.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    return {"sources": cmd_sources, "top": cmd_top, "plan": cmd_plan,
            "indexes": cmd_indexes, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
