"""Validate .quality-gate/branch.json against branch.schema.json.

Stdlib-only, mirrors the approach used by validate_language.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from quality_gate.lib.validate_language import (
    ValidationError,
    _validate,
)

SCHEMA_REL = Path(__file__).resolve().parent.parent / "schema" / "branch.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_REL.read_text(encoding="utf-8"))


def validate(data_or_path) -> None:
    """Validate a parsed dict or a path to a JSON file."""
    if isinstance(data_or_path, (str, Path)):
        with open(data_or_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = data_or_path
    _validate(data, load_schema())


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("usage: python -m quality_gate.lib.validate_branch PATH", file=sys.stderr)
        return 2
    try:
        validate(argv[0])
    except ValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
