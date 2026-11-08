# Stage 5 — BunJS language pack — Post-stage report

**Backlog items:** QG-BUN-1
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** quality-gate-skill.md

## Files changed

- `quality-gate/languages/bunjs/run.py` — replaced stub with real implementation: biome-primary/oxlint-fallback linting, `bun test --coverage` output parsing, jscpd duplication, per-file LOC collection with skip-dirs logic.
- `quality-gate/languages/bunjs/tools.json` — replaced stub with real manifest: bun, biome (primary), oxlint (fallback), jscpd; each entry has name, purpose, detect_command, install_command, docs_url. Changed from object-with-`tools`-key to top-level array (matching other packs).
- `quality-gate/languages/bunjs/sample-output.json` — new canonical example reflecting a realistic small BunJS project with biome, valid against language_metrics.schema.json.

## Gate results

- **py_compile** (run.py): pass
- **json.tool** (tools.json): pass
- **json.tool** (sample-output.json): pass
- **validate_language** (sample-output.json vs schema): pass
- **build gate** (`import quality_gate, quality_gate.cli`): pass
- **no shell scripts** under `languages/`: pass (0 results)

## Acceptance criteria audit

- [x] `run.py` real implementation with biome-primary, oxlint-fallback detection
- [x] `bun test --coverage` invoked for coverage (line_pct, branch_pct)
- [x] `biome check --reporter=json` invoked when biome available
- [x] `oxlint --format=json` invoked as fallback when biome absent
- [x] `jscpd` invoked for duplication (typescript + javascript languages)
- [x] `tools.json` real manifest with bun/biome/oxlint/jscpd entries
- [x] `sample-output.json` validates against language_metrics.schema.json
- [x] No per-file `bytes` field (omitted per parent note — schema has no such field)
- [x] Deterministic output: sorted tools_used/tools_missing, sorted files keys

## Deviations from plan

- `tools.json` shape: plan implied inheriting the Stage 1 stub format (object with `tools` key). Changed to top-level array to match python/go/rust packs for consistency. The schema does not constrain this file's structure; only `run.py` uses it indirectly via `tools_used`/`tools_missing`.
- oxlint `tools_missing` when biome is present: oxlint is reported in `tools_missing` when biome is detected, since only one lint tool runs. This is consistent with the spirit of the fallback design and avoids false "tool present" signals.

## Surprises / notes

- `bun test --coverage` emits coverage in a tabular text format to stderr; no dedicated JSON coverage format is available in bun's CLI as of this stage. The parser looks for an "All files" summary row and extracts numeric columns. If bun's output format changes, the coverage fields gracefully return `null` without crashing.
- biome's `--reporter=json` format places diagnostics under a `diagnostics` array with `severity` strings (`error`/`warning`/`information`/`hint`). Unknown severities are treated as warnings.
- Local installs (node_modules/.bin) are resolved for biome, oxlint, and jscpd so that projects using `bun add -d` without global installs are supported.
