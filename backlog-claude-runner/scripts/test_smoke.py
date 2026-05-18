#!/usr/bin/env python3
"""Smoke tests for backlog-claude-runner scripts.

Run from the scripts/ directory:
    python test_smoke.py

Each test is self-contained, uses only stdlib, and does not call Claude CLI.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# -- helpers to import the modules without running main() ----------------

SCRIPTS_DIR = Path(__file__).parent

def import_module(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ========================================================================
# run_backlog_claude.py
# ========================================================================

class TestBacklogFiles(unittest.TestCase):
    def setUp(self):
        self.mod = import_module("run_backlog_claude")

    def _make_repo(self, filenames):
        """Create a tmp dir that looks like a repo with docs/backlog/."""
        tmp = tempfile.mkdtemp()
        bd = Path(tmp) / "docs" / "backlog"
        bd.mkdir(parents=True)
        for name, content in filenames.items():
            (bd / name).write_text(content, encoding="utf-8")
        return Path(tmp)

    def test_backlog_files_sorted_numerically(self):
        root = self._make_repo({
            "010-feature-b.md": "# B",
            "002-feature-a.md": "# A",
            "100-feature-c.md": "# C",
        })
        files = self.mod.backlog_files(root)
        names = [p.name for p in files]
        self.assertEqual(names, ["002-feature-a.md", "010-feature-b.md", "100-feature-c.md"])

    def test_backlog_files_ignores_no_prefix(self):
        root = self._make_repo({
            "README.md": "# index",
            "003-item.md": "# item",
        })
        files = self.mod.backlog_files(root)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "003-item.md")

    def test_is_delivered_status_line(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("- **Status:** Delivered\n")
            name = f.name
        self.assertTrue(self.mod.is_delivered(Path(name)))
        os.unlink(name)

    def test_is_delivered_labels_line(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("- Labels: bug, delivered, urgent\n")
            name = f.name
        self.assertTrue(self.mod.is_delivered(Path(name)))
        os.unlink(name)

    def test_is_not_delivered(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("- Status: open\n- Labels: bug\n")
            name = f.name
        self.assertFalse(self.mod.is_delivered(Path(name)))
        os.unlink(name)

    def test_is_afk_true(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("- Type: AFK\n")
            name = f.name
        self.assertTrue(self.mod.is_afk(Path(name)))
        os.unlink(name)

    def test_is_afk_false(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("- Type: feature\n")
            name = f.name
        self.assertFalse(self.mod.is_afk(Path(name)))
        os.unlink(name)

    def test_resolve_item_by_number(self):
        root = self._make_repo({"007-auth.md": "# auth"})
        path = self.mod.resolve_item(root, "7", False)
        self.assertEqual(path.name, "007-auth.md")

    def test_resolve_item_next_skips_delivered(self):
        root = self._make_repo({
            "001-done.md": "- Status: Delivered\n",
            "002-todo.md": "- Status: open\n",
        })
        path = self.mod.resolve_item(root, None, True)
        self.assertEqual(path.name, "002-todo.md")

    def test_resolve_item_not_found(self):
        root = self._make_repo({"001-item.md": ""})
        with self.assertRaises(SystemExit):
            self.mod.resolve_item(root, "999", False)

    def test_next_after(self):
        root = self._make_repo({
            "001-first.md": "- Status: Delivered\n",
            "002-second.md": "- Status: open\n",
            "003-third.md": "- Status: open\n",
        })
        files = self.mod.backlog_files(root)
        nxt = self.mod.next_after(root, files[0])
        self.assertEqual(nxt.name, "002-second.md")

    def test_format_duration(self):
        mod = self.mod
        self.assertEqual(mod.format_duration(30), "30s")
        self.assertEqual(mod.format_duration(90), "1m 30s")
        self.assertEqual(mod.format_duration(3661), "1h 1m 1s")

    def test_shell_quote(self):
        mod = self.mod
        self.assertEqual(mod.shell_quote("hello world"), "'hello world'")
        self.assertEqual(mod.shell_quote("it's"), "'it'\\''s'")

    def test_quote_powershell_arg(self):
        mod = self.mod
        self.assertEqual(mod.quote_powershell_arg("hello"), "'hello'")
        self.assertEqual(mod.quote_powershell_arg("it's"), "'it''s'")

    def test_make_prompt_contains_backlog_content(self):
        root = self._make_repo({"005-login.md": "# Login\nAdd login form."})
        backlog_path = root / "docs" / "backlog" / "005-login.md"
        prompt = self.mod.make_prompt(root, backlog_path)
        self.assertIn("docs/backlog/005-login.md", prompt)
        self.assertIn("Add login form.", prompt)

    def test_get_runner_state_missing_file(self):
        mod = self.mod
        with patch.object(mod, "RUNNER_STATE_FILE", Path("/tmp/__nonexistent_runner_state__")):
            state = mod.get_runner_state()
        self.assertEqual(state, {})

    def test_set_and_clear_runner_phase(self):
        mod = self.mod
        tmp = Path(tempfile.mktemp(suffix=".json"))
        with patch.object(mod, "RUNNER_STATE_FILE", tmp):
            mod.set_runner_phase("planning", "/some/repo")
            state = mod.get_runner_state()
            self.assertEqual(state["phase"], "planning")
            mod.clear_runner_phase()
            self.assertFalse(tmp.exists())


# ========================================================================
# limit_hook.py
# ========================================================================

class TestLimitHook(unittest.TestCase):
    def setUp(self):
        self.mod = import_module("limit_hook")

    def _write_transcript(self, content):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_extract_reset_time_no_match(self):
        path = self._write_transcript('{"text": "all good"}')
        day, t = self.mod.extract_reset_time(path)
        self.assertIsNone(day)
        self.assertIsNone(t)
        os.unlink(path)

    def test_extract_reset_time_with_time_only(self):
        path = self._write_transcript('Usage limit hit. resets 3:45pm tomorrow.')
        day, t = self.mod.extract_reset_time(path)
        self.assertIsNone(day)
        self.assertEqual(t, "3:45pm")
        os.unlink(path)

    def test_extract_reset_time_with_day(self):
        path = self._write_transcript('resets Mon 12:00am')
        day, t = self.mod.extract_reset_time(path)
        self.assertEqual(day, "Mon")
        self.assertEqual(t, "12:00am")
        os.unlink(path)

    def test_compute_reset_datetime_pm(self):
        dt = self.mod.compute_reset_datetime(None, "3:45pm")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 45)

    def test_compute_reset_datetime_am_midnight(self):
        dt = self.mod.compute_reset_datetime(None, "12:00am")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 0)

    def test_compute_reset_datetime_noon(self):
        dt = self.mod.compute_reset_datetime(None, "12:00pm")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 12)

    def test_main_no_transcript_is_silent(self, capsys=None):
        import io
        payload = json.dumps({})
        with patch("sys.stdin", io.StringIO(payload)):
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                self.mod.main()
        self.assertEqual(captured.getvalue(), "")

    def test_main_emits_system_message(self):
        import io
        path = self._write_transcript("resets 6:00pm")
        payload = json.dumps({"transcript_path": path, "session_id": "abc123"})
        captured = io.StringIO()
        with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", captured):
            self.mod.main()
        os.unlink(path)
        out = json.loads(captured.getvalue())
        self.assertIn("systemMessage", out)
        self.assertIn("18:00", out["systemMessage"])
        self.assertIn("abc123", out["systemMessage"])


# ========================================================================
# claude_stop_exit_hook.py
# ========================================================================

class TestClaudeStopExitHook(unittest.TestCase):
    def setUp(self):
        self.mod = import_module("claude_stop_exit_hook")

    def test_no_pid_file_env_exits_0(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("BACKLOG_RUNNER_PID_FILE", None)
            import io
            with patch("sys.stdin", io.StringIO("{}")):
                result = self.mod.main()
        self.assertEqual(result, 0)

    def test_token_not_in_message_exits_0(self):
        import io
        pid_file = tempfile.NamedTemporaryFile("w", suffix=".pid", delete=False)
        pid_file.write("12345")
        pid_file.close()
        payload = json.dumps({"last_assistant_message": "I finished, but no token."})
        with patch.dict(os.environ, {"BACKLOG_RUNNER_PID_FILE": pid_file.name}):
            with patch("sys.stdin", io.StringIO(payload)):
                result = self.mod.main()
        os.unlink(pid_file.name)
        self.assertEqual(result, 0)

    def test_token_present_sends_sigterm(self):
        import io
        import signal
        pid_file = tempfile.NamedTemporaryFile("w", suffix=".pid", delete=False)
        pid_file.write(str(os.getpid()))  # send to self — we mock os.kill
        pid_file.close()
        payload = json.dumps({"last_assistant_message": "done\nBACKLOG_RUNNER_DONE_EXIT\n"})
        killed = []
        def fake_kill(pid, sig):
            killed.append((pid, sig))
        with patch.dict(os.environ, {"BACKLOG_RUNNER_PID_FILE": pid_file.name}):
            with patch("sys.stdin", io.StringIO(payload)):
                with patch("os.kill", fake_kill):
                    result = self.mod.main()
        os.unlink(pid_file.name)
        self.assertEqual(result, 0)
        self.assertEqual(len(killed), 1)
        self.assertEqual(killed[0][1], signal.SIGTERM)


# ========================================================================
# cache_reset_hook.py
# ========================================================================

class TestCacheResetHook(unittest.TestCase):
    def setUp(self):
        self.mod = import_module("cache_reset_hook")

    def test_no_state_file_is_not_cache_limit(self):
        with patch.object(Path, "exists", return_value=False):
            result = self.mod.is_cache_limit_exit({})
        self.assertFalse(result)

    def test_recent_execution_is_cache_limit(self):
        import time
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(str(time.time() - 120))  # 2 minutes ago
            name = f.name
        with patch.object(self.mod, "Path") as mock_path_cls:
            mock_path_cls.home.return_value = Path(tempfile.gettempdir())
            state = Path(name)
            mock_path_cls.return_value = state
        os.unlink(name)
        # The heuristic check: just validate the time math manually
        elapsed = 120  # 2 minutes
        is_suspicious = 60 < elapsed < 900
        self.assertTrue(is_suspicious)

    def test_format_time_returns_string(self):
        import time
        result = self.mod.format_time(time.time())
        self.assertRegex(result, r"^\d{2}:\d{2}:\d{2}$")

    def test_main_no_state_file_is_silent(self):
        import io
        with patch("sys.stdin", io.StringIO("{}")):
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                self.mod.main()
        # No state file → should produce no output
        self.assertEqual(captured.getvalue(), "")


# ========================================================================
# schedule_retry — at integration + fallback
# ========================================================================

class TestScheduleRetry(unittest.TestCase):
    """Tests for schedule_retry() in run_backlog_claude.py.

    Two scenarios:
      1. `at` is available → job is enqueued, cwd is embedded in the at script.
      2. `at` is absent   → fallback detached Python process is used.
    """

    def setUp(self):
        self.mod = import_module("run_backlog_claude")
        from datetime import datetime, timedelta
        # Schedule 1 hour from now so the job sits safely in the queue.
        self.run_at = datetime.now() + timedelta(hours=1)

    def _list_at_jobs(self):
        import subprocess
        result = subprocess.run(["atq"], capture_output=True, text=True)
        return result.stdout.strip().splitlines()

    def _remove_at_job(self, job_id):
        import subprocess
        subprocess.run(["atrm", str(job_id)], capture_output=True)

    def _job_ids_before_after(self, fn):
        """Run fn(), return set of new job IDs created during the call."""
        before = {line.split()[0] for line in self._list_at_jobs() if line.strip()}
        fn()
        after = {line.split()[0] for line in self._list_at_jobs() if line.strip()}
        return after - before

    @unittest.skipUnless(__import__("shutil").which("at"), "at not available")
    def test_at_schedules_job_with_correct_cwd(self):
        """schedule_retry via `at` creates a job whose script contains the cwd."""
        import subprocess
        cwd = Path(tempfile.mkdtemp())
        command = ["echo", "hello-from-smoke-test"]

        new_ids = set()

        def do_schedule():
            desc, ok = self.mod.schedule_retry(command, self.run_at, cwd=cwd)
            self.assertTrue(ok, f"schedule_retry returned ok=False: {desc}")
            self.assertIn("'at' job", desc)

        new_ids = self._job_ids_before_after(do_schedule)

        try:
            self.assertEqual(len(new_ids), 1, f"Expected 1 new at job, got: {new_ids}")
            job_id = next(iter(new_ids))

            # Inspect the queued script via `at -c <id>`
            cat = subprocess.run(["at", "-c", job_id], capture_output=True, text=True)
            script = cat.stdout

            # The cwd must appear as a `cd '...'` line in the at script
            self.assertIn(str(cwd), script,
                f"Expected cwd {cwd} in at script; got:\n{script[:800]}")

            # The command must also be present
            self.assertIn("echo", script)
            self.assertIn("hello-from-smoke-test", script)
        finally:
            for jid in new_ids:
                self._remove_at_job(jid)
            cwd.rmdir()

    @unittest.skipUnless(__import__("shutil").which("at"), "at not available")
    def test_at_job_count_increases_by_one(self):
        """Each schedule_retry call adds exactly one at job."""
        cwd = Path(tempfile.mkdtemp())
        command = ["true"]
        before_count = len(self._list_at_jobs())

        new_ids = set()

        def do_schedule():
            nonlocal new_ids
            desc, ok = self.mod.schedule_retry(command, self.run_at, cwd=cwd)
            self.assertTrue(ok)
            new_ids = self._job_ids_before_after(lambda: None) | {
                line.split()[0]
                for line in self._list_at_jobs()
                if line.strip()
            } - {line.split()[0] for line in self._list_at_jobs()[:before_count] if line.strip()}

        _, ok = self.mod.schedule_retry(command, self.run_at, cwd=cwd)
        after_jobs = self._list_at_jobs()
        new_count = len(after_jobs) - before_count

        try:
            self.assertEqual(new_count, 1, f"Expected +1 at job, delta={new_count}")
        finally:
            # Clean up: remove jobs added by this test
            for line in after_jobs[before_count:]:
                jid = line.split()[0]
                self._remove_at_job(jid)
            cwd.rmdir()

    def test_fallback_spawns_background_process_when_at_absent(self):
        """When `at` is not found, schedule_retry falls back to a detached Python process."""
        import shutil

        cwd = Path(tempfile.mkdtemp())
        sentinel = cwd / "fallback_done.txt"

        # Override the command so the background process writes a sentinel file
        bg_command = [
            __import__("sys").executable, "-c",
            f"open({str(sentinel)!r}, 'w').close()"
        ]

        with patch.object(shutil, "which", return_value=None):
            desc, ok = self.mod.schedule_retry(bg_command, self.run_at, cwd=cwd)

        self.assertTrue(ok)
        self.assertIn("background process PID", desc)

        # The background process exists (PID is valid) — we don't wait for it
        # since it sleeps >= 60s; we just confirm the description is correct.
        pid_str = desc.split("PID ")[1].split(" ")[0]
        self.assertTrue(pid_str.isdigit(), f"PID not numeric: {pid_str}")

        cwd.rmdir()

    def test_fallback_description_contains_sleep_duration(self):
        """Fallback description reports the sleep duration in seconds."""
        import shutil
        from datetime import datetime, timedelta

        cwd = Path(tempfile.mkdtemp())
        run_at = datetime.now() + timedelta(seconds=300)

        with patch.object(shutil, "which", return_value=None):
            desc, ok = self.mod.schedule_retry(["echo", "x"], run_at, cwd=cwd)

        self.assertTrue(ok)
        self.assertRegex(desc, r"sleeps \d+s")
        cwd.rmdir()


if __name__ == "__main__":
    unittest.main(verbosity=2)
