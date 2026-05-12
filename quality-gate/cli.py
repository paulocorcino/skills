"""Quality Gate CLI.

Subcommands:
    init             scaffold .quality-gate/ in the target repo
    run              detect projects, run language packs, ratchet, emit report
    status           summarize the last report.md
    update-baseline  write .quality-gate/baseline.json from current state
    to-backlog       parse last report and emit per-issue backlog markdown

Exit codes:
    0   PASSED
    1   FAILED                 — at least one regression
    2   PASSED_WITH_GAPS       — passed, but some tools were missing
    3   NO_BASELINE            — no baseline available to compare against
    4   TOOL_MISSING_REGRESSION  — a tool that was present in baseline is now missing
    10  CONFIG_ERROR
    20  INTERNAL_ERROR
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Exit codes (named constants for callers).
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_PASSED_WITH_GAPS = 2
EXIT_NO_BASELINE = 3
EXIT_TOOL_MISSING_REGRESSION = 4
EXIT_CONFIG_ERROR = 10
EXIT_INTERNAL_ERROR = 20


# ---------------------------------------------------------------- helpers

def _repo_root(arg_cwd: str | None) -> Path:
    return Path(arg_cwd).resolve() if arg_cwd else Path.cwd().resolve()


def _git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _run_language_pack(language: str, root: str, output: str) -> int:
    """Invoke languages/<lang>/run.py --root <root> --output <output>."""
    pack = Path(__file__).resolve().parent / "languages" / language / "run.py"
    if not pack.is_file():
        return EXIT_INTERNAL_ERROR
    proc = subprocess.run(
        [sys.executable, str(pack), "--root", root, "--output", output],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
    return proc.returncode


# ---------------------------------------------------------------- subcommands

def cmd_init(args: argparse.Namespace) -> int:
    repo = _repo_root(getattr(args, "cwd", None))
    qg = repo / ".quality-gate"
    qg.mkdir(parents=True, exist_ok=True)
    config = qg / "config.json"
    if not config.is_file():
        config.write_text(
            json.dumps({"main_branch": "main", "projects": []}, indent=2) + "\n",
            encoding="utf-8",
        )
    # Add report ignore.
    gitignore = qg / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text("report.md\n", encoding="utf-8")
    print(f"initialized: {qg}")
    return EXIT_PASSED


def cmd_run(args: argparse.Namespace) -> int:
    from quality_gate.lib import (
        baseline_io, config as config_mod, detect, ratchet, report, security,
        validate_language,
    )

    repo = _repo_root(getattr(args, "cwd", None))
    try:
        cfg = config_mod.load(repo)
    except config_mod.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    main_branch = args.main_branch or config_mod.main_branch(cfg)
    projects = detect.detect(repo, cfg)
    if args.language:
        projects = [p for p in projects if p["language"] == args.language]
    if args.only:
        only = set(args.only.split(","))
        projects = [p for p in projects if p["project_key"] in only]

    # Run each language pack, validate, and collect.
    tmp_dir = repo / ".quality-gate" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    tools_missing_any = False
    for p in projects:
        out_path = tmp_dir / f"{p['project_key'].replace('/', '_')}.{p['language']}.json"
        rc = _run_language_pack(p["language"], p["root"], str(out_path))
        if rc != 0:
            print(f"runner failed: {p['language']} @ {p['root']}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        try:
            validate_language.validate(str(out_path))
        except validate_language.ValidationError as exc:
            print(f"runner output invalid: {exc}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        data = json.loads(out_path.read_text(encoding="utf-8"))
        # Merge security stub.
        sec = security.collect(p)
        data["vulnerabilities"] = sec["vulnerabilities"]
        data.setdefault("tools_used", []).extend(sec["tools_used"])
        data.setdefault("tools_missing", []).extend(sec["tools_missing"])
        if data["tools_missing"]:
            tools_missing_any = True
        current[p["project_key"]] = data

    # Baseline.
    try:
        baseline = baseline_io.read_baseline(repo, main_branch=main_branch)
    except baseline_io.BaselineError as exc:
        print(f"baseline error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    regressions = ratchet.compare(current, baseline)

    # Render report.
    md = report.render(
        projects=current,
        regressions=regressions,
        commit=_git_head(repo),
        tools_versions={},
    )
    report_path = repo / ".quality-gate" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(md, encoding="utf-8")
    print(f"report: {report_path}")

    if baseline is None:
        return EXIT_NO_BASELINE
    if regressions:
        return EXIT_FAILED
    if tools_missing_any:
        return EXIT_PASSED_WITH_GAPS
    return EXIT_PASSED


def cmd_status(args: argparse.Namespace) -> int:
    repo = _repo_root(getattr(args, "cwd", None))
    report = repo / ".quality-gate" / "report.md"
    if not report.is_file():
        print("no report; run `python -m quality_gate run` first")
        return EXIT_NO_BASELINE
    text = report.read_text(encoding="utf-8")
    # Print Summary block.
    in_summary = False
    for line in text.splitlines():
        if line.startswith("## Summary"):
            in_summary = True
            print(line)
            continue
        if in_summary:
            if line.startswith("## "):
                break
            print(line)
    return EXIT_PASSED


def cmd_update_baseline(args: argparse.Namespace) -> int:
    from quality_gate.lib import (
        baseline_io, config as config_mod, detect, security, validate_language,
    )
    import datetime as _dt

    repo = _repo_root(getattr(args, "cwd", None))
    try:
        cfg = config_mod.load(repo)
    except config_mod.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    main_branch = args.main_branch or config_mod.main_branch(cfg)

    projects = detect.detect(repo, cfg)
    tmp_dir = repo / ".quality-gate" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    proj_metrics: dict[str, Any] = {}
    for p in projects:
        out_path = tmp_dir / f"{p['project_key'].replace('/', '_')}.{p['language']}.json"
        rc = _run_language_pack(p["language"], p["root"], str(out_path))
        if rc != 0:
            return EXIT_INTERNAL_ERROR
        try:
            validate_language.validate(str(out_path))
        except validate_language.ValidationError as exc:
            print(f"runner output invalid: {exc}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        data = json.loads(out_path.read_text(encoding="utf-8"))
        sec = security.collect(p)
        data["vulnerabilities"] = sec["vulnerabilities"]
        proj_metrics[p["project_key"]] = {
            "language": p["language"],
            "root": p["root"],
            "metrics": {
                "coverage": data["coverage"],
                "duplication": data["duplication"],
                "violations": data["violations"],
                "vulnerabilities": data["vulnerabilities"],
                "files": data["files"],
            },
        }

    payload = {
        "schema_version": "1.0.0",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _git_head(repo),
        "main_branch": main_branch,
        "tools_versions": {},
        "projects": proj_metrics,
    }
    try:
        baseline_io.write_baseline(repo, payload, main_branch=main_branch, force=args.force)
    except baseline_io.BaselineError as exc:
        print(f"baseline error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    print(f"baseline written: {repo / baseline_io.BASELINE_RELPATH}")
    return EXIT_PASSED


def cmd_to_backlog(args: argparse.Namespace) -> int:
    from quality_gate.lib import backlog
    repo = _repo_root(getattr(args, "cwd", None))
    written = backlog.run_to_backlog(repo)
    for p in written:
        print(str(p))
    return EXIT_PASSED


# ---------------------------------------------------------------- argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quality_gate",
        description="Quality Gate: ratchet-based quality enforcement for Python/Go/Rust/BunJS projects.",
    )
    parser.add_argument("--cwd", help="target repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{init,run,status,update-baseline,to-backlog}")

    p_init = sub.add_parser("init", help="scaffold .quality-gate/ in the target repo")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="detect projects, run gates, emit report")
    p_run.add_argument("--language", help="restrict to a single language (python|go|rust|bunjs)")
    p_run.add_argument("--only", help="comma-separated project_keys to include")
    p_run.add_argument("--main-branch", help="override main branch name")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="print the Summary block from the last report")
    p_status.set_defaults(func=cmd_status)

    p_ub = sub.add_parser("update-baseline", help="write .quality-gate/baseline.json")
    p_ub.add_argument("--force", action="store_true", help="allow writing from a non-main branch")
    p_ub.add_argument("--main-branch", help="override main branch name")
    p_ub.set_defaults(func=cmd_update_baseline)

    p_bk = sub.add_parser("to-backlog", help="emit per-issue backlog markdown from the last report")
    p_bk.set_defaults(func=cmd_to_backlog)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover — internal errors path
        print(f"internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
