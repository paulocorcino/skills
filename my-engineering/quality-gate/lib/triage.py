"""Classify regressions as caused-by-PR vs pre-existing.

A regression is `caused_by_pr` when its `file` is present in the set of files
changed between the configured base and HEAD (`git diff --name-only base...HEAD`).
Regressions with no `file` field (project-level, e.g. coverage drops) are
classified by the union of project files: caused_by_pr when any file under the
project's root is in the diff, else pre_existing.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable


def changed_files(repo_root: str | os.PathLike, base: str = "origin/main",
                  head: str = "HEAD") -> set[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return set()
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _is_under(path: str, root: str) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def classify(regressions: list[dict], changed: Iterable[str],
             project_roots: dict[str, str] | None = None) -> dict:
    """Return `{"caused_by_pr": [...], "pre_existing": [...]}`."""
    changed_set = {c for c in changed}
    project_roots = project_roots or {}
    caused: list[dict] = []
    pre: list[dict] = []
    for r in regressions:
        attribution = "pre_existing"
        f = r.get("file")
        if f and f in changed_set:
            attribution = "caused_by_pr"
        elif not f:
            root = project_roots.get(r["project"])
            if root and any(_is_under(c, root) for c in changed_set):
                attribution = "caused_by_pr"
        enriched = dict(r, attribution=attribution)
        (caused if attribution == "caused_by_pr" else pre).append(enriched)
    return {"caused_by_pr": caused, "pre_existing": pre}
