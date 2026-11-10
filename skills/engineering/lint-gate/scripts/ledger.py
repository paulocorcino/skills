"""The record of a lint transition plan, and its history.

The record (`lint-record.json`) is the measure the plan was cut from: per run,
the command and the sites per rule; the tool versions; a hash of each draft; the
phase of each rule; and the layout, the shape of the plan (lanes, waits, holds).

The history (`<record stem>.history.jsonl`) is the state: one JSON line per
event, appended by `progress.py` and by nothing else. An event with a `kind` is
a decision answered, an issue opened, a note or a phase closed; one without is a
point, a new measure.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple, TypedDict

from narrow import obj


class Run(TypedDict):
    command: str
    counts: dict[str, int]


class PhaseMeta(TypedDict, total=False):
    lane: str
    waits: list[str]


class DecisionMeta(TypedDict, total=False):
    holds: list[str]


class Layout(TypedDict, total=False):
    phases: dict[str, PhaseMeta]
    decisions: dict[str, DecisionMeta]


class Record(TypedDict, total=False):
    sha: str
    date: str
    tools: dict[str, str]
    drafts: dict[str, str]
    runs: dict[str, Run]
    phases: dict[str, str]
    layout: Layout


class Event(TypedDict, total=False):
    kind: str
    id: str
    answer: str
    url: str
    text: str
    why: str
    date: str
    sha: str
    total: int
    scope: int
    counts: dict[str, int]
    ready: list[str]


class Measure(NamedTuple):
    """The last point and the phases closed by a note."""

    point: Event | None  # None: no point yet, the record's counts stand
    closes: dict[str, Event]


RuleCounts = list[tuple[str, int, int]]  # run:rule, sites in the record, sites now


def bare(rule: str) -> str:
    """The rule's own name: `clippy::foo`, `eslint(no-foo)`, `eslint/no-foo` -> `foo`, `no-foo`."""
    return [part for part in re.split(r"::|/|\(|\)", rule) if part][-1]


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def counts_of(tally: str) -> dict[str, int]:
    data = obj(json.loads(Path(tally).read_text(encoding="utf-8")))
    return {rule: len(sites) for rule, sites in data.items() if isinstance(sites, list) and sites}


def load(path: str) -> Record:
    rec: Record = json.loads(Path(path).read_text(encoding="utf-8"))
    return rec


def history_path(record: str) -> Path:
    path = Path(record)
    return path.with_name(path.stem + ".history.jsonl")


def history(record: str) -> list[Event]:
    path = history_path(record)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[Event] = [json.loads(line) for line in lines if line.strip()]
    return events


def last_point(record: str) -> Event | None:
    points = [event for event in history(record) if "kind" not in event]
    return points[-1] if points else None


def append_event(record: str, event: Event) -> None:
    with history_path(record).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")


def of_kind(record: str, kind: str) -> dict[str, Event]:
    """The events of a kind by id; the last event of each id wins."""
    return {event["id"]: event for event in history(record) if event.get("kind") == kind}


def measure_of(record: str) -> Measure:
    return Measure(last_point(record), of_kind(record, "close"))


def layout_of(rec: Record) -> Layout:
    return rec.get("layout") or {}


def phase_ids(layout: Layout) -> list[str]:
    """The phases in the plan's order: 2 before 10."""
    return sorted(layout.get("phases", {}), key=lambda phase: (len(phase), phase))


def phase_of(phases: dict[str, str], run: str, rule: str) -> str | None:
    return phases.get(f"{run}:{rule}") or phases.get(rule)


def phase_rules(rec: Record, point: Event | None, phase: str) -> RuleCounts:
    now = None if point is None else point.get("counts", {})
    return [
        (f"{run}:{rule}", n, n if now is None else now.get(f"{run}:{rule}", 0))
        for run, held in rec["runs"].items()
        for rule, n in sorted(held["counts"].items())
        if phase_of(rec["phases"], run, rule) == phase
    ]


def _verdict(rules: RuleCounts, ready: set[str]) -> str:
    if any(now for _, _, now in rules):
        fresh = all(now >= then for _, then, now in rules)
        return "not started" if fresh else "in progress"
    return "ready to flip" if any(name in ready for name, _, _ in rules) else "closed"


def phase_state(rec: Record, measure: Measure, phase: str) -> tuple[str, RuleCounts]:
    """What the last measure says of a phase, and its rules. A phase is closed
    when its label starts with `closed`: every rule at 0 and flipped, or a
    `close` note in the history."""
    rules = phase_rules(rec, measure.point, phase)
    left = sum(now for _, _, now in rules)
    note = measure.closes.get(phase)
    if note:
        still = f" ({left} sites left at the last point)" if left else ""
        return f"closed by note {note['date']}: {note['why']}{still}", rules
    if not rules:
        return "no rule: read by its Done when", rules
    ready = set((measure.point or {}).get("ready", []))
    done = sum(1 for _, _, now in rules if not now)
    return f"{_verdict(rules, ready)} ({done} of {len(rules)} rules at 0)", rules


class Standing(NamedTuple):
    """Where each phase of the layout stands, in the plan's order."""

    labels: dict[str, str]  # phase -> what the last measure says of it
    closed: list[str]
    waiting: dict[str, list[str]]  # phase -> the phases it waits for that are not closed
    can_start: list[str]  # not closed, and each phase it waits for is


def _open_waits(meta: PhaseMeta, closed: list[str]) -> list[str]:
    return [wait for wait in meta.get("waits", []) if wait not in closed]


def standing(rec: Record, measure: Measure) -> Standing:
    phases = layout_of(rec).get("phases", {})
    ids = phase_ids(layout_of(rec))
    labels = {phase: phase_state(rec, measure, phase)[0] for phase in ids}
    closed = [phase for phase in ids if labels[phase].startswith("closed")]
    blockers = {phase: _open_waits(phases[phase], closed) for phase in ids}
    for phase in closed:
        del blockers[phase]
    waiting = {phase: waits for phase, waits in blockers.items() if waits}
    return Standing(labels, closed, waiting, sorted(set(blockers) - set(waiting), key=ids.index))


def _layout_problems(layout: Layout, with_rules: set[str]) -> list[str]:
    ids = layout.get("phases", {})
    missing = sorted(with_rules - set(ids))
    bad = [f"phase {phase} has rules but is not in the layout" for phase in missing]
    bad += [
        f"phase {phase} waits for phase {wait}, which is not in the layout"
        for phase, meta in sorted(ids.items())
        for wait in meta.get("waits", [])
        if wait not in ids
    ]
    bad += [
        f"decision {decision} holds phase {held}, which is not in the layout"
        for decision, meta in sorted(layout.get("decisions", {}).items())
        for held in meta.get("holds", [])
        if held not in ids
    ]
    return bad


def coverage(rec: Record) -> list[str]:
    """The problems of a record: a rule with sites and no phase, a phase naming
    a rule the record does not hold, a layout that names what is not there."""
    phases = rec["phases"]
    counted = [
        (run, rule, n)
        for run, held in rec["runs"].items()
        for rule, n in sorted(held["counts"].items())
    ]
    bad = [
        f"no phase: {run}:{rule} ({n} sites)"
        for run, rule, n in counted
        if not phase_of(phases, run, rule)
    ]
    held = {rule for _, rule, _ in counted} | {f"{run}:{rule}" for run, rule, _ in counted}
    bad += [
        f"phase {phase} names {rule}, which has no site in the record"
        for rule, phase in sorted(phases.items())
        if rule not in held
    ]
    layout = rec.get("layout")
    return bad + (_layout_problems(layout, set(phases.values())) if layout else [])
