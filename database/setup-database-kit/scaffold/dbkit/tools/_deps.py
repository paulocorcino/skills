"""Third-party dependencies of the dbkit/ tooling, hardcoded and self-contained.

`dbkit/` is a drop-in module, so it does not ship a repo-root requirements file that would
clash with the host application's own dependencies. The pins live here and are checked
at runtime; missing/mismatched packages fail loudly with the exact install command.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# package name → exact version the tools were validated against (Python 3.11).
REQUIRES: dict[str, str] = {
    "sqlfluff": "4.2.2",
    "sqlglot": "30.12.0",
}


def check_deps() -> None:
    """Exit with an actionable message if a required package is missing or mismatched."""
    problems: list[str] = []
    for pkg, want in REQUIRES.items():
        try:
            have = version(pkg)
        except PackageNotFoundError:
            problems.append(f"{pkg} is not installed (need {want})")
            continue
        if have != want:
            problems.append(f"{pkg} {have} installed, but the tools are pinned to {want}")
    if problems:
        install = " ".join(f"{pkg}=={want}" for pkg, want in REQUIRES.items())
        raise SystemExit(
            "dbkit/ tooling dependencies not satisfied:\n  - "
            + "\n  - ".join(problems)
            + f"\nInstall with:\n  pip install {install}"
        )
