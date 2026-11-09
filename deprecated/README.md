# Deprecated

Skills that a newer skill replaced. They are here for reference only. `npx skills` does not show them (`metadata.internal: true`).

- **quality-gate**: checked that quality never went down in Python, Go, Rust and BunJS projects, with its own runner. [lint-gate](../skills/engineering/lint-gate/SKILL.md) replaced it. lint-gate does not wrap the linters in its own tool: it makes each language's own linters strict. `quality_gate.py` is the import shim of quality-gate, and `quality-gate-docs/` has its decision records and its build plan.
