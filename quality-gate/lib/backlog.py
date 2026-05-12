"""`to-backlog` implementation.

Parse the last report.md, filter regressions classified as `pre_existing`,
and emit one markdown file per issue under
`<target-repo>/docs/backlogs/quality-gate-<slug>.md` following the
`to-issues` tracer-bullet vertical-slice format.

The Markdown report is the source of truth for the issue list: this module
re-parses the Regressions table (with attribution column) rather than holding
in-memory state, so manual edits to the report are honored.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


REPORT_RELPATH = ".quality-gate/report.md"
BACKLOG_RELDIR = "docs/backlogs"


_REGRESSION_HEADER_RX = re.compile(r"^## Regressions\s*$", re.MULTILINE)


def _slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return text or "regression"


def parse_regressions(report_md: str) -> list[dict]:
    """Return the regression rows from the report's Regressions table."""
    m = _REGRESSION_HEADER_RX.search(report_md)
    if not m:
        return []
    tail = report_md[m.end():]
    lines = tail.splitlines()
    # Find first table header line.
    header_idx = next((i for i, ln in enumerate(lines) if ln.startswith("| project")), None)
    if header_idx is None:
        return []
    header = [c.strip() for c in lines[header_idx].strip("|").split("|")]
    rows: list[dict] = []
    for ln in lines[header_idx + 2:]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def emit(regressions: Iterable[dict], target_repo: str | os.PathLike) -> list[Path]:
    """Write one issue file per regression. Return list of written paths."""
    out_dir = Path(target_repo) / BACKLOG_RELDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for r in regressions:
        slug_parts = [r.get("project", "unknown"), r.get("metric", "metric")]
        if r.get("file"):
            slug_parts.append(r["file"])
        slug = _slugify("-".join(slug_parts))[:80]
        path = out_dir / f"quality-gate-{slug}.md"
        body = _render_issue(r)
        path.write_text(body, encoding="utf-8")
        written.append(path)
    written.sort()
    return written


def _render_issue(r: dict) -> str:
    title = f"quality-gate: {r.get('project','?')} / {r.get('metric','?')}"
    lines = [f"# {title}", ""]
    lines += [
        "**Type:** quality-gate regression (pre-existing)",
        f"**Project:** {r.get('project','?')}",
        f"**Metric:** {r.get('metric','?')}",
    ]
    if r.get("file"):
        lines.append(f"**File:** {r['file']}")
    lines += [
        f"**Baseline:** {r.get('baseline','?')}",
        f"**Current:** {r.get('current','?')}",
        f"**Delta:** {r.get('delta','?')}",
        "",
        "## Tracer-bullet slice",
        "",
        "Smallest end-to-end change that moves this metric in the right",
        "direction. Include test, code, and report update in the same PR.",
        "",
        "## Acceptance criteria",
        "",
        f"- [ ] {r.get('metric','metric')} reaches or beats baseline for {r.get('project','?')}",
        "- [ ] Quality Gate run shows no regression on this metric",
        "- [ ] Change covered by automated test",
        "",
    ]
    return "\n".join(lines)


def run_to_backlog(repo_root: str | os.PathLike) -> list[Path]:
    """Convenience wrapper used by the CLI."""
    report = Path(repo_root) / REPORT_RELPATH
    if not report.is_file():
        return []
    md = report.read_text(encoding="utf-8")
    rows = parse_regressions(md)
    pre = [r for r in rows if r.get("severity", "block") and "pre" in r.get("severity", "").lower()]
    # If the report doesn't carry attribution, treat all rows as candidates.
    if not pre:
        pre = rows
    return emit(pre, repo_root)
