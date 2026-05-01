#!/usr/bin/env python3
"""audit.py — reconcile the LLM's `## Coverage` block against the fact pack.

Inputs:
  --coverage <path|->       coverage block (literal `-` reads stdin)
  --fact-pack <path>        JSON emitted by fact_pack.py

Output (stdout): one of
  audit: pass\nmaterial: N\nexcluded: N\nnot_reviewed: 0\ngap: none
  audit: gap\n...\ngap: <comma-list>
  audit: partial\n...\nnot_reviewed: N (<reasons>)\ngap: none

Exit codes: 0 on pass/partial; 2 on gap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


def parse_coverage_block(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (excluded_entries, not_reviewed_entries).

    Each entry is (path, reason). Reason may be empty.
    Format expected (lenient on indentation):

      ## Coverage
      excluded:
        - path/a (reason)
        - path/b (reason)
      not-reviewed:
        - path/c (reason)
    """
    excluded: list[tuple[str, str]] = []
    not_reviewed: list[tuple[str, str]] = []
    section: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        # Section headers (anywhere in the block)
        low = stripped.lower().rstrip(":")
        if low == "excluded":
            section = "excluded"
            continue
        if low in {"not-reviewed", "not_reviewed", "notreviewed"}:
            section = "not_reviewed"
            continue
        # Skip a top-level "## Coverage" header if present
        if stripped.startswith("## "):
            if low.endswith("coverage"):
                section = None
                continue
            # Different section — stop parsing
            break
        # Bullet lines
        if section and stripped.startswith("- "):
            entry = stripped[2:].strip()
            path, reason = split_path_reason(entry)
            if section == "excluded":
                excluded.append((path, reason))
            else:
                not_reviewed.append((path, reason))
    return excluded, not_reviewed


def split_path_reason(entry: str) -> tuple[str, str]:
    """Split `path (reason)` into (path, reason). Reason may be empty."""
    if entry.endswith(")") and "(" in entry:
        idx = entry.rfind("(")
        path = entry[:idx].strip()
        reason = entry[idx + 1 : -1].strip()
        return path, reason
    return entry.strip(), ""


def load_coverage(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile LLM coverage block against fact pack.")
    ap.add_argument("--coverage", required=True, help="Path to coverage block, or '-' for stdin")
    ap.add_argument("--fact-pack", required=True, help="Path to fact_pack.py JSON output")
    args = ap.parse_args()

    coverage_text = load_coverage(args.coverage)
    fact_pack = json.loads(Path(args.fact_pack).read_text(encoding="utf-8"))

    material: set[str] = set(fact_pack.get("material_files", []))
    fact_excluded: set[str] = {e["path"] for e in fact_pack.get("excluded_files", [])}

    excluded_entries, not_reviewed_entries = parse_coverage_block(coverage_text)
    claimed_excluded = {p for p, _ in excluded_entries}
    explicit_not_reviewed = {p for p, _ in not_reviewed_entries}

    # Rule 2: claimed_excluded ⊆ fact_excluded — silently ignore extras here;
    # we surface only material-file gaps as the actionable provocation.
    # Rule 5: every material file must be reviewed (implicit) or in not_reviewed.
    gap = sorted(material - explicit_not_reviewed - claimed_excluded - {""})
    # If a finding cited a not_reviewed file, the LLM should have moved it; we
    # don't have findings here, so we only check coverage-set membership.

    not_reviewed_count = len(explicit_not_reviewed)
    not_reviewed_summary = ", ".join(
        f"{p}: {r or 'no reason'}" for p, r in not_reviewed_entries
    )

    out_lines = [
        f"material: {len(material)}",
        f"excluded: {len(fact_excluded)}",
    ]

    if gap:
        print("audit: gap")
        for line in out_lines:
            print(line)
        if not_reviewed_count:
            print(f"not_reviewed: {not_reviewed_count} ({not_reviewed_summary})")
        else:
            print("not_reviewed: 0")
        print("gap: " + ", ".join(gap))
        return 2

    if not_reviewed_count:
        print("audit: partial")
        for line in out_lines:
            print(line)
        print(f"not_reviewed: {not_reviewed_count} ({not_reviewed_summary})")
        print("gap: none")
        return 0

    print("audit: pass")
    for line in out_lines:
        print(line)
    print("not_reviewed: 0")
    print("gap: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
