"""Read a tool's machine-readable output into hits, one parser per tool.

A site is one (rule, file, line, column). Duplicates are dropped: clippy reports
a site once per target that compiles the file, and a macro can repeat it; ruff
can report one rule twice at one position (PT018 on `assert a and b and c`).

A warning on stderr means the count is incomplete: the tool reported a parse or
build error, so part of the code was never checked.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from narrow import Json, items, num, obj, text, warn

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

Site = tuple[str, str, int, int]  # rule, file, line, column
# A site, its message and its fix: "safe" when the tool's own fix keeps the
# behavior, "unsafe" when it may change it, "" when the tool has none.
Hit = tuple[str, str, int, int, str, str]


def norm_path(path: str) -> str:
    path = path.replace("\\", "/")
    cwd = Path.cwd().as_posix().rstrip("/") + "/"
    if path.lower().startswith(cwd.lower()):
        path = path[len(cwd) :]
    return path.removeprefix("./")


def json_lines(raw: str) -> Iterator[Json]:
    for line in raw.splitlines():
        if not line.strip().startswith("{"):
            continue
        try:
            yield obj(json.loads(line))
        except json.JSONDecodeError:
            continue


_CLIPPY_SAFE = {"MachineApplicable"}
_CLIPPY_UNSAFE = {"MaybeIncorrect", "HasPlaceholders"}


def _clippy_fix(msg: Json) -> str:
    kinds = {
        text(obj(span).get("suggestion_applicability"))
        for part in [msg, *items(msg.get("children"))]
        for span in items(obj(part).get("spans"))
    }
    if kinds & _CLIPPY_SAFE:
        return "safe"
    return "unsafe" if kinds & _CLIPPY_UNSAFE else ""


def _clippy_code(msg: Json) -> str:
    """The lint a message carries, or "" for a message that is no lint site."""
    code = text(obj(msg.get("code")).get("code"))
    if not code:
        if msg.get("level") == "error":
            warn(f"compile error with no code: {text(msg.get('message'))[:100]}")
        return ""
    if re.fullmatch(r"E\d{4}", code):
        warn(f"compile error {code}: the crate did not build, its lints are missing")
        return ""
    return code


def _clippy_hit(code: str, msg: Json) -> Hit:
    spans = [obj(span) for span in items(msg.get("spans"))]
    primary = [span for span in spans if span.get("is_primary")] or spans
    said = text(msg.get("message"))
    if not primary:
        return code, "(no file)", 0, 0, said, ""
    span = primary[0]
    return (
        code,
        norm_path(text(span.get("file_name"))),
        num(span.get("line_start")),
        num(span.get("column_start")),
        said,
        _clippy_fix(msg),
    )


def parse_clippy(raw: str) -> Iterator[Hit]:
    for line in json_lines(raw):
        if line.get("reason") == "build-finished" and not line.get("success", True):
            warn("the build did not finish: crates that failed were not linted")
        if line.get("reason") != "compiler-message":
            continue
        msg = obj(line.get("message"))
        code = _clippy_code(msg)
        if code:
            yield _clippy_hit(code, msg)


def parse_oxlint(raw: str) -> Iterator[Hit]:
    for item in items(obj(json.loads(raw)).get("diagnostics")):
        diag = obj(item)
        code = text(diag.get("code")) or "(parse error)"
        said = text(diag.get("message"))
        if code == "(parse error)":
            warn(f"diagnostic with no rule in {diag.get('filename')}: {said[:100]}")
        labels = items(diag.get("labels")) or [{}]
        span = obj(obj(labels[0]).get("span"))
        file = norm_path(text(diag.get("filename"), "(no file)"))
        yield code, file, num(span.get("line")), num(span.get("column")), said, ""


def parse_eslint(raw: str) -> Iterator[Hit]:
    for item in items(json.loads(raw)):
        file = obj(item)
        for found in items(file.get("messages")):
            msg = obj(found)
            said = text(msg.get("message"))
            rule = text(msg.get("ruleId"))
            if not rule:
                warn(f"{file.get('filePath')}: {said[:100]}")
                rule = "(parse error)" if msg.get("fatal") else "(no rule)"
            path = norm_path(text(file.get("filePath")))
            yield rule, path, num(msg.get("line")), num(msg.get("column")), said, ""


def parse_ruff(raw: str) -> Iterator[Hit]:
    for item in items(json.loads(raw)):
        diag = obj(item)
        said = text(diag.get("message"))
        code = text(diag.get("code"))
        if not code:
            warn(f"{diag.get('filename')}: {said[:100]}")
            code = "(syntax error)"
        loc = obj(diag.get("location"))
        kind = text(obj(diag.get("fix")).get("applicability"))
        fix = kind if kind in ("safe", "unsafe") else ""
        path = norm_path(text(diag.get("filename")))
        yield code, path, num(loc.get("row")), num(loc.get("column")), said, fix


def parse_mypy(raw: str) -> Iterator[Hit]:
    for diag in json_lines(raw):
        if diag.get("severity") == "note":
            continue
        code = text(diag.get("code")) or "(no code)"
        if code == "syntax":
            warn(f"{diag.get('file')}: syntax error, the file was not checked")
        path = norm_path(text(diag.get("file")))
        said = text(diag.get("message"))
        yield code, path, num(diag.get("line")), num(diag.get("column")), said, ""


def parse_pyright(raw: str) -> Iterator[Hit]:
    for item in items(obj(json.loads(raw)).get("generalDiagnostics")):
        diag = obj(item)
        if diag.get("severity") == "information":
            continue
        start = obj(obj(diag.get("range")).get("start"))
        yield (
            text(diag.get("rule")) or "(no rule)",
            norm_path(text(diag.get("file"), "(no file)")),
            num(start.get("line")) + 1,
            num(start.get("character")) + 1,
            text(diag.get("message")),
            "",
        )


# staticcheck (SA1019, ST1003, QF1001, S1000) and gosec (G104) put their own
# check id at the start of the text: count those per id, not per linter.
_GO_CHECK_ID = re.compile(r"^([A-Z]{1,3}\d{3,4})\b")
# revive (`argument-limit: ...`) and gocritic (`ifElseChain: ...`) start with
# the name of their rule.
_GO_RULE_NAME = re.compile(r"^([A-Za-z][\w-]+): ")
_GO_NAMED_RULES = {"revive", "gocritic"}


def parse_golangci(raw: str) -> Iterator[Hit]:
    for item in items(obj(json.loads(raw)).get("Issues")):
        issue = obj(item)
        said = text(issue.get("Text"))
        rule = text(issue.get("FromLinter"), "(no linter)")
        pattern = _GO_RULE_NAME if rule in _GO_NAMED_RULES else _GO_CHECK_ID
        check = pattern.match(said)
        if check:
            rule = f"{rule}:{check.group(1)}"
        if rule == "typecheck":
            warn(f"typecheck: {said[:100]} (the package was not linted)")
        pos = obj(issue.get("Pos"))
        path = norm_path(text(pos.get("Filename"), "(no file)"))
        yield rule, path, num(pos.get("Line")), num(pos.get("Column")), said, ""


_TSC_LINE = re.compile(r"^(.+?)\((\d+),(\d+)\): error (TS\d+): ?(.*)")


def parse_tsc(raw: str) -> Iterator[Hit]:
    for line in raw.splitlines():
        m = _TSC_LINE.match(line)
        if m:
            yield (
                m.group(4),
                norm_path(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                m.group(5),
                "",
            )


def parse_jscpd(raw: str) -> Iterator[Hit]:
    """One site per clone, at its first file; the message carries its size."""
    for item in items(obj(json.loads(raw)).get("duplicates")):
        clone = obj(item)
        first, second = obj(clone.get("firstFile")), obj(clone.get("secondFile"))
        other = f"{norm_path(text(second.get('name'), '?'))}:{num(second.get('start'))}"
        # A block copied to several places makes several clones that start at
        # one place: the column slot holds a stable id of the other copy.
        other_id = int(hashlib.sha1(other.encode(), usedforsecurity=False).hexdigest()[:8], 16)
        yield (
            f"jscpd:{text(clone.get('format'), '?')}",
            norm_path(text(first.get("name"), "(no file)")),
            num(first.get("start"), num(obj(first.get("startLoc")).get("line"))),
            other_id,
            f"{num(clone.get('tokens'))} tokens, {num(clone.get('lines'))} lines, also at {other}",
            "",
        )


_VULTURE = re.compile(
    r"^(.+?):(\d+): (unused [a-z ]+?|unreachable code|unsatisfiable \w+ condition)\b(.*)$"
)


def parse_vulture(raw: str) -> Iterator[Hit]:
    for line in raw.splitlines():
        m = _VULTURE.match(line.strip())
        if m:
            rule = f"vulture:{m.group(3)}"
            yield rule, norm_path(m.group(1)), int(m.group(2)), 0, m.group(4).strip(), ""


def _knip_hits(kind: str, path: str, found: list[object]) -> Iterator[Hit]:
    for item in found:
        named = obj(item) if isinstance(item, dict) else {"name": str(item)}
        name = str(named.get("name", ""))
        yield f"knip:{kind}", path, num(named.get("line")), num(named.get("col")), name, ""


def parse_knip(raw: str) -> Iterator[Hit]:
    """knip --reporter json: one site per unused file, export, type or dependency."""
    for item in items(obj(json.loads(raw)).get("issues")):
        issue = obj(item)
        path = norm_path(text(issue.get("file"), "(no file)"))
        for kind, found in issue.items():
            if kind != "file":
                yield from _knip_hits(kind, path, items(found))


def parse_astgrep(raw: str) -> Iterator[Hit]:
    """ast-grep scan --json=stream (one object per line), or --json (one array)."""
    raw = raw.strip()
    if raw.startswith("["):
        found = items(json.loads(raw))
    else:
        found = [json.loads(line) for line in raw.splitlines() if line.strip()]
    for item in found:
        match = obj(item)
        start = obj(obj(match.get("range")).get("start"))
        yield (
            f"ast-grep:{text(match.get('ruleId'), '?')}",
            norm_path(text(match.get("file"), "(no file)")),
            num(start.get("line"), -1) + 1,
            num(start.get("column"), -1) + 1,
            text(match.get("message")),
            "",
        )


PARSERS: dict[str, Callable[[str], Iterator[Hit]]] = {
    "clippy": parse_clippy,
    "oxlint": parse_oxlint,
    "eslint": parse_eslint,
    "ruff": parse_ruff,
    "mypy": parse_mypy,
    "pyright": parse_pyright,
    "golangci": parse_golangci,
    "tsc": parse_tsc,
    "jscpd": parse_jscpd,
    "vulture": parse_vulture,
    "knip": parse_knip,
    "astgrep": parse_astgrep,
}
# What an empty output parses as: a clean tsc or ast-grep run prints nothing,
# every other format writes something.
_EMPTY = {
    "eslint": "[]",
    "ruff": "[]",
    "oxlint": "{}",
    "pyright": "{}",
    "golangci": "{}",
    "jscpd": "{}",
    "knip": "{}",
}
_SILENT_WHEN_CLEAN = ("tsc", "astgrep")


def read_output(path: str, fmt: str) -> str:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    if raw.strip() or fmt in _SILENT_WHEN_CLEAN:
        return raw
    warn("the output is empty: check that the tool ran")
    return _EMPTY.get(fmt, "")


def hits_of(fmt: str, path: str, prefix: str = "") -> list[Hit]:
    """The hits of an output file, one per site; a site keeps the first fix reported for it."""
    seen: dict[Site, Hit] = {}
    for rule, file, line, col, msg, fix in PARSERS[fmt](read_output(path, fmt)):
        name = file if not prefix or file.startswith("(") else f"{prefix}{file}"
        site = (rule, name, line, col)
        kept = seen.get(site)
        if kept is None:
            seen[site] = (*site, msg, fix)
        elif fix and not kept[5]:
            seen[site] = (*kept[:5], fix)
    return list(seen.values())
