#!/usr/bin/env python3
"""stop_audit.py — Stop hook for reviewer-v3.

Reads JSON from stdin (Claude Code stop-hook contract). Gates on a per-session
marker file written by mark_active.py. If the gate is open, extracts the last
assistant message's `## Coverage` block, runs fact_pack.py + audit.py, and emits
a `decision: block` (with provocation) on gap, or `decision: approve` (with
audit output as systemMessage) on pass/partial. Fail-open on any error.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent / "scripts"
FACT_PACK = SCRIPTS_DIR / "fact_pack.py"
AUDIT = SCRIPTS_DIR / "audit.py"
STATE_DIR = Path.home() / ".claude" / "state"

PROVOCATION = (
    "these material files are not in your coverage — review them or move them "
    "to `not-reviewed` with a reason; ignore if they don't make sense for this "
    "review."
)


def emit(decision: dict) -> None:
    sys.stdout.write(json.dumps(decision))
    sys.stdout.write("\n")
    sys.stdout.flush()


def log_error(session_id: str, msg: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path = STATE_DIR / f"reviewer-v3-{session_id}.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except OSError:
        pass


def read_last_assistant_message(transcript_path: Path) -> str:
    """Return the text body of the last assistant message in the JSONL transcript."""
    if not transcript_path.exists():
        return ""
    last_text = ""
    with transcript_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Anthropic transcript shape: {"type":"assistant","message":{"role":"assistant","content":[...]}}
            msg = entry.get("message")
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                last_text = extract_text(msg.get("content"))
            elif entry.get("role") == "assistant":
                last_text = extract_text(entry.get("content"))
    return last_text


def extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(block["text"])
                elif "text" in block and isinstance(block["text"], str):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def extract_coverage_block(body: str) -> str:
    """Extract the `## Coverage` section, terminated by the next `## ` header or EOF."""
    if not body:
        return ""
    lines = body.splitlines()
    capturing = False
    out: list[str] = []
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


def extract_not_exercised_block(body: str) -> str:
    """Extract the `not exercised:` header field plus its bullet entries.

    The block is the line starting `not exercised:` followed by indented
    bullet lines (`- ...`). Stops at the next non-bullet, non-blank line
    that is not indented (i.e. the next header field or section).
    """
    if not body:
        return ""
    lines = body.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if not capturing:
            if re.match(r"^\s*not\s*exercised\s*:", line, flags=re.IGNORECASE):
                capturing = True
                out.append(line)
            continue
        # Inside the block.
        if stripped.startswith("## "):
            break
        if stripped.startswith("- "):
            out.append(line)
            continue
        if not stripped:
            # Blank line: keep collecting in case bullets resume below;
            # but if the next non-blank is a non-bullet, we'll break there.
            out.append(line)
            continue
        # Non-bullet, non-blank, non-header → next field. Stop.
        break
    # Trim trailing blanks.
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def parse_base_from_body(body: str) -> str:
    m = re.search(r"^\s*base:\s*(\S.*?)\s*$", body, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    return "origin/main"


def parse_verdict_from_body(body: str) -> str:
    m = re.search(r"^\s*verdict:\s*(\S.*?)\s*$", body, flags=re.MULTILINE)
    if m:
        return m.group(1).strip().upper()
    return ""


def parse_auto_narrow_trailer(audit_output: str) -> tuple[bool, str, str]:
    """Return (auto_narrowed, narrowed_by_user_request, ratio_text).

    `narrowed_by_user_request` is one of "true", "false", "unspecified", "".
    `ratio_text` is e.g. "487/494" or "" if not parsed.
    """
    auto_narrowed = False
    narrowed = ""
    ratio = ""
    head_re = re.compile(
        r"^scope-auto-narrowed:\s*yes\s*\((\d+)/(\d+)\s*files",
        re.IGNORECASE,
    )
    flag_re = re.compile(
        r"narrowed-by-user-request:\s*(true|false|unspecified)",
        re.IGNORECASE,
    )
    for line in audit_output.splitlines():
        head_m = head_re.search(line)
        if head_m:
            auto_narrowed = True
            ratio = f"{head_m.group(1)}/{head_m.group(2)}"
            continue
        flag_m = flag_re.search(line)
        if flag_m:
            narrowed = flag_m.group(1).lower()
    return auto_narrowed, narrowed, ratio


def run_fact_pack(repo: Path, base: str, target: str, tmpdir: Path) -> Path:
    out_path = tmpdir / "fact_pack.json"
    proc = subprocess.run(
        [sys.executable, str(FACT_PACK), "--repo", str(repo), "--target", target, "--base", base],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"fact_pack failed (exit {proc.returncode}): {proc.stderr.strip()[:400]}")
    out_path.write_text(proc.stdout, encoding="utf-8")
    return out_path


def run_audit(
    coverage: str, fact_pack: Path, not_exercised: str | None, tmpdir: Path
) -> tuple[int, str]:
    cmd = [sys.executable, str(AUDIT), "--coverage", "-", "--fact-pack", str(fact_pack)]
    if not_exercised and not_exercised.strip():
        ne_path = tmpdir / "not_exercised.md"
        ne_path.write_text(not_exercised, encoding="utf-8")
        cmd.extend(["--not-exercised", str(ne_path)])
    proc = subprocess.run(
        cmd,
        input=coverage,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        emit({"decision": "approve"})
        return 0

    session_id = str(payload.get("session_id") or "").strip()
    transcript_path_str = payload.get("transcript_path") or ""
    cwd = payload.get("cwd") or "."
    stop_hook_active = bool(payload.get("stop_hook_active"))

    # Gate: only operate on sessions explicitly marked by reviewer-v3 SKILL.md.
    if not session_id:
        emit({"decision": "approve"})
        return 0
    marker = STATE_DIR / f"reviewer-v3-{session_id}"
    if not marker.exists():
        emit({"decision": "approve"})
        return 0

    # Re-entry cap: if we already provoked once, do not provoke again.
    if stop_hook_active:
        emit({"decision": "approve"})
        return 0

    try:
        transcript_path = Path(transcript_path_str) if transcript_path_str else None
        if transcript_path is None:
            emit({"decision": "approve"})
            return 0

        body = read_last_assistant_message(transcript_path)
        if not body.strip():
            emit({"decision": "approve"})
            return 0

        coverage_block = extract_coverage_block(body)
        if not coverage_block.strip():
            # No coverage block emitted. Provoke for one.
            emit(
                {
                    "decision": "block",
                    "reason": (
                        "Your report has no `## Coverage` section. "
                        "Emit one (Option F: list only `excluded:` and `not-reviewed:`); "
                        "everything else is implicitly reviewed."
                    ),
                }
            )
            return 0

        repo = Path(cwd).resolve()
        if not (repo / ".git").exists():
            emit({"decision": "approve"})
            return 0

        base = parse_base_from_body(body)

        with tempfile.TemporaryDirectory(prefix="reviewer-v3-") as td:
            tmpdir = Path(td)
            fact_pack_path = run_fact_pack(repo, base, "working-tree", tmpdir)
            not_exercised_block = extract_not_exercised_block(body)
            exit_code, audit_output = run_audit(
                coverage_block, fact_pack_path, not_exercised_block, tmpdir
            )

        if exit_code == 2:
            # Gap: extract the gap line for the provocation reason.
            gap_line = ""
            for line in audit_output.splitlines():
                if line.startswith("gap:"):
                    gap_line = line.strip()
                    break
            reason = f"{PROVOCATION}\n\n{audit_output.strip()}"
            emit({"decision": "block", "reason": reason})
            return 0

        # pass or partial. Apply A3 verdict ceiling: if scope auto-narrowed
        # without explicit user-request flag and the report still claims plain
        # APPROVED, provoke a verdict downgrade.
        auto_narrowed, narrowed_flag, ratio = parse_auto_narrow_trailer(audit_output)
        verdict = parse_verdict_from_body(body)
        if (
            auto_narrowed
            and narrowed_flag != "true"
            and verdict == "APPROVED"
        ):
            ratio_txt = ratio or "<n>/<m>"
            ceiling_reason = (
                f"You declared {ratio_txt} material files as not-reviewed without "
                "`narrowed-by-user-request: true`. Lower verdict to "
                "`APPROVED-WITH-FIXES` or widen coverage.\n\n"
                f"{audit_output.strip()}"
            )
            emit({"decision": "block", "reason": ceiling_reason})
            return 0

        # Otherwise approve and surface the audit output as systemMessage.
        emit({"decision": "approve", "systemMessage": audit_output.strip()})
        return 0

    except Exception as exc:  # noqa: BLE001
        log_error(
            session_id,
            f"stop_audit error: {exc}\n{traceback.format_exc()}",
        )
        emit({"decision": "approve"})
        return 0


if __name__ == "__main__":
    sys.exit(main())
