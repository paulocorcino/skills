"""Security pack stub.

Real implementation lands in Stage 6 (OSV-Scanner + Semgrep CE). The stub
returns a uniform, schema-aligned no-op result per project so downstream
stages (ratchet, report) can integrate against a stable contract today.
"""
from __future__ import annotations

from typing import Any


def collect(project: dict[str, Any]) -> dict[str, Any]:
    """Return a no-op security metrics payload for a single project.

    Shape mirrors the `vulnerabilities` + `tools_used` + `tools_missing` slots
    of `language_metrics.schema.json` so the orchestrator can merge it without
    a schema migration when Stage 6 swaps in the real implementation.
    """
    return {
        "vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "tools_used": [],
        "tools_missing": ["osv-scanner", "semgrep"],
    }


def collect_all(projects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return `{project_key: security_payload}` for a list of detected projects."""
    return {p["project_key"]: collect(p) for p in projects}
