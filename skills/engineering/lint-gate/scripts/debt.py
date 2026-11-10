#!/usr/bin/env python3
"""Write the debt list of a lint group: the block that turns a group on and keeps
each rule with sites off, marked `debt` with its count, or `noise` with its reason.

The block is the step-5 flip for a group. It is printed, not written: paste it in
the config where the comment says, keeping the file's line endings.

  debt.py oxlint --rules LIST --config CONFIG --sites SITES... [--plugins p,..]
                 [--categories c,..] [--target r,..] [--draft DRAFT]
                 [--noise NOISE.json] [--plan PATH]
  debt.py clippy --help-list HELP --sites SITES... --groups g,.. [--target l,..]
                 [--noise NOISE.json] [--plan PATH]
  debt.py golangci --sites SITES... [--noise NOISE.json] [--plan PATH] [--by-id gosec,gocritic]
  debt.py ruff --sites SITES... [--noise NOISE.json] [--plan PATH]
  debt.py mypy --sites SITES... [--noise NOISE.json] [--plan PATH]
  debt.py shrink BASE CONFIG [--plan PLAN]   # fails when the debt list of CONFIG grew against BASE

`shrink` is the check that keeps the list going one way: an entry that BASE does
not have, or a count above its BASE count, fails it. CI runs it against the base
branch: `git show origin/main:Cargo.toml > base.toml && debt.py shrink base.toml Cargo.toml`.
A base with no debt list (or no file) passes: that change brings the first list.
`shrink` also fails on an entry added to a debt list with no `debt:` or
`noise:` comment (a rule turned off with no reason, which no count sees), when
a `debt:` comment is tied to no entry (a config form it
does not read would pass any growth), and on a new `noise:` entry whose reason
cites no decision id (`D3`, `ADR-12`) found in PLAN: a rule off for good is a
decision, not a way out of the debt list.

  LIST     oxlint --rules --format json, of the pinned version
  CONFIG   the repo's .oxlintrc.json today (its plugins, categories and rules)
  HELP     cargo clippy -q -- -W help, of the pinned toolchain
  SITES    tally.py --json files of the draft runs (production and every target);
           a site in any of them counts once
  NOISE    {"<rule>": "<reason>"}: the rules off for good
  --target the rules the target names one by one, on top of the groups

oxlint: the rules that come on are those of every category and plugin on after
the change, minus those on before, plus --target. A new plugin brings its rules
of the categories already on, so they are counted too. A rule the config already
sets at `error` or `off` keeps its setting; one it sets at `warn`, and each rule
of a category at `warn`, comes on like the rest (the gate has no warn level), and
stderr names the `warn` lines the block's lines replace. A rule with sites is
`off` under `// debt: N sites`, a noise rule under `// noise: <reason>`, a rule
with no site is on by its category or, for --target, by an `"error"` line.
DRAFT is the target config the sites were measured with: a rule it sets with
options comes on with them (`["error", {"max": 4}]`), and one that waits as debt
says where they are (`// debt: 3 sites; its options are in DRAFT`).

clippy: each group of --groups goes to `deny` with priority -1; each lint of the
group with sites is `allow` under `# debt: N sites`. A --target lint with no site
is `deny`; one with sites is not in the block: the plan turns it on.

golangci: `default: all`, and each linter with sites goes in `disable` under
`# debt: N sites` (a linter's sites are the sum of its check ids: `gosec:G104`,
`revive:argument-limit`); a noise linter under `# noise: <reason>`. Merge the
target's own `disable` lines (the deprecated names `default: all` would turn on)
into the block. `--by-id` keeps a linter on and lists only its check ids with
sites, under `settings: <linter>:` (`excludes` for gosec, `disabled-checks` for
gocritic): its other checks stay enforced while the debt is paid.

Every comment sits on its own line: some config readers strip only whole-line
comments.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

sys.dont_write_bytecode = True  # a run writes nothing into this folder
sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling files, under `python -I` too

import debtlist
from narrow import csv, items, jsonc, load, obj, read, text, texts

if TYPE_CHECKING:
    from collections.abc import Callable

Sites = dict[str, set[str]]  # rule -> its sites
Ranked = list[tuple[int, str]]  # (sites, rule), the most sites first
Notes = dict[str, str]  # rule -> what its `debt:` comment says after the count


def union(paths: list[str], name: Callable[[str], str]) -> Sites:
    """The sites of the tally files per rule, `name` giving each rule its key;
    a site in several files counts once. A tally's own marks (`(syntax error)`,
    `(no rule)`) are no rule of the tool, so they stay out of a debt list."""
    out: Sites = {}
    for path in paths:
        rules = {rule: locs for rule, locs in obj(load(path)).items() if not rule.startswith("(")}
        for rule, locs in rules.items():
            out.setdefault(name(rule), set()).update(str(loc) for loc in items(locs))
    return out


def ranked(sites: Sites, skip: set[str] | dict[str, str]) -> Ranked:
    found = ((len(locs), rule) for rule, locs in sites.items() if locs and rule not in skip)
    return sorted(found, key=lambda pair: (-pair[0], pair[1]))


def plural(n: int) -> str:
    return f"{n} site" if n == 1 else f"{n} sites"


def noise_of(path: str | None) -> dict[str, str]:
    return {rule: text(reason) for rule, reason in obj(load(path)).items()} if path else {}


def commented(mark: str, kind: str, said: str, entry: str) -> list[str]:
    """An entry under its comment, each on its own line."""
    indent = entry[: len(entry) - len(entry.lstrip())]
    return [f"{indent}{mark} {kind}: {said}", entry]


def summary(what: str, debts: Ranked, noise: dict[str, str]) -> str:
    return f"{len(debts)} {what} in debt ({sum(n for n, _ in debts)} sites), {len(noise)} noise"


# ---- oxlint ----------------------------------------------------------------


def _oxlint_name(rule: str) -> str:
    """A tally's `scope(rule)` as the config's `scope/rule`."""
    m = re.fullmatch(r"([\w-]+)\((.+)\)", rule)
    return f"{m.group(1)}/{m.group(2)}" if m else rule


def _full(name: str) -> str:
    return name if "/" in name else f"eslint/{name}"


def _key(name: str) -> str:
    return name.split("/", 1)[1] if name.startswith("eslint/") else name


def _active(listing: list[tuple[str, str, str]], plugins: set[str], cats: set[str]) -> set[str]:
    return {
        name
        for name, scope, category in listing
        if (scope in plugins or scope == "eslint") and category in cats
    }


class _Coming(NamedTuple):
    """What an oxlint change turns on."""

    plugins: list[str]  # on after the change
    categories: list[str]
    fresh: list[str]  # the rules that come on: new to the config, or set at `warn` in it
    by_line: set[str]  # the rules no category turns on, or a `warn` line holds: each needs a line
    raised: list[str]  # the rules the config sets at `warn`: the block's line replaces theirs
    options: dict[str, str]  # rule -> the options of its end state, as JSON after the level
    notes: dict[str, str]  # rule -> where its options are, said in its `debt:` comment


_LEVELS = {"0": "off", "allow": "off", "1": "warn", "2": "error", "deny": "error"}


def _setting(value: object) -> tuple[str, list[object]]:
    """A rule's setting as its level and its options: `"warn"`, `1`, `["error", {...}]`."""
    parts = items(value) or [value]
    level = str(parts[0])
    return _LEVELS.get(level, level), parts[1:]


def _settings(path: str | None, key: str) -> dict[str, tuple[str, list[object]]]:
    """The level and options of each entry under `key` (rules, categories) of a config."""
    cfg = obj(jsonc(read(path))) if path else {}
    return {name: _setting(value) for name, value in obj(cfg.get(key)).items()}


def _oxlint_options(args: argparse.Namespace, raised: list[str]) -> tuple[dict[str, str], Notes]:
    """The options each rule comes on with: the draft's, or those of the `warn` line it had.
    The note is for a rule that waits as debt: the draft holds its options; a `warn` line
    the block replaces is the only place that held them, so the note keeps the line."""
    options: dict[str, str] = {}
    notes: Notes = {}
    was = {_full(key): opts for key, (_, opts) in _settings(args.config, "rules").items() if opts}
    for name in [name for name in raised if name in was]:
        options[name] = json.dumps(was[name])[1:-1]
        notes[name] = f'was ["warn", {options[name]}]'
    draft = _settings(args.draft, "rules")
    for name, opts in [(_full(key), opts) for key, (_, opts) in draft.items() if opts]:
        options[name] = json.dumps(opts)[1:-1]
        notes[name] = f"its options are in {args.draft}"
    return options, notes


def _at(path: str, key: str, level: str) -> set[str]:
    """The entries under `key` of a config that sit at the level."""
    return {name for name, (found, _) in _settings(path, key).items() if found == level}


def _oxlint_listing(path: str) -> list[tuple[str, str, str]]:
    """Each rule of the tool: its full name, its scope and its category."""
    rules = [obj(rule) for rule in items(load(path))]
    return [
        (
            f"{text(r.get('scope'))}/{text(r.get('value'))}",
            text(r.get("scope")),
            text(r.get("category")),
        )
        for r in rules
    ]


def _oxlint_coming(args: argparse.Namespace) -> _Coming | None:
    listing = _oxlint_listing(args.rules)
    target = {_full(name) for name in csv(args.target)}
    unknown = sorted(target - {name for name, _, _ in listing})
    if unknown:
        print("unknown --target rules:", ", ".join(unknown), file=sys.stderr)
        return None
    plugins_before = set(texts(obj(jsonc(read(args.config))).get("plugins")))
    plugins_after = plugins_before | set(csv(args.plugins))
    # A category at `warn` is not on yet: its rules with sites are debt like any other.
    cats_before = _at(args.config, "categories", "error")
    cats_after = cats_before | _at(args.config, "categories", "warn") | set(csv(args.categories))
    raised = {_full(key) for key in _at(args.config, "rules", "warn")}
    kept = {_full(key) for key in _settings(args.config, "rules")} - raised
    active_after = _active(listing, plugins_after, cats_after)
    coming = (active_after - _active(listing, plugins_before, cats_before)) | target | raised
    options, notes = _oxlint_options(args, sorted(raised))
    return _Coming(
        plugins=sorted(plugins_after),
        categories=sorted(cats_after),
        fresh=sorted(coming - kept),
        by_line=(target - active_after) | raised | set(options),
        raised=sorted(raised),
        options=options,
        notes=notes,
    )


def _oxlint_kinds(
    fresh: list[str], sites: dict[str, int], noise: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """The rules that come on, split: off for good, off as debt, and on."""
    off = [name for name in fresh if {name, _key(name)} & set(noise)]
    debt = [name for name in fresh if name not in off and sites.get(name, 0)]
    return off, debt, [name for name in fresh if name not in off and name not in debt]


def _oxlint_on(name: str, options: dict[str, str]) -> str:
    setting = f'["error", {options[name]}]' if name in options else '"error"'
    return f'"{_key(name)}": {setting},'


def oxlint(args: argparse.Namespace) -> int:
    coming = _oxlint_coming(args)
    if coming is None:
        return 1
    sites = {rule: len(locs) for rule, locs in union(args.sites, _oxlint_name).items()}
    noise = noise_of(args.noise)
    off, debt, rest = _oxlint_kinds(coming.fresh, sites, noise)
    out = [
        f'"plugins": {json.dumps(coming.plugins)},',
        f'"categories": {json.dumps(dict.fromkeys(coming.categories, "error"))},',
        "",
        "// The lint gate. A rule `off` below is one of two kinds. `debt`: it has",
        f"// sites today and {args.plan} turns it on; this list only shrinks.",
        "// `noise`: off for good, with the reason.",
    ]
    out += [_oxlint_on(name, coming.options) for name in sorted(set(rest) & coming.by_line)]
    for name in sorted(debt, key=lambda name: (-sites[name], name)):
        said = "; ".join([plural(sites[name]), *filter(None, [coming.notes.get(name)])])
        out += commented("//", "debt", said, f'"{_key(name)}": "off",')
    for name in off:
        reason = noise.get(name) or noise.get(_key(name)) or ""
        out += commented("//", "noise", reason, f'"{_key(name)}": "off",')
    print("\n".join(out))
    was_warn = ", ".join(_key(name) for name in coming.raised)
    print(
        f"\n{len(coming.fresh)} rules come on: {len(rest)} with no site, "
        f"{len(debt)} debt ({sum(sites[name] for name in debt)} sites), {len(off)} noise"
        + f"\nset at `warn` today, each line replaced by the block's: {was_warn}"
        * bool(was_warn),
        file=sys.stderr,
    )
    return 0


# ---- clippy ----------------------------------------------------------------


def _clippy_group(help_list: str, group: str) -> tuple[bool, list[str]] | None:
    """Whether the group is clippy's, and its lints, from `cargo clippy -- -W help`."""
    name = re.escape(group.replace("clippy::", "").replace("_", "-"))
    m = re.search(rf"^\s*(?:clippy::)?{name}\s+(.+)$", help_list, re.MULTILINE)
    if not m:
        return None
    members = [x.strip().replace("clippy::", "").replace("-", "_") for x in m.group(1).split(",")]
    return group.startswith("clippy::") or "clippy::" in m.group(1), members


def _clippy_block(
    group: str, members: list[str], prefix: str, args: argparse.Namespace
) -> tuple[list[str], int]:
    """The lines that turn a group on, and the sites of its debt."""
    noise = noise_of(args.noise)
    sites = union(args.sites, str)
    lines = [
        "",
        f"# The lint gate: `{group}` is on. A lint `allow` below is debt that {args.plan}",
        "# turns on (this list only shrinks), or noise, off for good with its reason.",
        f'{group} = {{ level = "deny", priority = -1 }}',
    ]
    for lint in sorted(set(members) & {name.removeprefix(prefix) for name in noise}):
        reason = noise.get(lint) or noise.get(prefix + lint) or ""
        lines += commented("#", "noise", reason, f'{lint} = "allow"')
    off = {name.removeprefix("clippy::") for name in noise}
    debts = ranked({lint: sites.get(prefix + lint, set()) for lint in members}, off)
    for n, lint in debts:
        lines += commented("#", "debt", plural(n), f'{lint} = "allow"')
    return lines, sum(n for n, _ in debts)


def clippy(args: argparse.Namespace) -> int:
    help_list = read(args.help_list)
    tables: dict[bool, list[str]] = {False: [], True: []}  # rustc's lints, clippy's lints
    total = 0
    for group in csv(args.groups):
        found = _clippy_group(help_list, group)
        if found is None:
            print(f"no group {group} in the help list", file=sys.stderr)
            return 1
        is_clippy, members = found
        prefix = "clippy::" if is_clippy else ""
        lines, debt = _clippy_block(group.replace("clippy::", ""), members, prefix, args)
        tables[is_clippy] += lines
        total += debt
    sites = union(args.sites, str)
    for lint in csv(args.target):
        if not sites.get(lint):
            tables[lint.startswith("clippy::")].append(f'{lint.replace("clippy::", "")} = "deny"')
    print("[workspace.lints.rust]" + "\n".join(["", *tables[False]]))
    print("\n[workspace.lints.clippy]" + "\n".join(["", *tables[True]]))
    print(f"\ndebt in the groups: {total} sites", file=sys.stderr)
    return 0


# ---- ruff, mypy ------------------------------------------------------------


def _last_part(rule: str) -> str:
    return rule.rsplit(":", maxsplit=1)[-1]


def ruff(args: argparse.Namespace) -> int:
    noise = noise_of(args.noise)
    debts = ranked(union(args.sites, _last_part), noise)
    out = [
        'select = ["ALL"]',
        f"# The lint gate: every rule is on. A code in `ignore` is debt that {args.plan}",
        "# turns on (this list only shrinks), or noise, off for good with its reason.",
        "ignore = [",
    ]
    for code in sorted(noise):
        out += commented("#", "noise", noise[code], f'  "{code}",')
    for n, code in debts:
        out += commented("#", "debt", plural(n), f'  "{code}",')
    print("\n".join([*out, "]"]))
    print(f"\n{summary('codes', debts, noise)}", file=sys.stderr)
    return 0


def mypy(args: argparse.Namespace) -> int:
    noise = noise_of(args.noise)
    debts = ranked(union(args.sites, _last_part), noise)
    out = [
        f"# The type gate: `strict`. A code in `disable_error_code` is debt that {args.plan}",
        "# turns on (this list only shrinks), or noise, off for good with its reason.",
        "disable_error_code =",
    ]
    for code in sorted(noise):
        out += commented("#", "noise", noise[code], f"    {code},")
    for n, code in debts:
        out += commented("#", "debt", plural(n), f"    {code},")
    print("\n".join(out))
    clash = sorted(set(csv(args.enabled)) & {code for _, code in debts})
    if clash:
        print(
            "\nremove from enable_error_code while they have debt (mypy does not disable a code "
            f"that enable_error_code names): {', '.join(clash)}",
            file=sys.stderr,
        )
    print(summary("codes", debts, noise), file=sys.stderr)
    return 0


# ---- golangci --------------------------------------------------------------

_BY_ID = {"gosec": "excludes", "gocritic": "disabled-checks"}


def _by_id_lines(linter: str, checks: Sites) -> list[str]:
    lines = [f"    {linter}:", f"      {_BY_ID[linter]}:"]
    for n, check in ranked(checks, set()):
        lines += commented("#", "debt", plural(n), f"        - {check}")
    return lines


def _go_sites(paths: list[str], by_id: set[str]) -> tuple[Sites, dict[str, Sites]]:
    """The sites per linter, and per check id for the linters of --by-id
    (`gosec:G104`): any other linter counts as a whole."""

    def name(rule: str) -> str:
        linter = rule.split(":", maxsplit=1)[0]
        return rule if linter in by_id else linter

    sites = union(paths, name)
    per_id: dict[str, Sites] = {}
    for rule in [rule for rule in sites if ":" in rule]:
        linter, check = rule.split(":", 1)
        per_id.setdefault(linter, {})[check] = sites.pop(rule)
    return sites, per_id


def golangci(args: argparse.Namespace) -> int:
    by_id = set(csv(args.by_id))
    unknown = by_id - set(_BY_ID)
    if unknown:
        supported, given = ", ".join(_BY_ID), ", ".join(sorted(unknown))
        print(f"--by-id supports {supported}, not {given}", file=sys.stderr)
        return 2
    sites, per_id = _go_sites(args.sites, by_id)
    noise = noise_of(args.noise)
    debts = ranked(sites, noise)
    out = [
        "linters:",
        "  default: all",
        f"  # The lint gate: every linter is on. A linter in `disable` is debt that {args.plan}",
        "  # turns on (this list only shrinks), or noise, off for good with its reason.",
        "  disable:",
    ]
    for name in sorted(noise):
        out += commented("#", "noise", noise[name], f"    - {name}")
    for n, name in debts:
        out += commented("#", "debt", plural(n), f"    - {name}")
    out += ["  settings:"] * bool(per_id)
    kept = []
    for linter in sorted(per_id):
        out += _by_id_lines(linter, per_id[linter])
        total = sum(len(locs) for locs in per_id[linter].values())
        kept.append(f"{linter}: on, {len(per_id[linter])} check ids in debt ({total} sites)")
    print("\n".join(out))
    print(*kept, sep="\n", end="\n" if kept else "", file=sys.stderr)
    print(summary("linters", debts, noise), file=sys.stderr)
    return 0


def shrink(args: argparse.Namespace) -> int:
    return debtlist.shrink(args.base, args.config, args.plan)


WRITERS = {
    "oxlint": oxlint,
    "clippy": clippy,
    "golangci": golangci,
    "ruff": ruff,
    "mypy": mypy,
    "shrink": shrink,
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="tool", required=True)
    for name in ("oxlint", "clippy", "golangci", "ruff", "mypy"):
        writer = sub.add_parser(name)
        writer.add_argument("--sites", nargs="+", required=True)
        writer.add_argument("--noise")
        writer.add_argument("--plan", default="the transition plan")
    oxlint_args, clippy_args = sub.choices["oxlint"], sub.choices["clippy"]
    oxlint_args.add_argument("--rules", required=True)
    oxlint_args.add_argument("--config", required=True)
    oxlint_args.add_argument("--plugins", default="")
    oxlint_args.add_argument("--categories", default="")
    oxlint_args.add_argument("--target", default="")
    oxlint_args.add_argument("--draft")
    clippy_args.add_argument("--help-list", required=True)
    clippy_args.add_argument("--groups", required=True)
    clippy_args.add_argument("--target", default="")
    sub.choices["golangci"].add_argument("--by-id")
    sub.choices["mypy"].add_argument(
        "--enabled", help="the codes of enable_error_code, comma-separated"
    )
    held = sub.add_parser("shrink")
    held.add_argument("base")
    held.add_argument("config")
    held.add_argument("--plan")
    return ap


def main() -> int:
    args = parser().parse_args()
    return WRITERS[args.tool](args)


if __name__ == "__main__":
    sys.exit(main())
