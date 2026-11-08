# Stage 3 — Go language pack — Post-stage report

**Backlog items:** QG-GO-1
**Commit:** _filled by parent_
**Plan:** quality-gate-skill.md

## Files changed

- `quality-gate/languages/go/run.py` — replaced stub with real implementation: `go test -coverprofile` + `go tool cover -func` for statement coverage; `golangci-lint run --out-format json` for violations (severity mapping: "error" -> errors, "warning" -> warnings, else info); `gocyclo -over 0` for per-file max cyclomatic complexity; `jscpd --languages go` for duplication; `vendor/` excluded from file stat collection.
- `quality-gate/languages/go/tools.json` — replaced stub with real manifest: go, golangci-lint (`go install .../golangci-lint@latest`), gocyclo (`go install .../gocyclo@latest`), jscpd (`npm install -g jscpd`).
- `quality-gate/languages/go/sample-output.json` — new canonical example output with realistic values for a 3-file Go project.

## Gate results

1. `python3 -m py_compile quality-gate/languages/go/run.py` — **PASS**
2. `python3 -m json.tool quality-gate/languages/go/tools.json` — **PASS**
3. `python3 -m json.tool quality-gate/languages/go/sample-output.json` — **PASS**
4. `python3 -m quality_gate.lib.validate_language quality-gate/languages/go/sample-output.json` — **PASS**

## Acceptance criteria audit

- [x] `run.py` invokes `go test -coverprofile` + `go tool cover -func` for coverage
- [x] `run.py` invokes `golangci-lint run --out-format json` for violations
- [x] `run.py` invokes `gocyclo` for per-file max cyclomatic complexity
- [x] `run.py` invokes `jscpd` for duplication
- [x] All outputs normalized to canonical schema
- [x] `tools.json` has real install commands (golangci-lint, gocyclo, jscpd)
- [x] `sample-output.json` validates against `language_metrics.schema.json`
- [x] No shell scripts introduced

## Deviations from plan

- `branch_pct` is `null` in sample-output.json: Go's native coverage tooling exposes statement coverage only; this matches the plan's note that branch coverage is not available natively.
- `REQUIRED_TOOLS` updated from stub's `["go", "golangci-lint", "gosec", "jscpd"]` to `["go", "golangci-lint", "gocyclo", "jscpd"]` to match the Stage 3 spec (gocyclo replaces gosec; security is handled by the security pack in Stage 6).

## Surprises / notes

- golangci-lint JSON output uses `"Pos"."Filename"` for file paths; a fallback to `"Filename"` at the issue root is included for version compatibility.
- gocyclo output format is `<complexity> <pkg> <func> <file>:<line>:<col>`; file path is the last colon-split field's first segment, relative to the project root.
- Per-file `bytes` field omitted to stay schema-valid (schema has no `bytes` field in `files[*]`), consistent with Stage 2 Python pack.
