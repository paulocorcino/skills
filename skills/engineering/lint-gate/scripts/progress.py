#!/usr/bin/env python3
"""The burndown of a lint transition plan: what the plan measured, what is left.

  progress.py record RECORD --sha SHA --date DATE --phases PHASES.json
                     --run NAME TALLY COMMAND [--run ...] [--tool NAME=VERSION ...]
                     [--draft PATH ...] [--layout LAYOUT.json]
  progress.py check RECORD [--plan PLAN]
  progress.py commands RECORD
  progress.py next RECORD
  progress.py show RECORD PHASE --plan PLAN
  progress.py decide RECORD ID ANSWER --date DATE
  progress.py issue RECORD ID URL --date DATE
  progress.py note RECORD TEXT --date DATE
  progress.py close RECORD PHASE WHY --date DATE
  progress.py log RECORD
  progress.py point RECORD --run NAME TALLY [--run ...] [--tool NAME=VERSION ...]
                    --sha SHA --date DATE [--config CONFIG ...] [--append]

`record` writes the record of the measure the plan was cut from: per run, the
command and the sites per rule (from the `tally.py --json` file of that run);
the tool versions; a hash of each draft config the commands read; and the phase
of each rule (PHASES: {"<rule as tally prints it>": "<phase>"}). It fails when
a rule with sites has no phase. Run it from the repo root; draft paths are
relative to it. NAME is the tool's name, as in --tool, so a version change
is tied to its run.

LAYOUT is the shape of the plan: {"phases": {"<id>": {"lane": "<lane>", "waits":
["<id>", ...]}}, "decisions": {"<id>": {"holds": ["<phase id>", ...]}}}; every
phase of PHASES is in it, and a phase with no rule (Phase 0) is in it too. A
record written again without --layout keeps the layout it had.

`check` fails when a rule with sites has no phase, or a phase names a rule the
record does not hold. With --plan it also reads the plan: every section of the
contract is there, each phase of the layout has its `### Phase <id>` heading and
each such heading a phase in the layout, each decision of the layout is named
in the plan, and the last line is the end marker, so a plan cut short fails.
`commands` prints each run's command, to measure again; a command names the
scratch folder its output goes to as `$SC`, and `commands` says to set it.

The state of the plan lives in the history file, one JSON line per event, and
only these commands write it, by appending: `decide` records the answer to a
decision, `issue` the issue opened for a phase or a decision, `note` a line of
progress (a slice landed, a flip), `close` that a phase is closed. `log` prints
the state: each decision open or answered, each issue, then the notes, the
closes and the points in date order. `show` prints one phase for the agent that
works it: its section of the plan, its lane and the state of each phase it
waits for, its rules with the counts of the record and of the last point, each
decision that holds it, and its issue.

A phase is closed when the last point has every rule of it at 0 and flipped, or
when the history holds its `close`. A phase with no rule (Phase 0) is closed
only by `close`, once its Done when holds; so is a phase whose last sites sit
in a slice held by a decision that edits no file of the phases waiting for it.

`next` prints the call to action from the layout and the history: the phases
that can start (not closed, each phase they wait for closed), the phases that
wait and for what, the phases closed, and the open decisions that hold a phase,
the earliest held first. A phase that can start under an open decision says so:
its slices under that decision wait, the rest goes on.

`point` compares a new measure, one tally file per run of the record, with the
record and with the last point: see `point.py` for the states. With --config
(each config that holds a debt list), a rule `closed` that its config still
lists as debt is `ready to flip`. --append adds the point to the history
(`<RECORD stem>.history.jsonl`). It exits 1 on `up` or `off in the repo`, after
printing everything.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.dont_write_bytecode = True  # a run writes nothing into this folder
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling files, under `python -I` too

import ledger
import point
from ledger import Layout, Record
from narrow import read, utf8_console

if TYPE_CHECKING:
    from collections.abc import Callable

SECTIONS = [
    "Working this plan",
    "Target",
    "Decisions for the human",
    "Phases",
    "One-way doors",
    "Fix discipline",
]
END = "<!-- end of the plan: progress.py check reads this line -->"
_PHASE = re.compile(r"^(#{3,4}) Phase ([\w.-]+)\b.*$", re.MULTILINE)


def phase_sections(plan: str) -> dict[str, str]:
    """Each `### Phase <id>` heading and its text, up to the next heading of its level or above."""
    out = {}
    for m in _PHASE.finditer(plan):
        level = len(m.group(1))
        rest = plan[m.end() :]
        stop = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
        out[m.group(2)] = m.group(0) + (rest[: stop.start()] if stop else rest)
    return out


def _has_section(plan: str, name: str) -> bool:
    return bool(re.search(rf"^#{{2,3}} {re.escape(name)}\s*$", plan, re.MULTILINE))


def _layout_against_plan(layout: Layout, plan: str) -> list[str]:
    found, ids = set(phase_sections(plan)), set(layout.get("phases", {}))
    bad = [
        f"phase {phase} is in the layout but the plan has no `### Phase {phase}` heading"
        for phase in sorted(ids - found)
    ]
    bad += [
        f"the plan has `### Phase {phase}`, which is not in the layout"
        for phase in sorted(found - ids)
    ]
    bad += [
        f"decision {decision} is in the layout but the plan never names it"
        for decision in sorted(layout.get("decisions", {}))
        if not re.search(rf"\b{re.escape(decision)}\b", plan)
    ]
    return bad


def plan_problems(rec: Record, plan_path: str) -> list[str]:
    plan = read(plan_path)
    bad = [
        f"no section `{name}`: the plan is cut short or a section is missing"
        for name in SECTIONS
        if not _has_section(plan, name)
    ]
    lines = [line for line in plan.splitlines() if line.strip()]
    if not lines or lines[-1].strip() != END:
        cut = f"the plan is cut short ({len(lines)} lines read)"
        bad.append(f"the last line is not the end marker: {cut}")
    layout = rec.get("layout")
    if not layout:
        return [*bad, "the record has no layout: write it again with --layout"]
    return bad + _layout_against_plan(layout, plan)


def cmd_record(a: argparse.Namespace) -> int:
    rec: Record = {
        "sha": a.sha,
        "date": a.date,
        "tools": point.pairs(a.tool, "--tool"),
        "drafts": {draft: ledger.sha256(draft) for draft in a.draft or []},
        "runs": {
            name: {"command": command, "counts": ledger.counts_of(tally)}
            for name, tally, command in a.run
        },
        "phases": json.loads(Path(a.phases).read_text(encoding="utf-8")),
    }
    kept = ledger.load(a.record).get("layout") if Path(a.record).exists() else None
    if a.layout:
        rec["layout"] = json.loads(Path(a.layout).read_text(encoding="utf-8"))
    elif kept:
        rec["layout"] = kept
    bad = ledger.coverage(rec)
    Path(a.record).write_text(
        json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    total = sum(sum(run["counts"].values()) for run in rec["runs"].values())
    print(
        f"record: {len(rec['runs'])} runs, {total} sites, {len(rec['phases'])} rules with a phase"
    )
    print(*bad, sep="\n", end="\n" if bad else "")
    return 1 if bad else 0


def cmd_check(a: argparse.Namespace) -> int:
    rec = ledger.load(a.record)
    bad = ledger.coverage(rec) + (plan_problems(rec, a.plan) if a.plan else [])
    print(*bad, sep="\n", end="\n" if bad else "")
    whole = ", and the plan is whole and matches the layout" if a.plan else ""
    print(f"{len(bad)} problems" if bad else f"every rule with sites has a phase{whole}")
    return 1 if bad else 0


def _known(a: argparse.Namespace, what: str, *tables: str) -> bool:
    """Whether the id names an entry of one of the layout's tables."""
    layout = ledger.layout_of(ledger.load(a.record))
    ids = {
        "phases": set(layout.get("phases", {})),
        "decisions": set(layout.get("decisions", {})),
    }
    known = any(a.id in ids[table] for table in tables)
    if not known:
        print(f"{a.id} is not {what} of the layout")
    return known


def cmd_decide(a: argparse.Namespace) -> int:
    if not _known(a, "a decision", "decisions"):
        return 1
    event: ledger.Event = {"kind": "decision", "id": a.id, "answer": a.answer, "date": a.date}
    ledger.append_event(a.record, event)
    print(f"{a.id} answered")
    return 0


def cmd_issue(a: argparse.Namespace) -> int:
    if not _known(a, "a phase or a decision", "phases", "decisions"):
        return 1
    ledger.append_event(a.record, {"kind": "issue", "id": a.id, "url": a.url, "date": a.date})
    print(f"issue of {a.id}: {a.url}")
    return 0


def cmd_note(a: argparse.Namespace) -> int:
    ledger.append_event(a.record, {"kind": "note", "text": a.text, "date": a.date})
    print("noted")
    return 0


def cmd_close(a: argparse.Namespace) -> int:
    if not _known(a, "a phase", "phases"):
        return 1
    rec = ledger.load(a.record)
    rules = ledger.phase_rules(rec, ledger.last_point(a.record), a.id)
    left = sum(now for _, _, now in rules)
    ledger.append_event(a.record, {"kind": "close", "id": a.id, "why": a.why, "date": a.date})
    by_note = f"; {left} sites left at the last point: closed by this note, not by the counts"
    print(f"Phase {a.id} closed{by_note if left else ''}")
    return 0


def _history_lines(rec: Record, record: str) -> list[tuple[str, str]]:
    total = sum(sum(run["counts"].values()) for run in rec["runs"].values())
    lines = [(rec["date"], f"{rec['date']} {rec['sha']}: record, {total} sites")]
    for event in ledger.history(record):
        date = event["date"]
        if "kind" not in event:
            scope = f", {event['scope']} of scope" if event.get("scope") else ""
            said = f"{date} {event['sha']}: point, {event['total']} sites left{scope}"
        elif event["kind"] == "note":
            said = f"{date}: {event['text']}"
        elif event["kind"] == "close":
            said = f"{date}: Phase {event['id']} closed: {event['why']}"
        else:
            continue
        lines.append((date, said))
    return sorted(lines, key=lambda line: line[0])  # stable: one date keeps the order written


def cmd_log(a: argparse.Namespace) -> int:
    rec = ledger.load(a.record)
    answers, issues = ledger.of_kind(a.record, "decision"), ledger.of_kind(a.record, "issue")
    layout = ledger.layout_of(rec)
    print("decisions:")
    for decision, meta in sorted(layout.get("decisions", {}).items()):
        holds = ", ".join(meta.get("holds", [])) or "nothing"
        answer = answers.get(decision)
        said = f"answered {answer['date']}: {answer['answer']}" if answer else "open"
        issue = f"  {issues[decision]['url']}" if decision in issues else ""
        print(f"  {decision} (holds {holds}): {said}{issue}")
    print("issues:")
    for phase in layout.get("phases", {}):
        if phase in issues:
            print(f"  Phase {phase}: {issues[phase]['url']}")
    print("history:")
    for _, line in _history_lines(rec, a.record):
        print(f"  {line}")
    return 0


def _open_holds(layout: Layout, record: str) -> dict[str, list[str]]:
    """Each open decision that holds a phase, with the phases it holds."""
    answers = ledger.of_kind(record, "decision")
    return {
        decision: meta.get("holds", [])
        for decision, meta in sorted(layout.get("decisions", {}).items())
        if decision not in answers and meta.get("holds")
    }


def _section(title: str, lines: list[str]) -> None:
    print(f"{title}:")
    print(*(lines or ["  none"]), sep="\n")


def _held(phase: str, holds: dict[str, list[str]]) -> str:
    by = [decision for decision, phases in holds.items() if phase in phases]
    return f"; held by {', '.join(by)} (open): its slices under it wait" if by else ""


def cmd_next(a: argparse.Namespace) -> int:
    rec = ledger.load(a.record)
    layout = ledger.layout_of(rec)
    now = ledger.standing(rec, ledger.measure_of(a.record))
    holds = _open_holds(layout, a.record)
    lanes = {phase: meta.get("lane", "-") for phase, meta in layout.get("phases", {}).items()}

    def waits(phases: list[str]) -> str:
        return ", ".join(f"Phase {p} ({now.labels.get(p, 'not in the layout')})" for p in phases)

    _section(
        "can start",
        [f"  Phase {p} (lane {lanes[p]}): {now.labels[p]}{_held(p, holds)}" for p in now.can_start],
    )
    _section(
        "waiting",
        [f"  Phase {p} (lane {lanes[p]}): waits for {waits(ws)}" for p, ws in now.waiting.items()],
    )
    _section("closed", [f"  Phase {phase}: {now.labels[phase]}" for phase in now.closed])
    earliest = sorted(holds.items(), key=lambda kv: min((len(p), p) for p in kv[1]))
    _section(
        "open decisions that hold a phase",
        [f"  {decision} holds Phase {', '.join(held)}" for decision, held in earliest],
    )
    if any(label.startswith("no rule") for label in now.labels.values()):
        print("a phase with no rule is closed by `progress.py close`, once its Done when holds")
    return 0


def _print_state(rec: Record, record: str, phase: str) -> None:
    """The state of a phase: its lane, what it waits for, its counts, what holds it."""
    layout = ledger.layout_of(rec)
    measure = ledger.measure_of(record)
    answers, issues = ledger.of_kind(record, "decision"), ledger.of_kind(record, "issue")
    last = measure.point
    source = f"last point {last['date']} {last['sha']}" if last else "record (no point yet)"
    print(f"--- state, from the {source}")
    meta = layout.get("phases", {})[phase]
    issue = f"; issue: {issues[phase]['url']}" if phase in issues else ""
    print(f"lane: {meta.get('lane', '-')}{issue}")
    for wait in meta.get("waits", []):
        print(f"waits for Phase {wait}: {ledger.phase_state(rec, measure, wait)[0]}")
    verdict, rules = ledger.phase_state(rec, measure, phase)
    print(f"this phase: {verdict}")
    for rule, then, now in rules:
        print(f"  {rule}: record {then}, now {now}")
    holders = [
        d
        for d, held in sorted(layout.get("decisions", {}).items())
        if phase in held.get("holds", [])
    ]
    for decision in holders:
        answer = answers.get(decision)
        said = f"answered {answer['date']}: {answer['answer']}" if answer else ""
        print(f"held by {decision}: {said or 'open, the slices it holds wait'}")


def cmd_show(a: argparse.Namespace) -> int:
    rec = ledger.load(a.record)
    phases = ledger.layout_of(rec).get("phases", {})
    if a.phase not in phases:
        print(f"phase {a.phase} is not in the layout; the phases are: {', '.join(phases)}")
        return 1
    sections = phase_sections(read(a.plan))
    if a.phase not in sections:
        print(f"the plan has no `### Phase {a.phase}` heading: run `check --plan`")
        return 1
    print(sections[a.phase].rstrip() + "\n")
    _print_state(rec, a.record, a.phase)
    print("the counts are the last measure; the phase's Measure first commands give today's")
    return 0


def cmd_commands(a: argparse.Namespace) -> int:
    rec = ledger.load(a.record)
    if any("$SC" in run["command"] for run in rec["runs"].values()):
        print(
            "`$SC` in a command is a scratch folder outside the repo, for the outputs: "
            "make one and set SC to its path first"
        )
    for name, run in rec["runs"].items():
        print(f"{name}: {run['command']}")
    if rec["tools"]:
        print(
            "at " + ", ".join(f"{tool} {version}" for tool, version in sorted(rec["tools"].items()))
        )
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "record": cmd_record,
    "check": cmd_check,
    "commands": cmd_commands,
    "next": cmd_next,
    "show": cmd_show,
    "decide": cmd_decide,
    "issue": cmd_issue,
    "note": cmd_note,
    "close": cmd_close,
    "log": cmd_log,
    "point": point.point,
}
# The words each event command takes after RECORD, with --date.
_EVENTS = {
    "decide": ("id", "answer"),
    "issue": ("id", "url"),
    "note": ("text",),
    "close": ("id", "why"),
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in COMMANDS:
        sub.add_parser(name).add_argument("record")
    for name, words in _EVENTS.items():
        for word in words:
            sub.choices[name].add_argument(word)
    for name in ("record", "point", *_EVENTS):
        sub.choices[name].add_argument("--date", required=True)
    for name in ("record", "point"):
        sub.choices[name].add_argument("--sha", required=True)
        sub.choices[name].add_argument("--tool", action="append")
    record, measure = sub.choices["record"], sub.choices["point"]
    record.add_argument("--phases", required=True)
    record.add_argument(
        "--run", nargs=3, action="append", required=True, metavar=("NAME", "TALLY", "COMMAND")
    )
    record.add_argument("--draft", action="extend", nargs="+")
    record.add_argument("--layout")
    sub.choices["check"].add_argument("--plan")
    sub.choices["show"].add_argument("phase")
    sub.choices["show"].add_argument("--plan", required=True)
    measure.add_argument(
        "--run", nargs=2, action="append", required=True, metavar=("NAME", "TALLY")
    )
    measure.add_argument("--config", action="append", help="a config that holds a debt list")
    measure.add_argument("--append", action="store_true")
    measure.add_argument("--all", action="store_true", help="list the flat rules too")
    return ap


def main() -> int:
    utf8_console()
    args = parser().parse_args()
    return COMMANDS[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
