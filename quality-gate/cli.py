"""Quality Gate CLI.

Subcommands:
    init        scaffold .quality-gate/ in the target repo
    establish   declare branch intent (mode=extend|replace); writes branch.json
                and, in replace mode, captures baseline.json snapshot
    run         detect projects, run language packs, ratchet, emit report
    status      summarize the last report.md
    to-backlog  parse last report and emit per-issue backlog markdown

Exit codes:
    0   PASSED
    1   FAILED                      — at least one regression
    2   PASSED_WITH_GAPS            — passed, but some tools were missing
    3   NO_BASELINE                 — mode declared but target ref has no baseline
    4   TOOL_MISSING_REGRESSION     — a tool that was present in baseline is now missing
    5   NO_INTENT                   — branch != main has no branch.json declared
    10  CONFIG_ERROR
    20  INTERNAL_ERROR
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

_DEBUG = bool(os.environ.get("QG_DEBUG"))

# Exit codes (named constants for callers).
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_PASSED_WITH_GAPS = 2
EXIT_NO_BASELINE = 3
EXIT_TOOL_MISSING_REGRESSION = 4
EXIT_NO_INTENT = 5
EXIT_CONFIG_ERROR = 10
EXIT_INTERNAL_ERROR = 20

BRANCH_SCHEMA_VERSION = "1.0.0"

_NO_PROJECTS_HINT = (
    "no projects detected — ensure at least one supported manifest is present: "
    "bun.lockb / bun.lock (BunJS), pyproject.toml / setup.py / requirements.txt (Python), "
    "go.mod (Go), Cargo.toml (Rust)."
)


def _no_intent_message(branch: str) -> str:
    return (
        f"NO_INTENT: branch {branch!r} has no declared mode.\n\n"
        "This branch was likely created before the quality-gate v2 redesign, or\n"
        "intent was never declared. Choose a mode based on what this branch does:\n\n"
        "  quality_gate establish --mode extend     # branch extends main (default for feature work)\n"
        "  quality_gate establish --mode replace    # branch replaces main's baseline (refactor / legacy main)\n\n"
        "Then:\n"
        "  git add .quality-gate/branch.json\n"
        "  git commit -m \"chore(qg): declare branch intent\"\n"
        "  quality_gate run\n\n"
        "See: references/branch-modes.md"
    )


def _no_baseline_message(mode: str, anchor_ref: str, refs_consulted: list[str]) -> str:
    refs_list = "\n".join(f"  - {r}" for r in refs_consulted) if refs_consulted else "  (none)"
    if mode == "extend":
        hint = (
            "In 'extend' mode the gate reads the baseline at the merge-base with the\n"
            "anchor ref. If your branch was created before the baseline existed in main,\n"
            "sync with main (rebase/merge) to advance the merge-base, then re-run."
        )
    elif mode == "replace":
        hint = (
            "In 'replace' mode the gate reads the baseline from the working tree of\n"
            "this branch. Run 'quality_gate establish --mode replace' to capture one."
        )
    else:
        hint = (
            "On main the gate reads the baseline from the working tree. Run\n"
            "'quality_gate establish --mode replace' to capture one."
        )
    return (
        f"NO_BASELINE: no baseline could be located (mode={mode}, anchor_ref={anchor_ref}).\n\n"
        f"Refs consulted:\n{refs_list}\n\n"
        f"{hint}"
    )


# ---------------------------------------------------------------- helpers

def _repo_root(arg_cwd: str | None) -> Path:
    return Path(arg_cwd).resolve() if arg_cwd else Path.cwd().resolve()


def _git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _print_summary(md: str) -> None:
    """Print the Summary section from a rendered report markdown string."""
    in_summary = False
    for line in md.splitlines():
        if line.startswith("## Summary"):
            in_summary = True
            print(line)
            continue
        if in_summary:
            if line.startswith("## "):
                break
            print(line)


def _run_language_pack(language: str, root: str, output: str) -> int:
    """Invoke languages/<lang>/run.py --root <root> --output <output>."""
    pack = Path(__file__).resolve().parent / "languages" / language / "run.py"
    if not pack.is_file():
        return EXIT_INTERNAL_ERROR
    proc = subprocess.run(
        [sys.executable, str(pack), "--root", root, "--output", output],
        capture_output=True, text=True,
    )
    # Always forward the runner's stderr — diagnostic warnings (broken tools,
    # parse failures) come through this channel even on successful exits.
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def _collect_project_metrics(repo: Path, projects: list[dict]) -> tuple[dict, bool, Optional[int]]:
    """Run language packs + security for every project.

    Returns (per_project_data, tools_missing_any, error_exit_code_or_None).
    """
    from quality_gate.lib import security, validate_language

    tmp_dir = repo / ".quality-gate" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    tools_missing_any = False
    for p in projects:
        out_path = tmp_dir / f"{p['project_key'].replace('/', '_')}.{p['language']}.json"
        rc = _run_language_pack(p["language"], p["root"], str(out_path))
        if rc != 0:
            print(f"runner failed: {p['language']} @ {p['root']}", file=sys.stderr)
            return {}, False, EXIT_INTERNAL_ERROR
        try:
            validate_language.validate(str(out_path))
        except validate_language.ValidationError as exc:
            print(f"runner output invalid: {exc}", file=sys.stderr)
            return {}, False, EXIT_INTERNAL_ERROR
        data = json.loads(out_path.read_text(encoding="utf-8"))
        sec = security.collect(p["root"])
        data["vulnerabilities"] = sec["vulnerabilities"]
        data.setdefault("tools_used", []).extend(sec["tools_used"])
        data.setdefault("tools_missing", []).extend(sec["tools_missing"])
        data.setdefault("tools_broken", [])
        data.setdefault("tools_reproduce", {})
        data.setdefault("top_rules", [])
        if data["tools_missing"] or data["tools_broken"]:
            tools_missing_any = True
        if p.get("name"):
            data["_project_name"] = p["name"]
        current[p["project_key"]] = data
    return current, tools_missing_any, None


# ---------------------------------------------------------------- subcommands

def cmd_init(args: argparse.Namespace) -> int:
    repo = _repo_root(getattr(args, "cwd", None))
    qg = repo / ".quality-gate"
    qg.mkdir(parents=True, exist_ok=True)
    config = qg / "config.json"
    already = config.is_file()
    if not already:
        config.write_text(
            json.dumps({"main_branch": "main", "projects": []}, indent=2) + "\n",
            encoding="utf-8",
        )
    gitignore = qg / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text("report.md\ntmp/\n", encoding="utf-8")
    if already:
        print(f"already initialized: {qg}")
    else:
        print(f"initialized: {qg}")
    print()
    print("Next steps:")
    print("  - On main: quality_gate establish --mode replace   # captures first baseline")
    print("  - On feature branches: quality_gate establish --mode {extend|replace}")
    print()
    print("Commit the resulting .quality-gate/ files. See references/bootstrap.md.")

    # Recommend adding .quality-gate/ to linter ignore lists based on detected manifests.
    hints: list[str] = []
    if (repo / "biome.json").is_file() or (repo / "biome.jsonc").is_file() or (repo / "package.json").is_file():
        hints.append("  biome   → add \".quality-gate/**\" to `files.ignore` in biome.json")
    if (repo / "package.json").is_file():
        hints.append("  oxlint  → add \".quality-gate/**\" to `ignorePatterns` in .oxlintrc.json (if used)")
    if (repo / "pyproject.toml").is_file() or (repo / "ruff.toml").is_file():
        hints.append("  ruff    → add \".quality-gate/\" to `exclude` in ruff.toml / [tool.ruff]")
    if (repo / ".golangci.yml").is_file() or (repo / "go.mod").is_file():
        hints.append("  golangci-lint → add \".quality-gate\" to `run.skip-dirs` in .golangci.yml")
    if hints:
        print()
        print("Recommended (one-time): add .quality-gate/ to your linter ignore lists so")
        print("they don't try to format/lint the gate's own files:")
        for h in hints:
            print(h)
    return EXIT_PASSED


def cmd_establish(args: argparse.Namespace) -> int:
    from quality_gate.lib import (
        baseline_io,
        config as config_mod,
        detect,
        security,
        validate_language,
    )

    repo = _repo_root(getattr(args, "cwd", None))
    try:
        cfg = config_mod.load(repo)
    except config_mod.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    main = args.main_branch or config_mod.main_branch(cfg)
    anchor_ref = args.anchor_ref or main

    branch = baseline_io.current_branch(repo) or main
    is_main = branch == main

    mode = args.mode
    if is_main and mode == "extend":
        print(
            "establish error: cannot use --mode extend on main "
            "(main has no anchor to itself; use --mode replace to refresh main's baseline)",
            file=sys.stderr,
        )
        return EXIT_CONFIG_ERROR

    existing_intent = None
    if not is_main:
        try:
            existing_intent = baseline_io.read_branch_intent(repo)
        except baseline_io.BranchIntentError as exc:
            print(f"branch intent error: {exc}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        if existing_intent is not None and not args.force:
            prev_mode = existing_intent.get("mode", "?")
            prev_at = existing_intent.get("established_at", "?")
            prev_commit = existing_intent.get("established_commit", "?")
            print(
                "establish refused: branch already declared "
                f"(mode={prev_mode!r}, established at {prev_commit} on {prev_at}). "
                "Use --force to override.",
                file=sys.stderr,
            )
            return EXIT_CONFIG_ERROR

    # In replace mode (or main with replace) we need a fresh snapshot.
    snapshot_needed = mode == "replace"

    # On main with replace, an existing branch.json is leakage — warn + remove.
    if is_main:
        try:
            leaked = baseline_io.read_branch_intent(repo)
        except baseline_io.BranchIntentError:
            leaked = None
        if leaked is not None:
            print(
                "warning: branch.json present on main (likely leaked from a merge); removing.",
                file=sys.stderr,
            )
            baseline_io.delete_branch_intent(repo)

    if snapshot_needed:
        projects = detect.detect(repo, cfg)
        if not projects:
            print(f"warning: {_NO_PROJECTS_HINT}", file=sys.stderr)
        per_project, _, err = _collect_project_metrics(repo, projects)
        if err is not None:
            return err
        proj_metrics: dict[str, Any] = {}
        for p in projects:
            data = per_project.get(p["project_key"])
            if data is None:
                continue
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
            "main_branch": main,
            "tools_versions": {},
            "projects": proj_metrics,
        }
        baseline_io.write_baseline(repo, payload)
        print(f"baseline written: {repo / baseline_io.BASELINE_RELPATH}")
    elif not is_main:
        # extend on a feature branch: ensure no orphan baseline.json from a prior replace
        if baseline_io.delete_baseline(repo):
            print(
                f"removed orphan baseline.json (no longer valid in 'extend' mode): "
                f"{repo / baseline_io.BASELINE_RELPATH}",
                file=sys.stderr,
            )

    # Write branch.json only on non-main branches.
    if not is_main:
        intent = {
            "schema_version": BRANCH_SCHEMA_VERSION,
            "mode": mode,
            "anchor_ref": anchor_ref,
            "established_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "established_commit": _git_head(repo),
        }
        if args.rationale:
            intent["rationale"] = args.rationale
        baseline_io.write_branch_intent(repo, intent)
        print(f"branch intent written: {repo / baseline_io.BRANCH_RELPATH} (mode={mode})")

    print()
    print("Next steps:")
    if not is_main:
        print("  git add .quality-gate/branch.json", end="")
        if snapshot_needed:
            print(" .quality-gate/baseline.json", end="")
        print()
        print("  git commit -m \"chore(qg): establish branch intent\"")
    else:
        print("  git add .quality-gate/baseline.json")
        print("  git commit -m \"chore(qg): refresh baseline on main\"")
    return EXIT_PASSED


def cmd_run(args: argparse.Namespace) -> int:
    from quality_gate.lib import (
        baseline_io,
        config as config_mod,
        detect,
        ratchet,
        report,
    )

    repo = _repo_root(getattr(args, "cwd", None))
    try:
        cfg = config_mod.load(repo)
    except config_mod.ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    main = args.main_branch or config_mod.main_branch(cfg)
    branch = baseline_io.current_branch(repo) or main
    is_main = branch == main
    preview = bool(getattr(args, "preview", False))

    # Branch intent — required off main (skipped in preview mode).
    intent: Optional[dict] = None
    if not preview:
        try:
            intent = baseline_io.read_branch_intent(repo)
        except baseline_io.BranchIntentError as exc:
            print(f"branch intent error: {exc}", file=sys.stderr)
            return EXIT_CONFIG_ERROR

    if preview:
        pass  # skip intent checks; no baseline read; no ratchet
    elif is_main and intent is not None:
        print(
            "warning: branch.json present on main (likely leaked from a merge). "
            "Ignoring it; consider 'git rm .quality-gate/branch.json' to clean up.",
            file=sys.stderr,
        )
        intent = None

    if not preview and not is_main and intent is None:
        print(_no_intent_message(branch), file=sys.stderr)
        return EXIT_NO_INTENT

    mode = intent["mode"] if intent else None
    anchor_ref = (intent["anchor_ref"] if intent else main)

    # Detect projects.
    projects = detect.detect(repo, cfg)
    if not projects:
        print(f"warning: {_NO_PROJECTS_HINT}", file=sys.stderr)
    if args.language:
        projects = [p for p in projects if p["language"] == args.language]
    if args.only:
        only = set(args.only.split(","))
        projects = [p for p in projects if p["project_key"] in only]
    if (args.language or args.only) and not projects:
        print("warning: no projects remaining after applying --language / --only filters.", file=sys.stderr)

    # Run language packs.
    current, tools_missing_any, err = _collect_project_metrics(repo, projects)
    if err is not None:
        return err

    # Baseline read (mode-aware). Skipped entirely in preview mode.
    if preview:
        baseline = None
        refs_consulted: list[str] = []
        regressions: list[dict] = []
        gate_status = "PREVIEW"
    else:
        try:
            baseline, refs_consulted = baseline_io.read_baseline(
                repo, mode=mode, anchor_ref=anchor_ref, on_main=is_main,
            )
        except baseline_io.BaselineError as exc:
            print(f"baseline error: {exc}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR

        regressions = ratchet.compare(current, baseline)

        # Determine gate status (textual, for the report Summary).
        if baseline is None:
            gate_status = "NO_BASELINE"
        elif regressions:
            gate_status = "FAILED"
        elif tools_missing_any:
            gate_status = "PASSED_WITH_GAPS"
        else:
            gate_status = "PASSED"

    # Compute per-project metric paths that exist in `current` but have no baseline
    # value. These cannot be ratcheted yet — render them as informational.
    unratcheted: dict[str, list[str]] = {}
    if not preview:
        baseline_projects = (baseline or {}).get("projects", {}) if baseline else {}
        for pkey, pdata in current.items():
            base_metrics = (baseline_projects.get(pkey, {}) or {}).get("metrics", {})
            missing: list[str] = []
            for group, leaves in (
                ("coverage", ("line_pct", "branch_pct")),
                ("duplication", ("pct",)),
            ):
                base_group = base_metrics.get(group, {}) or {}
                cur_group = pdata.get(group, {}) or {}
                for leaf in leaves:
                    if cur_group.get(leaf) is not None and base_group.get(leaf) is None:
                        missing.append(f"{group}.{leaf}")
            if missing:
                unratcheted[pkey] = missing

    md = report.render(
        projects=current,
        regressions=regressions,
        commit=_git_head(repo),
        tools_versions={},
        gate_status=gate_status,
        mode=("main" if is_main else mode),
        anchor_ref=(None if is_main else anchor_ref),
        unratcheted=unratcheted,
        preview=preview,
    )
    report_path = repo / ".quality-gate" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(md, encoding="utf-8")
    print(f"report: {report_path}")
    print()
    print(md)

    if preview:
        return EXIT_PASSED
    if baseline is None:
        print()
        print(
            _no_baseline_message(
                mode=("main" if is_main else (mode or "?")),
                anchor_ref=anchor_ref,
                refs_consulted=refs_consulted,
            ),
            file=sys.stderr,
        )
        return EXIT_NO_BASELINE
    if regressions:
        return EXIT_FAILED
    if tools_missing_any:
        return EXIT_PASSED_WITH_GAPS
    return EXIT_PASSED


def cmd_status(args: argparse.Namespace) -> int:
    repo = _repo_root(getattr(args, "cwd", None))
    report_path = repo / ".quality-gate" / "report.md"
    if not report_path.is_file():
        print("no report; run `python -m quality_gate run` first")
        return EXIT_NO_BASELINE
    text = report_path.read_text(encoding="utf-8")
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
    parser.add_argument("--debug", action="store_true", help="print traceback on internal errors")
    sub = parser.add_subparsers(
        dest="command", required=True,
        metavar="{init,establish,run,status,to-backlog}",
    )

    p_init = sub.add_parser("init", help="scaffold .quality-gate/ in the target repo")
    p_init.set_defaults(func=cmd_init)

    p_est = sub.add_parser(
        "establish",
        help="declare branch intent (mode=extend|replace); writes branch.json (and baseline.json in replace mode)",
    )
    p_est.add_argument("--mode", required=True, choices=["extend", "replace"], help="branch intent mode")
    p_est.add_argument("--anchor-ref", help="git ref to anchor against (default: main_branch)")
    p_est.add_argument("--rationale", help="human-readable note explaining the choice")
    p_est.add_argument("--force", action="store_true", help="overwrite existing branch.json/baseline.json")
    p_est.add_argument("--main-branch", help="override main branch name")
    p_est.set_defaults(func=cmd_establish)

    p_run = sub.add_parser("run", help="detect projects, run gates, emit report")
    p_run.add_argument("--language", help="restrict to a single language (python|go|rust|bunjs)")
    p_run.add_argument("--only", help="comma-separated project_keys to include")
    p_run.add_argument("--main-branch", help="override main branch name")
    p_run.add_argument("--preview", action="store_true",
                       help="collect metrics and render report without comparing to baseline (no ratchet, exit 0 unless internal error)")
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="print the Summary block from the last report")
    p_status.set_defaults(func=cmd_status)

    p_bk = sub.add_parser("to-backlog", help="emit per-issue backlog markdown from the last report")
    p_bk.set_defaults(func=cmd_to_backlog)

    return parser


def main(argv: list[str] | None = None) -> int:
    global _DEBUG
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "debug", False):
        _DEBUG = True
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover — internal errors path
        print(
            f"internal error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        if _DEBUG:
            traceback.print_exc(file=sys.stderr)
        else:
            print(
                "  (re-run with --debug or QG_DEBUG=1 for traceback)",
                file=sys.stderr,
            )
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
