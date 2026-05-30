"""BunJS language runner — real implementation (Stage 5).

Tools:
  bun    — required; used for `bun test --coverage`
  biome  — primary linter/formatter via `biome check --reporter=json`
  oxlint — fallback linter if biome absent
  jscpd  — duplication
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

LANGUAGE = "bunjs"
# Logical tool names; biome and oxlint are mutually exclusive (biome preferred)
REQUIRED_TOOLS = ["bun", "biome", "oxlint", "jscpd"]

# ── tool detection ────────────────────────────────────────────────────────────


def _bun_local(root: str, name: str) -> str | None:
    """Return the path to a locally-installed bun tool (node_modules/.bin/<name>)."""
    candidate = Path(root) / "node_modules" / ".bin" / name
    if candidate.exists():
        return str(candidate)
    return None


def detect_tools(root: str) -> tuple[list[str], list[str]]:
    used: list[str] = []
    missing: list[str] = []

    # bun
    if shutil.which("bun"):
        used.append("bun")
    else:
        missing.append("bun")

    # biome (prefer global, fall back to local)
    has_biome = bool(shutil.which("biome") or _bun_local(root, "biome"))
    if has_biome:
        used.append("biome")
        # oxlint is mutually exclusive with biome — not reported as missing
    else:
        missing.append("biome")
        has_oxlint = bool(shutil.which("oxlint") or _bun_local(root, "oxlint"))
        if has_oxlint:
            used.append("oxlint")
        else:
            missing.append("oxlint")

    # jscpd
    if shutil.which("jscpd") or _bun_local(root, "jscpd"):
        used.append("jscpd")
    else:
        missing.append("jscpd")

    return used, missing


# ── helpers ───────────────────────────────────────────────────────────────────


def _resolve_bin(root: str, name: str) -> str:
    """Return the absolute path for a tool (global or local)."""
    global_path = shutil.which(name)
    if global_path:
        return global_path
    local = _bun_local(root, name)
    if local:
        return local
    return name  # let subprocess raise FileNotFoundError


# ── coverage — bun test --coverage ───────────────────────────────────────────


def _run_coverage(root: str) -> tuple[float | None, float | None]:
    """Run `bun test --coverage` and parse LCOV text output from stdout/stderr."""
    try:
        result = subprocess.run(
            ["bun", "test", "--coverage"],
            cwd=root,
            capture_output=True,
            timeout=300,
        )
        # bun prints coverage summary to stderr in a table like:
        # All files | 85.00 | 70.00 | 90.00 |
        # We look for a "All files" row with percentages.
        output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        line_pct: float | None = None
        branch_pct: float | None = None
        for line in output.splitlines():
            if "All files" in line or "all files" in line.lower():
                # Extract numeric values from the row
                parts = [p.strip() for p in line.split("|") if p.strip()]
                numbers = []
                for p in parts:
                    try:
                        numbers.append(float(p))
                    except ValueError:
                        pass
                if len(numbers) >= 1:
                    line_pct = round(numbers[0], 2)
                if len(numbers) >= 2:
                    branch_pct = round(numbers[1], 2)
                break
        return line_pct, branch_pct
    except Exception:
        return None, None


# ── violations — biome check --reporter=json ──────────────────────────────────


def _run_biome(root: str) -> tuple[int, int, int, dict[str, int], dict[str, int], dict[str, dict[str, int]]]:
    """Return (errors, warnings, info, per_file_violations, rule_counts, per_file_rule_counts) from biome."""
    errors = warnings = info = 0
    per_file: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    per_file_rules: dict[str, dict[str, int]] = {}
    try:
        biome_bin = _resolve_bin(root, "biome")
        result = subprocess.run(
            [biome_bin, "check", "--reporter=json", "."],
            cwd=root,
            capture_output=True,
            timeout=120,
        )
        raw = result.stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            raw = result.stderr.decode("utf-8", errors="replace").strip()
        if not raw:
            return errors, warnings, info, per_file, rule_counts, per_file_rules
        data = json.loads(raw)
        root_path = Path(root).resolve()
        diagnostics = data.get("diagnostics", [])
        for diag in diagnostics:
            severity = diag.get("severity", "").lower()
            if severity == "error":
                errors += 1
            elif severity == "warning":
                warnings += 1
            elif severity in ("information", "hint"):
                info += 1
            else:
                warnings += 1  # treat unknown as warning
            # rule aggregation (biome diagnostic.category: "lint/style/useConst" etc.)
            category = diag.get("category")
            if isinstance(category, str) and category:
                rule_counts[category] = rule_counts.get(category, 0) + 1
            # per-file accounting via location
            location = diag.get("location", {})
            path_str = location.get("path", {})
            if isinstance(path_str, dict):
                path_str = path_str.get("file", "")
            if path_str:
                try:
                    rel = str(Path(path_str).resolve().relative_to(root_path))
                except (ValueError, OSError):
                    rel = str(path_str)
                per_file[rel] = per_file.get(rel, 0) + 1
                if isinstance(category, str) and category:
                    file_rules = per_file_rules.setdefault(rel, {})
                    file_rules[category] = file_rules.get(category, 0) + 1
    except Exception:
        pass
    return errors, warnings, info, per_file, rule_counts, per_file_rules


def _run_oxlint(root: str) -> tuple[int, int, int, dict[str, int], dict[str, int], dict[str, dict[str, int]]]:
    """Return (errors, warnings, info, per_file_violations, rule_counts, per_file_rule_counts) from oxlint JSON output."""
    errors = warnings = info = 0
    per_file: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    per_file_rules: dict[str, dict[str, int]] = {}
    try:
        oxlint_bin = _resolve_bin(root, "oxlint")
        result = subprocess.run(
            [oxlint_bin, "--format=json", "."],
            cwd=root,
            capture_output=True,
            timeout=120,
        )
        raw = result.stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            return errors, warnings, info, per_file, rule_counts, per_file_rules
        # oxlint JSON: array of {filePath, messages:[{severity,ruleId,...}]}
        data = json.loads(raw)
        root_path = Path(root).resolve()
        for file_result in data:
            fp = file_result.get("filePath", "")
            try:
                rel = str(Path(fp).resolve().relative_to(root_path))
            except (ValueError, OSError):
                rel = fp
            file_errors = 0
            for msg in file_result.get("messages", []):
                sev = msg.get("severity", 1)
                if sev == 2:
                    errors += 1
                    file_errors += 1
                elif sev == 1:
                    warnings += 1
                    file_errors += 1
                else:
                    info += 1
                rule_id = msg.get("ruleId")
                if isinstance(rule_id, str) and rule_id:
                    rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
                    file_rules = per_file_rules.setdefault(rel, {})
                    file_rules[rule_id] = file_rules.get(rule_id, 0) + 1
            if file_errors:
                per_file[rel] = per_file.get(rel, 0) + file_errors
    except Exception:
        pass
    return errors, warnings, info, per_file, rule_counts, per_file_rules


# ── duplication (jscpd) ───────────────────────────────────────────────────────


def _run_jscpd(root: str) -> tuple[float | None, str | None]:
    """Return (pct, error_msg). error_msg is non-None when jscpd ran but did not produce usable output."""
    try:
        jscpd_bin = _resolve_bin(root, "jscpd")
        with tempfile.TemporaryDirectory() as td:
            # Defaults chosen for monorepo viability:
            #   --silent / --noTips: keep stderr quiet for CI
            #   --ignore: skip well-known generated/vendor dirs (target can override
            #             via .jscpd.json or the `jscpd` section of package.json)
            #   --min-tokens 50: jscpd default; raise via .jscpd.json if needed
            #   timeout 300s: large monorepos exceed the prior 120s budget
            result = subprocess.run(
                [
                    jscpd_bin,
                    "--reporters", "json",
                    "--output", td,
                    "--format", "typescript,javascript",
                    "--min-tokens", "50",
                    "--ignore", "node_modules/**,dist/**,build/**,.next/**,coverage/**,.quality-gate/**",
                    "--silent",
                    "--noTips",
                    ".",
                ],
                cwd=root,
                capture_output=True,
                timeout=300,
            )
            report_file = Path(td) / "jscpd-report.json"
            if not report_file.exists():
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                msg = f"jscpd produced no report (exit={result.returncode}): {stderr[:200] or '<no stderr>'}"
                print(f"warning: {msg}", file=sys.stderr)
                return None, msg
            data = json.loads(report_file.read_text(encoding="utf-8"))
            stats = data.get("statistics", {}).get("total", {})
            pct = stats.get("percentage")
            if pct is None:
                msg = "jscpd report missing statistics.total.percentage"
                print(f"warning: {msg}", file=sys.stderr)
                return None, msg
            return round(float(pct), 2), None
    except Exception as exc:
        msg = f"jscpd failed: {type(exc).__name__}: {exc}"
        print(f"warning: {msg}", file=sys.stderr)
        return None, msg


# ── per-file LOC ──────────────────────────────────────────────────────────────


def _count_loc(file_path: Path) -> int:
    try:
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}


def _collect_files(
    root: str,
    per_file_violations: dict[str, int],
    per_file_rules: dict[str, dict[str, int]] | None = None,
    soft_limit: int = 300,
) -> dict:
    """Return files dict for files that cross soft_limit OR have violations."""
    root_path = Path(root).resolve()
    result: dict[str, dict] = {}
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "coverage"}
    rules_by_file = per_file_rules or {}
    for candidate in sorted(root_path.rglob("*")):
        if candidate.suffix not in _TS_EXTENSIONS:
            continue
        # skip ignored dirs
        parts = set(candidate.parts)
        if parts & skip_dirs:
            continue
        if any(part.startswith(".") for part in candidate.relative_to(root_path).parts):
            continue
        try:
            rel = str(candidate.relative_to(root_path))
        except ValueError:
            continue
        loc = _count_loc(candidate)
        viols = per_file_violations.get(rel, 0)
        if loc >= soft_limit or viols > 0:
            entry: dict = {
                "loc": loc,
                "complexity": None,
                "violations": viols,
            }
            rules = rules_by_file.get(rel) or {}
            if rules:
                top_rule = max(rules.items(), key=lambda kv: (kv[1], kv[0]))[0]
                entry["dominant_rule"] = top_rule
            result[rel] = entry
    return result


# ── main runner ───────────────────────────────────────────────────────────────


def run(root: str) -> dict:
    used, missing = detect_tools(root)
    root_str = str(Path(root).resolve())

    coverage = {"line_pct": None, "branch_pct": None}
    duplication = {"pct": None}
    violations = {"errors": 0, "warnings": 0, "info": 0}
    vulnerabilities = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    per_file_viols: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    tools_broken: list[str] = []
    tools_reproduce: dict[str, str] = {}

    if "bun" in used:
        lp, bp = _run_coverage(root_str)
        coverage = {"line_pct": lp, "branch_pct": bp}
        tools_reproduce["bun"] = "bun test --coverage"

    per_file_rules: dict[str, dict[str, int]] = {}
    if "biome" in used:
        err, warn, inf, per_file_viols, rule_counts, per_file_rules = _run_biome(root_str)
        violations = {"errors": err, "warnings": warn, "info": inf}
        tools_reproduce["biome"] = "bun x biome check --reporter=summary ."
    elif "oxlint" in used:
        err, warn, inf, per_file_viols, rule_counts, per_file_rules = _run_oxlint(root_str)
        violations = {"errors": err, "warnings": warn, "info": inf}
        tools_reproduce["oxlint"] = "bun x oxlint ."

    if "jscpd" in used:
        pct, err_msg = _run_jscpd(root_str)
        duplication = {"pct": pct}
        tools_reproduce["jscpd"] = (
            "bun x jscpd --reporters console --format typescript,javascript "
            "--ignore 'node_modules/**,dist/**,build/**,.next/**,coverage/**,.quality-gate/**' ."
        )
        if err_msg is not None:
            tools_broken.append("jscpd")

    # Top rules: sort by count desc, keep top 5
    top_rules = [
        {"rule": rule, "count": count}
        for rule, count in sorted(rule_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    ]

    files = _collect_files(root_str, per_file_viols, per_file_rules)

    return {
        "language": LANGUAGE,
        "root": root_str,
        "tools_used": sorted(used),
        "tools_missing": sorted(missing),
        "tools_broken": sorted(tools_broken),
        "tools_reproduce": tools_reproduce,
        "top_rules": top_rules,
        "coverage": coverage,
        "duplication": duplication,
        "violations": violations,
        "vulnerabilities": vulnerabilities,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quality Gate — BunJS language runner")
    p.add_argument("--root", required=True, help="BunJS project root (contains package.json + bun.lockb)")
    p.add_argument("--output", required=True, help="Path to write JSON output")
    args = p.parse_args(argv)
    payload = run(args.root)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
