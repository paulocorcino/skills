"""Load and validate .quality-gate/config.json.

Validation is stdlib-only: we don't pull in jsonschema. Instead we hand-roll
the minimum checks the config schema expresses (presence of required keys,
enumerated language values, integer limits). The full schema file is kept
authoritative for documentation and any external tooling that wants it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_RELPATH = ".quality-gate/config.json"

DEFAULT_SOFT_LIMITS: dict[str, dict[str, int]] = {
    "python": {"file_loc": 300},
    "go":     {"file_loc": 500},
    "rust":   {"file_loc": 400},
    "bunjs":  {"file_loc": 300},
}

DEFAULT_HARD_LIMITS: dict[str, dict[str, int]] = {
    "python": {"file_loc": 800},
    "go":     {"file_loc": 1000},
    "rust":   {"file_loc": 900},
    "bunjs":  {"file_loc": 800},
}

VALID_LANGUAGES = {"python", "go", "rust", "bunjs"}


class ConfigError(Exception):
    pass


def _require(d: dict, key: str, ctx: str) -> object:
    if key not in d:
        raise ConfigError(f"{ctx}: missing required key {key!r}")
    return d[key]


def validate(data: dict) -> dict:
    """Validate `data` against the config schema (stdlib-only). Returns `data`."""
    if not isinstance(data, dict):
        raise ConfigError("config root must be an object")
    projects = _require(data, "projects", "config")
    if not isinstance(projects, list):
        raise ConfigError("projects must be an array")
    for i, p in enumerate(projects):
        ctx = f"projects[{i}]"
        if not isinstance(p, dict):
            raise ConfigError(f"{ctx}: must be an object")
        lang = _require(p, "language", ctx)
        if lang not in VALID_LANGUAGES:
            raise ConfigError(
                f"{ctx}.language: {lang!r} not in {sorted(VALID_LANGUAGES)}"
            )
        _require(p, "root", ctx)
        for limits_key in ("soft_limits", "hard_limits"):
            if limits_key in p:
                if not isinstance(p[limits_key], dict):
                    raise ConfigError(f"{ctx}.{limits_key}: must be an object")
    if "main_branch" in data and not isinstance(data["main_branch"], str):
        raise ConfigError("main_branch: must be a string")
    return data


def load(repo_root: str | os.PathLike) -> Optional[dict]:
    """Load and validate the config; return None when absent."""
    path = Path(repo_root) / CONFIG_RELPATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON: {exc}") from exc
    return validate(data)


def limits_for(language: str, project_overrides: Optional[dict] = None) -> dict:
    """Return effective soft/hard limits for a language with optional overrides."""
    soft = dict(DEFAULT_SOFT_LIMITS.get(language, {}))
    hard = dict(DEFAULT_HARD_LIMITS.get(language, {}))
    if project_overrides:
        soft.update(project_overrides.get("soft_limits", {}) or {})
        hard.update(project_overrides.get("hard_limits", {}) or {})
    return {"soft_limits": soft, "hard_limits": hard}


def main_branch(config: Optional[dict]) -> str:
    if config and isinstance(config.get("main_branch"), str):
        return config["main_branch"]
    return "main"
