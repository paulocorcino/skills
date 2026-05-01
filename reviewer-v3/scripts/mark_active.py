#!/usr/bin/env python3
"""mark_active.py — write the per-session marker that gates stop_audit.py.

Invoked by reviewer-v3 SKILL.md on entry: `python mark_active.py <session_id>`.
The Stop hook checks this marker's existence before doing any audit work; if
absent, it exits 0 immediately (the session was not /reviewer-v3).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("usage: mark_active.py <session_id>", file=sys.stderr)
        return 2
    session_id = sys.argv[1].strip()
    state_dir = Path.home() / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    marker = state_dir / f"reviewer-v3-{session_id}"
    marker.write_text("active\n", encoding="utf-8")
    print(f"marked: {marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
