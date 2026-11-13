"""Read-only view of the model docs (`database.md` + `domains/*.md`) for the tools.

Single reader of the model's fixed formats (docs/db-model/README.md, "Per-table
block"), so `doccheck.py` and `erdgen.py` never parse the prose two ways:

    ### <Group>                      <- subdomain group (TableGroup in the DBML)
    #### <table>                     <- per-table block; heading = qualified name
    - **Concept:** <text>
    - **Implied:** <col>[, <col>] -> <table>.<col>[, <col>] — <note>

Pure text parsing, no judgment: a line that does not match a format is ignored here
(and `doccheck.py` reports the malformed `**Implied:**` lines).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from _paths import MODEL_DIR

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_CONCEPT = re.compile(r"^\s*[-*]\s+\*\*Concept:\*\*\s*(.*\S)\s*$")
_IMPLIED = re.compile(r"^\s*[-*]\s+\*\*Implied:\*\*\s*(.*\S)\s*$")
# <cols> -> <table>.<cols>  [— note]; accepts → or ->, — or -- as the note separator
# a list item opening with a table name: `- `name` …` or `- **name** …`
_ENTRY = re.compile(r"^\s*[-*]\s+(?:`([\w.]+)`|\*\*([\w.]+)\*\*)")
_IMPLIED_BODY = re.compile(
    r"^(?P<cols>[\w\s,`]+?)\s*(?:→|->)\s*`?(?P<ref>[\w.]+?)`?\s*\.\s*\(?(?P<rcols>[\w\s,`]+?)\)?"
    r"\s*(?:(?:—|--)\s*(?P<note>.*))?$"
)


@dataclass(frozen=True)
class Implied:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    note: str


@dataclass
class Block:
    name: str
    file: Path
    anchor: str
    group: str | None = None
    concept: str | None = None
    elimination: bool = False
    implied: list[Implied] = field(default_factory=list)
    bad_implied: list[str] = field(default_factory=list)


def model_files() -> list[Path]:
    """database.md first, then domains/*.md in name order."""
    files = []
    main = MODEL_DIR / "database.md"
    if main.exists():
        files.append(main)
    domains = MODEL_DIR / "domains"
    if domains.is_dir():
        files.extend(sorted(domains.glob("*.md")))
    return files


def model_text() -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in model_files())


def github_slug(heading: str, seen: dict[str, int]) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped (except - and _),
    spaces to '-', duplicates suffixed -1, -2, … in document order."""
    text = re.sub(r"[`*]", "", heading).strip().lower()
    slug = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
    n = seen.get(slug, 0)
    seen[slug] = n + 1
    return slug if n == 0 else f"{slug}-{n}"


def _split_cols(s: str) -> tuple[str, ...]:
    return tuple(c.strip().strip("`") for c in s.split(",") if c.strip().strip("`"))


def parse_implied(body: str) -> Implied | None:
    m = _IMPLIED_BODY.match(body.strip())
    if not m:
        return None
    cols, rcols = _split_cols(m["cols"]), _split_cols(m["rcols"])
    if not cols or len(cols) != len(rcols):
        return None
    return Implied(cols, m["ref"], rcols, (m["note"] or "").strip())


def table_blocks(table_names: set[str]) -> dict[str, Block]:
    """Per-table blocks keyed by qualified table name; only headings naming a known table."""
    blocks: dict[str, Block] = {}
    for f in model_files():
        seen: dict[str, int] = {}
        group: str | None = None
        file_title: str | None = None
        current: Block | None = None
        in_fence = False
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            h = _HEADING.match(line)
            if h:
                level, text = len(h[1]), h[2]
                anchor = github_slug(text, seen)
                current = None
                if level == 1 and file_title is None:
                    file_title = re.sub(r"[`*]", "", text).strip()
                if level <= 2:
                    group = None
                elif level == 3:
                    group = re.sub(r"[`*]", "", text).strip()
                elif level == 4:
                    name = re.sub(r"[`*]", "", text).strip()
                    if name in table_names and name not in blocks:
                        grp = group if group else (file_title if f.parent.name == "domains" else None)
                        current = blocks[name] = Block(name, f, anchor, grp)
                continue
            if current is None:
                continue
            if "elimination candidate" in line.lower():
                opener = _ENTRY.match(line)
                named = opener and (opener[1] or opener[2])
                if not named or named == current.name:  # a line about another table is not ours
                    current.elimination = True
            c = _CONCEPT.match(line)
            if c and current.concept is None:
                current.concept = c[1]
                continue
            i = _IMPLIED.match(line)
            if i:
                parsed = parse_implied(i[1])
                if parsed:
                    current.implied.append(parsed)
                else:
                    current.bad_implied.append(i[1])
    return blocks


def elimination_candidates(table_names: set[str]) -> set[str]:
    """Tables marked elimination candidate: inside their block, or on a one-line entry
    that opens with the table's name (`- `name` — … elimination candidate`)."""
    out = {n for n, b in table_blocks(table_names).items() if b.elimination}
    for line in model_text().splitlines():
        if "elimination candidate" not in line.lower():
            continue
        m = _ENTRY.match(line)
        name = m and (m[1] or m[2])
        if name in table_names:
            out.add(name)
    return out
