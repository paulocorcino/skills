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
    V.assert_commit_present("feat: add X")
    V.assert_only_files_touched(["src/x.ts"], base_sha="HEAD~1")
    V.run_gate("bun run build")
    V.assert_report_exists("docs/plans/<slug>-stage-1-report.md")
    sys.exit(V.summarize())
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class _Verifier:
    checks: list[Check] = field(default_factory=list)

    def _record(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name=name, ok=ok, detail=detail))
        marker = "PASS" if ok else "FAIL"
        line = f"[{marker}] {name}"
        if detail and not ok:
            line += f"\n        {detail}"
        print(line)
        return ok

    def run_gate(self, cmd: str, *, cwd: str | None = None) -> bool:
        """Execute a shell gate command. Pass = exit 0."""
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            return self._record(f"gate: {cmd}", False, "timeout after 600s")
        ok = proc.returncode == 0
        detail = ""
        if not ok:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-20:]
            detail = "\n        ".join(tail)
        return self._record(f"gate: {cmd}", ok, detail)

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
        """Files changed between base_sha..head_sha are a subset of allowlist."""
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

    def assert_grep_zero(
        self,
        pattern: str,
        paths: list[str],
        *,
        cwd: str | None = None,
    ) -> bool:
        """Invariant: pattern must NOT appear in any of `paths`."""
        cmd = ["grep", "-rEn", "--", pattern, *paths]
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        # grep exit 1 = no match (good); exit 0 = matches found (bad); exit >=2 = error.
        if proc.returncode == 1:
            return self._record(f"invariant absent: /{pattern}/", True)
        if proc.returncode == 0:
            hits = proc.stdout.strip().splitlines()[:5]
            return self._record(
                f"invariant absent: /{pattern}/",
                False,
                "\n        ".join(hits),
            )
        return self._record(
            f"invariant absent: /{pattern}/", False, proc.stderr.strip()
        )

    def assert_grep_nonzero(
        self,
        pattern: str,
        paths: list[str],
        *,
        cwd: str | None = None,
    ) -> bool:
        """Invariant: pattern MUST appear at least once in `paths`."""
        cmd = ["grep", "-rEn", "--", pattern, *paths]
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if proc.returncode == 0:
            return self._record(f"invariant present: /{pattern}/", True)
        if proc.returncode == 1:
            return self._record(
                f"invariant present: /{pattern}/", False, "no match"
            )
        return self._record(
            f"invariant present: /{pattern}/", False, proc.stderr.strip()
        )

    def assert_report_exists(self, path: str) -> bool:
        """Post-stage report file exists and is non-empty."""
        p = Path(path)
        ok = p.is_file() and p.stat().st_size > 0
        detail = "" if ok else f"missing or empty: {path}"
        return self._record(f"report exists: {path}", ok, detail)

    def assert_file_exists(self, path: str) -> bool:
        p = Path(path)
        ok = p.exists()
        return self._record(f"file exists: {path}", ok, "" if ok else f"missing: {path}")

    def assert_file_absent(self, path: str) -> bool:
        p = Path(path)
        ok = not p.exists()
        return self._record(f"file absent: {path}", ok, "" if ok else f"still exists: {path}")

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
        return 0 if passed == total else 1


V = _Verifier()
