"""Project detection.

Walks a repo root, identifies projects by their manifest files, and returns a
list of `{language, root, project_key}` dicts. If a `.quality-gate/config.json`
declares an explicit `projects` array, that list is used verbatim (after
validation by `lib.config`) and detection is skipped.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

# Manifest signature -> language. Order matters: more specific signatures first.
_MANIFEST_SIGNATURES: list[tuple[str, tuple[str, ...]]] = [
    ("bunjs", ("package.json", "bun.lockb")),
    ("python", ("pyproject.toml",)),
    ("python", ("setup.py",)),
    ("python", ("requirements.txt",)),
    ("go", ("go.mod",)),
    ("rust", ("Cargo.toml",)),
]

_SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv",
              "__pycache__", "target", ".next", ".quality-gate"}


def _matches(dir_files: set[str], required: tuple[str, ...]) -> bool:
    return all(name in dir_files for name in required)


def detect_projects(repo_root: str | os.PathLike) -> list[dict]:
    """Walk `repo_root` and return detected projects.

    Each entry: `{"language": str, "root": str, "project_key": str}`.
    `project_key` is the path relative to `repo_root` (or `"."` for root).
    A directory matched against a signature is not descended into for the
    same language (one project per matching root).
    """
    root = Path(repo_root).resolve()
    found: list[dict] = []
    matched_roots: set[Path] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        here = Path(dirpath)
        files = set(filenames)
        for language, required in _MANIFEST_SIGNATURES:
            if _matches(files, required):
                if here in matched_roots:
                    continue
                rel = here.relative_to(root)
                key = "." if str(rel) == "." else str(rel).replace(os.sep, "/")
                found.append({"language": language, "root": str(here), "project_key": key})
                matched_roots.add(here)
                break  # one language per dir

    found.sort(key=lambda p: (p["project_key"], p["language"]))
    return found


def detect_from_config(config: dict, repo_root: str | os.PathLike) -> list[dict]:
    """Honor an explicit `projects` array from .quality-gate/config.json."""
    root = Path(repo_root).resolve()
    result: list[dict] = []
    for entry in config.get("projects", []):
        lang = entry["language"]
        rel = entry["root"]
        abs_root = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        key = entry.get("project_key") or (rel.replace(os.sep, "/") if rel else ".")
        result.append({"language": lang, "root": str(abs_root), "project_key": key})
    result.sort(key=lambda p: (p["project_key"], p["language"]))
    return result


def detect(repo_root: str | os.PathLike, config: dict | None = None) -> list[dict]:
    """Top-level entry: config wins if it declares projects, else walk."""
    if config and config.get("projects"):
        return detect_from_config(config, repo_root)
    return detect_projects(repo_root)
