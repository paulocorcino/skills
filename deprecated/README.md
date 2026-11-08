# Deprecated

Skills a newer one replaced, kept for reference. They are hidden from `npx skills` (`metadata.internal: true`).

- **quality-gate**: a ratchet over Python, Go, Rust and BunJS projects, with its own runner. Replaced by [lint-gate](../skills/engineering/lint-gate/SKILL.md), which drives each stack's own linters to a hard gate instead of wrapping them. `quality_gate.py` is its import shim, and `quality-gate-docs/` its decision records and build plan.
