#!/usr/bin/env python3
"""Claude Code Stop hook: terminate the Claude CLI process when the assistant emits
the BACKLOG_RUNNER_DONE_EXIT token in its last message. No-op unless the runner has
exported BACKLOG_RUNNER_PID_FILE. Logs to /tmp/backlog-runner-hook.log."""
import json
import os
import signal
import sys
import time
from pathlib import Path


TOKEN = "BACKLOG_RUNNER_DONE_EXIT"
LOG_PATH = Path("/tmp/backlog-runner-hook.log")


def log(msg):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def main():
    pid_file = os.environ.get("BACKLOG_RUNNER_PID_FILE")
    log(f"hook invoked; pid_file_env={pid_file!r}")

    if not pid_file or not Path(pid_file).is_file():
        log("no pid file; exit 0")
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        log(f"stdin not JSON: {exc}; exit 0")
        return 0

    last = payload.get("last_assistant_message") or ""
    log(f"last_assistant_message tail: {last[-300:]!r}")

    if TOKEN not in last:
        log("token not found; exit 0")
        return 0

    try:
        pid = int(Path(pid_file).read_text().strip())
    except (OSError, ValueError) as exc:
        log(f"could not read pid file: {exc}; exit 0")
        return 0

    log(f"sending SIGTERM to pid {pid}")
    try:
        os.kill(pid, signal.SIGTERM)
        log("SIGTERM sent")
    except ProcessLookupError:
        log("pid not found")
    except PermissionError:
        log("permission denied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
