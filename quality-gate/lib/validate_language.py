"""Validate a language-runner output JSON against language_metrics.schema.json.

Stdlib-only implementation of the subset of JSON Schema draft-07 features we
actually use: type, enum, required, additionalProperties (false only), items,
properties, minimum, pattern. This is sufficient for our hand-authored schema.

Usable as a module (`validate(path)`) or CLI (`python -m quality_gate.lib.validate_language PATH`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_REL = Path(__file__).resolve().parent.parent / "schema" / "language_metrics.schema.json"


class ValidationError(Exception):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.json_path = path
        self.message = message


_JSON_TYPE_MAP = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
}


def _check_type(value: Any, type_spec: Any, path: str) -> None:
    if isinstance(type_spec, list):
        if not any(_matches_type(value, t) for t in type_spec):
            raise ValidationError(path, f"expected one of {type_spec}, got {type(value).__name__}")
        return
    if not _matches_type(value, type_spec):
        raise ValidationError(path, f"expected {type_spec}, got {type(value).__name__}")


def _matches_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    expected = _JSON_TYPE_MAP.get(name)
    return isinstance(value, expected) if expected is not None else True


def _validate(value: Any, schema: dict, path: str = "$") -> None:
    if "type" in schema:
        _check_type(value, schema["type"], path)

    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError(path, f"value {value!r} not in enum {schema['enum']}")

    if "pattern" in schema and isinstance(value, str):
        if not re.search(schema["pattern"], value):
            raise ValidationError(path, f"value does not match pattern {schema['pattern']}")

    if "minimum" in schema and isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema["minimum"]:
            raise ValidationError(path, f"value {value} < minimum {schema['minimum']}")

    if isinstance(value, dict):
        props = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []
        for r in required:
            if r not in value:
                raise ValidationError(path, f"missing required key {r!r}")
        if schema.get("additionalProperties") is False:
            extras = [k for k in value.keys() if k not in props]
            if extras:
                raise ValidationError(path, f"unexpected keys: {extras}")
        for k, v in value.items():
            if k in props:
                _validate(v, props[k], f"{path}.{k}")
            else:
                addl = schema.get("additionalProperties")
                if isinstance(addl, dict):
                    _validate(v, addl, f"{path}.{k}")

    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value):
                _validate(item, items, f"{path}[{i}]")


def load_schema() -> dict:
    return json.loads(SCHEMA_REL.read_text(encoding="utf-8"))


def validate(data_or_path) -> None:
    """Validate either a parsed dict or a path to a JSON file."""
    if isinstance(data_or_path, (str, Path)):
        with open(data_or_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = data_or_path
    _validate(data, load_schema())


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print("usage: python -m quality_gate.lib.validate_language PATH", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        validate(path)
    except ValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
