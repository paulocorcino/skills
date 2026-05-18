#!/usr/bin/env python3
"""Hook: Detect cache/session limit and auto-schedule resume."""
import json
import sys
import time
from pathlib import Path


def is_cache_limit_exit(stdin_json):
    """Detect if exit was due to cache/session limit.

    Heuristics:
    - Session was very recent (< 15 min, suggests cache reload needed)
    - Exit after tool execution (not user action)
    """
    state_file = Path.home() / ".claude" / ".backlog-cache-state"
    if not state_file.exists():
        return False

    try:
        last_exec = float(state_file.read_text().strip())
        elapsed = time.time() - last_exec
        # If execution was < 15 minutes ago, we're likely in same cache window
        # If stopped now, it's likely a cache/session limit (not fresh start)
        return 60 < elapsed < 900  # Between 1 min and 15 min = suspicious timing
    except (ValueError, OSError):
        return False


def get_reset_time():
    """Get when cache will reset (5 min from last execution)."""
    state_file = Path.home() / ".claude" / ".backlog-cache-state"
    try:
        if state_file.exists():
            last_exec = float(state_file.read_text().strip())
            reset_time = last_exec + 300  # 5 minutes
            return reset_time
    except (ValueError, OSError):
        pass
    return None


def format_time(timestamp):
    """Format timestamp as HH:MM:SS."""
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def main():
    try:
        stdin_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        stdin_data = {}

    # Check if this looks like a cache/session limit event
    if not is_cache_limit_exit(stdin_data):
        return

    reset_time = get_reset_time()
    if not reset_time:
        return

    now = time.time()
    wait_seconds = int(reset_time - now)

    if wait_seconds > 0:
        reset_formatted = format_time(reset_time)
        minutes = wait_seconds // 60
        seconds = wait_seconds % 60

        output = {
            "systemMessage": (
                f"⏳ Cache limit detected. Reset at {reset_formatted} "
                f"({minutes}m {seconds}s from now). "
                f"Run: `claude --resume` when ready."
            ),
            "continue": False,
            "stopReason": f"Cache/session limit. Resume in {minutes}m {seconds}s.",
        }

        print(json.dumps(output))


if __name__ == "__main__":
    main()
