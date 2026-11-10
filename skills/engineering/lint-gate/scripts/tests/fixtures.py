"""The tool outputs, tallies and configs the tests read, written into a folder."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import documents

if TYPE_CHECKING:
    from pathlib import Path

Json = dict[str, object]


def _clippy(code: str, file: str, line: int, text: str, fix: str = "") -> Json:
    span: Json = {"file_name": file, "line_start": line, "column_start": 5, "is_primary": True}
    children: list[Json] = [{"spans": [{"suggestion_applicability": fix}]}] if fix else []
    level = "error" if code.startswith("E0") else "warning"
    message: Json = {
        "code": {"code": code},
        "level": level,
        "message": text,
        "spans": [span],
        "children": children,
    }
    return {"reason": "compiler-message", "message": message}


CLIPPY_PROD: list[Json] = [
    _clippy("clippy::unwrap_used", "crates/a/src/lib.rs", 3, "used `unwrap()` on a `Result`"),
    _clippy("clippy::unwrap_used", "crates/a/src/lib.rs", 3, "used `unwrap()` on a `Result`"),
    _clippy(
        "clippy::needless_return",
        "crates/a/src/lib.rs",
        8,
        "unneeded `return`",
        "MachineApplicable",
    ),
    _clippy("clippy::cognitive_complexity", "crates/b/src/main.rs", 1, "complexity of (23/10)"),
    _clippy("clippy::cognitive_complexity", "crates/b/src/run.rs", 5, "complexity of (7/10)"),
    _clippy("E0308", "crates/c/src/lib.rs", 1, "mismatched types"),
    {"reason": "build-finished", "success": False},
]
CLIPPY_ALL: list[Json] = [
    *CLIPPY_PROD[:5],
    _clippy("clippy::unwrap_used", "crates/a/tests/it.rs", 2, "used `unwrap()` on a `Result`"),
]

RUFF: list[Json] = [
    {
        "code": "T201",
        "filename": "pkg/a.py",
        "location": {"row": 2, "column": 1},
        "message": "`print` found",
        "fix": {"applicability": "unsafe"},
    },
    {
        "code": "T201",
        "filename": "pkg/a.py",
        "location": {"row": 2, "column": 1},
        "message": "`print` found",
        "fix": {"applicability": "unsafe"},
    },
    {
        "code": "F401",
        "filename": "pkg/a.py",
        "location": {"row": 1, "column": 8},
        "message": "`os` imported but unused",
        "fix": {"applicability": "safe"},
    },
    {
        "code": "C901",
        "filename": "pkg/sub/b.py",
        "location": {"row": 4, "column": 5},
        "message": "`f` is too complex (13 > 10)",
        "fix": None,
    },
    {
        "code": "C901",
        "filename": "pkg/sub/b.py",
        "location": {"row": 40, "column": 5},
        "message": "`g` is too complex (6 > 10)",
        "fix": None,
    },
    {
        "code": None,
        "filename": "pkg/bad.py",
        "location": {"row": 1, "column": 1},
        "message": "SyntaxError: Expected an expression",
    },
]

MYPY: list[Json] = [
    {
        "file": "pkg/a.py",
        "line": 3,
        "column": 4,
        "code": "arg-type",
        "severity": "error",
        "message": "bad argument",
    },
    {
        "file": "pkg/a.py",
        "line": 3,
        "column": 4,
        "code": None,
        "severity": "note",
        "message": "a note",
    },
    {
        "file": "pkg/b.py",
        "line": 1,
        "column": 0,
        "code": "syntax",
        "severity": "error",
        "message": "invalid syntax",
    },
]

PYRIGHT: Json = {
    "generalDiagnostics": [
        {
            "file": "pkg/a.py",
            "severity": "error",
            "rule": "reportArgumentType",
            "message": "bad argument",
            "range": {"start": {"line": 2, "character": 3}},
        },
        {
            "file": "pkg/a.py",
            "severity": "information",
            "message": "a hint",
            "range": {"start": {"line": 0, "character": 0}},
        },
    ]
}

ESLINT: list[Json] = [
    {
        "filePath": "src/a.ts",
        "messages": [
            {
                "ruleId": "complexity",
                "line": 1,
                "column": 1,
                "message": "Function has a complexity of 13.",
            },
            {
                "ruleId": None,
                "fatal": True,
                "line": 9,
                "column": 2,
                "message": "Parsing error: unexpected token",
            },
        ],
    }
]

OXLINT: Json = {
    "diagnostics": [
        {
            "code": "eslint(no-console)",
            "filename": "src/a.ts",
            "message": "Unexpected console statement.",
            "labels": [{"span": {"line": 4, "column": 3}}],
        },
        {
            "code": "typescript(no-explicit-any)",
            "filename": "src/b.ts",
            "message": "Unexpected any.",
            "labels": [{"span": {"line": 1, "column": 10}}],
        },
        {"filename": "src/c.ts", "message": "Unexpected token"},
    ]
}

GOLANGCI: Json = {
    "Issues": [
        {
            "FromLinter": "gosec",
            "Text": "G104: Errors unhandled",
            "Pos": {"Filename": "cmd/x/main.go", "Line": 7, "Column": 2},
        },
        {
            "FromLinter": "revive",
            "Text": "argument-limit: maximum number of arguments exceeded; max 5 but got 7",
            "Pos": {"Filename": "internal/y/y.go", "Line": 3, "Column": 1},
        },
        {
            "FromLinter": "errcheck",
            "Text": "Error return value is not checked",
            "Pos": {"Filename": "internal/y/y.go", "Line": 9, "Column": 4},
        },
        {
            "FromLinter": "typecheck",
            "Text": "undefined: z",
            "Pos": {"Filename": "internal/z/z.go", "Line": 1, "Column": 1},
        },
    ]
}

TSC = """src/a.ts(3,5): error TS2322: Type 'string' is not assignable to type 'number'.
not a diagnostic
"""

VULTURE = """pkg/a.py:10: unused function 'helper' (60% confidence)
pkg/a.py:20: unreachable code after 'return' (100% confidence)
"""

KNIP: Json = {
    "issues": [
        {
            "file": "src/a.ts",
            "exports": [{"name": "unusedThing", "line": 3, "col": 14}],
            "dependencies": ["left-pad"],
        }
    ]
}

ASTGREP: list[Json] = [
    {
        "ruleId": "no-shell",
        "file": "src/a.rs",
        "message": "spawn through crate::proc",
        "range": {"start": {"line": 4, "column": 8}},
    }
]

JSCPD: Json = {
    "duplicates": [
        {
            "format": "python",
            "tokens": 60,
            "lines": 8,
            "firstFile": {"name": "a.py", "start": 10},
            "secondFile": {"name": "b.py", "start": 30},
        },
        {
            "format": "python",
            "tokens": 35,
            "lines": 6,
            "firstFile": {"name": "a.py", "start": 10},
            "secondFile": {"name": "c.py", "start": 5},
        },
    ]
}

# ---- drift.py ---------------------------------------------------------------

RUFF_RULES_OLD: list[Json] = [
    {"code": "T201", "status": "Stable"},
    {"code": "F401", "status": "Stable"},
    {"code": "OLD001", "status": "Stable"},
    {"code": "PRE001", "status": {"Preview": {"since": "0.1"}}},
    {"name": "no-code-rule"},
]
RUFF_RULES_NEW: list[Json] = [
    {"code": "T201", "status": "Stable"},
    {"code": "F401", "status": "Deprecated"},
    {"code": "NEW001", "status": "Stable"},
    {"code": "PRE001", "status": "Stable"},
]
RUFF_DRAFT = """[lint]
select = ["ALL"]
ignore = ["T201", "F401", "GONE99", "PRE"]

[lint.per-file-ignores]
"tests/**" = ["NEW001"]
"""

OXLINT_RULES: list[Json] = [
    {"scope": "eslint", "value": "no-console", "category": "restriction"},
    {"scope": "eslint", "value": "no-debugger", "category": "correctness"},
    {"scope": "eslint", "value": "no-alert", "category": "restriction"},
    {"scope": "typescript", "value": "no-explicit-any", "category": "restriction"},
    {"scope": "typescript", "value": "no-namespace", "category": "restriction"},
    {"scope": "unicorn", "value": "no-null", "category": "restriction"},
]
OXLINT_CONFIG = """{
  // the repo's config today
  "plugins": ["typescript"],
  "categories": {"correctness": "error"},
  "rules": {"no-alert": "warn"},
}
"""
OXLINT_DRAFT = """{
  "rules": {"no-console": "error", "typescript/no-explicit-any": "error", "no-such-rule": "error"}
}
"""

CLIPPY_HELP = """Lint groups provided by rustc:

    name  sub-lints
    ----  ---------
    rust-2018-idioms  bare-trait-objects, unused-extern-crates

Lint checks provided by plugins loaded by this crate:

    name                       default  meaning
    ----                       -------  -------
    clippy::unwrap-used        allow    checks for unwrap
    clippy::needless-return    warn     checks for return
    clippy::doc-markdown       allow    checks for backticks
    unused-extern-crates       allow    an extern crate never used

Lint groups provided by plugins loaded by this crate:

    clippy::pedantic  clippy::doc-markdown, clippy::needless-return, clippy::must-use-candidate
"""
CLIPPY_DRAFT = """[workspace.lints.clippy]
unwrap_used = "deny"
no_such_lint = "deny"

[workspace.lints.rust]
unused_extern_crates = "deny"
"""

TSC_OPTIONS = """--strict
Enable all strict type-checking options.
--noUncheckedIndexedAccess
Add undefined.
"""
TSC_DRAFT = """{
  "compilerOptions": {"strict": true, "nouncheckedindexedaccess": true, "noSuchOption": true}
}
"""

GOLANGCI_LINTERS = """errcheck: checks unchecked errors
gosec: inspects source for security problems
oldlint [deprecated]: replaced
"""
GOLANGCI_DRAFT = """linters:
  default: all
  disable:
    - oldlint
  enable:
    - errcheck
    - nosuchlinter
"""


def _dump(path: Path, data: object, *, lines: bool = False) -> None:
    if lines and isinstance(data, list):
        text = "\n".join(json.dumps(item) for item in data) + "\n"
    else:
        text = json.dumps(data)
    path.write_text(text, encoding="utf-8", newline="\n")


def write(folder: Path) -> None:
    """Write every fixture into `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    as_json: dict[str, object] = {
        "ruff.json": RUFF,
        "pyright.json": PYRIGHT,
        "eslint.json": ESLINT,
        "oxlint.json": OXLINT,
        "golangci.json": GOLANGCI,
        "knip.json": KNIP,
        "jscpd.json": JSCPD,
        "ruff-rules-old.json": RUFF_RULES_OLD,
        "ruff-rules-new.json": RUFF_RULES_NEW,
        "oxlint-rules.json": OXLINT_RULES,
        "tally-record.json": documents.TALLY_RECORD,
        "tally-point.json": documents.TALLY_POINT,
        "phases.json": documents.PHASES,
        "layout.json": documents.LAYOUT,
        "noise.json": {"must_use_candidate": "fires on every pure fn"},
    }
    for name, data in as_json.items():
        _dump(folder / name, data)
    as_lines: dict[str, list[Json]] = {
        "clippy.prod.json": CLIPPY_PROD,
        "clippy.all.json": CLIPPY_ALL,
        "mypy.jsonl": MYPY,
        "astgrep.jsonl": ASTGREP,
    }
    for name, items in as_lines.items():
        _dump(folder / name, items, lines=True)
    as_text = {
        "tsc.txt": TSC,
        "vulture.txt": VULTURE,
        "empty.json": "",
        "ruff-draft.toml": RUFF_DRAFT,
        "oxlintrc.json": OXLINT_CONFIG,
        "oxlint-draft.json": OXLINT_DRAFT,
        "clippy-help.txt": CLIPPY_HELP,
        "clippy-draft.toml": CLIPPY_DRAFT,
        "tsc-options.txt": TSC_OPTIONS,
        "tsc-draft.json": TSC_DRAFT,
        "golangci-linters.txt": GOLANGCI_LINTERS,
        "golangci-draft.yml": GOLANGCI_DRAFT,
        "cargo-base.toml": documents.CARGO_BASE,
        "cargo-shrunk.toml": documents.CARGO_SHRUNK,
        "cargo-grown.toml": documents.CARGO_GROWN,
        "cargo-unread.toml": documents.CARGO_UNREAD,
        "ruff-debt.toml": documents.RUFF_DEBT,
        "golangci-debt.yml": documents.GOLANGCI_DEBT,
        "mypy-debt.ini": documents.MYPY_DEBT,
        "oxlint-debt.json": documents.OXLINT_DEBT,
        "ruff-head.toml": documents.RUFF_HEAD_CONFIG,
        "plan.md": documents.PLAN,
        "plan-cut.md": documents.PLAN.replace(documents.END, "").replace(
            "### Phase 3 — Shape", "### Phase 9 — Shape"
        ),
        "SKILL.md": documents.SKILL,
        "ref.md": documents.REFERENCE,
        "evidence.md": documents.EVIDENCE,
        "evidence-bad.md": documents.EVIDENCE_BAD,
        "no-asof.md": "# A reference with no date line\n",
    }
    for name, text in as_text.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
