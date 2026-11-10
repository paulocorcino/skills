#!/usr/bin/env python3
"""The gate of these scripts: one command runs every check and prints one row per check.

  gate.py            every check, each tool at the pin of the skill's Python target
  gate.py --tests    the tests alone: the gate step of a repo that holds a copy of this folder

  tests        python -m unittest discover -s tests
  lint         ruff check, under ruff.toml
  format       ruff format --check
  types        mypy, under mypy.ini
  complexity   complexipy --max-complexity-allowed 10

The pins are those of the `As of` line of `../references/python.md`, and `uvx` runs
each tool at its pin: the whole gate runs where the skill is. A copy of this folder
has no such file; it runs `--tests`, which needs Python alone.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS = HERE.parent / "references" / "python.md"
TOOLS = ("ruff", "mypy", "complexipy")
TESTS = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
QUIET = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}  # the checks write nothing into this folder


def pins() -> dict[str, str]:
    """Tool -> its version in the `As of` line of the Python target."""
    asof = re.search(r"^As of .*$", PINS.read_text(encoding="utf-8"), re.MULTILINE)
    found = re.findall(rf"\b({'|'.join(TOOLS)}) (\d+(?:\.\d+)+)", asof.group(0) if asof else "")
    return dict(found)


def pinned_checks(pin: dict[str, str]) -> dict[str, list[str]]:
    ruff = ["uvx", f"ruff@{pin['ruff']}"]
    mypy = ["uvx", f"mypy@{pin['mypy']}", "--config-file", "mypy.ini", f"--cache-dir={os.devnull}"]
    cache = str(Path(tempfile.gettempdir()) / "lint-gate-complexipy")  # out of this folder
    complexipy = ["uvx", f"complexipy@{pin['complexipy']}", ".", "--cache-dir", cache]
    return {
        "lint": [*ruff, "check", "--no-cache", "."],
        "format": [*ruff, "format", "--no-cache", "--check", "."],
        "types": [*mypy, "."],
        "complexity": [*complexipy, "--max-complexity-allowed", "10"],
    }


def run(name: str, command: list[str]) -> bool:
    try:
        done = subprocess.run(
            command,
            cwd=HERE,
            env=QUIET,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as err:
        print(f"{name:<12}FAILED\n{command[0]} did not start: {err}")
        return False
    passed = done.returncode == 0
    print(f"{name:<12}{'ok' if passed else 'FAILED'}")
    if not passed:
        print(done.stdout + done.stderr)
    return passed


def any_console() -> None:
    """A tool's report prints on any console: a character it lacks becomes `?`."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def main() -> int:
    any_console()
    checks = {"tests": TESTS}
    if sys.argv[1:] != ["--tests"]:
        pin = pins() if PINS.exists() else {}
        missing = [tool for tool in TOOLS if tool not in pin]
        if missing:
            print(
                f"no pin for {', '.join(missing)} in {PINS}: a copy of this folder runs `--tests`"
            )
            return 2
        checks |= pinned_checks(pin)
    results = [run(name, command) for name, command in checks.items()]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
