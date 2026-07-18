#!/usr/bin/env python
"""lint.py — validate every versioned .sql with SQLFluff.

Method rules (docs/proposta-metodo.md):
- Dialect inferred from the folder (schema/native/<dialect>/, schema/overrides/<dialect>/);
  outside those, the project's canonical dialect is used.
- Files are sliced by DELIMITER (MySQL) / GO (T-SQL) BEFORE linting —
  those are client commands, not SQL.
- Paths under schema/native/ are BEST-EFFORT: parse errors on procedural
  constructs are a known SQLFluff gap (sqlfluff#901) and do not fail the
  build — N3 routines are proven by execution against a real database
  (dbverify).
- Every other path is STRICT: any violation fails.

Usage: python tools/lint.py [paths...]   (default: schema/ and dbkit/)
Output: per-file report; exit 1 on any strict failure.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlfluff.core import FluffConfig, Linter

from _dialect import canonical_dialect

ROOT = Path(__file__).resolve().parents[1]  # dbkit/
DEFAULT_PATHS = ["schema", "migrations", "seeds"]
# folders whose name defines the dialect of their contents
DIALECT_DIRS = {
    "mysql": "mysql",
    "mariadb": "mariadb",
    "postgres": "postgres",
    "sqlserver": "tsql",
    "tsql": "tsql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "oracle": "oracle",
    "clickhouse": "clickhouse",
    "hive": "hive",
    "sparksql": "sparksql",
    "databricks": "databricks",
}

_DELIMITER_RE = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
_GO_RE = re.compile(r"(?im)^\s*GO\s*$")


def _rel(path: Path) -> Path:
    """Path relative to dbkit/ when possible (for inference and display)."""
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def dialect_for(path: Path) -> str:
    for part in path.parts:
        if part.lower() in DIALECT_DIRS:
            return DIALECT_DIRS[part.lower()]
    return canonical_dialect()


def is_best_effort(path: Path) -> bool:
    return "native" in [p.lower() for p in path.parts]


def split_statements(sql: str, dialect: str) -> list[str]:
    """Slice by the client's batch separator. No separator → whole file."""
    if dialect == "tsql" and _GO_RE.search(sql):
        return [b.strip() for b in _GO_RE.split(sql) if b.strip()]
    if _DELIMITER_RE.search(sql):
        stmts: list[str] = []
        delim = ";"
        buf = ""
        for line in sql.splitlines(keepends=True):
            m = re.match(r"^\s*DELIMITER\s+(\S+)\s*$", line, re.IGNORECASE)
            if m:
                if buf.strip():
                    stmts.append(buf.strip())
                buf = ""
                delim = m.group(1)
                continue
            buf += line
            while delim in buf:
                idx = buf.find(delim)
                piece = buf[:idx].strip()
                if piece:
                    stmts.append(piece)
                buf = buf[idx + len(delim):]
        if buf.strip():
            stmts.append(buf.strip())
        return stmts
    return [sql]


def lint_file(path: Path, linters: dict[str, Linter]) -> tuple[int, int, list[str]]:
    """Return (strict_violations, best_effort_violations, messages)."""
    dialect = dialect_for(_rel(path))
    if dialect not in linters:
        cfg = FluffConfig.from_path(
            str(ROOT),
            overrides={"dialect": dialect, "large_file_skip_byte_limit": 0},
        )
        linters[dialect] = Linter(config=cfg)
    linter = linters[dialect]

    sql = path.read_text(encoding="utf-8", errors="replace")
    best_effort = is_best_effort(_rel(path))

    strict_count = 0
    soft_count = 0
    msgs: list[str] = []
    for stmt in split_statements(sql, dialect):
        result = linter.lint_string(stmt)
        for v in result.violations:
            code = v.rule_code() if callable(getattr(v, "rule_code", None)) else "PRS"
            desc = f"[{code}] L{v.line_no}: {v.description}"
            is_parse = code in ("PRS", "LXR", "????")
            if best_effort and is_parse:
                soft_count += 1
                msgs.append(f"  (N3 gap) {desc}")
            elif best_effort:
                soft_count += 1
                msgs.append(f"  (warn)   {desc}")
            else:
                strict_count += 1
                msgs.append(f"  ERROR    {desc}")
    return strict_count, soft_count, msgs


def resolve_target(arg: str) -> Path:
    """Accept a path relative to cwd, to the repo root, or to dbkit/."""
    for candidate in (Path(arg), ROOT.parent / arg, ROOT / arg):
        if candidate.exists():
            return candidate.resolve()
    return (ROOT / arg).resolve()


def main(argv: list[str]) -> int:
    targets = [resolve_target(p) for p in argv] if argv else [ROOT / p for p in DEFAULT_PATHS]
    files: list[Path] = []
    for t in targets:
        if t.is_file():
            files.append(t)
        elif t.is_dir():
            files.extend(sorted(t.rglob("*.sql")))

    if not files:
        print("No .sql files found.")
        return 0

    linters: dict[str, Linter] = {}
    total_strict = 0
    total_soft = 0
    for f in files:
        strict, soft, msgs = lint_file(f, linters)
        total_strict += strict
        total_soft += soft
        rel = _rel(f)
        if strict:
            print(f"FAIL   {rel}")
        elif soft:
            print(f"WARN   {rel}")
        else:
            print(f"OK     {rel}")
        for m in msgs:
            print(m)

    print(f"\n{len(files)} files | strict errors: {total_strict} | best-effort warnings: {total_soft}")
    return 1 if total_strict else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
