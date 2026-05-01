#!/usr/bin/env python3
"""install.py — idempotent registration of the reviewer-v3 Stop hook.

Modes:
  python install.py            install (or re-confirm existing) the Stop hook
  python install.py --check    print 'installed' or 'missing'; exit 0

The hook command is composed at install time using sys.executable and the
absolute path to hooks/stop_audit.py on this machine, then merged into
$HOME/.claude/settings.json with `Stop` matcher='*' and timeout=30.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HOOK_REL = Path("hooks") / "stop_audit.py"
SUBSTRING_MARKER = "reviewer-v3/hooks/stop_audit.py"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def hook_path() -> Path:
    return (Path(__file__).resolve().parent.parent / HOOK_REL).resolve()


def compose_command(python_exe: str, hook: Path) -> str:
    return f'"{python_exe}" "{hook.as_posix()}"'


def already_installed(settings: dict) -> bool:
    stop_groups = settings.get("hooks", {}).get("Stop", [])
    if not isinstance(stop_groups, list):
        return False
    for group in stop_groups:
        for inner in (group or {}).get("hooks", []) or []:
            cmd = (inner or {}).get("command", "")
            if SUBSTRING_MARKER in cmd:
                return True
    return False


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"failed: settings.json is not valid JSON ({e})", file=sys.stderr)
        sys.exit(1)


def write_settings_atomic(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".settings.", suffix=".json", dir=str(SETTINGS_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_path, SETTINGS_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def install(settings: dict, command: str) -> dict:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        print("failed: settings.hooks is not an object", file=sys.stderr)
        sys.exit(1)
    stop = hooks.setdefault("Stop", [])
    if not isinstance(stop, list):
        print("failed: settings.hooks.Stop is not a list", file=sys.stderr)
        sys.exit(1)
    stop.append(
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": command, "timeout": 30}
            ],
        }
    )
    return settings


def main() -> int:
    ap = argparse.ArgumentParser(description="Install reviewer-v3 Stop hook into settings.json.")
    ap.add_argument("--check", action="store_true", help="Print installed/missing and exit 0")
    args = ap.parse_args()

    hook = hook_path()
    if not hook.exists():
        print(f"failed: hook script missing at {hook}", file=sys.stderr)
        return 1

    settings = load_settings()

    if args.check:
        print("installed" if already_installed(settings) else "missing")
        return 0

    if already_installed(settings):
        print("already installed")
        return 0

    command = compose_command(sys.executable, hook)
    settings = install(settings, command)
    try:
        write_settings_atomic(settings)
    except OSError as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    print(f"installed: {command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
