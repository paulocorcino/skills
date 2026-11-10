"""Each script starts in a process of its own, under `python -I`, and leaves no bytecode."""

from __future__ import annotations

import unittest

from harness import SCRIPTS, ScriptCase

# script, arguments, exit code
STARTS = [
    ("tally.py", ("ruff", "ruff.json"), 0),
    ("debt.py", ("shrink", "cargo-base.toml", "cargo-base.toml"), 0),
    ("drift.py", ("age", "no-asof.md"), 1),
    ("progress.py", ("--help",), 0),
    ("rows.py", ("list", "SKILL.md", "ref.md"), 0),
]


class Isolated(ScriptCase):
    def test_every_script_finds_its_sibling_files(self) -> None:
        for name, args, code in STARTS:
            with self.subTest(name):
                ran = self.isolated(name, *args)
                self.assertNotIn("ModuleNotFoundError", ran.err)
                self.assertEqual(ran.code, code, ran.err)

    def test_a_run_writes_no_bytecode_beside_the_scripts(self) -> None:
        before = set(SCRIPTS.glob("__pycache__/*"))
        self.isolated("progress.py", "--help")
        self.assertEqual(set(SCRIPTS.glob("__pycache__/*")), before)


if __name__ == "__main__":
    unittest.main()
