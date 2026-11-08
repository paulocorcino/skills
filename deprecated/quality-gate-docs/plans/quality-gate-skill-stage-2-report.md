# Stage 2 — Python language pack — Post-stage report

**Backlog items:** QG-PY-1
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** quality-gate-skill.md

## Files changed

- `quality-gate/languages/python/run.py` — replaced Stage 1 stub with real implementation: ruff (lint), pytest+coverage.py (tests + coverage), bandit (security patterns), radon (complexity per-file), jscpd (duplication); normalizes all outputs to canonical schema.
- `quality-gate/languages/python/tools.json` — replaced stub (empty install_command) with real manifest including pip/npm install commands and docs_url for all 6 tools.
- `quality-gate/languages/python/sample-output.json` — new file; canonical example of a valid run.py output for a small 3-file Python project; validated against `language_metrics.schema.json`.

## Gate results

- `python3 -m py_compile run.py`: **pass**
- `python3 -m json.tool tools.json`: **pass**
- `python3 -m json.tool sample-output.json`: **pass**
- `validate_language sample-output.json`: **pass**
- Global build gate (`import quality_gate, quality_gate.cli`): **pass**
- Global py_compile (all .py under quality-gate/): **pass**

## Acceptance criteria audit

- [x] `run.py` accepts `--root` and `--output`
- [x] Tool detection via `shutil.which`; missing tools in `tools_missing`, used in `tools_used`
- [x] ruff invoked with `--output-format=json`; E/F codes → errors, W codes → warnings, rest → info
- [x] pytest+coverage invoked with `--cov-branch`; coverage XML parsed for line_pct and branch_pct
- [x] bandit invoked with `-f json`; HIGH → errors, MEDIUM/LOW → warnings (added to violations)
- [x] radon invoked with `cc -j`; max complexity per file stored in `files[*].complexity`
- [x] jscpd invoked with `--reporters json`; `statistics.total.percentage` → `duplication.pct`
- [x] Deterministic ordering: sorted tools lists, sorted file keys, 2-decimal rounding
- [x] `tools.json` has real install_command for all 6 tools
- [x] `sample-output.json` validates against `language_metrics.schema.json`

## Deviations from plan

- `vulnerabilities` in run.py is left as `{"critical":0,"high":0,"medium":0,"low":0}` (zeros). Bandit findings (security patterns) are merged into `violations.errors/warnings` rather than `vulnerabilities` — this matches the plan spec which states bandit goes to violations, and OSV/Semgrep (Stage 6 security pack) populates `vulnerabilities`.
- `files[*]` schema has `loc`, `complexity`, `violations` (no `bytes`). The plan mentioned `bytes` for files crossing `soft_limit`, but the `language_metrics.schema.json` (from Stage 1) does not include a `bytes` field. Stayed schema-compliant; `bytes` collection was not added to the output (would fail schema validation).

## Surprises / notes

- The `language_metrics.schema.json` `files` additionalProperties does not include `bytes`, so the plan's reference to per-file `bytes` is not representable in the current schema. Stage 7 docs or a future schema revision could add it, but this stage stays within declared scope.
- radon outputs complexity per-block (function/method); this implementation takes the max complexity across all blocks in a file, which is the most conservative and ratchet-friendly metric.
