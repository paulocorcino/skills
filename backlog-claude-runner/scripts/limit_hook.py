#!/usr/bin/env python3
"""StopFailure hook: handles rate_limit, session_limit (transcript-based reset time)
and server_error (fixed 5-minute retry)."""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

SERVER_ERROR_RETRY_MINUTES = 5


def extract_reset_time(transcript_path):
    """Scan JSONL transcript for 'resets 3:45pm' or 'resets Mon 12:00am'.
    Returns (day_str_or_None, time_str) or (None, None)."""
    try:
        text = Path(transcript_path).read_text(encoding="utf-8", errors="replace")
        match = re.search(
            r"resets\s+(?:([A-Za-z]{3})\s+)?(\d{1,2}:\d{2}\s*[ap]m)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1), match.group(2).replace(" ", "")
    except OSError:
        pass
    return None, None


def compute_reset_datetime(day_str, time_str):
    m = re.match(r"(\d{1,2}):(\d{2})([ap]m)", time_str, re.IGNORECASE)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    now = datetime.now()
    reset = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if day_str:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target = day_map.get(day_str[:3].lower())
        if target is not None:
            days = (target - now.weekday()) % 7 or 7
            reset += timedelta(days=days)
    elif reset <= now:
        reset += timedelta(days=1)

    return reset


def handle_limit(payload):
    """rate_limit / session_limit: parse reset time from transcript."""
    transcript_path = payload.get("transcript_path", "")
    session_id = payload.get("session_id", "")

    if not transcript_path:
        return

    day_str, time_str = extract_reset_time(transcript_path)
    if not time_str:
        print(json.dumps({"systemMessage": "Limit hit. No reset time found in transcript."}))
        return

    reset_dt = compute_reset_datetime(day_str, time_str)
    if not reset_dt:
        return

    retry_dt = reset_dt + timedelta(minutes=5)
    resume_hint = f"claude --resume {session_id}" if session_id else "claude --resume <session_id>"

    print(json.dumps({"systemMessage": (
        f"Limit hit · resets {reset_dt.strftime('%H:%M')} · retry at {retry_dt.strftime('%H:%M')}\n"
        f"Session: {session_id or 'unknown'}\n"
        f"Resume: {resume_hint}"
    )}))


def handle_server_error(payload):
    """server_error: fixed 5-minute retry."""
    session_id = payload.get("session_id", "")
    retry_dt = datetime.now() + timedelta(minutes=SERVER_ERROR_RETRY_MINUTES)
    resume_hint = f"claude --resume {session_id}" if session_id else "claude --resume <session_id>"

    print(json.dumps({"systemMessage": (
        f"Server error · retry at {retry_dt.strftime('%H:%M')}\n"
        f"Session: {session_id or 'unknown'}\n"
        f"Resume: {resume_hint}"
    )}))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    stop_reason = payload.get("stop_reason", "")

    if stop_reason == "server_error":
        handle_server_error(payload)
    else:
        handle_limit(payload)


if __name__ == "__main__":
    main()
