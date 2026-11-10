"""tally.py added: a site on a line the change writes fails; a line it only moves does not."""

from __future__ import annotations

import json
import unittest

from harness import ScriptCase

BASE = """fn a() {}

fn old() {
    x.unwrap();
}

fn other() {
    w.unwrap();
}
"""


def clippy_output(*sites: tuple[str, int]) -> str:
    """A clippy run with one `unwrap_used` at each (file, line)."""
    lines = []
    for file, line in sites:
        span = {"file_name": file, "line_start": line, "column_start": 7, "is_primary": True}
        message = {
            "code": {"code": "clippy::unwrap_used"},
            "level": "warning",
            "message": f"unwrap at {file}:{line}",
            "spans": [span],
        }
        lines.append(json.dumps({"reason": "compiler-message", "message": message}))
    return "\n".join(lines) + "\n"


class Added(ScriptCase):
    with_fixtures = False  # an untracked file is new code: the repo holds only what a test writes

    def setUp(self) -> None:
        super().setUp()
        self.git("init", "-q", ".")
        self.write("src/a.rs", BASE)
        self.git("add", "src")
        self.git("commit", "-q", "-m", "base")

    def added(self, *sites: tuple[str, int], ignore: str = "") -> tuple[int, str]:
        (self.folder / "draft.json").write_text(clippy_output(*sites), encoding="utf-8")
        options = ["--ignore", ignore] if ignore else []
        ran = self.script("tally.py", "added", "clippy", "draft.json", "--base", "HEAD", *options)
        return ran.code, ran.out + ran.err

    def test_a_site_on_an_old_line_is_the_plans(self) -> None:
        self.write("src/a.rs", BASE + "\nfn new() {}\n")
        code, out = self.added(("src/a.rs", 4))
        self.assertEqual(code, 0)
        self.assertIn("0 sites on lines this change adds", out)

    def test_a_site_on_a_new_line_fails(self) -> None:
        self.write("src/a.rs", BASE + "\nfn new() {\n    y.unwrap();\n}\n")
        code, out = self.added(("src/a.rs", 4), ("src/a.rs", 12))
        self.assertEqual(code, 1)
        self.assertIn("src/a.rs:12:7: clippy::unwrap_used", out)
        self.assertIn("1 sites on lines this change adds", out)

    def test_a_site_in_an_untracked_file_fails(self) -> None:
        self.write("src/new.rs", "fn n() {\n    z.unwrap();\n}\n")
        code, out = self.added(("src/new.rs", 2))
        self.assertEqual(code, 1)
        self.assertIn("src/new.rs:2:7", out)

    def test_ignore_leaves_a_rule_out(self) -> None:
        self.write("src/a.rs", BASE + "\nfn new() {\n    y.unwrap();\n}\n")
        code, _ = self.added(("src/a.rs", 12), ignore="clippy::unwrap_used")
        self.assertEqual(code, 0)

    def test_a_function_moved_to_a_new_file_is_not_new(self) -> None:
        """A file split carries its debt sites along: the lines are removed here and added there."""
        kept, moved = BASE.split("fn old()")
        self.write("src/a.rs", kept + moved.split("}\n\n", 1)[1])
        self.write("src/split.rs", "fn old() {\n    x.unwrap();\n}\n")
        code, out = self.added(("src/split.rs", 2), ("src/a.rs", 4))
        self.assertEqual(code, 0, out)
        self.assertIn("3 added lines are moves", out)

    def test_a_function_moved_inside_its_file_is_not_new(self) -> None:
        head, rest = BASE.split("fn old()")
        old, other = ("fn old()" + rest).split("\n\n", 1)
        self.write("src/a.rs", head + other + "\n" + old + "\n")
        code, out = self.added(("src/a.rs", 4), ("src/a.rs", 8))
        self.assertEqual(code, 0, out)

    def test_a_reindented_line_is_not_new(self) -> None:
        self.write("src/a.rs", BASE.replace("    x.unwrap();", "        x.unwrap();"))
        code, out = self.added(("src/a.rs", 4))
        self.assertEqual(code, 0, out)

    def test_a_rewrapped_statement_is_not_new(self) -> None:
        self.write("src/a.rs", BASE.replace("    x.unwrap();", "    x\n        .unwrap();"))
        code, out = self.added(("src/a.rs", 5))
        self.assertEqual(code, 0, out)
        self.assertIn("2 added lines are moves", out)

    def test_a_line_the_formatter_rewrote_is_not_new(self) -> None:
        """A quote style, a trailing comma, a statement split under parentheses."""
        self.write("src/a.rs", BASE.replace("x.unwrap();", "x.call('a', 1).unwrap();"))
        self.git("commit", "-q", "-am", "a call to format")
        self.write(
            "src/a.rs",
            BASE.replace("x.unwrap();", 'x.call(\n        "a",\n        1,\n    ).unwrap();'),
        )
        code, out = self.added(("src/a.rs", 7))
        self.assertEqual(code, 0, out)

    def test_a_site_written_into_a_moved_line_is_new(self) -> None:
        """`x.y` to `x!.y` keeps every word and adds a site: layout is not all punctuation."""
        self.write("src/a.rs", BASE.replace("x.unwrap();", "x!.unwrap();"))
        code, _ = self.added(("src/a.rs", 4))
        self.assertEqual(code, 1)

    def test_a_moved_line_pays_for_one_new_line_only(self) -> None:
        """The same text written twice where it was removed once: the second copy is new."""
        self.write("src/a.rs", BASE.replace("    x.unwrap();\n", ""))
        self.write("src/split.rs", "fn p() {\n    x.unwrap();\n    x.unwrap();\n}\n")
        code, out = self.added(("src/split.rs", 2), ("src/split.rs", 3))
        self.assertEqual(code, 1)
        self.assertIn("1 sites on lines this change adds", out)

    def test_a_base_git_does_not_know_fails(self) -> None:
        (self.folder / "draft.json").write_text(clippy_output(), encoding="utf-8")
        ran = self.script("tally.py", "added", "clippy", "draft.json", "--base", "nosuchref")
        self.assertEqual(ran.code, 1)
        self.assertIn("git diff nosuchref failed", ran.err)


if __name__ == "__main__":
    unittest.main()
