"""tally.py: the count of sites per rule, the ratchet, the curve, the pattern and the sizes."""

from __future__ import annotations

import json
import unittest

from harness import ScriptCase

# format, output file, sites, files, and a word the warning carries ("" for none)
FORMATS = [
    ("mypy", "mypy.jsonl", "2", "2", "syntax error"),
    ("pyright", "pyright.json", "1", "1", ""),
    ("eslint", "eslint.json", "2", "1", "Parsing error"),
    ("oxlint", "oxlint.json", "3", "3", "no rule"),
    ("golangci", "golangci.json", "4", "3", "typecheck"),
    ("tsc", "tsc.txt", "1", "1", ""),
    ("vulture", "vulture.txt", "2", "1", ""),
    ("knip", "knip.json", "2", "1", ""),
    ("astgrep", "astgrep.jsonl", "1", "1", ""),
    ("jscpd", "jscpd.json", "2", "1", ""),
]


class Plain(ScriptCase):
    def test_a_site_reported_twice_counts_once(self) -> None:
        ran = self.script("tally.py", "clippy", "clippy.prod.json")
        self.assertEqual(ran.code, 0)
        self.assertEqual(self.row(ran.out, "clippy::unwrap_used"), ["1", "1", "0", "0"])
        self.assertEqual(self.row(ran.out, "total"), ["4", "3", "1", "0"])

    def test_a_crate_that_did_not_build_warns(self) -> None:
        ran = self.script("tally.py", "clippy", "clippy.prod.json")
        self.assertIn("compile error E0308", ran.err)
        self.assertIn("the build did not finish", ran.err)

    def test_the_tools_own_fixes_split_safe_from_unsafe(self) -> None:
        ran = self.script("tally.py", "ruff", "ruff.json")
        self.assertEqual(self.row(ran.out, "F401"), ["1", "1", "1", "0"])
        self.assertEqual(self.row(ran.out, "T201"), ["1", "1", "0", "1"])
        self.assertIn("SyntaxError", ran.err)

    def test_scope_depth_groups_by_path(self) -> None:
        ran = self.script("tally.py", "clippy", "clippy.prod.json", "--scope-depth", "2")
        self.assertEqual(self.row(ran.out, "crates/b"), ["2"])

    def test_every_format_is_counted(self) -> None:
        for fmt, output, sites, files, warning in FORMATS:
            with self.subTest(fmt):
                ran = self.script("tally.py", fmt, output)
                self.assertEqual(ran.code, 0)
                self.assertEqual(self.row(ran.out, "total"), [sites, files])
                self.assertIn(warning, ran.err)

    def test_golangci_counts_per_check_id_and_rule_name(self) -> None:
        ran = self.script("tally.py", "golangci", "golangci.json")
        self.assertEqual(self.row(ran.out, "gosec:G104"), ["1", "1"])
        self.assertEqual(self.row(ran.out, "revive:argument-limit"), ["1", "1"])

    def test_an_empty_output_warns_unless_the_tool_is_silent_when_clean(self) -> None:
        self.assertIn("the output is empty", self.script("tally.py", "ruff", "empty.json").err)
        self.assertEqual(self.script("tally.py", "tsc", "empty.json").err, "")

    def test_diff_gives_the_sites_of_b_that_a_lacks(self) -> None:
        self.script("tally.py", "clippy", "clippy.prod.json", "--json", "prod.json")
        self.script("tally.py", "clippy", "clippy.all.json", "--json", "all.json")
        ran = self.script("tally.py", "diff", "prod.json", "all.json", "--json", "test.json")
        self.assertEqual(self.row(ran.out, "total"), ["1", "1"])
        sites = json.loads((self.folder / "test.json").read_text(encoding="utf-8"))
        self.assertEqual(sites, {"clippy::unwrap_used": ["crates/a/tests/it.rs:2:5"]})


class Ratchet(ScriptCase):
    def test_the_count_it_holds_passes(self) -> None:
        self.assertEqual(self.script("tally.py", "ruff", "ruff.json", "--expect", "5").code, 0)

    def test_a_count_above_is_new_debt(self) -> None:
        ran = self.script("tally.py", "ruff", "ruff.json", "--expect", "1")
        self.assertEqual(ran.code, 1)
        self.assertIn("new debt", ran.out)

    def test_a_count_below_lowers_the_ratchet(self) -> None:
        ran = self.script("tally.py", "ruff", "ruff.json", "--expect", "9")
        self.assertEqual(ran.code, 1)
        self.assertIn("lower the ratchet to 5", ran.out)


class Curve(ScriptCase):
    def test_it_counts_the_sites_over_each_limit(self) -> None:
        ran = self.script(
            "tally.py", "curve", "ruff", "ruff.json", "--rule", "C901", "--at", "5,10"
        )
        self.assertEqual(self.row(ran.out, "5"), ["2"])
        self.assertEqual(self.row(ran.out, "10"), ["1"])
        self.assertIn("highest: 13 pkg/sub/b.py:4", ran.out)

    def test_it_reads_each_tools_message(self) -> None:
        cases = [
            ("clippy", "clippy.prod.json", "clippy::cognitive_complexity", "23"),
            ("eslint", "eslint.json", "complexity", "13"),
            ("golangci", "golangci.json", "revive:argument-limit", "7"),
            ("jscpd", "jscpd.json", "jscpd:python", "60"),
        ]
        for fmt, output, rule, highest in cases:
            with self.subTest(fmt):
                ran = self.script("tally.py", "curve", fmt, output, "--rule", rule)
                self.assertIn(f"highest: {highest} ", ran.out)

    def test_it_reads_the_depth_of_each_nested_block(self) -> None:
        deep = [
            {
                "code": "eslint(max-depth)",
                "filename": "src/a.ts",
                "message": f"Blocks are nested too deeply ({depth}). Maximum allowed is 0.",
                "labels": [{"span": {"line": depth, "column": 1}}],
            }
            for depth in (1, 2, 3, 4)
        ]
        self.write("depth.json", json.dumps({"diagnostics": deep}))
        ran = self.script(
            "tally.py", "curve", "oxlint", "depth.json", "--rule", "eslint(max-depth)", "--at", "3"
        )
        self.assertEqual(self.row(ran.out, "3"), ["1"])
        self.assertEqual(ran.err, "")

    def test_a_rule_with_no_value_fails(self) -> None:
        ran = self.script("tally.py", "curve", "ruff", "ruff.json", "--rule", "T201")
        self.assertEqual(ran.code, 1)
        self.assertIn("no site of T201 with a value", ran.err)


class Tracked(ScriptCase):
    """`pattern` and `sizes` read the files git tracks."""

    def setUp(self) -> None:
        super().setUp()
        self.write("src/a.rs", "fn a() {}\n// TODO: one\nfn b() {}\n\n")
        self.write("src/b.rs", "fn c() {}\n// FIXME two\n" + "x" * 130 + "\n")
        self.git("init", "-q", ".")
        self.git("add", "src")
        self.write("src/untracked.rs", "// TODO: not counted\n")

    def test_pattern_counts_matching_lines_of_tracked_files(self) -> None:
        ran = self.script("tally.py", "pattern", r"//\s*(TODO|FIXME)\b", "--ext", ".rs")
        self.assertEqual(ran.code, 0)
        self.assertIn("2 files read", ran.out)
        self.assertEqual(self.row(ran.out, "total"), ["2", "2"])

    def test_pattern_is_a_ratchet_with_expect(self) -> None:
        held = self.script("tally.py", "pattern", "TODO", "src", "--ext", ".rs", "--expect", "1")
        grown = self.script("tally.py", "pattern", "TODO", "src", "--ext", ".rs", "--expect", "0")
        self.assertEqual((held.code, grown.code), (0, 1))

    def test_no_tracked_file_fails(self) -> None:
        ran = self.script("tally.py", "pattern", "x", "--ext", ".zz")
        self.assertEqual(ran.code, 1)
        self.assertIn("no tracked file", ran.err)

    def test_sizes_counts_non_blank_lines_and_wide_lines(self) -> None:
        ran = self.script("tally.py", "sizes", "--ext", ".rs", "--lines", "1,3", "--width", "100")
        self.assertEqual(self.row(ran.out, "1"), ["2"])
        self.assertEqual(self.row(ran.out, "3"), ["0"])
        self.assertEqual(self.row(ran.out, "100"), ["1"])


if __name__ == "__main__":
    unittest.main()
