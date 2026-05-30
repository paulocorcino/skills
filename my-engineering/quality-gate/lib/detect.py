"""Project detection.

Walks a repo root, identifies projects by their manifest files, and returns a
list of `{language, root, project_key}` dicts. If a `.quality-gate/config.json`
declares an explicit `projects` array, that list is used verbatim (after
validation by `lib.config`) and detection is skipped.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore


def _read_project_name(root: Path, language: str) -> Optional[str]:
    """Best-effort: extract a human project name from the manifest. None on any failure."""
    try:
        if language == "bunjs":
            pkg = root / "package.json"
            if pkg.is_file():
                data = json.loads(pkg.read_text(encoding="utf-8"))
                name = data.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        elif language == "python":
            pyproject = root / "pyproject.toml"
            if pyproject.is_file() and tomllib is not None:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                name = (data.get("project", {}).get("name")
                        or data.get("tool", {}).get("poetry", {}).get("name"))
                if isinstance(name, str) and name.strip():
                    return name.strip()
        elif language == "rust":
            cargo = root / "Cargo.toml"
            if cargo.is_file() and tomllib is not None:
                data = tomllib.loads(cargo.read_text(encoding="utf-8"))
                name = data.get("package", {}).get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        elif language == "go":
            gomod = root / "go.mod"
            if gomod.is_file():
                for line in gomod.read_text(encoding="utf-8").splitlines():
                    m = re.match(r"^\s*module\s+(\S+)", line)
                    if m:
                        module = m.group(1).strip()
                        return module.rsplit("/", 1)[-1] or module
    except Exception:
        return None
    return None

# Manifest signature -> language. Order matters: more specific signatures first.
# BunJS: bun.lockb (binary, Bun <1.1) listed before bun.lock (text, Bun >=1.1) so the
# binary format wins when both exist, but text-only repos are still detected.
_MANIFEST_SIGNATURES: list[tuple[str, tuple[str, ...]]] = [
    ("bunjs", ("package.json", "bun.lockb")),
    ("bunjs", ("package.json", "bun.lock")),
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
                entry = {"language": language, "root": str(here), "project_key": key}
                name = _read_project_name(here, language)
                if name:
                    entry["name"] = name
                found.append(entry)
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
        out = {"language": lang, "root": str(abs_root), "project_key": key}
        name = entry.get("name") or entry.get("project_name") or _read_project_name(abs_root, lang)
        if name:
            out["name"] = name
        result.append(out)
    result.sort(key=lambda p: (p["project_key"], p["language"]))
    return result


def detect(repo_root: str | os.PathLike, config: dict | None = None) -> list[dict]:
    """Top-level entry: config wins if it declares projects, else walk."""
    if config and config.get("projects"):
        return detect_from_config(config, repo_root)
    return detect_projects(repo_root)
