"""Read the debt list of a config, and hold it to one direction (`debt.py shrink`).

One entry per line, in any of the config forms a debt list takes:

  "rule": ...  /  lint = ...        a key (JSON, TOML table)
  - linter                          a YAML list item
  "CODE",                           a TOML array item (ruff `ignore`)
  error-code,                       an INI list item (mypy `disable_error_code`)

A `debt: N sites` or `noise: <reason>` comment sits on its own line above its
entry, or at the end of the entry's line; a noise comment may cover a line of
several items.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from narrow import read

_KEY = (
    r'^\s*(?:-\s+"?(?P<yaml>[\w/@.-]+)"?(?=\s*(?:#|$))'
    r'|"(?P<item>[\w/@.-]+)",?(?=\s*(?:#|//|$))'
    r'|"?(?P<key>[\w/@.-]+)"?\s*[:=]'
    r"|(?P<bare>[A-Za-z][\w-]*),?(?=\s*(?:#|$)))"
)
_COUNT = r"(?:#|//)\s*debt:\s*(?P<count>\d+) sites?"
_NOISE = r"(?:#|//)\s*noise:\s*(?P<reason>.+?)\s*$"
_ENTRY = re.compile(_KEY)
_INLINE_DEBT = re.compile(_KEY + r".*?" + _COUNT)
_INLINE_NOISE = re.compile(_KEY + r".*?" + _NOISE)
_ALONE_DEBT = re.compile(r"^\s*" + _COUNT + r"\b.*$")  # a note may follow: `; Phase 1`
_ALONE_NOISE = re.compile(r"^\s*" + _NOISE)
_ANY_DEBT = re.compile(r"(?:#|//)\s*debt:")
_ITEMS = re.compile(r'^\s*(?:"[\w/@.-]+",?\s*)+(?:#.*)?$')
_OFF = re.compile(r'[:=]\s*"?(off|allow)"?\s*,?\s*(?:#.*|//.*)?$')
_DECISION = re.compile(r"\b(D\d+|ADR-\d+)\b")
_LIST_FORMS = ("item", "yaml", "bare")


class DebtList(NamedTuple):
    debt: dict[str, int]  # rule -> the sites its `debt:` comment gives
    noise: dict[str, str]  # rule -> the reason of its `noise:` comment
    unread: int  # `debt:` comments tied to no entry: a form this does not read
    plain: set[str]  # entries of a debt block with no `debt:` or `noise:` comment


def _name(m: re.Match[str]) -> str:
    return str(m.group("yaml") or m.group("item") or m.group("key") or m.group("bare"))


def _is_code(line: str) -> bool:
    return bool(line.strip()) and not line.strip().startswith(("#", "//"))


class _Scan:
    """One pass over the lines of a config. A block is a run of entry, comment
    and blank lines; its plain entries count only when the block holds a debt
    or noise entry, so a list of paths or members stays out."""

    def __init__(self) -> None:
        self.debt: dict[str, int] = {}
        self.noise: dict[str, str] = {}
        self.plain: set[str] = set()
        self.comments = 0
        self._block: set[str] = set()
        self._listed = False
        self._pending_debt: int | None = None
        self._pending_noise: str | None = None

    def feed(self, line: str) -> None:
        before = len(self.debt) + len(self.noise)
        if _ANY_DEBT.search(line) and not (_INLINE_DEBT.match(line) or _ALONE_DEBT.match(line)):
            self.comments += (
                1  # a form this does not read: counted, so it shows as tied to no entry
            )
        key = _ENTRY.match(line)
        if not (self._inline(line) or self._alone(line) or self._under_comment(line, key)):
            self._uncommented(line, key)
        self._listed = self._listed or len(self.debt) + len(self.noise) > before

    def end(self) -> None:
        if self._listed:
            self.plain |= self._block
        self._block, self._listed = set(), False

    def _clear(self) -> None:
        self._pending_debt = self._pending_noise = None

    def _inline(self, line: str) -> bool:
        """An entry with its comment at the end of its line."""
        debt, noise = _INLINE_DEBT.match(line), _INLINE_NOISE.match(line)
        if debt:
            self.comments += 1
            self.debt[_name(debt)] = int(debt.group("count"))
        elif noise:
            self.noise[_name(noise)] = noise.group("reason")
        else:
            return False
        self._clear()
        return True

    def _alone(self, line: str) -> bool:
        """A comment on its own line: it waits for the entry under it."""
        debt, noise = _ALONE_DEBT.match(line), _ALONE_NOISE.match(line)
        if debt:
            self.comments += 1
            self._pending_debt, self._pending_noise = int(debt.group("count")), None
        elif noise:
            self._pending_noise, self._pending_debt = noise.group("reason"), None
        return bool(debt or noise)

    def _under_comment(self, line: str, key: re.Match[str] | None) -> bool:
        """The entry a waiting comment covers."""
        if self._pending_noise is not None and _ITEMS.match(line):
            self.noise.update(
                dict.fromkeys(re.findall(r'"([\w/@.-]+)"', line), self._pending_noise)
            )
        elif key and self._pending_debt is not None:
            self.debt[_name(key)] = self._pending_debt
        elif key and self._pending_noise is not None:
            self.noise[_name(key)] = self._pending_noise
        else:
            return False
        self._clear()
        return True

    def _uncommented(self, line: str, key: re.Match[str] | None) -> None:
        if not _is_code(line):
            return
        if key and (any(key.group(form) for form in _LIST_FORMS) or _OFF.search(line)):
            self._block.add(_name(key))
        elif not key:
            self.end()  # a line that is no entry and no comment ends the block
        self._clear()


def entries(config: str) -> DebtList:
    scan = _Scan()
    for line in config.replace("\r\n", "\n").split("\n"):
        scan.feed(line)
    scan.end()
    return DebtList(scan.debt, scan.noise, scan.comments - len(scan.debt), scan.plain)


def _uncited(reason: str, plan: str) -> bool:
    cited = _DECISION.findall(reason)
    return not cited or not all(re.search(rf"\b{re.escape(c)}\b", plan) for c in cited)


def _growth(base: DebtList, head: DebtList, plan: str) -> list[str]:
    bad = [
        f"new noise entry: {name} ({reason}): a rule off for good is a decision; "
        "cite its id (Dn, ADR-n) in the reason, recorded in the plan (--plan)"
        for name, reason in head.noise.items()
        if name not in base.noise and _uncited(reason, plan)
    ]
    bad += [
        f"new debt entry: {rule} ({n})" for rule, n in head.debt.items() if rule not in base.debt
    ]
    # A rule turned off with no comment is an exit the counts above never see.
    bad += [
        f"new entry with no `debt:` or `noise:` comment: {rule}: a rule off says why"
        for rule in sorted(head.plain - base.plain)
    ]
    bad += [
        f"debt grew: {rule} {base.debt[rule]} -> {n}"
        for rule, n in head.debt.items()
        if rule in base.debt and n > base.debt[rule]
    ]
    return bad


def shrink(base_path: str, config: str, plan_path: str | None) -> int:
    """Exit 1 when the debt list of CONFIG grew against BASE."""
    base = entries(read(base_path)) if Path(base_path).exists() else DebtList({}, {}, 0, set())
    head = entries(read(config))
    if head.unread:
        print(
            f"{head.unread} `debt:` comments are tied to no entry: "
            "shrink cannot read this config's form"
        )
        return 1
    sites = sum(head.debt.values())
    if not base.debt:
        # The change that brings the first debt list has nothing to shrink against.
        print(
            "the base has no debt list: this change brings the first one, "
            f"{len(head.debt)} entries ({sites} sites), {len(head.noise)} noise"
        )
        return 0
    bad = _growth(base, head, read(plan_path) if plan_path else "")
    print(*bad, sep="\n", end="\n" if bad else "")
    gone = len(set(base.debt) - set(head.debt))
    verdict = "" if bad else "; the list did not grow"
    print(f"{len(head.debt)} debt entries ({sites} sites), {gone} gone since the base{verdict}")
    return 1 if bad else 0
