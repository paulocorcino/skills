# Stage 1 — Core skeleton (SKILL.md, schemas, lib, cli, _template, stub runners) — Post-stage report

**Backlog items:** QG-CORE-1
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** quality-gate-skill.md

## Files changed
- `quality-gate/SKILL.md` — initial SKILL.md with YAML frontmatter (`name: quality-gate`), happy-path, subcommand table, inviolable rules, exit-code table, references stubs, and layout diagram.
- `quality-gate/__init__.py` — empty package marker.
- `quality-gate/__main__.py` — dispatches `python -m` invocations to `quality_gate.cli.main()` (kept for completeness; primary entry point is the shim, see Deviations).
- `quality-gate/cli.py` — argparse CLI with subcommands `init`/`run`/`status`/`update-baseline`/`to-backlog`; flags `--cwd`, `--language`, `--only`, `--main-branch`, `--force`; exit-code constants per spec; orchestrates detect → run.py → validate → security stub → ratchet → report.
- `quality-gate/schema/baseline.schema.json` — JSON Schema draft-07 for `.quality-gate/baseline.json` (schema_version, generated_at, commit, main_branch, tools_versions, projects map).
- `quality-gate/schema/language_metrics.schema.json` — canonical language-runner output schema (language, root, tools_used, tools_missing, coverage, duplication, violations, vulnerabilities, files).
- `quality-gate/schema/config.schema.json` — JSON Schema for `.quality-gate/config.json` (projects array + soft/hard limit overrides).
- `quality-gate/lib/__init__.py` — empty package marker.
- `quality-gate/lib/detect.py` — manifest-based project detection with `_SKIP_DIRS`, plus `detect_from_config` honoring an explicit `projects` array.
- `quality-gate/lib/baseline_io.py` — `read_baseline` (prefers `git show <main>:…`, falls back to working tree only on main), `write_baseline` (atomic temp + rename; refuses non-main writes without `--force`).
- `quality-gate/lib/config.py` — stdlib-only validator + defaults for soft/hard limits per language.
- `quality-gate/lib/ratchet.py` — `compare()` implementing zero-tolerance counters, 0.05-point percentage tolerance, absolute floors for lint errors / vuln criticals, per-file no-grow rule; deterministic sort.
- `quality-gate/lib/report.py` — deterministic markdown renderer; Metadata block excluded from `report_hash` (sha256 over the data sections); 2-decimal rounding; alphabetical ordering everywhere.
- `quality-gate/lib/triage.py` — classifies regressions as `caused_by_pr` vs `pre_existing` using `git diff --name-only <base>...HEAD`, with project-root fallback for project-level metrics.
- `quality-gate/lib/validate_language.py` — stdlib-only JSON Schema (draft-07 subset) validator for language-runner outputs; module + CLI (`python -m quality_gate.lib.validate_language PATH`).
- `quality-gate/lib/security.py` — STUB returning the agreed no-op payload per project; Stage 6 will swap in OSV-Scanner + Semgrep CE.
- `quality-gate/lib/backlog.py` — parses Regressions table from `report.md` and emits one tracer-bullet markdown issue per regression under `<repo>/docs/backlogs/`.
- `quality-gate/languages/__init__.py` — empty package marker.
- `quality-gate/languages/_template/{run.py,tools.json,metadata.json}` — canonical contract reference (documented runner, example tool entry, example metadata).
- `quality-gate/languages/python/{run.py,tools.json,metadata.json}` — STUB run.py emitting schema-valid empty output (REQUIRED_TOOLS: ruff/pytest/coverage/bandit/radon/jscpd); real metadata (soft 300 / hard 800).
- `quality-gate/languages/go/{run.py,tools.json,metadata.json}` — STUB run.py (REQUIRED_TOOLS: go/golangci-lint/gosec/jscpd); real metadata (soft 500 / hard 1000).
- `quality-gate/languages/rust/{run.py,tools.json,metadata.json}` — STUB run.py (REQUIRED_TOOLS: cargo/clippy/tarpaulin/jscpd); real metadata (soft 400 / hard 900).
- `quality-gate/languages/bunjs/{run.py,tools.json,metadata.json}` — STUB run.py (REQUIRED_TOOLS: bun/eslint/tsc/jscpd); real metadata (soft 300 / hard 800).
- `quality_gate.py` — Python-import shim at repo root (see Deviations).
- `docs/plans/quality-gate-skill-verify-stage-1.py` — verification script (see Deviations).
- `docs/plans/quality-gate-skill-stage-1-report.md` — this report.

## Gate results
- **Package import**: pass — `PYTHONPATH=… python3 -c "import quality_gate; import quality_gate.cli; …"` exits 0.
- **py_compile**: pass — every `.py` under `quality-gate/` compiles.
- **JSON validity**: pass — all `schema/*.json` and `languages/*/{tools,metadata}.json` parse via `python3 -m json.tool`.
- **CLI surface**: pass — `python3 -m quality_gate --help` exits 0 and lists `init`, `run`, `status`, `update-baseline`, `to-backlog`.
- **Invariant — no shell scripts under languages/**: pass — `find … -name '*.sh' | wc -l` returns 0.
- **Stub runners → schema-valid output**: pass for python, go, rust, bunjs (`validate_language` returns OK on each).
- **SKILL.md frontmatter invariant**: pass — file begins `---\nname: quality-gate\n` (manually verified).
- **Live newly-discoverable skill**: confirmed — the harness's skill-discovery refreshed mid-stage and surfaced `quality-gate` in the available-skills list.

## Acceptance criteria audit
- [x] Skill folder `quality-gate/` and all declared subdirectories created.
- [x] Three JSON Schemas materialized and valid.
- [x] All eight `lib/` modules implemented; `lib/security.py` is the only intentional stub.
- [x] CLI with all five subcommands wired through the lib modules; exit codes per spec table.
- [x] `__init__.py` and `__main__.py` in place.
- [x] `languages/_template/` triplet documents the contract.
- [x] Each `languages/<lang>/` triplet: stub `run.py` (schema-valid output), stub `tools.json`, real `metadata.json`.
- [x] `SKILL.md` with YAML frontmatter (`name: quality-gate`), happy path, inviolable rules, references stubs.
- [x] Every invariant from `## Global conventions` holds (build gate, py_compile, json.tool, no `.sh` under languages, SKILL.md frontmatter, runner outputs validate against schema).

## Deviations from plan
1. **Python-import shim at `quality_gate.py`.** The plan declares the skill folder as `quality-gate/` (hyphen, per Claude skill discovery convention), but `## Global conventions` mandates `import quality_gate` (underscore — Python module-name rules disallow hyphens). To satisfy BOTH constraints, I kept the directory `quality-gate/` and added a top-level shim `/home/corcino/.claude/skills/quality_gate.py` that uses `importlib.util.spec_from_file_location` with `submodule_search_locations` to wire the hyphenated directory in as the `quality_gate` package. The shim also dispatches `python -m quality_gate` to `quality_gate.cli.main()` (necessary because `-m` loads the shim, not the package's `__main__.py`, since the hyphenated dir is not a discoverable package root). This is the same approach the parent's judgment note recommended.
2. **`docs/plans/quality-gate-skill-verify-stage-1.py` rewritten.** The pre-existing verify script (from the plan landing commit) called `V.assert_only_files_touched(allowed_globs=[…], …)`, but `_verify._Verifier.assert_only_files_touched` only accepts `allowlist=[…]` as a positional list of explicit paths. The mismatch raised `TypeError` before any gate could run. I rewrote the script to use the supported API and to pass the Stage 1 declared file list (plus the shim and the report) verbatim. Behavior is now consistent with `_verify.py`'s contract; no changes to `_verify.py` itself.
3. **`__main__.py` retained.** Even though the shim handles `python -m quality_gate` dispatch, I kept the package's own `__main__.py` (still importing `quality_gate.cli.main`) so that direct execution via the package directory (`python3 quality-gate/__main__.py` after a manual `sys.path` adjustment) continues to work for developers experimenting outside the standard PYTHONPATH setup.

## Surprises / notes
- The Claude Code harness re-scanned skills mid-stage and surfaced `quality-gate` in the available-skills list as soon as `SKILL.md` was written. Confirms the folder name (`quality-gate/`, hyphen) is the right one for skill discovery — and validates the shim approach over renaming the directory.
- `lib/validate_language.py` is hand-rolled (stdlib-only) on a deliberate subset of draft-07 (type, enum, required, additionalProperties: false, properties, items, minimum, pattern). This avoids a `jsonschema` dependency, but downstream stages that introduce more exotic schema features (oneOf, allOf, refs) will need to extend it.
- `lib/baseline_io.write_baseline` is atomic (temp file + `os.replace`) but does NOT stage/commit — caller responsibility. The CLI `update-baseline` subcommand only writes; staging is left to the operator (matches the design rule "skill stays general").
- `lib/triage.py` and `lib/backlog.py` are wired but unexercised in Stage 1; downstream stages or the e2e gate should add fixture-backed tests when the language packs land.
- The fully-qualified e2e import line in `## End-to-end verification` already covers all Stage 1 modules; no additional Stage-1-only imports are missing from the e2e script.
