#!/usr/bin/env python3
"""run_smoke.py — end-to-end smoke test for reviewer-v3.

Invokes the `claude` CLI with /reviewer-v3 against
~/somoschat/repositories/baileys2api_bun on `feat/dev-setup`, captures every
side effect (stream JSON, transcript, settings.json before/after, marker,
hook log, reference fact_pack + audit), and writes a PASS/FAIL SUMMARY.md
into a timestamped run directory.

Usage:
    python3 run_smoke.py [--target-repo PATH] [--prompt-file PATH] [--budget USD]

Default target: /home/corcino/somoschat/repositories/baileys2api_bun
Default prompt: /home/corcino/.claude/skills/reviewer-v3/prompt_teste.md
Default budget: 10.00
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
HOOKS_DIR = SKILL_DIR / "hooks"
TESTS_DIR = SKILL_DIR / "tests"
RUNS_DIR = TESTS_DIR / "runs"

DEFAULT_TARGET = Path("/home/corcino/somoschat/repositories/baileys2api_bun")
DEFAULT_PROMPT = SKILL_DIR / "prompt_teste.md"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
STATE_DIR = Path.home() / ".claude" / "state"
PROJECTS_DIR = Path.home() / ".claude" / "projects"

REQUIRED_SECTIONS = (
    "## Findings",
    "## Coverage",
    "## Open Questions",
    "## Verification",
    "## Notes",
)


def log(msg: str) -> None:
    print(f"[smoke] {msg}", flush=True)


def snapshot_settings(out: Path) -> str:
    if SETTINGS_PATH.exists():
        text = SETTINGS_PATH.read_text(encoding="utf-8")
    else:
        text = ""
    out.write_text(text, encoding="utf-8")
    return text


def transcript_for(session_id: str, cwd: Path) -> Path | None:
    """Find the JSONL transcript matching session_id under ~/.claude/projects/."""
    if not PROJECTS_DIR.exists():
        return None
    for candidate in PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return candidate
    return None


def extract_last_assistant_text(transcript: Path) -> str:
    if not transcript.exists():
        return ""
    last = ""
    with transcript.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = entry.get("message")
            content = None
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content")
            elif entry.get("role") == "assistant":
                content = entry.get("content")
            if content is None:
                continue
            if isinstance(content, str):
                last = content
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        parts.append(block)
                last = "\n".join(parts)
    return last


def extract_coverage_block(body: str) -> str:
    if not body:
        return ""
    lines = body.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.strip().lower().startswith("## coverage"):
            capturing = True
            out.append(line)
            continue
        if capturing and line.startswith("## ") and not line.strip().lower().startswith("## coverage"):
            break
        if capturing:
            out.append(line)
    return "\n".join(out)


def install_marker(text: str) -> bool:
    """Look for any reviewer-v3 stop_audit.py command in settings.json."""
    if not text.strip():
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    stop = data.get("hooks", {}).get("Stop", [])
    if not isinstance(stop, list):
        return False
    for group in stop:
        for inner in (group or {}).get("hooks", []) or []:
            if "reviewer-v3/hooks/stop_audit.py" in (inner or {}).get("command", ""):
                return True
    return False


def count_stop_hook_events(stream_jsonl: Path) -> tuple[int, list[dict]]:
    if not stream_jsonl.exists():
        return 0, []
    matches: list[dict] = []
    with stream_jsonl.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Hook events when --include-hook-events is on. Shape varies; match
            # generously: any object whose JSON representation references the
            # Stop hook event name or our hook script path.
            blob = json.dumps(evt)
            if "stop_audit.py" in blob or '"hook_event_name":"Stop"' in blob or '"hook":"Stop"' in blob:
                matches.append(evt)
    return len(matches), matches


def run_reference_fact_pack(repo: Path, base: str, out: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "fact_pack.py"), "--repo", str(repo), "--target", "working-tree", "--base", base],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        (out.parent / "fact-pack.stderr.log").write_text(proc.stderr, encoding="utf-8")
        return False, proc.stderr
    return True, ""


def run_reference_audit(coverage_text: str, fact_pack_path: Path, out: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "audit.py"), "--coverage", "-", "--fact-pack", str(fact_pack_path)],
        input=coverage_text,
        capture_output=True,
        text=True,
        timeout=15,
    )
    out.write_text(proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
    return proc.returncode, proc.stdout


def negative_gate_check(run_dir: Path) -> tuple[bool, str]:
    """Confirm stop_audit.py exits with `decision: approve` when no marker is set."""
    fake_input = json.dumps(
        {
            "session_id": "smoke-no-marker-" + uuid.uuid4().hex[:8],
            "transcript_path": "/tmp/nonexistent",
            "cwd": "/tmp",
            "stop_hook_active": False,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "stop_audit.py")],
        input=fake_input,
        capture_output=True,
        text=True,
        timeout=10,
    )
    out = proc.stdout.strip()
    (run_dir / "negative-gate.txt").write_text(
        f"input: {fake_input}\nstdout: {out}\nstderr: {proc.stderr}\nexit: {proc.returncode}\n",
        encoding="utf-8",
    )
    try:
        decision = json.loads(out)
    except json.JSONDecodeError:
        return False, f"non-JSON output: {out!r}"
    return decision.get("decision") == "approve" and proc.returncode == 0, out


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-test reviewer-v3 via the claude CLI.")
    ap.add_argument("--target-repo", default=str(DEFAULT_TARGET))
    ap.add_argument("--prompt-file", default=str(DEFAULT_PROMPT))
    ap.add_argument("--budget", default="10.00")
    ap.add_argument("--no-claude", action="store_true", help="Skip claude invocation (debug only)")
    args = ap.parse_args()

    target_repo = Path(args.target_repo).resolve()
    prompt_file = Path(args.prompt_file).resolve()

    if not target_repo.exists() or not (target_repo / ".git").exists():
        print(f"target repo not a git checkout: {target_repo}", file=sys.stderr)
        return 1
    if not prompt_file.exists():
        print(f"prompt file missing: {prompt_file}", file=sys.stderr)
        return 1

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"run dir: {run_dir}")

    session_id = str(uuid.uuid4())
    (run_dir / "session_id.txt").write_text(session_id + "\n", encoding="utf-8")
    log(f"session_id: {session_id}")

    # Snapshot before
    settings_before = snapshot_settings(run_dir / "settings.before.json")
    install_before = install_marker(settings_before)
    log(f"settings.json install marker before: {install_before}")

    # Compose the prompt: prepend the literal slash command so the SKILL trigger fires.
    user_prompt_body = prompt_file.read_text(encoding="utf-8").strip()
    full_prompt = f"/reviewer-v3 {user_prompt_body}"
    (run_dir / "prompt.txt").write_text(full_prompt + "\n", encoding="utf-8")

    stream_path = run_dir / "claude-stream.jsonl"
    stderr_path = run_dir / "claude-stderr.log"
    debug_path = run_dir / "claude-debug.log"

    cmd = [
        "claude",
        "-p",
        full_prompt,
        "--session-id",
        session_id,
        "--output-format",
        "stream-json",
        "--include-hook-events",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--add-dir",
        str(SKILL_DIR),
        "--add-dir",
        "/home/corcino/somoschat",
        "--add-dir",
        str(target_repo),
        "--debug-file",
        str(debug_path),
        "--max-budget-usd",
        args.budget,
    ]
    (run_dir / "command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    log("invoking claude CLI (this may take a few minutes)…")

    if args.no_claude:
        log("--no-claude set; skipping invocation")
    else:
        with stream_path.open("w", encoding="utf-8") as out_fh, stderr_path.open(
            "w", encoding="utf-8"
        ) as err_fh:
            proc = subprocess.Popen(
                cmd,
                cwd=str(target_repo),
                stdout=out_fh,
                stderr=err_fh,
            )
            rc = proc.wait()
            log(f"claude exit code: {rc}")
            (run_dir / "claude-exit.txt").write_text(str(rc) + "\n", encoding="utf-8")

    # Snapshot after
    settings_after = snapshot_settings(run_dir / "settings.after.json")
    install_after = install_marker(settings_after)
    log(f"settings.json install marker after: {install_after}")

    # Settings diff (textual)
    if settings_before != settings_after:
        diff_proc = subprocess.run(
            ["diff", "-u", str(run_dir / "settings.before.json"), str(run_dir / "settings.after.json")],
            capture_output=True,
            text=True,
        )
        (run_dir / "settings.diff").write_text(diff_proc.stdout, encoding="utf-8")
    else:
        (run_dir / "settings.diff").write_text("(no changes)\n", encoding="utf-8")

    # Marker presence
    marker = STATE_DIR / f"reviewer-v3-{session_id}"
    marker_present = marker.exists()
    (run_dir / "marker-status.txt").write_text(
        f"path: {marker}\nexists: {marker_present}\n",
        encoding="utf-8",
    )
    log(f"marker present: {marker_present}")

    # Hook log
    hook_log = STATE_DIR / f"reviewer-v3-{session_id}.log"
    if hook_log.exists():
        shutil.copy2(hook_log, run_dir / "hook.log")
    else:
        (run_dir / "hook.log").write_text("(no hook log written)\n", encoding="utf-8")

    # Transcript
    transcript = transcript_for(session_id, target_repo)
    if transcript and transcript.exists():
        shutil.copy2(transcript, run_dir / "transcript.jsonl")
        last_msg = extract_last_assistant_text(transcript)
    else:
        last_msg = ""
    (run_dir / "final-message.md").write_text(last_msg or "(no assistant message captured)\n", encoding="utf-8")
    coverage = extract_coverage_block(last_msg)
    (run_dir / "coverage-block.md").write_text(coverage or "(no ## Coverage block found)\n", encoding="utf-8")

    sections_present = {sec: sec in last_msg for sec in REQUIRED_SECTIONS}

    # Stop hook event count from stream JSON
    hook_count, _ = count_stop_hook_events(stream_path)
    log(f"stop-hook events observed: {hook_count}")

    # Reference fact_pack and audit
    fact_pack_path = run_dir / "fact-pack-reference.json"
    fp_ok, fp_err = run_reference_fact_pack(target_repo, "origin/main", fact_pack_path)
    audit_path = run_dir / "audit-reference.txt"
    audit_exit, audit_out = (None, "")
    if fp_ok and coverage:
        audit_exit, audit_out = run_reference_audit(coverage, fact_pack_path, audit_path)
    elif not coverage:
        audit_path.write_text("(skipped: no coverage block to audit)\n", encoding="utf-8")
    else:
        audit_path.write_text(f"(skipped: fact_pack failed: {fp_err})\n", encoding="utf-8")

    # Negative-gate check
    neg_ok, neg_out = negative_gate_check(run_dir)
    log(f"negative gate (no marker → approve): {'PASS' if neg_ok else 'FAIL'}")

    # Compose SUMMARY.md
    fp_data = {}
    if fp_ok and fact_pack_path.exists():
        try:
            fp_data = json.loads(fact_pack_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    material_count = len(fp_data.get("material_files", []))
    excluded_count = len(fp_data.get("excluded_files", []))

    checks = []
    checks.append(("A", "marker file exists (mark_active.py invoked)", marker_present))
    checks.append(("B", "Stop hook installed in settings.json", install_after))
    checks.append(("C", "stop_audit.py fired during the session", hook_count > 0))
    for sec in REQUIRED_SECTIONS:
        checks.append((f"D:{sec}", f"final report contains `{sec}`", sections_present[sec]))
    checks.append(("E", "fact_pack.py succeeded against target repo", fp_ok))
    checks.append(
        (
            "F",
            "audit.py reconciled the captured coverage (exit 0 or 2)",
            audit_exit in (0, 2) if audit_exit is not None else False,
        )
    )
    checks.append(("G", "stop_audit.py approves immediately when marker absent", neg_ok))

    pass_count = sum(1 for _, _, ok in checks if ok)
    total = len(checks)

    summary = [
        f"# reviewer-v3 smoke run — {timestamp}",
        "",
        f"- session_id: `{session_id}`",
        f"- target_repo: `{target_repo}`",
        f"- prompt source: `{prompt_file}`",
        f"- claude exit code: see `claude-exit.txt`",
        f"- result: **{pass_count}/{total} checks PASS**",
        "",
        "## Checks",
        "",
        "| ID | Check | Result |",
        "|---|---|---|",
    ]
    for cid, desc, ok in checks:
        summary.append(f"| {cid} | {desc} | {'PASS' if ok else 'FAIL'} |")

    summary.extend(
        [
            "",
            "## Reference data",
            "",
            f"- fact_pack: `{fact_pack_path.name}` (material={material_count}, excluded={excluded_count})",
            f"- audit_reference: `{audit_path.name}` (exit={audit_exit}, first line: `{audit_out.splitlines()[0] if audit_out else '(empty)'}`)",
            f"- coverage_block: `{(run_dir / 'coverage-block.md').name}` ({len(coverage)} chars)",
            f"- final_message: `{(run_dir / 'final-message.md').name}` ({len(last_msg)} chars)",
            f"- transcript: `{('transcript.jsonl' if (run_dir / 'transcript.jsonl').exists() else '(missing)')}`",
            f"- hook stop events captured: {hook_count}",
            f"- negative-gate output: `{neg_out}`",
            "",
            "## Files",
            "",
            "- `prompt.txt` — exact prompt sent to claude",
            "- `command.txt` — exact CLI invocation",
            "- `claude-stream.jsonl` — stream-json output (full)",
            "- `claude-stderr.log` — claude stderr",
            "- `claude-debug.log` — claude --debug-file output",
            "- `claude-exit.txt` — claude exit code",
            "- `settings.before.json` / `settings.after.json` / `settings.diff`",
            "- `marker-status.txt` — gating marker file existence",
            "- `hook.log` — error log written by stop_audit.py (if any)",
            "- `transcript.jsonl` — Anthropic conversation transcript",
            "- `final-message.md` — last assistant message body",
            "- `coverage-block.md` — extracted `## Coverage` section",
            "- `fact-pack-reference.json` — direct fact_pack.py invocation for ground truth",
            "- `audit-reference.txt` — audit.py output against the captured coverage",
            "- `negative-gate.txt` — negative-gate stop_audit.py invocation",
            "",
            "## Inspection commands",
            "",
            "```bash",
            f"cd {run_dir}",
            "less SUMMARY.md",
            "less final-message.md",
            "less coverage-block.md",
            "diff settings.before.json settings.after.json",
            "jq -c 'select(.type==\"assistant\")' transcript.jsonl | head",
            "```",
            "",
        ]
    )

    (run_dir / "SUMMARY.md").write_text("\n".join(summary), encoding="utf-8")
    log(f"SUMMARY: {pass_count}/{total} PASS — {run_dir / 'SUMMARY.md'}")
    return 0 if pass_count == total else 2


if __name__ == "__main__":
    sys.exit(main())
