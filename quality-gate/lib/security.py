"""Security pack: OSV-Scanner (dep vulns) + Semgrep CE (SAST).

Invoked by the orchestrator (cli.py) once per detected project.  Returns a
dict that the orchestrator merges into the project's metrics before the
ratchet comparison step.

Return shape
------------
{
    "vulnerabilities": {"critical": N, "high": N, "medium": N, "low": N},
    "violations_security": {"errors": N, "warnings": N},
    "tools_used": ["osv-scanner", ...],
    "tools_missing": ["semgrep", ...],
}

Graceful degradation
--------------------
If a tool is absent or fails to produce JSON the entry is omitted from
``tools_used`` and added to ``tools_missing``.  The ratchet anti-cheat rule
(a tool that was present in the baseline but is now missing = FAIL) lives in
``lib/ratchet.py``; this module never raises on tool absence.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


# ---------------------------------------------------------------------------
# OSV-Scanner
# ---------------------------------------------------------------------------

_OSV_SEVERITIES = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    # fallback for any non-standard label
}


def _run_osv(project_root: str) -> dict[str, int] | None:
    """Return severity-bucketed vuln counts or None if the tool is unavailable."""
    if not shutil.which("osv-scanner"):
        return None
    try:
        result = subprocess.run(
            ["osv-scanner", "--format", "json", "-r", project_root],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # osv-scanner exits non-zero when vulnerabilities are found; that is OK.
        raw = result.stdout.strip()
        if not raw:
            return {"critical": 0, "high": 0, "medium": 0, "low": 0}
        data = json.loads(raw)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        return None

    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    # Schema: {"results": [{"packages": [{"vulnerabilities": [...]}]}]}
    for result_block in data.get("results", []):
        for pkg in result_block.get("packages", []):
            for vuln in pkg.get("vulnerabilities", []):
                # severity may be nested under database_specific or severity list
                severity_str = ""
                for sev_entry in vuln.get("severity", []):
                    score_type = sev_entry.get("type", "")
                    if score_type in ("CVSS_V3", "CVSS_V2"):
                        # map numeric CVSS to bucket
                        score = sev_entry.get("score", "")
                        severity_str = _cvss_to_bucket(score)
                        break
                if not severity_str:
                    # fall back to database_specific.severity
                    db_sev = (
                        vuln.get("database_specific", {}).get("severity", "").upper()
                    )
                    severity_str = _OSV_SEVERITIES.get(db_sev, "low")
                counts[severity_str] = counts.get(severity_str, 0) + 1

    return counts


def _cvss_to_bucket(score_str: str) -> str:
    """Map a CVSS vector string or numeric score string to a severity bucket."""
    # score_str may be a raw float string like "7.5" or a CVSS vector
    try:
        score = float(score_str)
    except (ValueError, TypeError):
        return "low"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Semgrep CE
# ---------------------------------------------------------------------------

_SEMGREP_SEVERITY_MAP = {
    # Semgrep uses: ERROR, WARNING, INFO, INVENTORY
    "ERROR": "errors",
    "WARNING": "warnings",
    "INFO": "warnings",
    "INVENTORY": "warnings",
}


def _run_semgrep(project_root: str) -> dict[str, int] | None:
    """Return violations_security counts or None if tool is unavailable."""
    if not shutil.which("semgrep"):
        return None
    try:
        result = subprocess.run(
            ["semgrep", "--json", "--config=auto", project_root],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "SEMGREP_SEND_METRICS": "off"},
        )
        raw = result.stdout.strip()
        if not raw:
            return {"errors": 0, "warnings": 0}
        data = json.loads(raw)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        return None

    counts: dict[str, int] = {"errors": 0, "warnings": 0}
    for finding in data.get("results", []):
        sev = finding.get("extra", {}).get("severity", "WARNING").upper()
        bucket = _SEMGREP_SEVERITY_MAP.get(sev, "warnings")
        counts[bucket] += 1

    return counts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect(project_root: str) -> dict[str, Any]:
    """Run security scanners against *project_root* and return aggregated metrics.

    Parameters
    ----------
    project_root:
        Absolute (or relative) path to the project directory to scan.

    Returns
    -------
    dict with keys:
        vulnerabilities        — severity buckets from OSV-Scanner
        violations_security    — error/warning counts from Semgrep
        tools_used             — tools that produced results
        tools_missing          — tools not found on PATH
    """
    tools_used: list[str] = []
    tools_missing: list[str] = []

    # --- OSV-Scanner ---
    osv_counts = _run_osv(project_root)
    if osv_counts is not None:
        tools_used.append("osv-scanner")
        vuln_counts = osv_counts
    else:
        tools_missing.append("osv-scanner")
        vuln_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    # --- Semgrep ---
    semgrep_counts = _run_semgrep(project_root)
    if semgrep_counts is not None:
        tools_used.append("semgrep")
        violations_security = semgrep_counts
    else:
        tools_missing.append("semgrep")
        violations_security = {"errors": 0, "warnings": 0}

    return {
        "vulnerabilities": vuln_counts,
        "violations_security": violations_security,
        "tools_used": sorted(tools_used),
        "tools_missing": sorted(tools_missing),
    }


def collect_all(projects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return ``{project_key: security_payload}`` for a list of detected projects."""
    return {p["project_key"]: collect(p["root"]) for p in projects}
