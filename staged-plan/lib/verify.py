"""Verify primitives for staged-plan stages.

Vendored into each repo at <repo>/docs/plans/_verify.py so generated stage
scripts can `from _verify import V` regardless of executor (Claude Code, Codex,
human dev). Python 3 stdlib only - runs on Linux, macOS, Windows native.

Generated script pattern:

    #!/usr/bin/env python3
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from _verify import V

    V.assert_clean_tree()
    V.assert_commit_present(r"^feat: add X")
    V.assert_only_files_touched(["src/x.ts"], base_sha="HEAD~1")
    V.run_gate("bun run build", slug="my-plan", stage=1, gate="build")
    V.assert_report_exists("docs/plans/<slug>-stage-1-report.md")
    V.assert_no_placeholders("docs/plans/<slug>.md")
    sys.exit(V.summarize())

Design principles (review-driven):
- Guardrails, not summaries: scripts validate contract and preserve evidence;
  agent owns judgment.
- Lossless: full gate output is written to docs/plans/logs/ alongside the tail
  shown in stdout, so a 20-line tail never costs the underlying evidence.
- Cross-platform: stdlib only. No grep, no bash, no shell-out for matching.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Resolve repo root once. Stage scripts live at <repo>/docs/plans/, so the
# repo root is two parents up from this module's location.
_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODULE_DIR.parent.parent if _MODULE_DIR.name == "plans" else None


def _resolve(path: str | Path) -> Path:
    """Resolve path relative to repo root if known, else cwd."""
    p = Path(path)
    if p.is_absolute():
        return p
    if _REPO_ROOT is not None:
        return (_REPO_ROOT / p).resolve()
    return p.resolve()


def _logs_dir() -> Path:
    """Where full gate logs are written."""
    base = _REPO_ROOT if _REPO_ROOT is not None else Path.cwd()
    d = base / "docs" / "plans" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    log_path: Path | None = None


@dataclass
class _Verifier:
    checks: list[Check] = field(default_factory=list)

    def _record(self, name: str, ok: bool, detail: str = "", log_path: Path | None = None) -> bool:
        self.checks.append(Check(name=name, ok=ok, detail=detail, log_path=log_path))
        marker = "PASS" if ok else "FAIL"
        line = f"[{marker}] {name}"
        if detail and not ok:
            line += f"\n        {detail}"
        if log_path is not None:
            line += f"\n        full log: {log_path}"
        print(line)
        return ok

    # ------------------------------------------------------------------ gates

    def run_gate(
        self,
        cmd: str,
        *,
        cwd: str | None = None,
        timeout: int = 600,
        slug: str | None = None,
        stage: int | None = None,
        gate: str | None = None,
    ) -> bool:
        """Execute a shell gate command. Pass = exit 0.

        Full stdout+stderr is written to docs/plans/logs/<slug>-stage-<N>-<gate>.log
        when slug/stage/gate are provided. The tail (last 20 lines) is shown in
        the on-screen FAIL detail; the log file always has the complete output.
        Partial output is preserved on timeout.
        """
        log_path: Path | None = None
        if slug and stage is not None and gate:
            safe_gate = re.sub(r"[^A-Za-z0-9._-]+", "_", gate)
            log_path = _logs_dir() / f"{slug}-stage-{stage}-{safe_gate}.log"

        stdout, stderr, returncode, timed_out = "", "", -1, False
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")

        if log_path is not None:
            header = f"$ {cmd}\n# cwd={cwd or os.getcwd()} timeout={timeout}s timed_out={timed_out} returncode={returncode}\n\n"
            log_path.write_text(header + "--- STDOUT ---\n" + stdout + "\n--- STDERR ---\n" + stderr)

        if timed_out:
            return self._record(
                f"gate: {cmd}",
                False,
                f"timeout after {timeout}s (partial output preserved)",
                log_path,
            )

        ok = returncode == 0
        detail = ""
        if not ok:
            tail = (stdout + stderr).strip().splitlines()[-20:]
            detail = "\n        ".join(tail)
        return self._record(f"gate: {cmd}", ok, detail, log_path)

    # ------------------------------------------------------------------ git

    def assert_clean_tree(self, *, cwd: str | None = None) -> bool:
        """Working tree clean: git status --porcelain returns empty."""
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        clean = proc.returncode == 0 and proc.stdout.strip() == ""
        detail = proc.stdout.strip() if not clean else ""
        return self._record("working tree clean", clean, detail)

    def assert_commit_present(
        self, subject_pattern: str, *, depth: int = 20, cwd: str | None = None
    ) -> bool:
        """Last `depth` commits contain a subject matching `subject_pattern` (regex)."""
        proc = subprocess.run(
            ["git", "log", f"-{depth}", "--pretty=format:%H %s"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return self._record(
                f"commit present: /{subject_pattern}/", False, proc.stderr.strip()
            )
        rx = re.compile(subject_pattern)
        for line in proc.stdout.splitlines():
            if rx.search(line):
                return self._record(
                    f"commit present: /{subject_pattern}/", True, line[:80]
                )
        return self._record(
            f"commit present: /{subject_pattern}/",
            False,
            f"no match in last {depth} commits",
        )

    def assert_only_files_touched(
        self,
        allowlist: list[str],
        *,
        base_sha: str = "HEAD~1",
        head_sha: str = "HEAD",
        cwd: str | None = None,
    ) -> bool:
        """Files changed between base_sha..head_sha are a subset of allowlist.

        For the standard pattern (one delivery commit per stage with the
        post-stage report committed alongside the code), pass the report path
        in the allowlist as well.
        """
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base_sha}..{head_sha}"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return self._record(
                "scope: only declared files touched", False, proc.stderr.strip()
            )
        touched = {p.strip() for p in proc.stdout.splitlines() if p.strip()}
        allowed = set(allowlist)
        unexpected = sorted(touched - allowed)
        ok = not unexpected
        detail = "" if ok else f"unexpected: {', '.join(unexpected)}"
        return self._record("scope: only declared files touched", ok, detail)

    # --------------------------------------------------- file content (no grep)

    def _walk_files(self, paths: list[str]) -> list[Path]:
        """Expand a list of files/dirs into a flat list of files.

        Pure Python; no shell-out to grep/find. Skips common noise (.git,
        node_modules, dist, build, .venv, __pycache__, target).
        """
        skip_dirs = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", "target", ".next"}
        result: list[Path] = []
        for raw in paths:
            p = _resolve(raw)
            if p.is_file():
                result.append(p)
            elif p.is_dir():
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    for f in files:
                        result.append(Path(root) / f)
        return result

    def _scan(self, pattern: str, paths: list[str], max_hits: int = 5) -> list[str]:
        rx = re.compile(pattern)
        hits: list[str] = []
        for f in self._walk_files(paths):
            try:
                with f.open("r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if rx.search(line):
                            hits.append(f"{f}:{lineno}: {line.rstrip()}")
                            if len(hits) >= max_hits:
                                return hits
            except OSError:
                continue
        return hits

    def assert_grep_zero(self, pattern: str, paths: list[str]) -> bool:
        """Invariant: pattern must NOT appear in any file under `paths`."""
        hits = self._scan(pattern, paths)
        ok = not hits
        detail = "" if ok else "\n        ".join(hits)
        return self._record(f"invariant absent: /{pattern}/", ok, detail)

    def assert_grep_nonzero(self, pattern: str, paths: list[str]) -> bool:
        """Invariant: pattern MUST appear at least once in `paths`."""
        hits = self._scan(pattern, paths, max_hits=1)
        ok = bool(hits)
        detail = "" if ok else "no match"
        return self._record(f"invariant present: /{pattern}/", ok, detail)

    # ---------------------------------------------------------------- artifacts

    def assert_report_exists(self, path: str) -> bool:
        """Post-stage report file exists and is non-empty.

        Path is resolved against repo root when relative, so this works whether
        the script is invoked from repo root, from docs/plans/, or elsewhere.
        """
        p = _resolve(path)
        ok = p.is_file() and p.stat().st_size > 0
        detail = "" if ok else f"missing or empty: {p}"
        return self._record(f"report exists: {path}", ok, detail)

    def assert_file_exists(self, path: str) -> bool:
        p = _resolve(path)
        ok = p.exists()
        return self._record(f"file exists: {path}", ok, "" if ok else f"missing: {p}")

    def assert_file_absent(self, path: str) -> bool:
        p = _resolve(path)
        ok = not p.exists()
        return self._record(f"file absent: {path}", ok, "" if ok else f"still exists: {p}")

    # ----------------------------------------------------------- plan validation

    _PLACEHOLDER_RX = re.compile(r"<FILL[^>]*>|<FILL-OR-DELETE[^>]*>|<repo>|<plan-slug>|<plan title>|<absolute path>")

    def assert_no_placeholders(self, plan_path: str) -> bool:
        """Plan file contains no unfilled scaffold placeholders.

        Run this BEFORE Phase 2 launches Stage 1. A plan with surviving
        <FILL>, <FILL-OR-DELETE>, or other scaffold tokens is incomplete and
        will cause subagents to follow boilerplate instead of real instructions.
        """
        p = _resolve(plan_path)
        if not p.is_file():
            return self._record(f"plan filled: {plan_path}", False, f"missing: {p}")
        text = p.read_text(encoding="utf-8", errors="replace")
        hits: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if self._PLACEHOLDER_RX.search(line):
                hits.append(f"{p.name}:{lineno}: {line.strip()[:120]}")
                if len(hits) >= 10:
                    break
        ok = not hits
        detail = "" if ok else "\n        ".join(hits)
        return self._record(f"plan filled: {plan_path}", ok, detail)

    # ---------------------------------------------------------------- summary

    def summarize(self) -> int:
        """Print a summary table; return 0 if all green, else 1."""
        passed = sum(1 for c in self.checks if c.ok)
        total = len(self.checks)
        print()
        print(f"=== {passed}/{total} checks passed ===")
        if passed != total:
            print("Failures:")
            for c in self.checks:
                if not c.ok:
                    print(f"  - {c.name}")
                    if c.detail:
                        for line in c.detail.splitlines():
                            print(f"      {line}")
                    if c.log_path is not None:
                        print(f"      full log: {c.log_path}")
        return 0 if passed == total else 1


V = _Verifier()
