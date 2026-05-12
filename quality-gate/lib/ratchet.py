"""Ratchet comparison: current vs baseline.

Rules (locked by the grill-me session):
- Integer counters: zero-tolerance (current must be <= baseline).
- Percentages (coverage line_pct/branch_pct): 0.05 percentage-point tolerance
  for being *lower* than baseline.
- Lint errors must always be 0 (regardless of baseline).
- Vulnerability criticals must always be 0 (regardless of baseline).
- Per-file: baseline-listed files cannot grow worse (loc/violations may not
  exceed baseline; complexity, when present, may not exceed baseline).

`compare(current, baseline)` returns a sorted list of regression dicts:
    {metric, project, file?, baseline, current, delta, severity}

Severity is "block" when the rule is an absolute floor (lint errors,
vuln criticals) or any regression; we only emit regressions, so all entries
default to "block". Callers map this to exit codes.
"""
from __future__ import annotations

from typing import Any, Optional

PERCENT_TOLERANCE = 0.05  # percentage points


def _round2(x: Any) -> Any:
    if isinstance(x, (int, float)):
        return round(float(x), 2)
    return x


def _delta(current: Any, baseline: Any) -> Any:
    if isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
        return _round2(float(current) - float(baseline))
    return None


def _reg(metric: str, project: str, baseline: Any, current: Any,
         *, file: Optional[str] = None, severity: str = "block") -> dict:
    r = {
        "metric": metric,
        "project": project,
        "baseline": _round2(baseline),
        "current": _round2(current),
        "delta": _delta(current, baseline),
        "severity": severity,
    }
    if file is not None:
        r["file"] = file
    return r


def _compare_counters(metrics_cur: dict, metrics_base: dict, project: str,
                      group: str, keys: tuple[str, ...]) -> list[dict]:
    """Integer counters: zero-tolerance."""
    out: list[dict] = []
    cur = (metrics_cur or {}).get(group, {}) or {}
    base = (metrics_base or {}).get(group, {}) or {}
    for k in keys:
        c = int(cur.get(k, 0) or 0)
        b = int(base.get(k, 0) or 0)
        if c > b:
            out.append(_reg(f"{group}.{k}", project, b, c))
    return out


def _compare_percent(metrics_cur: dict, metrics_base: dict, project: str,
                     group: str, key: str) -> list[dict]:
    """Coverage-style percentage: regression when current < baseline - tolerance."""
    out: list[dict] = []
    cur = ((metrics_cur or {}).get(group, {}) or {}).get(key)
    base = ((metrics_base or {}).get(group, {}) or {}).get(key)
    if isinstance(cur, (int, float)) and isinstance(base, (int, float)):
        if float(cur) + PERCENT_TOLERANCE < float(base):
            out.append(_reg(f"{group}.{key}", project, base, cur))
    return out


def _compare_dup_percent(metrics_cur: dict, metrics_base: dict, project: str) -> list[dict]:
    """Duplication percentage: regression when current > baseline + tolerance."""
    out: list[dict] = []
    cur = ((metrics_cur or {}).get("duplication", {}) or {}).get("pct")
    base = ((metrics_base or {}).get("duplication", {}) or {}).get("pct")
    if isinstance(cur, (int, float)) and isinstance(base, (int, float)):
        if float(cur) > float(base) + PERCENT_TOLERANCE:
            out.append(_reg("duplication.pct", project, base, cur))
    return out


def _compare_files(metrics_cur: dict, metrics_base: dict, project: str) -> list[dict]:
    """Per-file: baseline-listed files cannot grow worse."""
    out: list[dict] = []
    cur_files = (metrics_cur or {}).get("files", {}) or {}
    base_files = (metrics_base or {}).get("files", {}) or {}
    for path, base_metrics in sorted(base_files.items()):
        cur_metrics = cur_files.get(path)
        if not cur_metrics:
            continue  # file removed; not a regression
        for metric_key in ("loc", "violations", "complexity"):
            b = base_metrics.get(metric_key)
            c = cur_metrics.get(metric_key)
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                if float(c) > float(b):
                    out.append(_reg(f"files.{metric_key}", project, b, c, file=path))
    return out


def _absolute_floors(metrics_cur: dict, project: str) -> list[dict]:
    """Lint errors and vuln criticals must always be 0."""
    out: list[dict] = []
    errs = int(((metrics_cur or {}).get("violations", {}) or {}).get("errors", 0) or 0)
    if errs > 0:
        out.append(_reg("violations.errors", project, 0, errs))
    crits = int(((metrics_cur or {}).get("vulnerabilities", {}) or {}).get("critical", 0) or 0)
    if crits > 0:
        out.append(_reg("vulnerabilities.critical", project, 0, crits))
    return out


def compare(current_projects: dict, baseline: Optional[dict]) -> list[dict]:
    """Return sorted regression list.

    `current_projects`: mapping of project_key -> language_metrics output.
    `baseline`: parsed baseline.json, or None (then only absolute floors apply).
    """
    base_projects = (baseline or {}).get("projects", {}) or {}
    regressions: list[dict] = []
    for project, cur in sorted((current_projects or {}).items()):
        cur_metrics = cur if "violations" in cur else cur.get("metrics", {})
        base_entry = base_projects.get(project, {})
        base_metrics = base_entry.get("metrics", {}) if isinstance(base_entry, dict) else {}

        regressions += _absolute_floors(cur_metrics, project)

        if baseline is not None and base_metrics:
            regressions += _compare_counters(
                cur_metrics, base_metrics, project,
                "violations", ("errors", "warnings", "info"),
            )
            regressions += _compare_counters(
                cur_metrics, base_metrics, project,
                "vulnerabilities", ("critical", "high", "medium", "low"),
            )
            regressions += _compare_percent(cur_metrics, base_metrics, project, "coverage", "line_pct")
            regressions += _compare_percent(cur_metrics, base_metrics, project, "coverage", "branch_pct")
            regressions += _compare_dup_percent(cur_metrics, base_metrics, project)
            regressions += _compare_files(cur_metrics, base_metrics, project)

    # Deterministic ordering.
    regressions.sort(key=lambda r: (r["project"], r["metric"], r.get("file", "")))
    return regressions
