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


# Diagnostic-only install hints. The skill never executes these; the report
# surfaces them so the operator (or LLM) can decide whether to install.
_TOOL_INSTALL_HINTS: dict[str, str] = {
    "bun": "curl -fsSL https://bun.sh/install | bash",
    "biome": "bun add -d @biomejs/biome",
    "oxlint": "bun add -d oxlint",
    "jscpd": "bun add -d jscpd  # or: npm i -g jscpd",
    "ruff": "pipx install ruff  # or per-project: pip install ruff",
    "pytest": "pip install pytest  # per-project dev dep",
    "coverage": "pip install coverage  # per-project dev dep",
    "bandit": "pipx install bandit",
    "radon": "pipx install radon",
    "go": "https://go.dev/dl/",
    "golangci-lint": "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest",
    "gocyclo": "go install github.com/fzipp/gocyclo/cmd/gocyclo@latest",
    "cargo": "https://rustup.rs/",
    "cargo-llvm-cov": "cargo install cargo-llvm-cov",
    "clippy": "rustup component add clippy",
    "osv-scanner": "go install github.com/google/osv-scanner/cmd/osv-scanner@latest",
    "semgrep": "pipx install semgrep",
}


def _section_project(
    project_key: str,
    metrics: dict,
    display: str | None = None,
    unratcheted: list[str] | None = None,
) -> list[str]:
    header = display if display else project_key
    lines: list[str] = [f"## Project: {header}", ""]
    unr = set(unratcheted or [])

    def _note(metric_path: str) -> str:
        return " (no baseline yet)" if metric_path in unr else ""

    cov = metrics.get("coverage", {}) or {}
    lines += ["### Coverage", ""]
    lines += _table(
        ["metric", "value"],
        [
            ["line_pct" + _note("coverage.line_pct"), _round2(cov.get("line_pct"))],
            ["branch_pct" + _note("coverage.branch_pct"), _round2(cov.get("branch_pct"))],
        ],
    )
    lines.append("")

    dup = metrics.get("duplication", {}) or {}
    lines += ["### Duplication", ""]
    lines += _table(
        ["metric", "value"],
        [["pct" + _note("duplication.pct"), _round2(dup.get("pct"))]],
    )
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
                fm.get("dominant_rule") or "—",
            ])
        lines += ["### Files", ""]
        lines += _table(["path", "loc", "complexity", "violations", "dominant_rule"], rows)
        lines.append("")

    return lines


def _top_offenders(files: dict) -> tuple[list[list[str]], list[list[str]]]:
    """Return (top_by_absolute, top_by_density) tables — each up to 5 rows.

    Density = violations per 100 LOC. Files with loc==0 are excluded from density.
    """
    by_abs: list[tuple[str, int, int, float, str]] = []
    by_density: list[tuple[str, int, int, float, str]] = []
    for path, fm in files.items():
        fm = fm or {}
        viols = int(fm.get("violations", 0) or 0)
        loc = int(fm.get("loc", 0) or 0)
        if viols <= 0:
            continue
        rule = fm.get("dominant_rule") or "—"
        density = (viols * 100.0 / loc) if loc > 0 else 0.0
        by_abs.append((path, viols, loc, density, rule))
        if loc > 0:
            by_density.append((path, viols, loc, density, rule))
    by_abs.sort(key=lambda r: (-r[1], r[0]))
    by_density.sort(key=lambda r: (-r[3], r[0]))
    abs_rows = [[p, str(v), str(l), _round2(d), r] for p, v, l, d, r in by_abs[:5]]
    den_rows = [[p, str(v), str(l), _round2(d), r] for p, v, l, d, r in by_density[:5]]
    return abs_rows, den_rows


def render(
    *,
    projects: dict,
    regressions: list[dict],
    commit: str,
    tools_versions: Optional[dict] = None,
    generated_at: Optional[str] = None,
    gate_status: Optional[str] = None,
    mode: Optional[str] = None,
    anchor_ref: Optional[str] = None,
    unratcheted: Optional[dict[str, list[str]]] = None,
    preview: bool = False,
) -> str:
    """Return the report markdown as a single string.

    Optional fields:
      gate_status — explicit verdict for the Summary (PASSED, FAILED,
                    NO_BASELINE, NO_INTENT, PASSED_WITH_GAPS, etc.).
      mode        — branch intent mode (extend|replace|main); recorded in Metadata.
      anchor_ref  — branch's anchor ref; recorded in Metadata.
    """
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tools_versions = tools_versions or {}

    md: list[str] = ["# Quality Gate Report", ""]

    # Metadata block — excluded from hash.
    md += ["<!-- BEGIN METADATA -->"]
    md += [f"- generated_at: {generated_at}"]
    md += [f"- commit: {commit}"]
    if mode is not None:
        md += [f"- mode: {mode}"]
    if anchor_ref is not None:
        md += [f"- anchor_ref: {anchor_ref}"]
    if tools_versions:
        md += ["- tools_versions:"]
        for tool in sorted(tools_versions.keys()):
            md += [f"  - {tool}: {tools_versions[tool]}"]
    md += ["<!-- END METADATA -->", ""]

    # Body starts here — included in hash.
    body_start = len(md)

    md += ["## Summary", ""]
    if gate_status is not None:
        md += [f"- gate_status: {gate_status}"]
    md += [f"- projects: {len(projects)}"]
    md += [f"- regressions: {len(regressions)}"]

    # Top rule offenders, aggregated across all projects.
    rule_totals: dict[str, int] = {}
    for pdata in projects.values():
        if not isinstance(pdata, dict):
            continue
        for entry in pdata.get("top_rules") or []:
            rule = entry.get("rule")
            count = entry.get("count")
            if isinstance(rule, str) and isinstance(count, int):
                rule_totals[rule] = rule_totals.get(rule, 0) + count
    if rule_totals:
        top = sorted(rule_totals.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        md += ["- top_rules: " + ", ".join(f"{r}×{c}" for r, c in top)]

    # Surface metrics that have no baseline value yet (informational, not regressions).
    if unratcheted:
        flat = sorted({m for ms in unratcheted.values() for m in ms})
        if flat:
            md += ["- unratcheted (no baseline yet): " + ", ".join(flat)]
    md += [""]

    missing_by_project: dict[str, list[str]] = {}
    broken_by_project: dict[str, list[str]] = {}
    for key in sorted(projects.keys()):
        pdata = projects[key]
        metrics = pdata if "violations" in pdata else pdata.get("metrics", {})
        name = pdata.get("_project_name") if isinstance(pdata, dict) else None
        display = f"{name} ({key})" if name and name != key else key
        md += _section_project(
            key, metrics, display=display, unratcheted=(unratcheted or {}).get(key),
        )
        files = metrics.get("files", {}) or {}
        abs_rows, den_rows = _top_offenders(files)
        if abs_rows or den_rows:
            md += ["### Top Offenders", ""]
            if abs_rows:
                md += ["**By absolute violations**", ""]
                md += _table(["path", "violations", "loc", "density_per_100loc", "dominant_rule"], abs_rows)
                md += [""]
            if den_rows:
                md += ["**By density (violations / 100 LOC)**", ""]
                md += _table(["path", "violations", "loc", "density_per_100loc", "dominant_rule"], den_rows)
                md += [""]
        tm = pdata.get("tools_missing") if isinstance(pdata, dict) else None
        if tm:
            missing_by_project[key] = sorted(set(tm))
        tb = pdata.get("tools_broken") if isinstance(pdata, dict) else None
        if tb:
            broken_by_project[key] = sorted(set(tb))

    if broken_by_project:
        md += ["## Broken Tools", ""]
        md += [
            "These tools were installed but failed to produce usable output. The corresponding",
            "metrics are `—` and the gate cannot ratchet them. See stderr from the last run for",
            "the underlying error.",
            "",
        ]
        rows = []
        for key in sorted(broken_by_project.keys()):
            for tool in broken_by_project[key]:
                rows.append([key, tool])
        md += _table(["project", "tool"], rows)
        md += [""]

    if missing_by_project:
        md += ["## Missing Tools", ""]
        md += [
            "These tools were not found on PATH; the corresponding metrics are reported as `—`.",
            "Install commands below are suggestions — the gate never runs them automatically.",
            "",
        ]
        rows = []
        for key in sorted(missing_by_project.keys()):
            for tool in missing_by_project[key]:
                hint = _TOOL_INSTALL_HINTS.get(tool, "—")
                rows.append([key, tool, hint])
        md += _table(["project", "tool", "install hint"], rows)
        md += [""]

    # Reproduce commands per tool, grouped by project.
    reproduce_blocks: list[str] = []
    for key in sorted(projects.keys()):
        pdata = projects[key]
        if not isinstance(pdata, dict):
            continue
        repro = pdata.get("tools_reproduce") or {}
        if not repro:
            continue
        reproduce_blocks.append(f"### {key}")
        reproduce_blocks.append("")
        reproduce_blocks.append("```bash")
        for tool in sorted(repro.keys()):
            reproduce_blocks.append(f"# {tool}")
            reproduce_blocks.append(repro[tool])
        reproduce_blocks.append("```")
        reproduce_blocks.append("")
    if reproduce_blocks:
        md += ["## Reproduce", ""]
        md += reproduce_blocks

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
