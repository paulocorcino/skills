#!/usr/bin/env python3
"""audit.py — reconcile the LLM's `## Coverage` block against the fact pack.

Inputs:
  --coverage <path|->        coverage block (literal `-` reads stdin)
  --fact-pack <path>         JSON emitted by fact_pack.py
  --not-exercised <path|->   optional `not exercised:` block from the report
                             header. Used to enforce ADR-0003 F2 (one line per
                             command, no class bundling).

Output (stdout): one of
  audit: pass\nmaterial: N\nexcluded: N\nnot_reviewed: 0\ngap: none
  audit: gap\n...\ngap: <comma-list>
  audit: partial\n...\nnot_reviewed: N (<reasons>)\ngap: none

When pass/partial and the LLM declared `not-reviewed` covering more than
40% of the material set or more than 30 files, an auto-narrow trailer is
appended:

  scope-auto-narrowed: yes (N/M files; reason: <aggregate>)
         — narrowed-by-user-request: true|false|unspecified

When `narrowed-by-user-request` is `false` or `unspecified`, the
provocation block from ADR-0002 §A3 follows the trailer.

ADR-0003 format defects (informational; do not change exit code):
  - F1 glob in not-reviewed → `format-defect: glob-in-not-reviewed`
  - F1 category-empty       → `format-defect: category-empty`
  - F2 bundled not-exercised → `format-defect: bundled-not-exercised`

Exit codes: 0 on pass/partial; 2 on gap. Auto-narrow and format defects
are informational, not blocking — the verdict ceiling lives in the Stop
hook.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AUTO_NARROW_PCT = 0.40
AUTO_NARROW_ABS = 30

PROVOCATION = (
    "You declared {n}/{m} material files as not-reviewed with reason "
    "'{reason}'. If the user explicitly requested a narrowed scope (e.g. "
    "'check only the brief acceptance criteria'), confirm by adding "
    "`narrowed-by-user-request: true` to your Coverage block. Otherwise, "
    "consider widening coverage or splitting `not-reviewed` reasons by "
    "file group."
)

GLOB_RE = re.compile(r"[*?\[\]]")
CATEGORY_RE = re.compile(r"^category\s*:\s*(.+)$", re.IGNORECASE)
# Heuristic for F2 bundling: an entry whose left side (before `—`/`-`/`:`
# blocker separator) names two or more check keywords joined by comma or
# `and`/`+`. Examples that match: "typecheck, lint, unit: infeasible",
# "typecheck and lint — side effects".
CHECK_TOKEN = (
    r"typecheck|tsc|lint|test|tests|unit|integration|contract|build|"
    r"docker|docker:build|release|format|fmt|ci|e2e"
)
BUNDLE_RE = re.compile(
    rf"^\s*(?:{CHECK_TOKEN})\s*(?:,|\band\b|\+)\s*(?:{CHECK_TOKEN})\b",
    re.IGNORECASE,
)


def parse_coverage_block(
    text: str,
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
    str | None,
]:
    """Return (excluded, not_reviewed_paths, categories, glob_offenders, narrowed).

    `categories` is a list of (prefix, reason) entries from `category:` lines
    inside `not-reviewed:`. `glob_offenders` is the list of raw bullet entries
    that contained glob syntax.
    """
    excluded: list[tuple[str, str]] = []
    not_reviewed_paths: list[tuple[str, str]] = []
    categories: list[tuple[str, str]] = []
    glob_offenders: list[str] = []
    narrowed: str | None = None
    section: str | None = None
    flag_re = re.compile(r"^narrowed-by-user-request\s*:\s*(\S+)\s*$", re.IGNORECASE)

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        flag_match = flag_re.match(stripped)
        if flag_match:
            value = flag_match.group(1).strip().lower().rstrip(".,;")
            if value in {"true", "false"}:
                narrowed = value
            continue
        low = stripped.lower().rstrip(":")
        if low == "excluded":
            section = "excluded"
            continue
        if low in {"not-reviewed", "not_reviewed", "notreviewed"}:
            section = "not_reviewed"
            continue
        if stripped.startswith("## "):
            if low.endswith("coverage"):
                section = None
                continue
            break
        if section and stripped.startswith("- "):
            entry = stripped[2:].strip()
            cat_match = CATEGORY_RE.match(entry)
            if section == "not_reviewed" and cat_match:
                prefix, reason = split_path_reason(cat_match.group(1).strip())
                if GLOB_RE.search(prefix):
                    glob_offenders.append(entry)
                else:
                    categories.append((prefix, reason))
                continue
            path, reason = split_path_reason(entry)
            if section == "not_reviewed" and GLOB_RE.search(path):
                glob_offenders.append(entry)
                continue
            if section == "excluded":
                excluded.append((path, reason))
            else:
                not_reviewed_paths.append((path, reason))
    return excluded, not_reviewed_paths, categories, glob_offenders, narrowed


def split_path_reason(entry: str) -> tuple[str, str]:
    """Split `path (reason)` into (path, reason). Reason may be empty."""
    if entry.endswith(")") and "(" in entry:
        idx = entry.rfind("(")
        path = entry[:idx].strip()
        reason = entry[idx + 1 : -1].strip()
        return path, reason
    return entry.strip(), ""


def aggregate_reasons(reasons: list[str]) -> str:
    seen: list[str] = []
    for reason in reasons:
        r = reason.strip() or "no reason"
        if r not in seen:
            seen.append(r)
    return "; ".join(seen) if seen else "no reason"


def files_under_prefix(prefix: str, material: set[str]) -> set[str]:
    """Return material files whose path starts with `prefix`.

    Prefix matching is literal. Trailing `/` is normalized so `src/adapters`
    and `src/adapters/` both match files under that directory. A bare
    file path matches itself.
    """
    p = prefix.rstrip("/")
    return {
        f
        for f in material
        if f == p or f.startswith(p + "/")
    }


def load_text(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


def parse_not_exercised_block(text: str) -> list[str]:
    """Return the list of bullet entries (raw text after `- `).

    Accepts either the bare `not exercised:` block or a fragment containing
    it. Stops at a blank line followed by another field, or at the next
    Markdown header.
    """
    entries: list[str] = []
    in_block = False
    header_re = re.compile(r"^\s*not\s*exercised\s*:\s*(.*)$", re.IGNORECASE)
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not in_block:
            m = header_re.match(line)
            if m:
                in_block = True
                tail = m.group(1).strip()
                # Inline form: "not exercised: none" or one-liner
                if tail and tail.lower() not in {"none", "n/a", "-"}:
                    # Treat the inline value as a single entry only if it
                    # looks like a bullet payload (rare); otherwise skip.
                    if tail.startswith("-"):
                        entries.append(tail.lstrip("- ").strip())
            continue
        # We are in the block.
        if stripped.startswith("## "):
            break
        if stripped.startswith("- "):
            entries.append(stripped[2:].strip())
            continue
        # A non-bullet, non-blank line that doesn't start with whitespace
        # likely starts a new header field. Stop.
        if stripped and not raw.startswith((" ", "\t")) and ":" in stripped:
            break
    return entries


def detect_bundled(entries: list[str]) -> list[str]:
    offenders: list[str] = []
    for entry in entries:
        # Split off the blocker separator: prefer em dash, then `:`, then `-`.
        head = entry
        for sep in ("—", " — ", ": ", " - "):
            if sep in entry:
                head = entry.split(sep, 1)[0]
                break
        if BUNDLE_RE.search(head.strip()):
            offenders.append(entry)
    return offenders


def maybe_emit_auto_narrow(
    not_reviewed_count: int,
    reasons: list[str],
    material_count: int,
    narrowed_flag: str | None,
) -> None:
    if not_reviewed_count == 0:
        return
    triggers = (
        (not_reviewed_count / max(material_count, 1)) > AUTO_NARROW_PCT
        or not_reviewed_count > AUTO_NARROW_ABS
    )
    if not triggers:
        return
    reason = aggregate_reasons(reasons)
    flag_value = narrowed_flag if narrowed_flag in {"true", "false"} else "unspecified"
    print(
        f"scope-auto-narrowed: yes ({not_reviewed_count}/{material_count} files; reason: {reason})"
    )
    print(f"       — narrowed-by-user-request: {flag_value}")
    if flag_value != "true":
        print()
        print(PROVOCATION.format(n=not_reviewed_count, m=material_count, reason=reason))


def emit_format_defects(
    glob_offenders: list[str],
    category_empty: list[tuple[str, str]],
    bundled: list[str],
) -> None:
    if not (glob_offenders or category_empty or bundled):
        return
    print()
    if glob_offenders:
        print("format-defect: glob-in-not-reviewed")
        for offender in glob_offenders:
            print(f"  - {offender}")
    if category_empty:
        print("format-defect: category-empty")
        for prefix, reason in category_empty:
            label = f"{prefix} ({reason})" if reason else prefix
            print(f"  - category: {label}")
    if bundled:
        print("format-defect: bundled-not-exercised")
        for offender in bundled:
            print(f"  - {offender}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile LLM coverage block against fact pack.")
    ap.add_argument("--coverage", required=True, help="Path to coverage block, or '-' for stdin")
    ap.add_argument("--fact-pack", required=True, help="Path to fact_pack.py JSON output")
    ap.add_argument(
        "--not-exercised",
        default=None,
        help="Optional path to the report's `not exercised:` block, or '-' for stdin",
    )
    args = ap.parse_args()

    coverage_text = load_text(args.coverage)
    fact_pack = json.loads(Path(args.fact_pack).read_text(encoding="utf-8"))

    material: set[str] = set(fact_pack.get("material_files", []))
    fact_excluded: set[str] = {e["path"] for e in fact_pack.get("excluded_files", [])}

    (
        excluded_entries,
        not_reviewed_paths,
        categories,
        glob_offenders,
        narrowed_flag,
    ) = parse_coverage_block(coverage_text)
    claimed_excluded = {p for p, _ in excluded_entries}

    explicit_paths = {p for p, _ in not_reviewed_paths}
    category_covered: set[str] = set()
    category_lines: list[str] = []
    category_empty: list[tuple[str, str]] = []
    for prefix, reason in categories:
        matched = files_under_prefix(prefix, material)
        if not matched:
            category_empty.append((prefix, reason))
        category_covered |= matched
        label = f"{prefix} ({reason})" if reason else prefix
        category_lines.append(f"category: {label} — {len(matched)} files under prefix")

    explicit_not_reviewed = explicit_paths | category_covered
    gap = sorted(material - explicit_not_reviewed - claimed_excluded - {""})

    not_reviewed_count = len(explicit_not_reviewed)
    reasons_list = [r for _, r in not_reviewed_paths] + [r for _, r in categories]
    not_reviewed_summary_parts: list[str] = []
    for p, r in not_reviewed_paths:
        not_reviewed_summary_parts.append(f"{p}: {r or 'no reason'}")
    for prefix, r in categories:
        not_reviewed_summary_parts.append(f"category {prefix}: {r or 'no reason'}")
    not_reviewed_summary = ", ".join(not_reviewed_summary_parts)

    bundled: list[str] = []
    if args.not_exercised:
        ne_text = load_text(args.not_exercised)
        ne_entries = parse_not_exercised_block(ne_text)
        # If the file does not contain a `not exercised:` header, treat each
        # bullet line as an entry — supports passing the bare block.
        if not ne_entries:
            ne_entries = [
                line.strip()[2:].strip()
                for line in ne_text.splitlines()
                if line.strip().startswith("- ")
            ]
        bundled = detect_bundled(ne_entries)

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
        for line in category_lines:
            print(line)
        print("gap: " + ", ".join(gap))
        emit_format_defects(glob_offenders, category_empty, bundled)
        return 2

    if not_reviewed_count:
        print("audit: partial")
        for line in out_lines:
            print(line)
        print(f"not_reviewed: {not_reviewed_count} ({not_reviewed_summary})")
        for line in category_lines:
            print(line)
        print("gap: none")
        maybe_emit_auto_narrow(
            not_reviewed_count, reasons_list, len(material), narrowed_flag
        )
        emit_format_defects(glob_offenders, category_empty, bundled)
        return 0

    print("audit: pass")
    for line in out_lines:
        print(line)
    print("not_reviewed: 0")
    for line in category_lines:
        print(line)
    print("gap: none")
    emit_format_defects(glob_offenders, category_empty, bundled)
    return 0


if __name__ == "__main__":
    sys.exit(main())
