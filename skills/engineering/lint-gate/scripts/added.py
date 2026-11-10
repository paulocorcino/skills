"""The lines a change adds, for `tally.py added`.

A line is new when the change writes it. A line the change only moves is the
plan's, not the change's: splitting a file, reordering a function or running the
formatter carries its debt sites along without adding one. Two readings make a
line a move, both blind to layout (whitespace, quotes, commas, parentheses and
semicolons, the characters a formatter rewrites):

  - a hunk whose removed text equals its added text (a re-indent, a re-wrap,
    a quote style, a trailing comma);
  - an added line whose text is among the lines the change removes anywhere,
    each removed line paying for one added line.

So a site moves with its line, and the count of a debt rule cannot rise through
a move: text written twice where it was removed once is new the second time.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from formats import PARSERS, hits_of

if TYPE_CHECKING:
    from collections.abc import Iterator

_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class Hunk(NamedTuple):
    path: str  # "" for a deleted file
    start: int  # the first added line
    removed: list[str]
    added: list[str]


class Added(NamedTuple):
    lines: dict[str, set[int]]  # path -> the line numbers the change writes
    moved: int  # the added lines read as moves


_LAYOUT = re.compile(r"""[\s'",();]+""")


def squash(line: str) -> str:
    """The text of a line, layout apart."""
    return _LAYOUT.sub("", line)


def _take(lines: Iterator[str], count: int) -> list[str]:
    """The next `count` lines of a hunk body, without their sign."""
    out: list[str] = []
    while len(out) < count:
        line = next(lines, None)
        if line is None:
            break
        if not line.startswith("\\"):  # "\ No newline at end of file"
            out.append(line[1:])
    return out


def hunks(diff: str) -> Iterator[Hunk]:
    """The hunks of a `git diff -U0`: the body is read by the counts of its header."""
    lines = iter(diff.splitlines())
    path: str | None = None
    for line in lines:
        if line.startswith("+++ "):
            path = "" if line[4:] == "/dev/null" else line[4:].removeprefix("b/")
            continue
        m = _HUNK.match(line)
        if m and path is not None:
            removed = _take(lines, int(m.group(1) or 1))
            yield Hunk(path, int(m.group(2)), removed, _take(lines, int(m.group(3) or 1)))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _untracked() -> Iterator[tuple[str, int, str]]:
    """Each line of the files git does not track yet: new code too."""
    for file in _git("ls-files", "--others", "--exclude-standard").stdout.splitlines():
        try:
            body = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        yield from ((file, n, line) for n, line in enumerate(body, 1))


def _changed(diff: str) -> tuple[Counter[str], list[tuple[str, int, str]], int]:
    """The lines a diff removes, the lines it adds, and how many of the added
    lines sit in a hunk that only re-wraps its text."""
    removed: Counter[str] = Counter()
    added: list[tuple[str, int, str]] = []
    rewrapped = 0
    for hunk in hunks(diff):
        if hunk.added and squash("".join(hunk.removed)) == squash("".join(hunk.added)):
            rewrapped += len(hunk.added)
            continue
        removed.update(map(squash, hunk.removed))
        added += [(hunk.path, hunk.start + i, line) for i, line in enumerate(hunk.added)]
    return removed, added, rewrapped


def added_lines(base: str) -> Added:
    """What the working tree adds against BASE, moves left out."""
    diff = _git("diff", "-U0", "--no-color", "--no-ext-diff", base, "--")
    if diff.returncode != 0:
        sys.exit(f"git diff {base} failed: {diff.stderr.strip()}")
    removed, added, moved = _changed(diff.stdout)
    lines: dict[str, set[int]] = defaultdict(set)
    for path, number, line in [*added, *_untracked()]:
        key = squash(line)
        if key and removed[key] > 0:
            removed[key] -= 1
            moved += 1
        else:
            lines[path].add(number)
    return Added(lines, moved)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tally.py added")
    ap.add_argument("format", choices=sorted(PARSERS))
    ap.add_argument("output")
    ap.add_argument("--base", required=True, help="the merge base the change is measured against")
    ap.add_argument("--ignore", default="", help="rules left out, comma-separated")
    args = ap.parse_args(argv)
    skip = {rule for rule in args.ignore.split(",") if rule}
    new = added_lines(args.base)
    hits = sorted(
        (file, line, col, rule, msg)
        for rule, file, line, col, msg, _fix in hits_of(args.format, args.output)
        if rule not in skip and line in new.lines.get(file, ())
    )
    for file, line, col, rule, msg in hits:
        print(f"{file}:{line}:{col}: {rule} {msg}")
    verdict = "; new code meets the whole target, debt rules too: fix them" if hits else ""
    moves = (
        f" ({new.moved} added lines are moves: the change removes their text)" if new.moved else ""
    )
    print(f"{len(hits)} sites on lines this change adds{verdict}{moves}")
    return 1 if hits else 0
