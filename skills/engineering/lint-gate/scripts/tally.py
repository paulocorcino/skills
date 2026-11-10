#!/usr/bin/env python3
"""Count lint sites per rule from a tool's machine-readable output.

A site is one (rule, file, line, column); `formats.py` reads each tool.

  tally.py FORMAT OUTPUT [--json OUT.json] [--scope-depth N]
  tally.py diff A.json B.json                  # sites in B that are not in A
  tally.py curve FORMAT OUTPUT --rule RULE [--at 5,8,10,12,15,20]
  tally.py pattern REGEX [PATH...] --ext .rs,.ts [--expect N] [--scope-depth N]
  tally.py sizes [PATH...] --ext .py,.ts [--lines 300,400,500,700] [--width 80,100,120]
  tally.py added FORMAT OUTPUT --base REF [--ignore RULE,RULE]

OUTPUT is the file the tool wrote (`-` for stdin). FORMAT is one of:

  clippy    cargo clippy --message-format=json            (JSON lines)
  oxlint    oxlint --format json
  eslint    eslint -f json
  ruff      ruff check --output-format json
  mypy      mypy -O json                                  (JSON lines)
  pyright   pyright --outputjson
  golangci  golangci-lint run --output.json.path=FILE     (v2)
  tsc       tsc --noEmit --pretty false                   (text)
  vulture   vulture <paths>                               (text)
  knip      knip --reporter json
  astgrep   ast-grep scan --json=stream <paths>          (a clean run prints nothing)
  jscpd     jscpd --reporters json --output DIR           (DIR/jscpd-report.json; one
            site per clone, at its first file; pass --prefix with the scanned folder)

--expect N makes the count a ratchet: it fails when the total is above N (new
debt) and when it is below N (the change that removed sites lowers N, so the
gain is kept).

--scope-depth N groups each rule by the first N path components (a crate,
a package, a directory), to cut the work into slices.

`diff` splits test sites from production when the tool cannot: tally the run
over production code only (A) and the run over every target (B); the diff is
the test sites.

`curve` gives the debt of a numeric limit at several thresholds from one run.
Run the tool with that limit set very low (complexity 1, arguments 0), so it
reports every function with its value; `curve` reads the value from each
message and counts the sites above each threshold. The messages it reads:
"(13 > 10)" (ruff), "(23/10)" and "(7/5)" (clippy), "complexity of 13"
(oxlint, eslint), "complexity 23 of" (gocognit), "but got 7" (revive),
"too many parameters (6)" and "nested too deeply (4)" (oxlint and eslint
`max-params`, `max-depth`, `max-statements`; `max-depth` reports each block
past the limit, so a run at 0 gives the exact count of every limit).

`pattern` counts the lines of the files tracked by git (under PATH, with an
extension of --ext) that match REGEX: the ratchet of a forbidden pattern no
linter has, such as a `TODO` in Rust or a suppression marker. With --expect it
fails above and below N, as the plain mode does.

`sizes` gives the debt of a file-size limit and a line-width limit: the files
tracked by git under PATH with an extension of --ext, the number of their
non-blank lines, and the lines wider than each width.

The plain mode adds the columns `safe` and `unsafe` when the tool reports its
own fixes (ruff, clippy): the sites its fix command rewrites, apart from the
ones that need a hand.

`added` holds new code to the whole target while the debt is paid: it reads
the output of a draft run (every rule of the target on, the debt rules too)
and fails on each site that sits on a line the change adds against REF (the
merge base: `git merge-base HEAD origin/main`; the working tree counts, so it
runs before a commit too). A site on an old line is the plan's; a site on a
new line is the change's. A line the change only moves is an old line: its
text, layout apart, is among the lines the change removes (a file split, a
function reordered, a reformat; `added.py` has the rule). --ignore leaves out
rules that report a line the change did not write (complexity at the `def`: a
baseline holds those).

Warnings on stderr mean the count is incomplete: the tool reported a parse or
build error, so part of the code was never checked.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True  # a run writes nothing into this folder
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling files, under `python -I` too

import added
from formats import PARSERS, Site, hits_of
from narrow import csv, items, obj, warn

_PREFIX_HELP = "put before every path (jscpd names files from the scanned folder)"


def scope_of(path: str, depth: int) -> str:
    parts = path.split("/")
    return "/".join(parts[:depth]) if len(parts) > depth else "/".join(parts[:-1]) or "."


def _fix_cols(sites: set[Site], fixes: dict[Site, str]) -> str:
    if not fixes:
        return ""
    kinds = [fixes.get(site, "") for site in sites]
    return f"  {kinds.count('safe'):>4}  {kinds.count('unsafe'):>6}"


def _scope_lines(sites: set[Site], depth: int | None, width: int) -> list[str]:
    if not depth:
        return []
    per_scope: dict[str, int] = defaultdict(int)
    for site in sites:
        per_scope[scope_of(site[1], depth)] += 1
    ranked = sorted(per_scope.items(), key=lambda kv: (-kv[1], kv[0]))
    return [f"  {scope:<{width - 2}}  {n:>6}" for scope, n in ranked]


def print_table(sites: set[Site], depth: int | None, fixes: dict[Site, str] | None = None) -> None:
    fixes = fixes or {}
    by_rule: dict[str, set[Site]] = defaultdict(set)
    for site in sites:
        by_rule[site[0]].add(site)
    rows = sorted(by_rule.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    width = max([len(rule) for rule, _ in rows] + [4])

    def row(name: str, found: set[Site]) -> str:
        files = len({site[1] for site in found})
        return f"{name:<{width}}  {len(found):>6}  {files:>5}{_fix_cols(found, fixes)}"

    head = f"  {'safe':>4}  {'unsafe':>6}" if fixes else ""
    print(f"{'rule':<{width}}  {'sites':>6}  {'files':>5}{head}")
    for rule, found in rows:
        print(row(rule, found))
        for line in _scope_lines(found, depth, width):
            print(line)
    print(row("total", sites))


def dump(sites: set[Site], path: str) -> None:
    out: dict[str, list[str]] = defaultdict(list)
    for rule, file, line, col in sorted(sites):
        out[rule].append(f"{file}:{line}:{col}")
    with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)


def load(path: str) -> set[Site]:
    sites: set[Site] = set()
    for rule, locs in obj(json.loads(Path(path).read_text(encoding="utf-8"))).items():
        for loc in items(locs):
            file, line, col = str(loc).rsplit(":", 2)
            sites.add((rule, file, int(line), int(col)))
    return sites


def ints(option: str) -> list[int]:
    return sorted({int(part) for part in csv(option)})


def ratchet(count: int, expect: int | None) -> int:
    """Exit 1 unless the count is exactly the constant the ratchet holds."""
    if expect is None or count == expect:
        return 0
    if count > expect:
        advice = "new debt; fix it, the count does not go up"
    else:
        advice = f"the count went down; lower the ratchet to {count} in this change"
    print(f"ratchet: {count} sites, the ratchet holds {expect}: {advice}")
    return 1


_VALUE = [
    re.compile(r"\((\d+)\s*[>/]\s*\d+\)"),
    re.compile(r"complexity of (\d+)"),
    re.compile(r"complexity (\d+) of"),
    re.compile(r"but got (\d+)"),
    re.compile(r"too (?:many \w+|deeply) \((\d+)\)"),
    re.compile(r"^(\d+) tokens"),
    re.compile(r"\(complexity: (\d+)\)"),
]


def value_of(msg: str) -> int | None:
    for pattern in _VALUE:
        m = pattern.search(msg)
        if m:
            return int(m.group(1))
    return None


def cmd_curve(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tally.py curve")
    ap.add_argument("format", choices=sorted(PARSERS))
    ap.add_argument("output")
    ap.add_argument("--rule", required=True, help="the rule id as the plain tally prints it")
    ap.add_argument("--at", default="5,8,10,12,15,20,30,50")
    ap.add_argument("--prefix", default="", help=_PREFIX_HELP)
    args = ap.parse_args(argv)
    hits = [hit for hit in hits_of(args.format, args.output, args.prefix) if hit[0] == args.rule]
    values = [(v, f"{hit[1]}:{hit[2]}") for hit in hits if (v := value_of(hit[4])) is not None]
    if len(values) < len(hits):
        warn(f"{len(hits) - len(values)} sites of {args.rule} carry no value this script can read")
    if not values:
        warn(
            f"no site of {args.rule} with a value: check the rule id and that the limit was set low"
        )
        return 1
    print(f"{'limit':>6}  {'sites over it':>13}")
    for limit in ints(args.at):
        print(f"{limit:>6}  {sum(1 for v, _ in values if v > limit):>13}")
    worst = sorted(values, reverse=True)[:5]
    print("highest:", ", ".join(f"{v} {loc}" for v, loc in worst))
    return 0


def tracked(paths: list[str], ext: str) -> list[str]:
    """The files git tracks under the paths with one of the extensions; none, with a warning."""
    listed = subprocess.run(
        ["git", "ls-files", "--", *paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if listed.returncode != 0:
        warn(f"git ls-files failed: {listed.stderr.strip()}")
        return []
    files = [file for file in listed.stdout.splitlines() if file.endswith(tuple(csv(ext)))]
    if not files:
        warn("no tracked file matches the extensions")
    return files


def _matches(files: list[str], regex: str) -> set[Site]:
    pattern = re.compile(regex)
    sites: set[Site] = set()
    for file in files:
        with Path(file).open(encoding="utf-8", errors="replace") as fh:
            sites.update(
                (f"pattern:{regex}", file, n, m.start() + 1)
                for n, line in enumerate(fh, 1)
                if (m := pattern.search(line))
            )
    return sites


def cmd_pattern(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tally.py pattern")
    ap.add_argument("regex")
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--ext", required=True, help="comma-separated, e.g. .rs,.ts")
    ap.add_argument("--expect", type=int)
    ap.add_argument("--scope-depth", type=int)
    args = ap.parse_intermixed_args(argv)  # the paths may follow the options
    files = tracked(args.paths, args.ext)
    if not files:
        return 1
    sites = _matches(files, args.regex)
    print(f"{len(files)} files read")
    print_table(sites, args.scope_depth)
    return ratchet(len(sites), args.expect)


def cmd_sizes(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tally.py sizes")
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--ext", required=True, help="comma-separated, e.g. .py,.ts")
    ap.add_argument("--lines", default="200,300,400,500,700,1000")
    ap.add_argument("--width", default="80,100,120")
    args = ap.parse_args(argv)
    files = tracked(args.paths, args.ext)
    if not files:
        return 1
    sizes: list[tuple[int, str]] = []
    widths: list[int] = []
    for file in files:
        lines = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
        sizes.append((sum(1 for line in lines if line.strip()), file))
        widths.extend(len(line) for line in lines)
    print(f"{len(files)} files")
    print(f"{'lines':>6}  {'files over it':>13}")
    for limit in ints(args.lines):
        print(f"{limit:>6}  {sum(1 for n, _ in sizes if n > limit):>13}")
    print("largest:", ", ".join(f"{n} {file}" for n, file in sorted(sizes, reverse=True)[:5]))
    print(f"{'width':>6}  {'lines over it':>13}")
    for limit in ints(args.width):
        print(f"{limit:>6}  {sum(1 for w in widths if w > limit):>13}")
    return 0


def cmd_diff(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tally.py diff")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--json")
    ap.add_argument("--scope-depth", type=int)
    args = ap.parse_args(argv)
    sites = load(args.b) - load(args.a)
    if args.json:
        dump(sites, args.json)
    print_table(sites, args.scope_depth)
    return 0


def cmd_plain(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("format", choices=sorted(PARSERS))
    ap.add_argument("output", help="the tool's output file, or - for stdin")
    ap.add_argument("--json", help="write the sites to this file, for `diff`")
    ap.add_argument("--scope-depth", type=int)
    ap.add_argument("--prefix", default="", help=_PREFIX_HELP)
    ap.add_argument("--expect", type=int, help="a ratchet: fail unless the total is exactly this")
    args = ap.parse_args(argv)
    hits = hits_of(args.format, args.output, args.prefix)
    sites = {hit[:4] for hit in hits}
    if args.json:
        dump(sites, args.json)
    print_table(sites, args.scope_depth, {hit[:4]: hit[5] for hit in hits if hit[5]})
    return ratchet(len(sites), args.expect)


COMMANDS = {
    "added": added.main,
    "curve": cmd_curve,
    "pattern": cmd_pattern,
    "sizes": cmd_sizes,
    "diff": cmd_diff,
}


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in COMMANDS:
        return COMMANDS[argv[0]](argv[1:])
    return cmd_plain(argv)


if __name__ == "__main__":
    sys.exit(main())
