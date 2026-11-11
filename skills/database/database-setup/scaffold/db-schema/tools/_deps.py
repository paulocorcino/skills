"""Third-party dependencies of the db-schema/ tooling, hardcoded and self-contained.

`db-schema/` is a drop-in module, so it does not ship a repo-root requirements file that would
clash with the host application's own dependencies. The pins live here and are checked
at runtime; missing/mismatched packages fail loudly with the exact install command.

The pins age: upstream keeps releasing (new dialect support, rule changes, fixes) while
these stay frozen. VALIDATED_ON records when the pins were last proven against the tools;
past STALE_AFTER_DAYS, check_deps warns — never fails, and never touches the network.
Moving a pin means re-validating: install the candidate, run verify.py green, read the
upstream changelog for rule/dialect changes, then update REQUIRES and VALIDATED_ON together.
"""
from __future__ import annotations

import sys
from datetime import date
from importlib.metadata import PackageNotFoundError, version

# package name → exact version the tools were validated against (Python 3.11).
REQUIRES: dict[str, str] = {
    "sqlfluff": "4.2.2",
    "sqlglot": "30.12.0",
}

# Date REQUIRES was last validated (ISO). Bump it with every pin move.
VALIDATED_ON = "2026-10-15"
STALE_AFTER_DAYS = 180


def pin_age_days(today: date | None = None) -> int:
    """Days since the pins were last validated."""
    return ((today or date.today()) - date.fromisoformat(VALIDATED_ON)).days


def check_deps() -> None:
    """Exit with an actionable message if a required package is missing or mismatched;
    warn on stderr when the pins themselves are stale."""
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
            "db-schema/ tooling dependencies not satisfied:\n  - "
            + "\n  - ".join(problems)
            + f"\nInstall with:\n  pip install {install}"
        )
    age = pin_age_days()
    if age > STALE_AFTER_DAYS:
        print(
            f"warning: db-schema/ dependency pins last validated {VALIDATED_ON} ({age} days ago, "
            f"limit {STALE_AFTER_DAYS}). Check newer releases and re-validate; see _deps.py.",
            file=sys.stderr,
        )
