"""Render a deterministic report.md.

Structure:
    # Quality Gate Report
    <Metadata block — excluded from report_hash>
    ## Summary
    ## Project: <key>
      ### Coverage / Duplication / Violations / Vulnerabilities tables
    ## Regressions
    <report_hash line — computed over data sections only>

Determinism:
- Alphabetical ordering for projects, files, metric keys.
- Percentages rounded to 2 decimals.
- `report_hash` is sha256 over the body BETWEEN the Metadata block and the
  hash line itself (so timestamps/commits/tool versions do not influence it).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional


def _round2(x):
    if isinstance(x, (int, float)):
        return f"{round(float(x), 2):.2f}"
    return "—" if x is None else str(x)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def _section_project(project_key: str, metrics: dict) -> list[str]:
    lines: list[str] = [f"## Project: {project_key}", ""]

    cov = metrics.get("coverage", {}) or {}
    lines += ["### Coverage", ""]
    lines += _table(
        ["metric", "value"],
        [
            ["line_pct", _round2(cov.get("line_pct"))],
            ["branch_pct", _round2(cov.get("branch_pct"))],
        ],
    )
    lines.append("")

    dup = metrics.get("duplication", {}) or {}
    lines += ["### Duplication", ""]
    lines += _table(["metric", "value"], [["pct", _round2(dup.get("pct"))]])
    lines.append("")

    vio = metrics.get("violations", {}) or {}
    lines += ["### Violations", ""]
    lines += _table(
        ["severity", "count"],
        [
            ["errors", str(int(vio.get("errors", 0) or 0))],
            ["warnings", str(int(vio.get("warnings", 0) or 0))],
            ["info", str(int(vio.get("info", 0) or 0))],
        ],
    )
    lines.append("")

    vul = metrics.get("vulnerabilities", {}) or {}
    lines += ["### Vulnerabilities", ""]
    lines += _table(
        ["severity", "count"],
        [
            ["critical", str(int(vul.get("critical", 0) or 0))],
            ["high", str(int(vul.get("high", 0) or 0))],
            ["medium", str(int(vul.get("medium", 0) or 0))],
            ["low", str(int(vul.get("low", 0) or 0))],
        ],
    )
    lines.append("")

    files = metrics.get("files", {}) or {}
    if files:
        rows = []
        for path in sorted(files.keys()):
            fm = files[path] or {}
            rows.append([
                path,
                str(int(fm.get("loc", 0) or 0)),
                _round2(fm.get("complexity")),
                str(int(fm.get("violations", 0) or 0)),
            ])
        lines += ["### Files", ""]
        lines += _table(["path", "loc", "complexity", "violations"], rows)
        lines.append("")

    return lines


def render(
    *,
    projects: dict,
    regressions: list[dict],
    commit: str,
    tools_versions: Optional[dict] = None,
    generated_at: Optional[str] = None,
) -> str:
    """Return the report markdown as a single string."""
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tools_versions = tools_versions or {}

    md: list[str] = ["# Quality Gate Report", ""]

    # Metadata block — excluded from hash.
    md += ["<!-- BEGIN METADATA -->"]
    md += [f"- generated_at: {generated_at}"]
    md += [f"- commit: {commit}"]
    if tools_versions:
        md += ["- tools_versions:"]
        for tool in sorted(tools_versions.keys()):
            md += [f"  - {tool}: {tools_versions[tool]}"]
    md += ["<!-- END METADATA -->", ""]

    # Body starts here — included in hash.
    body_start = len(md)

    md += ["## Summary", ""]
    md += [f"- projects: {len(projects)}"]
    md += [f"- regressions: {len(regressions)}"]
    md += [""]

    for key in sorted(projects.keys()):
        pdata = projects[key]
        metrics = pdata if "violations" in pdata else pdata.get("metrics", {})
        md += _section_project(key, metrics)

    md += ["## Regressions", ""]
    if not regressions:
        md += ["_None._", ""]
    else:
        rows = []
        for r in regressions:
            rows.append([
                r["project"],
                r["metric"],
                r.get("file", ""),
                _round2(r["baseline"]),
                _round2(r["current"]),
                _round2(r.get("delta")),
                r.get("severity", "block"),
            ])
        md += _table(
            ["project", "metric", "file", "baseline", "current", "delta", "severity"],
            rows,
        )
        md += [""]

    body = "\n".join(md[body_start:])
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    md += [f"<!-- report_hash: {digest} -->", ""]
    return "\n".join(md)
