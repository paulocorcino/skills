"""Reference template for a language pack runner.

Contract every languages/<lang>/run.py must satisfy:

1. Invocable as a standalone script:
       python3 run.py --root <project-root> --output <path-to-json>

2. Declares the tools it depends on as a module-level `REQUIRED_TOOLS` list
   of strings (executable names looked up on PATH).

3. Detects which required tools are missing (`shutil.which` returns None)
   and writes them into `tools_missing` in the output JSON. Tools that ARE
   present go into `tools_used`. Tools missing is NOT an error — the
   orchestrator decides how to weight gaps via exit codes.

4. Writes a JSON file that validates against
   `quality-gate/schema/language_metrics.schema.json`. Field shape:

       {
         "language":        "<python|go|rust|bunjs>",
         "root":            "<absolute path>",
         "tools_used":      [...],
         "tools_missing":   [...],
         "coverage":        {"line_pct": <number|null>, "branch_pct": <number|null>},
         "duplication":     {"pct": <number|null>},
         "violations":      {"errors": int, "warnings": int, "info": int},
         "vulnerabilities": {"critical": int, "high": int, "medium": int, "low": int},
         "files":           { "<rel-path>": {"loc": int, "complexity": <number|null>, "violations": int} }
       }

5. Exit 0 on success; non-zero ONLY when the runner itself cannot proceed
   (e.g. cannot write the output file). Missing tools are NOT a failure.

6. No shell scripts. No subshell-only logic. All runner logic in Python so
   the orchestrator can rely on a single language toolchain.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

LANGUAGE = "python"  # override in each language pack
REQUIRED_TOOLS: list[str] = []  # override in each language pack


def detect_tools() -> tuple[list[str], list[str]]:
    used, missing = [], []
    for t in REQUIRED_TOOLS:
        (used if shutil.which(t) else missing).append(t)
    return used, missing


def empty_metrics() -> dict:
    return {
        "coverage": {"line_pct": None, "branch_pct": None},
        "duplication": {"pct": None},
        "violations": {"errors": 0, "warnings": 0, "info": 0},
        "vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "files": {},
    }


def run(root: str) -> dict:
    used, missing = detect_tools()
    payload = {
        "language": LANGUAGE,
        "root": str(Path(root).resolve()),
        "tools_used": used,
        "tools_missing": missing,
    }
    payload.update(empty_metrics())
    return payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    payload = run(args.root)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
