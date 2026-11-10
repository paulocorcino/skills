#!/usr/bin/env python3
"""Compare a tool's own list of rules with a reference and with a draft config.

The references of this skill are a cache with an `as of` version; the tool is
the source of truth. Each tool prints its rules:

  oxlint    oxlint --rules --format json > LIST
  ruff      ruff rule --all --output-format json > LIST
  clippy    cargo clippy -q -- -W help > LIST           (rustc and clippy lints)
  tsc       tsc --all > LIST                            (compiler options)
  golangci  golangci-lint linters > LIST                (with every linter enabled)

  drift.py diff FORMAT OLD_LIST NEW_LIST    # rules added and removed between two versions
  drift.py check FORMAT LIST DRAFT          # names in the draft the tool does not know,
                                            # or marks deprecated, removed or preview

  drift.py age [--days N] REF...           # each `As of` line against the registries

`diff` takes the list printed by the reference's `as of` version and the list of
the pinned version: the added rules are the candidates nobody has looked at yet.
`age` reads `As of YYYY-MM-DD: tool 1.2.3, ...` and asks npm, PyPI or GitHub for
each tool's latest stable release. It exits 1, research required, when the date
is older than N days (default 90), a tool has a newer major (a newer minor for a
0.x tool), or a registry did not answer.
`check` reads the draft config (oxlintrc JSON with comments, ruff TOML or
pyproject, Cargo.toml lints, tsconfig JSON with comments, .golangci.yml) and
needs no second version.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tomllib
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

sys.dont_write_bytecode = True  # a run writes nothing into this folder
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling files, under `python -I` too

from narrow import items, jsonc, obj, read, text

if TYPE_CHECKING:
    from collections.abc import Callable

Rules = dict[str, str]  # name -> status ("stable", "deprecated", "preview", ...)


# ---- the tool's list -------------------------------------------------------


def list_oxlint(raw: str) -> Rules:
    rules = [obj(rule) for rule in items(json.loads(raw))]
    return {f"{text(rule.get('scope'))}/{text(rule.get('value'))}": "stable" for rule in rules}


def _ruff_status(status: object) -> str:
    if isinstance(status, dict):
        return str(next(iter(status))).lower()
    return str(status or "stable").lower()


def list_ruff(raw: str) -> Rules:
    rules = [obj(rule) for rule in items(json.loads(raw))]
    # A rule listed without a code cannot be named in a config.
    return {text(r.get("code")): _ruff_status(r.get("status")) for r in rules if r.get("code")}


_LINT_ROW = re.compile(r"^\s*((?:clippy::)?[a-z][\w-]*)\s+(allow|warn|deny|forbid)\s")
_GROUP_ROW = re.compile(
    r"^\s*((?:clippy::)?[a-z][\w-]*)\s+((?:clippy::)?[a-z][\w-]*(?:,\s*)?)+\s*$"
)


def list_clippy(raw: str) -> Rules:
    found = (_LINT_ROW.match(line) or _GROUP_ROW.match(line) for line in raw.splitlines())
    names = (m.group(1) for m in found if m)
    return {name.replace("-", "_"): "stable" for name in names if name not in ("name", "----")}


def list_tsc(raw: str) -> Rules:
    options = (line[2:].split(",")[0].strip() for line in raw.splitlines() if line.startswith("--"))
    return dict.fromkeys(options, "stable")


def list_golangci(raw: str) -> Rules:
    out = {}
    for line in raw.splitlines():
        m = re.match(r"^([a-z0-9_]+)( \[deprecated\])?: (.*)$", line)
        if m:
            old = m.group(2) or "deprecated" in m.group(3).lower()
            out[m.group(1)] = "deprecated" if old else "stable"
    return out


LISTS: dict[str, Callable[[str], Rules]] = {
    "oxlint": list_oxlint,
    "ruff": list_ruff,
    "clippy": list_clippy,
    "tsc": list_tsc,
    "golangci": list_golangci,
}


def rules_of(fmt: str, path: str) -> Rules:
    """The tool's list; an empty file is an empty list, for the caller to report."""
    raw = read(path)
    return LISTS[fmt](raw) if raw.strip() else {}


# ---- the names a draft uses ------------------------------------------------


def names_oxlint(raw: str) -> list[str]:
    cfg = obj(jsonc(raw))
    keys = list(obj(cfg.get("rules")))
    for override in items(cfg.get("overrides")):
        keys += list(obj(obj(override).get("rules")))
    return [key if "/" in key else f"eslint/{key}" for key in keys]


def names_ruff(raw: str) -> list[str]:
    cfg = tomllib.loads(raw)
    root = cfg.get("tool", {}).get("ruff", cfg)
    lint = root.get("lint", root)
    codes: list[str] = []
    for key in ("select", "extend-select", "ignore", "extend-ignore", "fixable", "unfixable"):
        codes += lint.get(key, [])
    for key in ("per-file-ignores", "extend-per-file-ignores"):
        for listed in (lint.get(key) or {}).values():
            codes += listed
    return [code for code in codes if code != "ALL"]


def names_clippy(raw: str) -> list[str]:
    cfg = tomllib.loads(raw)
    out: list[str] = []
    for table in (cfg.get("workspace", {}).get("lints", {}), cfg.get("lints", {})):
        out += [f"clippy::{key}" for key in (table.get("clippy") or {})]
        out += list(table.get("rust") or {})
    return out


def names_tsc(raw: str) -> list[str]:
    return list(obj(obj(jsonc(raw)).get("compilerOptions")))


_GO_SECTION = re.compile(r"^\s{2,4}(enable|disable):\s*$")
_GO_ITEM = re.compile(r"^\s+-\s+([a-z0-9_]+)\s*(#.*)?$")


def _golangci_listed(raw: str, *, comments_end: bool) -> list[tuple[str, str]]:
    """Each linter under `enable:` or `disable:`, with its section. A line at the
    section's own depth ends it; with `comments_end`, a comment there does too."""
    skip = ("-",) if comments_end else ("-", "#")
    out: list[tuple[str, str]] = []
    section = ""
    for line in raw.splitlines():
        head = _GO_SECTION.match(line)
        if head:
            section = head.group(1)
            continue
        if section and re.match(r"^\s{2,4}\S", line) and not line.strip().startswith(skip):
            section = ""
        item = _GO_ITEM.match(line)
        if section and item:
            out.append((section, item.group(1)))
    return out


def disabled_golangci(raw: str) -> set[str]:
    """The names under a `disable:` list: a deprecated linter belongs there, since
    `default: all` turns deprecated linters on too."""
    listed = _golangci_listed(raw, comments_end=False)
    return {name for section, name in listed if section == "disable"}


def names_golangci(raw: str) -> list[str]:
    return [name for _, name in _golangci_listed(raw, comments_end=True)]


NAMES: dict[str, Callable[[str], list[str]]] = {
    "oxlint": names_oxlint,
    "ruff": names_ruff,
    "clippy": names_clippy,
    "tsc": names_tsc,
    "golangci": names_golangci,
}


def known(fmt: str, name: str, rules: Rules) -> str | None:
    """The status of a name, or None when the tool does not know it."""
    if name in rules:
        return rules[name]
    if fmt == "ruff":  # a prefix selects a family: "D", "PLR09", "TRY"
        return "stable" if any(code.startswith(name) for code in rules) else None
    if fmt == "tsc":
        return {key.lower(): status for key, status in rules.items()}.get(name.lower())
    return None


# ---- the age of a reference ------------------------------------------------

# Tool name in an `As of` line -> where its latest stable release is.
REGISTRY = {
    "oxlint": "npm:oxlint",
    "oxlint-tsgolint": "npm:oxlint-tsgolint",
    "typescript": "npm:typescript",
    "typescript-eslint": "npm:typescript-eslint",
    "eslint": "npm:eslint",
    "knip": "npm:knip",
    "jscpd": "npm:jscpd",
    "ruff": "pypi:ruff",
    "mypy": "pypi:mypy",
    "pyright": "pypi:pyright",
    "vulture": "pypi:vulture",
    "ast-grep": "npm:@ast-grep/cli",
    "deptry": "pypi:deptry",
    "pip-audit": "pypi:pip-audit",
    "complexipy": "pypi:complexipy",
    "golangci-lint": "github:golangci/golangci-lint",
    "Rust": "github:rust-lang/rust",
    "clippy": "",  # clippy ships with Rust
}
_URL = {
    "npm": "https://registry.npmjs.org/{}/latest",
    "pypi": "https://pypi.org/pypi/{}/json",
    "github": "https://api.github.com/repos/{}/releases/latest",
}
_ASOF = re.compile(r"^As of (\d{4}-\d{2}-\d{2}): (.*?\.)(?:\s|$)", re.MULTILINE)
_PAIR = re.compile(r"([A-Za-z][\w.-]*) v?(\d+(?:\.\d+)*)\b")


def latest(source: str) -> str:
    kind, name = source.split(":", 1)
    req = urllib.request.Request(_URL[kind].format(name), headers={"User-Agent": "lint-gate-drift"})  # noqa: S310  # the URL is one of the three https registries of _URL
    with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310  # the same request
        data = obj(json.load(response))
    if kind == "npm":
        return text(data["version"]).lstrip("v")
    if kind == "pypi":
        return text(obj(data["info"])["version"]).lstrip("v")
    return text(data["tag_name"]).lstrip("v")


def ver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def _compare(tool: str, have: str, new: str) -> tuple[str, str]:
    """The state of a tool against its latest release, and the reason to research, if any."""
    mine = ver(have)
    theirs = ver(new)[: len(mine)]  # "typescript-eslint 8" names a major: any 8.x is current
    level = 0 if mine and mine[0] else 1  # the minor is the major of a 0.x tool
    if theirs[: level + 1] > mine[: level + 1]:
        return "newer major: research", f"{tool} {have} -> {new}"
    return ("newer: drift.py diff" if theirs > mine else "current"), ""


def _tool_reason(tool: str, have: str) -> str:
    """Print the tool's line; the reason it asks for research, or ""."""
    source = REGISTRY.get(tool)
    if source == "":
        return ""
    if source is None:
        print(f"  {tool} {have}: no registry known, check by hand")
        return f"{tool} unchecked"
    try:
        new = latest(source)
    except (OSError, ValueError, KeyError) as err:
        # A registry that does not answer is a reason to research.
        print(f"  {tool} {have}: registry did not answer ({err})")
        return f"{tool} unchecked"
    state, reason = _compare(tool, have, new)
    print(f"  {tool} {have} -> {new}: {state}")
    return reason


def _reference_reasons(ref: str, today: dt.date, days: int) -> list[str]:
    asof = _ASOF.search(read(ref))
    if not asof:
        print(f"{ref}: no `As of YYYY-MM-DD:` line: research required")
        return ["no date"]
    old = (today - dt.date.fromisoformat(asof.group(1))).days
    reasons = [f"{old} days old"] if old > days else []
    print(f"{ref}: as of {asof.group(1)} ({old} days)")
    reasons += [_tool_reason(tool, have) for tool, have in _PAIR.findall(asof.group(2))]
    reasons = [reason for reason in reasons if reason]
    verdict = f"required ({'; '.join(reasons)})" if reasons else "not required"
    print(f"  research: {verdict}")
    return reasons


def age(refs: list[str], days: int) -> int:
    today = dt.datetime.now(tz=dt.UTC).date()
    research = [ref for ref in refs if _reference_reasons(ref, today, days)]
    return 1 if research else 0


def cmd_age(argv: list[str]) -> int:
    days = 90
    if argv[0] == "--days" and len(argv) >= 3:  # `--days N REF`: three words at least
        days, argv = int(argv[1]), argv[2:]
    return age(argv, days)


def cmd_diff(fmt: str, old_list: str, new_list: str) -> int:
    old, new = rules_of(fmt, old_list), rules_of(fmt, new_list)
    if not old or not new:
        print("warning: an empty list: check the command that printed it", file=sys.stderr)
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = [
        f"{name}: {old[name]} -> {new[name]}"
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    print(f"{len(old)} -> {len(new)} rules")
    print(f"added ({len(added)}):", *added, sep="\n  ")
    print(f"removed ({len(removed)}):", *removed, sep="\n  ")
    print(f"status changed ({len(changed)}):", *changed, sep="\n  ")
    return 0


def _name_problem(status: str | None, name: str) -> str:
    if status is None:
        return f"unknown: {name} (renamed or removed: find it in the changelog)"
    if status not in ("stable", "allow", "warn", "deny"):
        return f"{status}: {name}"
    return ""


def cmd_check(fmt: str, tool_list: str, draft_path: str) -> int:
    rules = rules_of(fmt, tool_list)
    if not rules:
        print(
            "warning: the tool's list is empty: check the command that printed it", file=sys.stderr
        )
        return 1
    draft = read(draft_path)
    disabled = disabled_golangci(draft) if fmt == "golangci" else set()
    bad = []
    for name in NAMES[fmt](draft):
        status = known(fmt, name, rules)
        # A deprecated linter under `disable` is off on purpose: `default: all` would turn it on.
        if not (status == "deprecated" and name in disabled):
            bad.append(_name_problem(status, name))
    bad = [line for line in bad if line]
    print(*bad, sep="\n", end="\n" if bad else "")
    print(f"{len(bad)} names to resolve" if bad else "every name in the draft is known and stable")
    return 1 if bad else 0


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "age":  # `age REF`: two words at least
        return cmd_age(argv[1:])
    if len(argv) != 4 or argv[0] not in ("diff", "check") or argv[1] not in LISTS:  # OP FORMAT A B
        print(__doc__, file=sys.stderr)
        return 2
    command = cmd_diff if argv[0] == "diff" else cmd_check
    return command(*argv[1:])


if __name__ == "__main__":
    sys.exit(main())
