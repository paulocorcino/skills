"""progress.py: the record, the history, the point, and what can start next."""

from __future__ import annotations

import json
import unittest

from harness import Ran, ScriptCase

RECORD = (
    "record", "rec.json", "--sha", "abc123", "--date", "2026-01-01", "--phases", "phases.json",
    "--run", "ruff", "tally-record.json", "ruff check --output-format json",
    "--tool", "ruff=0.17.4", "--draft", "ruff-draft.toml",
)  # fmt: skip


class Recorded(ScriptCase):
    """Each test starts from the record of the fixture plan: phases 0 to 3, decisions D1 and D2."""

    def setUp(self) -> None:
        super().setUp()
        self.progress(*RECORD, "--layout", "layout.json")

    def progress(self, *args: str) -> Ran:
        return self.script("progress.py", *args)

    def point(self, *more: str, tally: str = "tally-point.json", tool: str = "0.17.4") -> Ran:
        measure = ("--run", "ruff", tally, "--tool", f"ruff={tool}")
        return self.progress("point", "rec.json", *measure, "--sha", "def456", *more)

    def section(self, out: str, title: str) -> list[str]:
        """The lines `next` prints under a title."""
        body = out.split(f"{title}:\n", 1)[1]
        lines = []
        for line in body.splitlines():
            if not line.startswith("  "):
                break
            lines.append(line.strip())
        return lines


class Record(Recorded):
    def test_several_drafts_follow_one_flag_or_one_each(self) -> None:
        for drafts in (
            ("--draft", "ruff-draft.toml", "tsc-draft.json"),
            ("--draft", "tsc-draft.json"),
        ):
            self.progress(*RECORD, *drafts)
            rec = json.loads((self.folder / "rec.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(rec["drafts"]), ["ruff-draft.toml", "tsc-draft.json"])

    def test_it_holds_the_counts_the_tools_and_the_layout(self) -> None:
        rec = json.loads((self.folder / "rec.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["runs"]["ruff"]["counts"], {"C901": 1, "F401": 1, "T201": 3})
        self.assertEqual(rec["tools"], {"ruff": "0.17.4"})
        self.assertEqual(rec["layout"]["phases"]["2"], {"lane": "python", "waits": ["1"]})

    def test_a_rule_with_sites_and_no_phase_fails(self) -> None:
        self.write("short.json", '{"T201": "2"}')
        ran = self.progress(*RECORD[:6], "--phases", "short.json", *RECORD[8:])
        self.assertEqual(ran.code, 1)
        self.assertIn("no phase: ruff:C901 (1 sites)", ran.out)

    def test_written_again_without_a_layout_it_keeps_the_one_it_had(self) -> None:
        self.progress(*RECORD)
        rec = json.loads((self.folder / "rec.json").read_text(encoding="utf-8"))
        self.assertIn("D1", rec["layout"]["decisions"])

    def test_commands_prints_each_run_to_measure_again(self) -> None:
        ran = self.progress("commands", "rec.json")
        self.assertIn("ruff: ruff check --output-format json", ran.out)
        self.assertIn("at ruff 0.17.4", ran.out)
        self.assertNotIn("$SC", ran.out)

    def test_commands_says_what_the_scratch_folder_of_a_command_is(self) -> None:
        run = ("--run", "ruff", "tally-record.json", "ruff check -o $SC/ruff.json")
        self.progress(*RECORD[:8], *run, *RECORD[12:])
        out = self.progress("commands", "rec.json").out
        self.assertTrue(out.startswith("`$SC` in a command is a scratch folder outside the repo"))


class Check(Recorded):
    def test_a_whole_plan_that_matches_the_layout_passes(self) -> None:
        ran = self.progress("check", "rec.json", "--plan", "plan.md")
        self.assertEqual(ran.code, 0, ran.out)

    def test_a_plan_cut_short_fails(self) -> None:
        ran = self.progress("check", "rec.json", "--plan", "plan-cut.md")
        self.assertEqual(ran.code, 1)
        self.assertIn("the last line is not the end marker", ran.out)
        self.assertIn("phase 3 is in the layout but the plan has no `### Phase 3` heading", ran.out)
        self.assertIn("the plan has `### Phase 9`, which is not in the layout", ran.out)


class History(Recorded):
    def test_each_event_is_one_appended_line(self) -> None:
        self.progress("decide", "rec.json", "D1", "the cli module", "--date", "2026-01-02")
        self.progress("issue", "rec.json", "2", "https://example.test/1", "--date", "2026-01-02")
        self.progress("note", "rec.json", "slice a landed", "--date", "2026-01-03")
        lines = (self.folder / "rec.history.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [json.loads(line)["kind"] for line in lines], ["decision", "issue", "note"]
        )

    def test_an_id_the_layout_does_not_hold_is_refused(self) -> None:
        refused = [
            self.progress("decide", "rec.json", "D9", "x", "--date", "2026-01-02"),
            self.progress(
                "issue", "rec.json", "7", "https://example.test/2", "--date", "2026-01-02"
            ),
            self.progress("close", "rec.json", "7", "done", "--date", "2026-01-02"),
        ]
        self.assertEqual([ran.code for ran in refused], [1, 1, 1])
        self.assertFalse((self.folder / "rec.history.jsonl").exists())

    def test_log_prints_the_state_in_date_order(self) -> None:
        self.progress("note", "rec.json", "slice a landed", "--date", "2026-01-03")
        self.progress("decide", "rec.json", "D1", "the cli module", "--date", "2026-01-02")
        self.progress(
            "close", "rec.json", "0", "one command runs every check", "--date", "2026-01-02"
        )
        out = self.progress("log", "rec.json").out
        self.assertIn("D1 (holds 2): answered 2026-01-02: the cli module", out)
        self.assertIn("D2 (holds nothing): open", out)
        history = out.split("history:\n")[1].splitlines()
        self.assertEqual(
            [line.strip() for line in history],
            [
                "2026-01-01 abc123: record, 5 sites",
                "2026-01-02: Phase 0 closed: one command runs every check",
                "2026-01-03: slice a landed",
            ],
        )


class Point(Recorded):
    def test_each_rule_gets_its_state(self) -> None:
        ran = self.point("--date", "2026-01-04", "--config", "ruff-head.toml")
        self.assertEqual(ran.code, 1)
        self.assertEqual(self.row(ran.out, "ruff:C901"), ["3", "1", "2", "up"])
        self.assertEqual(self.row(ran.out, "ruff:T201"), ["2", "3", "1", "down"])
        self.assertEqual(self.row(ran.out, "ruff:F401")[3:], ["ready", "to", "flip"])
        self.assertEqual(self.row(ran.out, "ruff:E501")[3:], ["off", "in", "the", "repo"])
        self.assertIn(
            "record abc123 2026-01-01: 5 sites; now def456 2026-01-04: 4 sites (-1 net)", ran.out
        )

    def test_a_rule_at_zero_with_no_entry_left_is_closed(self) -> None:
        ran = self.point("--date", "2026-01-04")
        self.assertEqual(self.row(ran.out, "ruff:F401")[3:], ["closed"])

    def test_a_new_rule_under_a_bumped_tool_is_scope(self) -> None:
        ran = self.point("--date", "2026-01-04", tool="0.18.0")
        self.assertEqual(self.row(ran.out, "ruff:E501")[3:], ["scope"])
        self.assertIn("version changed: ruff 0.17.4 -> 0.18.0", ran.out)
        self.assertIn("plus 1 sites of scope", ran.out)

    def test_a_debt_comment_above_the_count_is_named(self) -> None:
        ran = self.point("--date", "2026-01-04", "--config", "ruff-head.toml")
        self.assertIn("debt comment above the count: ruff:T201 says 3, now 1", ran.out)

    def test_a_flat_measure_passes_and_hides_the_flat_rules(self) -> None:
        ran = self.point("--date", "2026-01-04", tally="tally-record.json")
        self.assertEqual(ran.code, 0)
        self.assertIn("(3 rules flat; --all lists them)", ran.out)

    def test_every_run_of_the_record_is_measured(self) -> None:
        ran = self.progress(
            "point",
            "rec.json",
            "--run",
            "mypy",
            "tally-point.json",
            "--sha",
            "x",
            "--date",
            "2026-01-04",
        )
        self.assertEqual(ran.code, 1)
        self.assertIn("run ruff not measured", ran.out)
        self.assertIn("run mypy is not in the record", ran.out)

    def test_append_adds_the_point_to_the_history(self) -> None:
        self.point("--date", "2026-01-04", "--config", "ruff-head.toml", "--append")
        line = (self.folder / "rec.history.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        event = json.loads(line)
        self.assertEqual(event["counts"], {"ruff:C901": 2, "ruff:E501": 1, "ruff:T201": 1})
        self.assertEqual(event["ready"], ["ruff:F401"])
        self.assertEqual(event["total"], 4)

    def test_show_prints_the_phase_with_its_state(self) -> None:
        self.point("--date", "2026-01-04", "--config", "ruff-head.toml", "--append")
        out = self.progress("show", "rec.json", "2", "--plan", "plan.md").out
        self.assertTrue(out.startswith("### Phase 2 — Output"))
        self.assertNotIn("Phase 3", out)
        self.assertIn("--- state, from the last point 2026-01-04 def456", out)
        self.assertIn("waits for Phase 1: ready to flip (1 of 1 rules at 0)", out)
        self.assertIn("this phase: in progress (0 of 1 rules at 0)", out)
        self.assertIn("ruff:T201: record 3, now 1", out)
        self.assertIn("held by D1: open, the slices it holds wait", out)


class Next(Recorded):
    def next(self) -> str:
        ran = self.progress("next", "rec.json")
        self.assertEqual(ran.code, 0)
        return ran.out

    def close_gate(self) -> None:
        self.progress(
            "close", "rec.json", "0", "one command runs every check", "--date", "2026-01-02"
        )

    def test_only_the_phase_that_waits_for_nothing_can_start(self) -> None:
        out = self.next()
        self.assertEqual(
            self.section(out, "can start"), ["Phase 0 (lane gate): no rule: read by its Done when"]
        )
        self.assertEqual(len(self.section(out, "waiting")), 3)
        self.assertEqual(self.section(out, "closed"), ["none"])
        self.assertIn("closed by `progress.py close`", out)

    def test_a_phase_with_no_rule_closes_by_note_and_frees_each_lane(self) -> None:
        self.close_gate()
        out = self.next()
        started = [line.split(":")[0] for line in self.section(out, "can start")]
        self.assertEqual(started, ["Phase 1 (lane python)", "Phase 3 (lane shape)"])
        self.assertEqual(
            self.section(out, "waiting"),
            ["Phase 2 (lane python): waits for Phase 1 (not started (0 of 1 rules at 0))"],
        )
        self.assertIn("Phase 0: closed by note 2026-01-02", self.section(out, "closed")[0])

    def test_a_phase_ready_to_flip_still_holds_the_next(self) -> None:
        self.close_gate()
        self.point("--date", "2026-01-04", "--config", "ruff-head.toml", "--append")
        out = self.next()
        self.assertIn(
            "Phase 1 (lane python): ready to flip (1 of 1 rules at 0)",
            self.section(out, "can start"),
        )
        self.assertIn("Phase 2 (lane python): waits for Phase 1", self.section(out, "waiting")[0])

    def test_a_closed_phase_frees_the_next_and_an_open_decision_marks_it(self) -> None:
        self.close_gate()
        self.point("--date", "2026-01-04", "--append")
        out = self.next()
        self.assertIn(
            "Phase 2 (lane python): in progress (0 of 1 rules at 0); "
            "held by D1 (open): its slices under it wait",
            self.section(out, "can start"),
        )
        self.assertEqual(
            self.section(out, "open decisions that hold a phase"), ["D1 holds Phase 2"]
        )

    def test_an_answered_decision_holds_nothing(self) -> None:
        self.close_gate()
        self.point("--date", "2026-01-04", "--append")
        self.progress("decide", "rec.json", "D1", "the cli module", "--date", "2026-01-05")
        out = self.next()
        self.assertNotIn("held by", out)
        self.assertEqual(self.section(out, "open decisions that hold a phase"), ["none"])

    def test_a_phase_closed_by_note_with_sites_left_says_so(self) -> None:
        ran = self.progress(
            "close", "rec.json", "2", "the last slice waits on D1", "--date", "2026-01-05"
        )
        self.assertIn(
            "3 sites left at the last point: closed by this note, not by the counts", ran.out
        )
        closed = self.section(self.next(), "closed")
        note = "closed by note 2026-01-05: the last slice waits on D1"
        self.assertEqual(closed, [f"Phase 2: {note} (3 sites left at the last point)"])


if __name__ == "__main__":
    unittest.main()
