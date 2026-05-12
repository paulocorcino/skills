"""BunJS language runner — STUB (Stage 1). Stage 5 replaces with real integration."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

LANGUAGE = "bunjs"
REQUIRED_TOOLS = ["bun", "eslint", "tsc", "jscpd"]


def detect_tools() -> tuple[list[str], list[str]]:
    used, missing = [], []
    for t in REQUIRED_TOOLS:
        (used if shutil.which(t) else missing).append(t)
    return used, missing


def run(root: str) -> dict:
    used, missing = detect_tools()
    return {
        "language": LANGUAGE,
        "root": str(Path(root).resolve()),
        "tools_used": used,
        "tools_missing": missing,
        "coverage": {"line_pct": None, "branch_pct": None},
        "duplication": {"pct": None},
        "violations": {"errors": 0, "warnings": 0, "info": 0},
        "vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "files": {},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(run(args.root), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
