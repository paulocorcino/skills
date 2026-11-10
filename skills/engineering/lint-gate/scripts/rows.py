#!/usr/bin/env python3
"""Hold the run to every row of the references it read.

A reference is a set of tables: each row is a check, a tool, a rule group or a
knob the target names. Skipping a row fails nothing by itself; this script
makes the skip fail.

  rows.py list REF...                             # the Coverage table to fill: one line per row
  rows.py check EVIDENCE REF... [--record RECORD] # fails when a row has no verdict in EVIDENCE
  rows.py check EVIDENCE --record RECORD          # the repo's gate: the evidence against the record
  rows.py keys REF... --in FILE...                # the target config keys no FILE names

The plan's evidence (`lint-evidence.md`) carries a `## Coverage` (or
`### Coverage`) section with a table `| Row | Verdict |`. A verdict is one of:

  on                        the check runs in the gate today (`on — <note>` too)
  sites N                   the rule has N sites; its phase is in the debt table
  phase N                   a phase of the plan delivers it
  closed by <check>         an exit and the check that closes it
  open                      an exit no tool closes; a human reads it (`open — <note>` too)
  decision — <Dn>           waiting on a decision of the plan
  n/a — <why>               the repo has nothing it applies to
  out — <why>               a row of a "Do not turn on" table, kept off
  not measured — <why>      a knob whose measure needs what the run lacks

A knob (a row of SKILL.md's Knobs table) and a row of an optional family (a
table under a heading that names an optional family) are asked with their
data, so their `decision` verdict carries a count after its id
(`decision — D14, sites 197`); a bare `decision — D14` fails.

`check` reports the rows with no line, the lines with no valid verdict, and
the lines that name a row no reference has (a reference changed). It then
prints the count of each verdict and, one per line, every row a verdict leaves
outside the gate (`open`, `n/a`, `out`, `not measured`) with its reason: a
verdict's form is checked here, its truth is the human's to read.

With --record (the plan's `lint-record.json`) `check` also holds the evidence
to the record, whose counts a script wrote: each `phase N` and `decision — Dn`
verdict names a phase or a decision of the layout, and each rule of the record
has its row in the debt table of Measured (`| Rule | Tool | ... | Production |
Test | ... | Phase |`) with the record's sites (Production plus Test) and phase.

With no REF, `check` holds the rows the evidence already has: each verdict's
form, and with --record the record. That form reads only files of the repo, so
it runs in the repo's gate; which rows there are is checked with the
references, by the run that has them.

`keys` reads the code blocks of the references (the target configs: TOML, INI,
JSON with comments, YAML) and prints every key, lint or linter they set that
none of the FILEs names: pass the repo's real configs, the drafts and the plan.
A key the run took in is in a config or a draft; one it left is in the plan with
its reason.
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

sys.dont_write_bytecode = True  # a run writes nothing into this folder
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling files, under `python -I` too

import ledger
from narrow import read, utf8_console

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_SEP = re.compile(r"^\|[\s|:-]+\|\s*$")
_VERDICT = re.compile(
    r"^(on|open|on — .+|open — .+|sites \d[\d,]*.*|phase [\w.-]+.*|closed by .+"
    r"|decision — .+|n/a — .+|out — .+|not measured — .+)$"
)
_KINDS = ["on", "sites", "phase", "closed by", "decision", "open", "n/a", "out", "not measured"]
_OUTSIDE = ("open", "n/a", "out", "not measured")
_CELL = re.compile(r"(?<!\\)\|")


class Table(NamedTuple):
    family: bool  # under a heading that names an optional family
    head: list[str]
    rows: list[list[str]]


def cells(line: str) -> list[str]:
    """The cells of a table row; an escaped pipe stays inside its cell."""
    return _CELL.split(line.strip().strip("|"))


def clean(cell: str) -> str:
    cell = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cell)
    cell = cell.replace("`", "").replace("**", "")
    return re.sub(r"\s+", " ", cell).strip()


def tables_of(doc: str) -> Iterator[Table]:
    lines = doc.splitlines()
    family = False
    i = 0
    while i < len(lines):
        if lines[i].startswith("#"):
            family = bool(re.search(r"optional famil", lines[i], re.IGNORECASE))
        if lines[i].startswith("|") and i + 1 < len(lines) and _SEP.match(lines[i + 1]):
            body = list(itertools.takewhile(lambda line: line.startswith("|"), lines[i + 2 :]))
            head = [clean(cell) for cell in cells(lines[i])]
            yield Table(family, head, [[clean(cell) for cell in cells(row)] for row in body])
            i += 2 + len(body)
        else:
            i += 1


def rows_of(path: Path) -> dict[str, bool]:
    """The rows of a reference, in order, each with whether it is asked with its
    data: every knob, and every row under a heading that names an optional family."""
    stem = "knobs" if path.name == "SKILL.md" else path.stem
    out: dict[str, bool] = {}
    for table in tables_of(read(path)):
        for first in filter(None, (row[0] for row in table.rows)):
            rid = f"{stem}: {first}"
            if rid in out:
                rid = f"{stem}: {first} ({table.head[0]})"
            out[rid] = stem == "knobs" or table.family
    return out


def coverage(evidence: str) -> dict[str, str]:
    """Row -> verdict, from the Coverage table."""
    m = re.search(r"^#{2,3} Coverage\s*$(.*?)(?=^#{1,3} |\Z)", evidence, re.MULTILINE | re.DOTALL)
    if not m:
        return {}
    lines = [
        line for line in m.group(1).splitlines() if line.startswith("|") and not _SEP.match(line)
    ]
    rows = [[clean(cell) for cell in cells(line)] for line in lines]
    return {row[0]: row[1] for row in rows if len(row) > 1 and row[0] not in ("Row", "")}


def kind_of(verdict: str) -> str:
    return next((k for k in _KINDS if verdict == k or verdict.startswith(f"{k} ")), "")


# ---- the evidence against the record ---------------------------------------


class DebtRow(NamedTuple):
    rule: str
    tool: str
    sites: int  # production plus test
    phase: str


def _number(cell: str) -> int:
    m = re.match(r"\s*(\d[\d,]*)", cell)
    return int(m.group(1).replace(",", "")) if m else 0


_DEBT_COLUMNS = ("tool", "production", "test", "phase")


def _debt_rows(table: Table, col: dict[str, int]) -> list[DebtRow]:
    tool, production, test, phase = (col[name] for name in _DEBT_COLUMNS)
    whole = [row for row in table.rows if len(row) >= len(table.head)]
    return [
        DebtRow(row[0], row[tool], _number(row[production]) + _number(row[test]), row[phase])
        for row in whole
    ]


def debt_table(evidence: str) -> list[DebtRow] | None:
    """The debt table of Measured, or None when the evidence has none."""
    for table in tables_of(evidence):
        col = {name.lower(): i for i, name in enumerate(table.head)}
        if col.get("rule") == 0 and set(_DEBT_COLUMNS) <= set(col):
            return _debt_rows(table, col)
    return None


def _row_for(table: list[DebtRow], run: str, rule: str) -> DebtRow | None:
    named = [row for row in table if row.rule == rule or ledger.bare(row.rule) == ledger.bare(rule)]
    return next((row for row in named if row.tool == run), named[0] if named else None)


def _debt_problems(rec: ledger.Record, table: list[DebtRow]) -> list[str]:
    bad = []
    for run, held in rec["runs"].items():
        for rule, n in sorted(held["counts"].items()):
            row = _row_for(table, run, rule)
            phase = ledger.phase_of(rec["phases"], run, rule) or ""
            if row is None:
                bad.append(f"no row in the debt table: {run}:{rule} ({n} sites in the record)")
            elif row.sites != n:
                bad.append(
                    f"debt table: {run}:{rule} has {row.sites} sites (production plus test), "
                    f"the record {n}"
                )
            elif phase not in re.findall(r"[\w.-]+", row.phase):
                bad.append(
                    f"debt table: {run}:{rule} is in phase {row.phase!r}, the record says {phase}"
                )
    return bad


_NO_TABLE = (
    "no debt table in the evidence (`| Rule | Tool | ... | Production | Test | ... | Phase |`)"
)


def _named(got: dict[str, str], pattern: str) -> list[tuple[str, str]]:
    """Each row whose verdict matches, with the id the verdict names."""
    found = ((row, re.match(pattern, verdict)) for row, verdict in got.items())
    return [(row, m.group(1)) for row, m in found if m]


def record_problems(evidence: str, got: dict[str, str], record: str) -> list[str]:
    rec = ledger.load(record)
    layout = ledger.layout_of(rec)
    phases, decisions = layout.get("phases", {}), layout.get("decisions", {})
    bad = [
        f"{row}: phase {phase} is not a phase of the record's layout"
        for row, phase in _named(got, r"phase ([\w.-]+)")
        if phase not in phases
    ]
    bad += [
        f"{row}: {decision} is not a decision of the record's layout"
        for row, decision in _named(got, r"decision — ([\w-]+)")
        if decision not in decisions
    ]
    table = debt_table(evidence)
    if table is None:
        # A plan whose debt is paid has a record with no rule, and no table to hold.
        paid = not any(run["counts"] for run in rec["runs"].values())
        return bad if paid else [*bad, _NO_TABLE]
    return bad + _debt_problems(rec, table)


# ---- the commands ----------------------------------------------------------


def cmd_list(argv: list[str]) -> int:
    print("| Row | Verdict |\n|---|---|")
    for rid in [rid for ref in argv for rid in rows_of(Path(ref))]:
        print(f"| {rid} | |")
    return 0


def _blind(verdict: str) -> bool:
    """A `decision` verdict with no count after its id."""
    return verdict.startswith("decision") and not re.search(
        r"\d", re.sub(r"^decision — \S+", "", verdict)
    )


def _summary(verdicts: list[tuple[str, str]]) -> None:
    """The count of each verdict, and every row a verdict leaves outside the gate."""
    kinds = [kind_of(verdict) for _, verdict in verdicts]
    counts = ", ".join(f"{kind} {kinds.count(kind)}" for kind in _KINDS if kind in kinds)
    print(f"verdicts: {counts or 'none'}")
    outside = [pair for pair in verdicts if kind_of(pair[1]) in _OUTSIDE]
    if outside:
        print("outside the gate, for the human to read:")
    for row, verdict in sorted(outside, key=lambda pair: _OUTSIDE.index(kind_of(pair[1]))):
        print(f"  {row}: {verdict}")


def _problems(want: dict[str, bool], got: dict[str, str]) -> dict[str, list[str]]:
    held = {row: got[row] for row in want if row in got}
    asked = {row: verdict for row, verdict in held.items() if want[row]}
    invalid = {row: verdict for row, verdict in held.items() if not _VERDICT.match(verdict)}
    blind = {row: verdict for row, verdict in asked.items() if _blind(verdict)}
    return {
        "no line": sorted(set(want) - set(got), key=list(want).index),
        "no valid verdict": [f"{row}: {verdict!r}" for row, verdict in invalid.items()],
        "not a row of the references": sorted(set(got) - set(want), key=list(got).index),
        "a decision with no count (the question carries its data)": [
            f"{row}: {verdict!r}" for row, verdict in blind.items()
        ],
    }


def _wanted(refs: list[str], got: dict[str, str]) -> dict[str, bool]:
    """The rows to hold, each with whether it is asked with its data: those of the
    references, or with none given the evidence's own, a knob known by its name."""
    if refs:
        return {rid: asked for ref in refs for rid, asked in rows_of(Path(ref)).items()}
    print("no reference given: the rows held are the evidence's own")
    return {row: row.startswith("knobs: ") for row in got}


def cmd_check(argv: list[str]) -> int:
    record = None
    if "--record" in argv:
        at = argv.index("--record")
        record, argv = argv[at + 1], argv[:at] + argv[at + 2 :]
    evidence = read(argv[0])
    got = coverage(evidence)
    if not got:
        print(f"{argv[0]}: no `## Coverage` table")
        return 1
    want = _wanted(argv[1:], got)
    problems = _problems(want, got)
    problems["against the record"] = record_problems(evidence, got, record) if record else []
    for label, found in problems.items():
        print(*(f"{label}: {item}" for item in found), sep="\n", end="\n" if found else "")
    valid = len(want) - len(problems["no line"]) - len(problems["no valid verdict"])
    print(f"{len(want)} rows, {valid} with a verdict")
    _summary([(row, got[row]) for row in want if row in got])
    return 1 if any(problems.values()) else 0


_BLOCK = re.compile(r"^```(toml|ini|jsonc|json|yaml)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_KEY = {
    "toml": re.compile(r'^\s*"?([A-Za-z][\w./-]*)"?(?:\.msg)?\s*='),
    "ini": re.compile(r"^\s*([A-Za-z][\w.-]*)\s*="),
    "jsonc": re.compile(r'^\s*"([A-Za-z][\w/@.-]*)"\s*:'),
    "yaml": re.compile(r"^\s*(?:-\s+)?([A-Za-z][\w.-]*)\s*(?::|$|#)"),
}
_KEY["json"] = _KEY["jsonc"]


def keys_of(path: Path) -> list[str]:
    """The keys the code blocks of a reference set, in order, each once."""
    found = (
        _KEY[block.group(1)].match(line)
        for block in _BLOCK.finditer(read(path))
        for line in block.group(2).splitlines()
        if not line.lstrip().startswith(("#", "//", "{", "["))
    )
    return list(dict.fromkeys(m.group(1) for m in found if m))


def _is_named(key: str, haystack: str) -> bool:
    name = re.escape(key.rsplit("/", maxsplit=1)[-1]).replace("_", "[_-]")
    return bool(re.search(rf"(?<![\w-]){name}(?![\w-])", haystack))


def cmd_keys(argv: list[str]) -> int:
    if "--in" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    at = argv.index("--in")
    refs = [Path(ref) for ref in argv[:at]]
    haystack = "\n".join(read(file) for file in argv[at + 1 :])
    missing = [
        f"{ref.stem}: {key}" for ref in refs for key in keys_of(ref) if not _is_named(key, haystack)
    ]
    print(*(f"named nowhere: {item}" for item in missing), sep="\n", end="\n" if missing else "")
    total = sum(len(keys_of(ref)) for ref in refs)
    print(f"{total} keys, {len(missing)} named in no config and not in the plan")
    return 1 if missing else 0


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "list": cmd_list,
    "check": cmd_check,
    "keys": cmd_keys,
}


def main() -> int:
    utf8_console()
    argv = sys.argv[1:]
    # `list` and `check` take a reference at least; `keys` prints its own usage.
    if not argv or argv[0] not in COMMANDS or (argv[0] != "keys" and len(argv) == 1):
        print(__doc__, file=sys.stderr)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
