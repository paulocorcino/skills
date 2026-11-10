"""The debt lists, the plan, the record's inputs and the evidence the tests read."""

from __future__ import annotations

Json = dict[str, object]

# ---- debt.py shrink ---------------------------------------------------------

CARGO_BASE = """[workspace]
members = [
  "crates/a",
]

[workspace.lints.clippy]
pedantic = { level = "deny", priority = -1 }
# debt: 12 sites
doc_markdown = "allow"
# debt: 3 sites; Phase 2
needless_return = "allow"
# noise: fires on every pure fn
must_use_candidate = "allow"
"""
CARGO_SHRUNK = CARGO_BASE.replace("# debt: 12 sites", "# debt: 9 sites").replace(
    '# debt: 3 sites; Phase 2\nneedless_return = "allow"\n', ""
)
CARGO_GROWN = (
    CARGO_BASE.replace("# debt: 12 sites", "# debt: 14 sites")
    + '# debt: 2 sites\nunwrap_used = "allow"\nsimilar_names = "allow"\n'
    + '# noise: taste\nif_not_else = "allow"\n'
    + '# noise: convention (D2)\nitems_after_statements = "allow"\n'
)
CARGO_UNREAD = CARGO_BASE + "# debt: 4 sites\n\n[profile.release]\nlto = true\n"
RUFF_DEBT = """ignore = [
  # noise: conflicts with the formatter
  "COM812", "ISC001",
  # debt: 5 sites
  "T201",
  "E501",  # debt: 7 sites
]
"""
GOLANGCI_DEBT = """linters:
  default: all
  disable:
    # debt: 4 sites
    - errcheck
    # noise: deprecated
    - oldlint
"""
MYPY_DEBT = """[mypy]
strict = True
disable_error_code =
    # debt: 6 sites
    arg-type,
    # noise: a library types it Any
    no-any-return,
"""
OXLINT_DEBT = """{
  "rules": {
    // debt: 2 sites
    "no-console": "off",
    "typescript/no-explicit-any": "off", // debt: 1 site
  }
}
"""

# ---- progress.py ------------------------------------------------------------

TALLY_RECORD: Json = {
    "T201": ["a.py:1:1", "a.py:2:1", "b.py:1:1"],
    "C901": ["a.py:5:1"],
    "F401": ["a.py:1:8"],
}
TALLY_POINT: Json = {
    "T201": ["a.py:1:1"],
    "C901": ["a.py:5:1", "c.py:9:1"],
    "E501": ["a.py:7:101"],
}
PHASES: Json = {"T201": "2", "C901": "3", "F401": "1"}
LAYOUT: Json = {
    "phases": {
        "0": {"lane": "gate", "waits": []},
        "1": {"lane": "python", "waits": ["0"]},
        "2": {"lane": "python", "waits": ["1"]},
        "3": {"lane": "shape", "waits": ["0"]},
    },
    "decisions": {"D1": {"holds": ["2"]}, "D2": {"holds": []}},
}
RUFF_HEAD_CONFIG = 'ignore = [\n  # debt: 3 sites\n  "T201",\n  # debt: 1 site\n  "F401",\n]\n'
END = "<!-- end of the plan: progress.py check reads this line -->"
PLAN = f"""# Lint transition

## Working this plan

Work one phase at a time.

## Target

Every rule an error.

## Decisions for the human

- D1: which module owns output.
- D2: the line width.

## Phases

### Phase 0 — The gate

Done when: one command runs every check.

### Phase 1 — Unused imports

Rules: F401, fix by command.

### Phase 2 — Output

Rules: T201, fix then flip. Held by D1.

### Phase 3 — Shape

Rules: C901, baseline ratchet.

## One-way doors

none — a small repo

## Fix discipline

A fix keeps the behavior.

{END}
"""

# ---- rows.py ----------------------------------------------------------------

SKILL = """# Skill

## Knobs

| Knob | Reference | Curve |
|---|---|---|
| Function complexity | 10 | curve |
| Optional family: docs | on | counts |
"""
REFERENCE = """# Python target

## Tools

| Check | Command |
|---|---|
| Format | `ruff format --check` |
| Lint | `ruff check` |
| Types | `mypy` |
| A pipe \\| inside | `x` |

```toml
line-length = 100
[lint.mccabe]
max-complexity = 10
```

## Do not turn on

| Rule | Why |
|---|---|
| `PLR2004` | named constants |
| Format | a second table repeats the name |
"""
EVIDENCE = """# Evidence

## Measured

| Rule | Tool | Class | Production | Test | Scopes | Strategy | Phase |
|---|---|---|---|---|---|---|---|
| T201 | ruff | Capability | 2 | 1 | pkg | Fix then flip | 2 |
| C901 | ruff | Shape | 1 | 0 | pkg | Baseline ratchet | 3 |
| F401 | ruff | Surface | 1 | 0 | pkg | Fix by command | 1 |

## Coverage

| Row | Verdict |
|---|---|
| knobs: Function complexity | sites 1 |
| knobs: Optional family: docs | decision — D2, sites 4 |
| ref: Format | on |
| ref: Lint | phase 2 |
| ref: Types | n/a — no type checker in this repo |
| ref: A pipe \\| inside | closed by the gate |
| ref: PLR2004 | out — named constants |
| ref: Format (Rule) | open — a human reads it |
"""
EVIDENCE_BAD = (
    EVIDENCE.replace("| ref: Lint | phase 2 |\n", "")
    .replace("| ref: Format | on |", "| ref: Format | fine |")
    .replace("decision — D2, sites 4", "decision — D2")
    + "| ref: Gone | on |\n"
)
