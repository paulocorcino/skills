#!/usr/bin/env python
"""verify.py — verification pipeline orchestrator.

Two modes, one contract (exit 0 = green, any failing step = exit 1):

OFFLINE (default) — what CI and the golden rule run. Every step reads only the
repo, so it needs no credentials and never touches a database:
  1. lint.py            — every .sql passes SQLFluff (strict outside native/)
  2. erdgen.py --check  — committed diagrams in sync with schema/tables/
  3. buildsql.py        — schema assembles per dialect (N2 gate)
  4. doccheck.py        — every table / native object mentioned in model docs

LIVE (--live) — the offline steps plus `extract_<dialect>.py reconcile` against
the adopted database (.env credentials, read-only; the tool is discovered by
glob over dbkit/tools/extract_*.py). Run it at the START of any
schema work session while the live DB can still change outside the repo:
reconcile compares live fingerprints against the committed inventory and the
carved files, and reports DRIFT / NEW / APPLIED / DROPPED / MISSING (failures)
plus UNDEPLOYED (warning — a repo-designed object whose migration hasn't landed
yet; expected intermediate state). Each failure is a per-object DIRECTION
decision, never an auto-fix:
  - the change came from outside (app, DBA hotfix) -> re-carve the object
    (import the fact) and update the model docs alongside;
  - the repo intends the change -> that is a migration to apply, not drift.
Once deploys flow only from the repo, drift stops being routine import and
becomes an alarm that someone bypassed the process (record that flip as an ADR).

--live is deliberately NOT a default step: CI runs without credentials, and a
pipeline that silently skips a step teaches readers to ignore the summary.

The summary also lists the pipeline steps that are NOT built yet, so a green run
is never mistaken for full coverage.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _deps import check_deps

ROOT = Path(__file__).resolve().parents[1]

STEPS: list[tuple[str, list[str]]] = [
    ("lint", [sys.executable, str(ROOT / "tools" / "lint.py")]),
    ("erd-check", [sys.executable, str(ROOT / "tools" / "erdgen.py"), "--check"]),
    ("buildsql", [sys.executable, str(ROOT / "tools" / "buildsql.py")]),
    ("doccheck", [sys.executable, str(ROOT / "tools" / "doccheck.py")]),
]

# Appended only under --live: needs .env credentials and a reachable database,
# which CI does not have. Kept out of STEPS so the offline pipeline never
# half-runs it. The introspection tool is named extract_<source-dialect>.py
# (porting contract in its docstring), so it is discovered by glob — no
# hardcoded dialect, same doctrine as .sqlfluff.
def live_steps() -> list[tuple[str, list[str]]]:
    tools = sorted((ROOT / "tools").glob("extract_*.py"))
    if not tools:
        sys.exit("verify --live: no dbkit/tools/extract_<dialect>.py found — "
                 "adopt a database first (database-adoption skill)")
    if len(tools) > 1:
        sys.exit("verify --live: multiple extract tools found "
                 f"({', '.join(t.name for t in tools)}) — one adopted source per "
                 "repo is the current design; extend verify.py if that changed")
    return [("reconcile", [sys.executable, str(tools[0]), "reconcile"])]

# Pipeline steps designed but not implemented. Listed in the summary as "not built"
# so a green run is not read as full coverage.
NOT_BUILT: list[str] = ["levelcheck", "dbverify", "pytest"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="also run extract.py reconcile against the adopted "
                             "database (read-only; needs .env)")
    args = parser.parse_args()

    check_deps()
    steps = STEPS + (live_steps() if args.live else [])
    failed: list[str] = []
    for name, cmd in steps:
        print(f"\n===== {name} =====")
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            failed.append(name)

    print("\n===== SUMMARY =====")
    for name, _ in steps:
        print(f"  {'FAILED' if name in failed else 'ok     '} {name}")
    for name in NOT_BUILT:
        print(f"  not-built  {name}")
    print(f"\nRan {len(steps)} check(s); {len(NOT_BUILT)} pipeline step(s) not built yet.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
