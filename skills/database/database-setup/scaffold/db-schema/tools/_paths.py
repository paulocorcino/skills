"""Single source of the two roots the tooling spans: `db-schema/` and the model docs.

The DDL lives inside `db-schema/`; the domain documentation lives outside it, in the
repo's own docs tree. `KIT_ROOT` is derived from this file's position and never needs
configuring. `MODEL_DIR` is the one path the tooling cannot derive — a monorepo puts
its docs at the workspace root, several levels above `db-schema/` — so it is declared
here, once, and every tool imports it instead of rebuilding the path.

**Adjust `MODEL_DIR` when `db-schema/` is not at the repo root.** The default assumes
they are siblings:

    <repo>/db-schema/     <- KIT_ROOT
    <repo>/docs/db-model/ <- MODEL_DIR

In a monorepo with `packages/api/db-schema/` and docs at the workspace root, make it
`KIT_ROOT.parents[2] / "docs" / "db-model"`.
"""
from __future__ import annotations

import os
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]

# The only configurable path in the tooling — see the module docstring.
MODEL_DIR = KIT_ROOT.parent / "docs" / "db-model"


# Links that erdgen.py writes into schema.dbml notes are relative to the model docs, which
# works in an editor and in the repo browser. Viewers that render the DBML elsewhere
# (dbdiagram, dbdocs) cannot resolve them: set this to the repo's file URL root, e.g.
# "https://github.com/<org>/<repo>/blob/main/", and links become absolute.
LINK_BASE: str | None = None


def link_to(target: Path) -> str:
    """Link from the model docs (where schema.dbml lives) to a file in the repo."""
    repo_root = KIT_ROOT.parent
    if LINK_BASE:
        return LINK_BASE + str(target.resolve().relative_to(repo_root)).replace("\\", "/")
    return os.path.relpath(target.resolve(), MODEL_DIR.resolve()).replace("\\", "/")


def model_path(*parts: str) -> Path:
    """A path inside the model docs (`docs/db-model/` by default)."""
    return MODEL_DIR.joinpath(*parts)


def display(path: Path) -> str:
    """Render a path for humans: relative to the repo root when it lives under it."""
    repo_root = KIT_ROOT.parent
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path)
