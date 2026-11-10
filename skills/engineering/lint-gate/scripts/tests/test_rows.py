"""rows.py: every row of the references gets a verdict, and the evidence agrees with the record."""

from __future__ import annotations

import unittest

import documents
from harness import ScriptCase

REFS = ("SKILL.md", "ref.md")


class Rows(ScriptCase):
    def test_list_prints_one_line_per_row_the_knobs_first(self) -> None:
        out = self.script("rows.py", "list", *REFS).out.splitlines()
        self.assertEqual(out[2], "| knobs: Function complexity | |")
        self.assertIn("| ref: A pipe \\| inside | |", out)
        self.assertIn(
            "| ref: Format (Rule) | |", out, "a name used twice takes its table's heading"
        )
        self.assertEqual(len(out), 2 + 8)

    def test_keys_names_the_target_keys_no_file_holds(self) -> None:
        ran = self.script("rows.py", "keys", "ref.md", "--in", "ruff-draft.toml")
        self.assertEqual(ran.code, 1)
        self.assertIn("named nowhere: ref: line-length", ran.out)
        self.assertIn("named nowhere: ref: max-complexity", ran.out)
        self.assertEqual(self.script("rows.py", "keys", "ref.md", "--in", "ref.md").code, 0)

    def test_no_command_prints_the_usage(self) -> None:
        ran = self.script("rows.py")
        self.assertEqual(ran.code, 2)
        self.assertIn("decision — <Dn>", ran.err)


class Check(ScriptCase):
    def check(self, evidence: str, *more: str) -> tuple[int, str]:
        self.write("evidence.md", evidence)
        ran = self.script("rows.py", "check", "evidence.md", *REFS, *more)
        return ran.code, ran.out

    def test_a_verdict_on_every_row_passes(self) -> None:
        code, out = self.check(documents.EVIDENCE)
        self.assertEqual(code, 0, out)
        self.assertIn("8 rows, 8 with a verdict", out)

    def test_it_counts_each_verdict(self) -> None:
        _, out = self.check(documents.EVIDENCE)
        self.assertIn(
            "verdicts: on 1, sites 1, phase 1, closed by 1, decision 1, open 1, n/a 1, out 1", out
        )

    def test_it_lists_every_row_a_verdict_leaves_outside_the_gate(self) -> None:
        _, out = self.check(documents.EVIDENCE)
        outside = out.split("outside the gate, for the human to read:\n")[1].splitlines()
        self.assertEqual(
            outside,
            [
                "  ref: Format (Rule): open — a human reads it",
                "  ref: Types: n/a — no type checker in this repo",
                "  ref: PLR2004: out — named constants",
            ],
        )

    def test_a_row_with_no_line_fails(self) -> None:
        code, out = self.check(documents.EVIDENCE.replace("| ref: Lint | phase 2 |\n", ""))
        self.assertEqual(code, 1)
        self.assertIn("no line: ref: Lint", out)

    def test_a_phase_id_need_not_be_a_number(self) -> None:
        code, out = self.check(documents.EVIDENCE.replace("| phase 2 |", "| phase gate-1 |"))
        self.assertEqual(code, 0, out)

    def test_a_verdict_of_another_form_fails(self) -> None:
        code, out = self.check(
            documents.EVIDENCE.replace("| ref: Format | on |", "| ref: Format | fine |")
        )
        self.assertEqual(code, 1)
        self.assertIn("no valid verdict: ref: Format: 'fine'", out)

    def test_a_line_for_a_row_no_reference_has_fails(self) -> None:
        code, out = self.check(documents.EVIDENCE + "| ref: Gone | on |\n")
        self.assertEqual(code, 1)
        self.assertIn("not a row of the references: ref: Gone", out)

    def test_a_knob_decision_with_no_count_fails(self) -> None:
        code, out = self.check(
            documents.EVIDENCE.replace("decision — D2, sites 4", "decision — D2")
        )
        self.assertEqual(code, 1)
        self.assertIn("a decision with no count", out)

    def test_evidence_with_no_coverage_table_fails(self) -> None:
        code, out = self.check("# Evidence\n\nNothing here.\n")
        self.assertEqual(code, 1)
        self.assertIn("no `## Coverage` table", out)


class AgainstTheRecord(ScriptCase):
    def setUp(self) -> None:
        super().setUp()
        self.script(
            "progress.py", "record", "rec.json", "--sha", "abc123", "--date", "2026-01-01",
            "--phases", "phases.json", "--layout", "layout.json",
            "--run", "ruff", "tally-record.json", "ruff check",
        )  # fmt: skip

    def check(self, old: str = "", new: str = "") -> tuple[int, str]:
        self.write(
            "evidence.md", documents.EVIDENCE.replace(old, new) if old else documents.EVIDENCE
        )
        ran = self.script("rows.py", "check", "evidence.md", *REFS, "--record", "rec.json")
        return ran.code, ran.out

    def test_evidence_that_agrees_with_the_record_passes(self) -> None:
        code, out = self.check()
        self.assertEqual(code, 0, out)

    def test_a_count_that_differs_from_the_record_fails(self) -> None:
        code, out = self.check(
            "| T201 | ruff | Capability | 2 | 1 |", "| T201 | ruff | Capability | 9 | 1 |"
        )
        self.assertEqual(code, 1)
        self.assertIn("ruff:T201 has 10 sites (production plus test), the record 3", out)

    def test_a_phase_that_differs_from_the_record_fails(self) -> None:
        code, out = self.check("Fix then flip | 2 |", "Fix then flip | 3 |")
        self.assertEqual(code, 1)
        self.assertIn("ruff:T201 is in phase '3', the record says 2", out)

    def test_a_rule_of_the_record_with_no_row_fails(self) -> None:
        code, out = self.check("| F401 | ruff | Surface | 1 | 0 | pkg | Fix by command | 1 |\n", "")
        self.assertEqual(code, 1)
        self.assertIn("no row in the debt table: ruff:F401 (1 sites in the record)", out)

    def test_a_verdict_naming_a_phase_the_layout_lacks_fails(self) -> None:
        code, out = self.check("| ref: Lint | phase 2 |", "| ref: Lint | phase 7 |")
        self.assertEqual(code, 1)
        self.assertIn("ref: Lint: phase 7 is not a phase of the record's layout", out)

    def test_a_verdict_naming_a_decision_the_layout_lacks_fails(self) -> None:
        code, out = self.check("decision — D2, sites 4", "decision — D8, sites 4")
        self.assertEqual(code, 1)
        self.assertIn("D8 is not a decision of the record's layout", out)

    def in_the_gate(self, old: str = "", new: str = "") -> tuple[int, str]:
        """`check` as a repo's gate runs it: the evidence and the record, no reference."""
        self.write("evidence.md", documents.EVIDENCE.replace(old, new))
        ran = self.script("rows.py", "check", "evidence.md", "--record", "rec.json")
        return ran.code, ran.out

    def test_with_no_reference_it_holds_the_rows_the_evidence_has(self) -> None:
        code, out = self.in_the_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("8 rows, 8 with a verdict", out)

    def test_with_no_reference_a_bad_verdict_and_a_count_off_the_record_fail(self) -> None:
        code, out = self.in_the_gate("| ref: Format | on |", "| ref: Format | fine |")
        self.assertEqual(code, 1)
        self.assertIn("no valid verdict: ref: Format: 'fine'", out)
        code, out = self.in_the_gate("Capability | 2 | 1 |", "Capability | 9 | 1 |")
        self.assertEqual(code, 1)
        self.assertIn("the record 3", out)
        code, out = self.in_the_gate("decision — D2, sites 4", "decision — D2")
        self.assertEqual(code, 1, "a knob is known by its row's name")

    def test_a_record_with_no_rule_needs_no_debt_table(self) -> None:
        self.write("none.json", "{}")
        self.script(
            "progress.py", "record", "rec.json", "--sha", "abc123", "--date", "2026-01-01",
            "--phases", "none.json", "--layout", "layout.json",
            "--run", "ruff", "none.json", "ruff",
        )  # fmt: skip
        code, out = self.check("| Rule | Tool | Class |", "| Lint | Tool | Class |")
        self.assertEqual(code, 0, out)

    def test_evidence_with_no_debt_table_fails(self) -> None:
        code, out = self.check("| Rule | Tool | Class |", "| Lint | Tool | Class |")
        self.assertEqual(code, 1)
        self.assertIn("no debt table in the evidence", out)


if __name__ == "__main__":
    unittest.main()
