#!/usr/bin/env python3
"""check_pins.py — maintenance-time report: scaffold dependency pins vs the latest on PyPI.

Read-only: it reports, never edits. Run it during skill maintenance (not during an
install). Moving a pin is the maintainer's call after re-validation — see the
"Maintenance: dependency pins" section of SKILL.md.

    python scripts/check_pins.py [--deps PATH]

Exit 0 when every pin is current, 1 when any pin is behind, 2 when PyPI is unreachable.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_DEPS = Path(__file__).resolve().parents[1] / "scaffold" / "db-schema" / "tools" / "_deps.py"


def load_deps(path: Path):
    spec = importlib.util.spec_from_file_location("_deps", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def latest(pkg: str) -> str:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=15) as r:
        return json.load(r)["info"]["version"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deps", type=Path, default=DEFAULT_DEPS, help="_deps.py to check")
    args = ap.parse_args()
    deps = load_deps(args.deps)

    print(f"pins validated on {deps.VALIDATED_ON} ({deps.pin_age_days()} days ago, "
          f"warn after {deps.STALE_AFTER_DAYS})")
    behind = 0
    for pkg, pinned in deps.REQUIRES.items():
        try:
            newest = latest(pkg)
        except OSError as e:
            print(f"error: PyPI unreachable for {pkg}: {e}", file=sys.stderr)
            return 2
        state = "current" if newest == pinned else "BEHIND"
        behind += newest != pinned
        print(f"  {pkg:10} pinned {pinned:10} latest {newest:10} {state}")
        if newest != pinned:
            print(f"    changelog: https://pypi.org/project/{pkg}/{newest}/")
    return 1 if behind else 0


if __name__ == "__main__":
    sys.exit(main())
