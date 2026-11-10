"""drift.py: a tool's own list of rules against another version and against a draft."""

from __future__ import annotations

import unittest

from harness import ScriptCase

# format, the tool's list, the draft, the lines `check` prints for the draft's bad names
CHECKS = [
    ("ruff", "ruff-rules-new.json", "ruff-draft.toml", ["deprecated: F401", "unknown: GONE99"]),
    ("oxlint", "oxlint-rules.json", "oxlint-draft.json", ["unknown: eslint/no-such-rule"]),
    ("clippy", "clippy-help.txt", "clippy-draft.toml", ["unknown: clippy::no_such_lint"]),
    ("tsc", "tsc-options.txt", "tsc-draft.json", ["unknown: noSuchOption"]),
    ("golangci", "golangci-linters.txt", "golangci-draft.yml", ["unknown: nosuchlinter"]),
]


class Drift(ScriptCase):
    def test_diff_names_the_rules_added_removed_and_changed(self) -> None:
        ran = self.script("drift.py", "diff", "ruff", "ruff-rules-old.json", "ruff-rules-new.json")
        self.assertEqual(ran.code, 0)
        self.assertIn("4 -> 4 rules", ran.out)
        self.assertIn("added (1):\n  NEW001", ran.out)
        self.assertIn("removed (1):\n  OLD001", ran.out)
        self.assertIn("F401: stable -> deprecated", ran.out)
        self.assertIn("PRE001: preview -> stable", ran.out)

    def test_check_names_what_the_tool_does_not_know_in_each_format(self) -> None:
        for fmt, listing, draft, bad in CHECKS:
            with self.subTest(fmt):
                ran = self.script("drift.py", "check", fmt, listing, draft)
                self.assertEqual(ran.code, 1)
                found = [line.split(" (")[0] for line in ran.out.splitlines()[:-1]]
                self.assertEqual(found, bad)

    def test_a_prefix_selects_a_ruff_family(self) -> None:
        ran = self.script("drift.py", "check", "ruff", "ruff-rules-new.json", "ruff-draft.toml")
        self.assertNotIn("PRE", ran.out)

    def test_a_deprecated_linter_under_disable_is_off_on_purpose(self) -> None:
        ran = self.script(
            "drift.py", "check", "golangci", "golangci-linters.txt", "golangci-draft.yml"
        )
        self.assertNotIn("oldlint", ran.out)

    def test_a_draft_of_known_names_passes(self) -> None:
        self.write("good.toml", '[lint]\nselect = ["ALL"]\nignore = ["T201"]\n')
        ran = self.script("drift.py", "check", "ruff", "ruff-rules-new.json", "good.toml")
        self.assertEqual(ran.code, 0)
        self.assertIn("every name in the draft is known and stable", ran.out)

    def test_an_empty_list_fails_with_a_warning(self) -> None:
        ran = self.script("drift.py", "check", "ruff", "empty.json", "ruff-draft.toml")
        self.assertEqual(ran.code, 1)
        self.assertIn("the tool's list is empty", ran.err)

    def test_age_asks_for_research_on_a_reference_with_no_date(self) -> None:
        ran = self.script("drift.py", "age", "no-asof.md")
        self.assertEqual(ran.code, 1)
        self.assertIn("no `As of YYYY-MM-DD:` line: research required", ran.out)

    def test_age_reads_a_date_line_that_names_no_tool(self) -> None:
        self.write("fresh.md", "# Target\n\nAs of 2999-01-01: no version pinned here.\n")
        ran = self.script("drift.py", "age", "fresh.md")
        self.assertEqual(ran.code, 0)
        self.assertIn("research: not required", ran.out)

    def test_age_asks_for_research_past_the_days(self) -> None:
        self.write("old.md", "# Target\n\nAs of 2000-01-01: no version pinned here.\n")
        ran = self.script("drift.py", "age", "--days", "30", "old.md")
        self.assertEqual(ran.code, 1)
        self.assertIn("days old", ran.out)

    def test_anything_else_prints_the_usage(self) -> None:
        ran = self.script("drift.py", "nope")
        self.assertEqual(ran.code, 2)
        self.assertIn("drift.py diff FORMAT", ran.err)


if __name__ == "__main__":
    unittest.main()
