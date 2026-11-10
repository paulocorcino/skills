"""Run the scripts as their callers do: by command line, from a folder of fixtures."""

from __future__ import annotations

import contextlib
import io
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import NamedTuple

import fixtures

SCRIPTS = Path(__file__).resolve().parent.parent


class Ran(NamedTuple):
    code: int
    out: str
    err: str


class ScriptCase(unittest.TestCase):
    """Each test gets a fresh folder holding every fixture, and runs the scripts in it."""

    folder: Path
    with_fixtures = True

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        if self.with_fixtures:
            fixtures.write(self.folder)

    def script(self, name: str, *args: str) -> Ran:
        """Run a script as `python NAME ARGS` from the folder, inside this process:
        a process per call makes the suite ten times slower."""
        out, err = io.StringIO(), io.StringIO()
        argv, sys.argv = sys.argv, [str(SCRIPTS / name), *args]
        code: str | int | None = 0
        try:
            with contextlib.chdir(self.folder), redirect_stdout(out), redirect_stderr(err):
                runpy.run_path(sys.argv[0], run_name="__main__")
        except SystemExit as stop:
            code = stop.code
        finally:
            sys.argv = argv
        if isinstance(code, str):  # `sys.exit("message")` prints the message and exits 1
            err.write(code + "\n")
        return Ran(
            code if isinstance(code, int) else int(code is not None), out.getvalue(), err.getvalue()
        )

    def isolated(self, name: str, *args: str) -> Ran:
        """Run a script in a process of its own, as `python -I NAME ARGS`."""
        done = subprocess.run(
            [sys.executable, "-I", str(SCRIPTS / name), *args],
            cwd=self.folder,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return Ran(done.returncode, done.stdout, done.stderr)

    def git(self, *args: str) -> None:
        identity = ["-c", "user.name=t", "-c", "user.email=t@example.test"]
        subprocess.run(
            ["git", *identity, "-c", "core.autocrlf=false", *args],
            cwd=self.folder,
            capture_output=True,
            check=True,
        )

    def write(self, name: str, body: str) -> None:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline="\n")

    def row(self, out: str, name: str) -> list[str]:
        """The cells of the table row that starts with `name`."""
        head = name.split()
        found = [line.split() for line in out.splitlines() if line.split()[: len(head)] == head]
        self.assertTrue(found, f"no row {name!r} in:\n{out}")
        return found[0][len(head) :]
