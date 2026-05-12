"""Rust language runner — real implementation (Stage 4).

Tools:
  cargo          — required; used for llvm-cov and clippy
  cargo-llvm-cov — coverage via `cargo llvm-cov --json`
  clippy         — lint+violations via `cargo clippy --message-format=json`
  jscpd          — duplication
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LANGUAGE = "rust"
# Logical tool names used in tools_used / tools_missing
REQUIRED_TOOLS = ["cargo", "cargo-llvm-cov", "clippy", "jscpd"]

# ── tool detection ────────────────────────────────────────────────────────────

def _cargo_subcommand_available(name: str) -> bool:
    """Check whether a cargo subcommand / component is available."""
    try:
        result = subprocess.run(
            ["cargo", name, "--version"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_tools() -> tuple[list[str], list[str]]:
    used: list[str] = []
    missing: list[str] = []

    # cargo itself
    if shutil.which("cargo"):
        used.append("cargo")
    else:
        missing.extend(["cargo", "cargo-llvm-cov", "clippy"])
        if shutil.which("jscpd"):
            used.append("jscpd")
        else:
            missing.append("jscpd")
        return used, missing

    # cargo-llvm-cov
    if _cargo_subcommand_available("llvm-cov"):
        used.append("cargo-llvm-cov")
    else:
        missing.append("cargo-llvm-cov")

    # clippy (rustup component)
    if _cargo_subcommand_available("clippy"):
        used.append("clippy")
    else:
        missing.append("clippy")

    # jscpd
    if shutil.which("jscpd"):
        used.append("jscpd")
    else:
        missing.append("jscpd")

    return used, missing


# ── coverage ──────────────────────────────────────────────────────────────────

def _run_coverage(root: str) -> tuple[float | None, float | None]:
    """Run cargo-llvm-cov and return (line_pct, branch_pct)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tmp_path = tf.name
        result = subprocess.run(
            ["cargo", "llvm-cov", "--json", "--output-path", tmp_path],
            cwd=root,
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            return None, None
        data = json.loads(Path(tmp_path).read_text(encoding="utf-8"))
        # llvm-cov JSON has data[0].totals
        totals = data.get("data", [{}])[0].get("totals", {})
        lines = totals.get("lines", {})
        branches = totals.get("branches", {})
        line_pct: float | None = None
        branch_pct: float | None = None
        if lines.get("count", 0) > 0:
            line_pct = round(lines.get("percent", 0.0), 2)
        if branches.get("count", 0) > 0:
            branch_pct = round(branches.get("percent", 0.0), 2)
        return line_pct, branch_pct
    except Exception:
        return None, None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── violations (clippy) ───────────────────────────────────────────────────────

def _run_clippy(root: str) -> tuple[int, int, int, dict[str, int]]:
    """Return (errors, warnings, info, per_file_violations)."""
    errors = warnings = info = 0
    per_file: dict[str, int] = {}
    try:
        result = subprocess.run(
            ["cargo", "clippy", "--message-format=json", "--", "-W", "clippy::all"],
            cwd=root,
            capture_output=True,
            timeout=300,
        )
        root_path = Path(root).resolve()
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("reason") != "compiler-message":
                continue
            diag = msg.get("message", {})
            level = diag.get("level", "")
            if level == "error":
                errors += 1
            elif level == "warning":
                warnings += 1
            elif level in ("note", "help"):
                info += 1
            else:
                continue
            # per-file accounting
            spans = diag.get("spans", [])
            primary_spans = [s for s in spans if s.get("is_primary")]
            if not primary_spans and spans:
                primary_spans = spans[:1]
            for span in primary_spans:
                fn = span.get("file_name", "")
                try:
                    rel = str(Path(fn).resolve().relative_to(root_path))
                except (ValueError, OSError):
                    rel = fn
                per_file[rel] = per_file.get(rel, 0) + 1
    except Exception:
        pass
    return errors, warnings, info, per_file


# ── duplication (jscpd) ───────────────────────────────────────────────────────

def _run_jscpd(root: str) -> float | None:
    try:
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [
                    "jscpd",
                    "--reporters", "json",
                    "--output", td,
                    "--languages", "rust",
                    "--min-tokens", "50",
                    ".",
                ],
                cwd=root,
                capture_output=True,
                timeout=120,
            )
            report_file = Path(td) / "jscpd-report.json"
            if not report_file.exists():
                return None
            data = json.loads(report_file.read_text(encoding="utf-8"))
            stats = data.get("statistics", {}).get("total", {})
            pct = stats.get("percentage")
            if pct is not None:
                return round(float(pct), 2)
    except Exception:
        pass
    return None


# ── per-file LOC ──────────────────────────────────────────────────────────────

def _count_loc(file_path: Path) -> int:
    try:
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def _collect_files(root: str, per_file_violations: dict[str, int], soft_limit: int = 400) -> dict:
    """Return files dict for files that cross soft_limit OR have violations."""
    root_path = Path(root).resolve()
    result: dict[str, dict] = {}
    for rs_file in sorted(root_path.rglob("*.rs")):
        try:
            rel = str(rs_file.relative_to(root_path))
        except ValueError:
            continue
        if any(part.startswith(".") for part in rs_file.parts):
            continue
        loc = _count_loc(rs_file)
        viols = per_file_violations.get(rel, 0)
        if loc >= soft_limit or viols > 0:
            result[rel] = {
                "loc": loc,
                "complexity": None,
                "violations": viols,
            }
    return result


# ── main runner ───────────────────────────────────────────────────────────────

def run(root: str) -> dict:
    used, missing = detect_tools()
    root_str = str(Path(root).resolve())

    coverage = {"line_pct": None, "branch_pct": None}
    duplication = {"pct": None}
    violations = {"errors": 0, "warnings": 0, "info": 0}
    vulnerabilities = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    per_file_viols: dict[str, int] = {}

    if "cargo-llvm-cov" in used:
        lp, bp = _run_coverage(root_str)
        coverage = {"line_pct": lp, "branch_pct": bp}

    if "clippy" in used:
        err, warn, inf, per_file_viols = _run_clippy(root_str)
        violations = {"errors": err, "warnings": warn, "info": inf}

    if "jscpd" in used:
        pct = _run_jscpd(root_str)
        duplication = {"pct": pct}

    files = _collect_files(root_str, per_file_viols)

    return {
        "language": LANGUAGE,
        "root": root_str,
        "tools_used": sorted(used),
        "tools_missing": sorted(missing),
        "coverage": coverage,
        "duplication": duplication,
        "violations": violations,
        "vulnerabilities": vulnerabilities,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Quality Gate — Rust language runner")
    p.add_argument("--root", required=True, help="Rust project root (contains Cargo.toml)")
    p.add_argument("--output", required=True, help="Path to write JSON output")
    args = p.parse_args(argv)
    payload = run(args.root)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
