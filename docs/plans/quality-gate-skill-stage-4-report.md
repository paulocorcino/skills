# Stage 4 — Rust language pack — Post-stage report

**Backlog items:** QG-RS-1
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** quality-gate-skill.md

## Files changed

- `quality-gate/languages/rust/run.py` — real implementation replacing Stage 1 stub: detects cargo/cargo-llvm-cov/clippy/jscpd availability; runs `cargo llvm-cov --json` for line/branch coverage; runs `cargo clippy --message-format=json -- -W clippy::all` for violations (errors/warnings/info); runs `jscpd --languages rust` for duplication; collects per-file LOC and violation counts for files crossing soft_limit (400) or with violations.
- `quality-gate/languages/rust/tools.json` — real manifest replacing stub: cargo (rustup install), cargo-llvm-cov (`cargo install cargo-llvm-cov`), clippy (`rustup component add clippy`), jscpd (`npm install -g jscpd`). Changed from object-with-key `{"tools":[...]}` to bare array (consistent with Go/Python Stage 2-3 pattern; validate_language only checks run.py output, not tools.json shape).
- `quality-gate/languages/rust/sample-output.json` — canonical example output (created new); passes `validate_language.py` against `language_metrics.schema.json`. No `bytes` field (schema has no such field; omitted per parent note).

## Gate results

- `py_compile quality-gate/languages/rust/run.py` — **pass**
- `python3 -m json.tool tools.json` — **pass**
- `python3 -m json.tool sample-output.json` — **pass**
- `validate_language sample-output.json` — **pass**

## Acceptance criteria audit

- [x] `run.py` invokes `cargo llvm-cov --json` for coverage
- [x] `run.py` invokes `cargo clippy --message-format=json -- -W clippy::all` for violations; errors=`level=error`, warnings=`level=warning`
- [x] `run.py` invokes `jscpd` for duplication
- [x] `tools.json` real manifest with detect/install commands and docs_url for all four tools
- [x] `sample-output.json` validates against `language_metrics.schema.json`
- [x] No shell scripts under `languages/rust/`
- [x] Per-file entries include `loc`, `complexity` (null — clippy provides no per-function complexity score), `violations`

## Deviations from plan

- Stage 1 stub listed `tarpaulin` in `REQUIRED_TOOLS`; Stage 4 replaces coverage with `cargo-llvm-cov` per the plan spec. Stub's tool list was a placeholder only.
- `tools.json` format changed from `{"tools":[...]}` to a bare JSON array, matching the Go and Python packs from Stages 2-3 (the schema validator does not check tools.json shape).
- `complexity` is always `null` per file: Rust/clippy does not emit a per-function cyclomatic number in its JSON output. The field is nullable in the schema so this is valid. A future enhancement could parse `cargo-geiger` or custom metrics.

## Surprises / notes

- `cargo llvm-cov` requires `llvm-tools` component (`rustup component add llvm-tools-preview`); the runner handles absence gracefully via `_cargo_subcommand_available`.
- Clippy JSON output is NDJSON (one JSON object per line); the runner iterates `splitlines()` and parses each independently.
- Per-file `branches` coverage is null in sample (llvm-cov may not report branch counts for all projects); schema allows null so this is fine.
