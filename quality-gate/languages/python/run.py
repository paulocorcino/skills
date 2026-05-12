"""Python language runner — real implementation (Stage 2).

Tools: ruff (lint), pytest+coverage.py (tests + coverage),
       bandit (security patterns), radon (complexity), jscpd (duplication).

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
import xml.etree.ElementTree as ET
from pathlib import Path

LANGUAGE = "python"
REQUIRED_TOOLS = ["ruff", "pytest", "coverage", "bandit", "radon", "jscpd"]


def detect_tools() -> tuple[list[str], list[str]]:
    used, missing = [], []
    for t in REQUIRED_TOOLS:
        (used if shutil.which(t) else missing).append(t)
    return sorted(used), sorted(missing)


def _run(cmd: list[str], cwd: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess; never raises on non-zero exit."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
    )


# ---------------------------------------------------------------------------
# ruff — lint
# ---------------------------------------------------------------------------

def run_ruff(root: str) -> dict:
    """Return {"errors": int, "warnings": int, "info": int, "files": {rel: count}}."""
    result = _run(
        ["ruff", "check", "--output-format=json", "--no-cache", "."],
        cwd=root,
    )
    try:
        diagnostics = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        diagnostics = []

    errors = warnings = info = 0
    per_file: dict[str, int] = {}
    for d in diagnostics:
        # ruff JSON: {"code": ..., "message": ..., "filename": ..., "location": ...}
        # Treat E/F codes (errors) vs W codes (warnings); rest as info.
        code = d.get("code") or ""
        if code.startswith(("E", "F")):
            errors += 1
        elif code.startswith("W"):
            warnings += 1
        else:
            info += 1
        fname = d.get("filename", "")
        if fname:
            rel = os.path.relpath(fname, root)
            per_file[rel] = per_file.get(rel, 0) + 1

    return {"errors": errors, "warnings": warnings, "info": info, "files": per_file}


# ---------------------------------------------------------------------------
# pytest + coverage.py
# ---------------------------------------------------------------------------

def run_pytest_coverage(root: str) -> dict:
    """Return {"line_pct": float|null, "branch_pct": float|null}."""
    with tempfile.TemporaryDirectory() as tmp:
        cov_xml = os.path.join(tmp, "coverage.xml")
        _run(
            [
                "python", "-m", "pytest",
                "-p", "no:randomly",
                "--tb=no", "-q",
                f"--cov={root}",
                "--cov-report=xml:" + cov_xml,
                "--cov-branch",
            ],
            cwd=root,
        )
        if not os.path.exists(cov_xml):
            return {"line_pct": None, "branch_pct": None}

        try:
            tree = ET.parse(cov_xml)
            cov_el = tree.getroot()
            line_rate = cov_el.get("line-rate")
            branch_rate = cov_el.get("branch-rate")
            line_pct = round(float(line_rate) * 100, 2) if line_rate is not None else None
            branch_pct = round(float(branch_rate) * 100, 2) if branch_rate is not None else None
        except Exception:
            return {"line_pct": None, "branch_pct": None}

    return {"line_pct": line_pct, "branch_pct": branch_pct}


# ---------------------------------------------------------------------------
# bandit — security lint
# ---------------------------------------------------------------------------

def run_bandit(root: str) -> dict:
    """Return {"errors": int, "warnings": int} for security findings.

    bandit severities: HIGH -> errors, MEDIUM/LOW -> warnings.
    """
    result = _run(
        ["bandit", "-r", ".", "-f", "json", "-q"],
        cwd=root,
    )
    try:
        data = json.loads(result.stdout or "{}")
        results = data.get("results", [])
    except json.JSONDecodeError:
        return {"errors": 0, "warnings": 0}

    errors = sum(1 for r in results if r.get("issue_severity", "").upper() == "HIGH")
    warnings = sum(1 for r in results if r.get("issue_severity", "").upper() in ("MEDIUM", "LOW"))
    return {"errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# radon — complexity
# ---------------------------------------------------------------------------

def run_radon(root: str) -> dict:
    """Return {"files": {rel: {"complexity": float}}}."""
    result = _run(
        ["radon", "cc", "-j", "-a", "."],
        cwd=root,
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"files": {}}

    per_file: dict[str, float] = {}
    for fname, blocks in data.items():
        if not isinstance(blocks, list):
            continue
        complexities = [b.get("complexity", 0) for b in blocks if isinstance(b, dict)]
        if complexities:
            max_c = max(complexities)
            rel = os.path.relpath(fname, root)
            per_file[rel] = round(float(max_c), 2)

    return {"files": per_file}


# ---------------------------------------------------------------------------
# jscpd — duplication
# ---------------------------------------------------------------------------

def run_jscpd(root: str) -> dict:
    """Return {"pct": float|null}."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run(
            [
                "jscpd",
                "--reporters", "json",
                "--output", tmp,
                "--languages", "python",
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
# per-file stat
# ---------------------------------------------------------------------------

def collect_file_stats(root: str) -> dict[str, dict]:
    """Collect loc and bytes for .py files under root."""
    stats: dict[str, dict] = {}
    root_path = Path(root).resolve()
    for py_file in sorted(root_path.rglob("*.py")):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            loc = len(text.splitlines())
            size = py_file.stat().st_size
        except OSError:
            continue
        rel = str(py_file.relative_to(root_path))
        stats[rel] = {"loc": loc, "bytes": size}
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

    # ruff
    ruff_data: dict = {"errors": 0, "warnings": 0, "info": 0, "files": {}}
    if "ruff" in used:
        ruff_data = run_ruff(root)
        violations["errors"] += ruff_data["errors"]
        violations["warnings"] += ruff_data["warnings"]
        violations["info"] += ruff_data["info"]

    # pytest + coverage
    if "pytest" in used and "coverage" in used:
        coverage = run_pytest_coverage(root)

    # bandit
    bandit_data: dict = {"errors": 0, "warnings": 0}
    if "bandit" in used:
        bandit_data = run_bandit(root)
        violations["errors"] += bandit_data["errors"]
        violations["warnings"] += bandit_data["warnings"]

    # radon
    radon_data: dict = {"files": {}}
    if "radon" in used:
        radon_data = run_radon(root)

    # jscpd
    if "jscpd" in used:
        duplication = run_jscpd(root)

    # Merge per-file data
    all_files = sorted(set(list(file_stats.keys()) + list(radon_data["files"].keys()) + list(ruff_data["files"].keys())))
    for rel in all_files:
        entry: dict = {}
        if rel in file_stats:
            entry["loc"] = file_stats[rel]["loc"]
        else:
            entry["loc"] = 0
        entry["complexity"] = radon_data["files"].get(rel)
        entry["violations"] = ruff_data["files"].get(rel, 0)
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
    p = argparse.ArgumentParser(description="Python quality-gate language runner")
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
