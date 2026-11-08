"""Go language runner — real implementation (Stage 3).

Tools: go (test + coverage via -coverprofile + go tool cover -func),
       golangci-lint (lint, --out-format json),
       gocyclo (cyclomatic complexity per file),
       jscpd (duplication).

Contract: accepts --root and --output; writes schema-valid JSON to --output.
Missing tools are not errors; they are recorded in tools_missing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LANGUAGE = "go"
REQUIRED_TOOLS = ["go", "golangci-lint", "gocyclo", "jscpd"]


def detect_tools() -> tuple[list[str], list[str]]:
    used, missing = [], []
    for t in REQUIRED_TOOLS:
        (used if shutil.which(t) else missing).append(t)
    return sorted(used), sorted(missing)


def _run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run a subprocess; never raises on non-zero exit."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# go test — coverage
# ---------------------------------------------------------------------------

def run_go_coverage(root: str) -> dict:
    """Return {"line_pct": float|null, "branch_pct": float|null}.

    Go's coverage tooling exposes statement (line-equivalent) coverage only;
    branch coverage is not available natively, so branch_pct is always null.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cov_out = os.path.join(tmp, "coverage.out")
        result = _run(
            ["go", "test", "./...", f"-coverprofile={cov_out}", "-covermode=atomic"],
            cwd=root,
        )
        if not os.path.exists(cov_out):
            return {"line_pct": None, "branch_pct": None}

        func_result = _run(["go", "tool", "cover", "-func", cov_out], cwd=root)
        # Last line: "total: (statements)   NN.N%"
        for line in reversed(func_result.stdout.splitlines()):
            m = re.search(r"(\d+\.\d+)%", line)
            if m:
                return {"line_pct": round(float(m.group(1)), 2), "branch_pct": None}
    return {"line_pct": None, "branch_pct": None}


# ---------------------------------------------------------------------------
# golangci-lint — lint violations
# ---------------------------------------------------------------------------

def run_golangci_lint(root: str) -> dict:
    """Return {"errors": int, "warnings": int, "info": int, "files": {rel: count}}.

    Severity mapping:
      golangci-lint JSON issues have a "Severity" field.
      "error" -> errors; "warning" -> warnings; anything else -> info.
      Linters that typically emit errors: errcheck, staticcheck, govet, unused.
      Linters that typically emit warnings: everything else.
    """
    result = _run(
        ["golangci-lint", "run", "--out-format", "json", "./..."],
        cwd=root,
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"errors": 0, "warnings": 0, "info": 0, "files": {}}

    issues = data.get("Issues") or []
    errors = warnings = info = 0
    per_file: dict[str, int] = {}
    for issue in issues:
        severity = (issue.get("Severity") or "").lower()
        if severity == "error":
            errors += 1
        elif severity == "warning":
            warnings += 1
        else:
            info += 1
        pos = issue.get("Pos") or {}
        fname = pos.get("Filename") or issue.get("Filename") or ""
        if fname:
            rel = os.path.relpath(fname, root)
            per_file[rel] = per_file.get(rel, 0) + 1

    return {"errors": errors, "warnings": warnings, "info": info, "files": per_file}


# ---------------------------------------------------------------------------
# gocyclo — per-file max cyclomatic complexity
# ---------------------------------------------------------------------------

def run_gocyclo(root: str) -> dict:
    """Return {"files": {rel: max_complexity_float}}.

    gocyclo output line format:
        <complexity> <package> <function> <file>:<line>:<col>
    """
    result = _run(["gocyclo", "-over", "0", "."], cwd=root)
    per_file: dict[str, float] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            complexity = float(parts[0])
        except ValueError:
            continue
        # Last part is file:line:col
        file_part = parts[-1].split(":")[0]
        rel = os.path.relpath(os.path.join(root, file_part), root) if not os.path.isabs(file_part) else os.path.relpath(file_part, root)
        current = per_file.get(rel, 0.0)
        if complexity > current:
            per_file[rel] = round(complexity, 2)
    return {"files": per_file}


# ---------------------------------------------------------------------------
# jscpd — duplication
# ---------------------------------------------------------------------------

def run_jscpd(root: str) -> dict:
    """Return {"pct": float|null}."""
    with tempfile.TemporaryDirectory() as tmp:
        _run(
            [
                "jscpd",
                "--reporters", "json",
                "--output", tmp,
                "--languages", "go",
                "--ignore", "**/.git/**",
                ".",
            ],
            cwd=root,
        )
        report_file = os.path.join(tmp, "jscpd-report.json")
        if not os.path.exists(report_file):
            return {"pct": None}
        try:
            data = json.load(open(report_file))
            pct = data.get("statistics", {}).get("total", {}).get("percentage")
            if pct is None:
                return {"pct": None}
            return {"pct": round(float(pct), 2)}
        except Exception:
            return {"pct": None}


# ---------------------------------------------------------------------------
# per-file stat (loc)
# ---------------------------------------------------------------------------

def collect_file_stats(root: str) -> dict[str, dict]:
    """Collect loc for .go files under root (excluding vendor/)."""
    stats: dict[str, dict] = {}
    root_path = Path(root).resolve()
    for go_file in sorted(root_path.rglob("*.go")):
        # Skip vendor directory
        try:
            rel_parts = go_file.relative_to(root_path).parts
        except ValueError:
            continue
        if "vendor" in rel_parts:
            continue
        try:
            text = go_file.read_text(encoding="utf-8", errors="replace")
            loc = len(text.splitlines())
        except OSError:
            continue
        rel = str(go_file.relative_to(root_path))
        stats[rel] = {"loc": loc}
    return stats


# ---------------------------------------------------------------------------
# main run
# ---------------------------------------------------------------------------

def run(root: str) -> dict:
    root = str(Path(root).resolve())
    used, missing = detect_tools()

    violations = {"errors": 0, "warnings": 0, "info": 0}
    coverage = {"line_pct": None, "branch_pct": None}
    duplication = {"pct": None}
    vuln = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    files: dict[str, dict] = {}

    file_stats = collect_file_stats(root)

    lint_data: dict = {"errors": 0, "warnings": 0, "info": 0, "files": {}}
    gocyclo_data: dict = {"files": {}}

    if "go" in used:
        coverage = run_go_coverage(root)

    if "golangci-lint" in used:
        lint_data = run_golangci_lint(root)
        violations["errors"] += lint_data["errors"]
        violations["warnings"] += lint_data["warnings"]
        violations["info"] += lint_data["info"]

    if "gocyclo" in used:
        gocyclo_data = run_gocyclo(root)

    if "jscpd" in used:
        duplication = run_jscpd(root)

    # Merge per-file data
    all_files = sorted(
        set(list(file_stats.keys()) + list(gocyclo_data["files"].keys()) + list(lint_data["files"].keys()))
    )
    for rel in all_files:
        entry: dict = {}
        entry["loc"] = file_stats[rel]["loc"] if rel in file_stats else 0
        entry["complexity"] = gocyclo_data["files"].get(rel)
        entry["violations"] = lint_data["files"].get(rel, 0)
        files[rel] = entry

    return {
        "language": LANGUAGE,
        "root": root,
        "tools_used": used,
        "tools_missing": missing,
        "coverage": coverage,
        "duplication": duplication,
        "violations": violations,
        "vulnerabilities": vuln,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Go quality-gate language runner")
    p.add_argument("--root", required=True, help="Project root directory")
    p.add_argument("--output", required=True, help="Output JSON file path")
    args = p.parse_args(argv)
    payload = run(args.root)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
