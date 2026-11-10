"""Narrow a parsed JSON value once, where it enters.

A tool's output and a config are data from outside: each reader takes the shape
it expects and gets an empty value where the data has another one.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

Json = dict[str, object]


def obj(value: object) -> Json:
    return value if isinstance(value, dict) else {}


def items(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def num(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def texts(value: object) -> list[str]:
    return [item for item in items(value) if isinstance(item, str)]


def csv(value: str | None) -> list[str]:
    """The names of a comma-separated option, in order."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig", errors="replace")


def load(path: str | Path) -> object:
    parsed: object = json.loads(Path(path).read_text(encoding="utf-8"))
    return parsed


def jsonc(raw: str) -> object:
    """JSON with comments and trailing commas."""
    bare = re.sub(
        r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', lambda m: m.group(1) or "", raw, flags=re.DOTALL
    )
    parsed: object = json.loads(re.sub(r",(\s*[}\]])", r"\1", bare))
    return parsed


def utf8_console() -> None:
    """The plan's text and the dashes of a verdict print on any console."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)
