"""A burndown point: a new measure against the record and the last point.

Per rule: `closed` (no site left), `down`, `flat`, `up` (the debt grew while
the rule is off), and for a rule with no site in the record: `off in the repo`
when the tool versions and the drafts are the record's (the rule was on, so the
gate would fail on its sites: it was turned off), or `scope` when a version or
a draft changed (a rule the record never measured). A rule `closed` that a
config still lists as debt is `ready to flip`: the next change deletes its
entry. Per phase: `closed`, `ready to flip`, `in progress`, `not started` or
`regressed`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from debtlist import entries
from ledger import Event, Record, append_event, bare, counts_of, last_point, load, phase_of, sha256
from narrow import read

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterator

_ORDER = ["up", "off in the repo", "scope", "ready to flip", "flat", "down", "closed"]
_DONE = ("closed", "ready to flip")
_REGRESSED = {
    "up": " (the debt grew while the rule is off)",
    "off in the repo": (
        " (no site in the record and the same versions: the rule was turned off in the repo)"
    ),
}


class Row(NamedTuple):
    run: str
    rule: str
    phase: str
    then: int  # the sites in the record
    prev: int | None  # the sites at the last point
    now: int
    state: str

    @property
    def name(self) -> str:
        return f"{self.run}:{self.rule}"


class Changes(NamedTuple):
    """What moved under the measure since the record: a count then mixes fixes and the move."""

    bumped: dict[str, tuple[str, str | None]]  # tool -> the record's version, this point's
    drafts: list[str]

    def same(self, rec: Record, run: str) -> bool:
        """A run is named for its tool (`--run ruff ...`, `--tool ruff=0.17.4`);
        a run whose name is not a tool is held to every version."""
        if self.drafts:
            return False
        return run not in self.bumped if run in rec["tools"] else not self.bumped


def pairs(given: list[str] | None, what: str) -> dict[str, str]:
    out = {}
    for item in given or []:
        name, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"{what} takes NAME=VALUE, got {item!r}")
        out[name] = value
    return out


def state_of(then: int, now: int, *, same: bool) -> str:
    if then == 0:
        return "off in the repo" if same else "scope"
    if now == 0:
        return "closed"
    return "down" if now < then else "up" if now > then else "flat"


def _changes(rec: Record, tools: dict[str, str]) -> Changes:
    bumped = {k: (v, tools.get(k)) for k, v in rec["tools"].items() if tools.get(k) != v}
    drafts = [
        d for d, digest in rec["drafts"].items() if not Path(d).exists() or sha256(d) != digest
    ]
    return Changes(bumped, drafts)


def _listed(configs: list[str] | None) -> dict[str, int]:
    """Rule -> the sites its `debt:` comment gives, over the configs that hold a debt list."""
    listed: dict[str, int] = {}
    for config in configs or []:
        listed |= {bare(rule): n for rule, n in entries(read(config)).debt.items()}
    return listed


def _measured(rec: Record, given: dict[str, str]) -> Iterator[tuple[str, str, int, int]]:
    """Each rule of each run with its sites in the record and now."""
    for run, held in rec["runs"].items():
        now = counts_of(given[run])
        for rule in sorted(set(held["counts"]) | set(now)):
            yield run, rule, held["counts"].get(rule, 0), now.get(rule, 0)


def _rows(
    rec: Record, given: dict[str, str], changes: Changes, listed: dict[str, int], last: Event | None
) -> list[Row]:
    before = None if last is None else last.get("counts", {})
    rows = []
    for run, rule, then, now in _measured(rec, given):
        state = state_of(then, now, same=changes.same(rec, run))
        if state == "closed" and bare(rule) in listed:
            state = "ready to flip"
        prev = None if before is None else before.get(f"{run}:{rule}", 0)
        phase = phase_of(rec["phases"], run, rule) or "-"
        rows.append(Row(run, rule, phase, then, prev, now, state))
    return sorted(rows, key=lambda r: (_ORDER.index(r.state), -r.now, r.run, r.rule))


def _print_rules(rows: list[Row], *, flat_too: bool) -> None:
    width = max([len(row.name) for row in rows] + [4])
    print(f"{'rule':<{width}}  {'phase':>6}  {'record':>6}  {'last':>6}  {'now':>6}  state")
    shown = [row for row in rows if flat_too or row.state != "flat"]
    for row in shown:
        prev = "" if row.prev is None else row.prev
        print(
            f"{row.name:<{width}}  {row.phase:>6}  {row.then:>6}  {prev:>6}  {row.now:>6}"
            f"  {row.state}"
        )
    if len(shown) < len(rows):
        print(f"({len(rows) - len(shown)} rules flat; --all lists them)")


def _phase_verdict(states: list[str]) -> str:
    done = sum(1 for state in states if state in _DONE)
    if "up" in states:
        verdict = "regressed"
    elif all(state == "closed" for state in states):
        verdict = "closed"
    elif done == len(states):
        verdict = "ready to flip"
    else:
        verdict = "in progress" if done or "down" in states else "not started"
    return f"{verdict} ({done} of {len(states)} rules at 0)"


def _print_phases(rows: list[Row]) -> None:
    phases: dict[str, list[str]] = {}
    for row in rows:
        if row.then > 0:
            phases.setdefault(row.phase, []).append(row.state)
    print(f"\n{'phase':>6}  state")
    for phase in sorted(phases, key=lambda p: (len(p), p)):
        print(f"{phase:>6}  {_phase_verdict(phases[phase])}")


def _print_stale(rows: list[Row], listed: dict[str, int]) -> None:
    for row in rows:
        said = listed.get(bare(row.rule), 0)
        if row.state in ("down", "flat") and said > row.now:
            print(
                f"debt comment above the count: {row.name} says {said}, now {row.now}: "
                "the next change of its phase lowers it"
            )


class Totals(NamedTuple):
    then: int  # the sites of the record
    now: int  # the sites left of the rules the record measured
    scope: int  # the sites of rules the record never measured


def _totals(rows: list[Row]) -> Totals:
    return Totals(
        sum(row.then for row in rows),
        sum(row.now for row in rows if row.state != "scope"),
        sum(row.now for row in rows if row.state == "scope"),
    )


def _run_problems(rec: Record, given: dict[str, str]) -> list[str]:
    bad = [
        f"run {run} not measured: every run of the record is measured again, "
        "or the point says nothing about its rules"
        for run in rec["runs"]
        if run not in given
    ]
    return bad + [f"run {run} is not in the record" for run in given if run not in rec["runs"]]


def _print_changes(changes: Changes) -> None:
    for tool, (old, new) in changes.bumped.items():
        print(
            f"version changed: {tool} {old} -> {new or 'not given'}: "
            "its counts mix fixes and the bump"
        )
    for draft in changes.drafts:
        print(
            f"draft changed since the record: {draft}: its runs' new rules are scope, not erosion"
        )


def _append(a: argparse.Namespace, rows: list[Row], totals: Totals, regressed: int) -> None:
    event: Event = {
        "sha": a.sha,
        "date": a.date,
        "total": totals.now,
        "scope": totals.scope,
        "counts": {row.name: row.now for row in rows if row.now},
        "ready": sorted(row.name for row in rows if row.state == "ready to flip"),
    }
    append_event(a.record, event)
    closed = sum(1 for row in rows if row.state in _DONE)
    scope = f", {totals.scope} sites of scope" if totals.scope else ""
    regressions = f", {regressed} regressions" if regressed else ""
    print(
        f"\npoint appended: {a.date} {a.sha}: {totals.now} of {totals.then} sites left, "
        f"{closed} rules at 0{scope}{regressions}"
    )


def point(a: argparse.Namespace) -> int:
    rec = load(a.record)
    given = dict(a.run)
    unread = _run_problems(rec, given)
    if unread:
        print(*unread, sep="\n")
        return 1
    listed = _listed(a.config)
    last = last_point(a.record)
    changes = _changes(rec, pairs(a.tool, "--tool"))
    rows = _rows(rec, given, changes, listed, last)
    _print_rules(rows, flat_too=a.all)
    _print_phases(rows)
    totals = _totals(rows)
    scope = f", plus {totals.scope} sites of scope" if totals.scope else ""
    since = f"; last point {last['sha']} {last['date']}: {last['total']}" if last else ""
    print(
        f"\nrecord {rec['sha']} {rec['date']}: {totals.then} sites; now {a.sha} {a.date}: "
        f"{totals.now} sites ({totals.now - totals.then:+d} net){scope}{since}"
    )
    _print_changes(changes)
    _print_stale(rows, listed)
    if last and a.date < last["date"]:
        print(
            f"warning: this point ({a.date}) is dated before the last one ({last['date']}): "
            "check the date"
        )
    bad = [row for row in rows if row.state in _REGRESSED]
    for row in bad:
        print(f"{row.state}: {row.name}{_REGRESSED[row.state]}")
    if a.append:
        _append(a, rows, totals, len(bad))
    return 1 if bad else 0
