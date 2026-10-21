#!/usr/bin/env python3
"""complexity.py — McCabe cyclomatic complexity of the functions a change touches.

Usage: python complexity.py --fact-pack <fact_pack.json>

Reads repo, base, target, and material_files from the fact pack, so the
complexity facts cover exactly the reviewed set. For each function whose line
range intersects a changed hunk, compares its CCN at target against the same
function at the comparison point (merge-base for a ref target, base for
working-tree). This script does not assign severity; SKILL.md's Complexity
rule does.

Output (stdout):
  complexity: ok (<n> touched functions)
  complexity: flagged (<n> touched functions, <m> above ok)
  COMPLEXITY band=<moderate|high> ccn=<n> base_ccn=<n|none> status=<new|worsened|unchanged|improved> ref=<file:line> fn=<name>
  complexity: not-exercised (<reason>)

Bands: ok <= 11, moderate 12-21, high >= 22.

Analysis uses lizard. On first run it is installed, hash-pinned from
complexity-requirements.txt, into <skill-dir>/.vendor/ — never into the target
repo or the global environment. Set REVIEWER_NO_AUTO_INSTALL=1 to disable the
install; complexity is then `not-exercised` unless lizard is already importable.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

OK_MAX = 11
MODERATE_MAX = 21

SKILL_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = SKILL_DIR / ".vendor"
REQUIREMENTS = Path(__file__).resolve().with_name("complexity-requirements.txt")
INSTALL_TIMEOUT_S = 180

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def load_lizard():
    """Return (lizard_module, None) or (None, reason)."""
    sys.path.insert(0, str(VENDOR_DIR))
    try:
        return importlib.import_module("lizard"), None
    except ImportError:
        pass
    if os.environ.get("REVIEWER_NO_AUTO_INSTALL") == "1":
        return None, "lizard not installed; auto-install disabled by REVIEWER_NO_AUTO_INSTALL"
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "--quiet", "--disable-pip-version-check", "--no-input",
                "--require-hashes", "--target", str(VENDOR_DIR),
                "-r", str(REQUIREMENTS),
            ],
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"lizard install timed out after {INSTALL_TIMEOUT_S}s"
    except OSError as exc:
        return None, f"lizard install could not start pip: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, f"lizard install failed: {tail[-1] if tail else 'pip exit ' + str(proc.returncode)}"
    importlib.invalidate_caches()
    try:
        return importlib.import_module("lizard"), None
    except ImportError as exc:
        return None, f"lizard installed but not importable: {exc}"


def run_git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def changed_lines(diff_text: str) -> set[int]:
    """New-side line numbers touched by a `git diff -U0` body."""
    lines: set[int] = set()
    for raw in diff_text.splitlines():
        m = HUNK_RE.match(raw)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count == 0:
            # Pure deletion after `start`: the enclosing function still changed.
            lines.update((start, start + 1))
        else:
            lines.update(range(start, start + count))
    return lines


def band(ccn: int) -> str:
    if ccn <= OK_MAX:
        return "ok"
    if ccn <= MODERATE_MAX:
        return "moderate"
    return "high"


def analyze(lizard, rel: str, code: str):
    return lizard.analyze_file.analyze_source_code(rel, code).function_list


def main() -> int:
    ap = argparse.ArgumentParser(description="Report McCabe complexity of functions touched by the change.")
    ap.add_argument("--fact-pack", required=True, help="JSON emitted by fact_pack.py")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pack = json.loads(Path(args.fact_pack).read_text(encoding="utf-8"))
    repo = Path(pack["repo"])
    base = pack.get("base") or ""
    target = pack.get("target") or "HEAD"
    if not base:
        print("complexity: not-exercised (fact pack has no base)")
        return 0

    lizard, reason = load_lizard()
    if lizard is None:
        print(f"complexity: not-exercised ({reason})")
        return 0
    from lizard_languages import get_reader_for

    working_tree = target == "working-tree"
    if working_tree:
        compare_ref = base
    else:
        compare_ref = (run_git(repo, "merge-base", base, target) or "").strip() or base

    touched = 0
    flagged: list[str] = []
    for rel in pack.get("material_files", []):
        if get_reader_for(rel) is None:
            continue
        if working_tree:
            path = repo / rel
            if not path.is_file():
                continue
            new_code = path.read_text(encoding="utf-8", errors="replace")
            diff = run_git(repo, "diff", "-U0", compare_ref, "--", rel)
        else:
            new_code = run_git(repo, "show", f"{target}:{rel}")
            if new_code is None:
                continue
            diff = run_git(repo, "diff", "-U0", compare_ref, target, "--", rel)
        old_code = run_git(repo, "show", f"{compare_ref}:{rel}")

        # No comparison version (added or untracked): every line is new.
        hit = changed_lines(diff or "") if old_code is not None else None
        old_by_long: dict[str, int] = {}
        old_by_name: dict[str, int] = {}
        if old_code is not None:
            for fn in analyze(lizard, rel, old_code):
                old_by_long.setdefault(fn.long_name, fn.cyclomatic_complexity)
                old_by_name.setdefault(fn.name, fn.cyclomatic_complexity)

        for fn in analyze(lizard, rel, new_code):
            if hit is not None and not any(fn.start_line <= n <= fn.end_line for n in hit):
                continue
            touched += 1
            ccn = fn.cyclomatic_complexity
            if band(ccn) == "ok":
                continue
            base_ccn = old_by_long.get(fn.long_name, old_by_name.get(fn.name))
            if base_ccn is None:
                status = "new"
            elif ccn > base_ccn:
                status = "worsened"
            elif ccn < base_ccn:
                status = "improved"
            else:
                status = "unchanged"
            flagged.append(
                f"COMPLEXITY band={band(ccn)} ccn={ccn} "
                f"base_ccn={'none' if base_ccn is None else base_ccn} status={status} "
                f"ref={rel}:{fn.start_line} fn={fn.name}"
            )

    if flagged:
        print(f"complexity: flagged ({touched} touched functions, {len(flagged)} above ok)")
        for line in flagged:
            print(line)
    else:
        print(f"complexity: ok ({touched} touched functions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
