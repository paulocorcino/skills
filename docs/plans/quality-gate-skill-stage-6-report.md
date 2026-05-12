# Stage 6 — Security pack (OSV-Scanner + Semgrep CE) — Post-stage report

**Backlog items:** QG-SEC-1
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** quality-gate-skill.md

## Files changed

- `quality-gate/lib/security.py` — replaced stub with real implementation; detects osv-scanner and semgrep on PATH, invokes each with JSON output format, aggregates vulnerability severity counts (critical/high/medium/low) and SAST violation counts (errors/warnings), gracefully degrades when either tool is absent.
- `quality-gate/lib/security_tools.json` — new manifest declaring osv-scanner and semgrep with detect_command, install_command, and docs_url.
- `quality-gate/lib/security-sample-output.json` — canonical example of `security.collect()` output for documentation and future debugging.

## Gate results

- **py_compile security.py:** pass
- **json.tool security_tools.json:** pass
- **json.tool security-sample-output.json:** pass
- **ratchet.py untouched (`git diff --quiet`):** pass
- **`security.collect('/tmp')` contract check:** pass — returns dict with `vulnerabilities`, `tools_used`, `tools_missing` keys; gracefully lists both tools as missing when neither is installed.
- **Build gate (`import quality_gate, quality_gate.cli`):** pass

## Acceptance criteria audit

- [x] `lib/security.py` invokes `osv-scanner --format json -r <root>` via subprocess
- [x] `lib/security.py` invokes `semgrep --json --config=auto <root>` via subprocess
- [x] Graceful fallback when either tool is absent (populates `tools_missing`, returns zero counts)
- [x] `lib/security_tools.json` manifest with `name`, `purpose`, `detect_command`, `install_command`, `docs_url` for both tools
- [x] `lib/security-sample-output.json` canonical example
- [x] `lib/ratchet.py` NOT modified
- [x] `collect_all()` helper preserved and updated to pass `project["root"]` instead of the whole dict

## Deviations from plan

- The stub's `collect(project: dict)` signature accepted a project dict; the plan's Stage 6 spec shows `collect(project_root: str)`. Adopted the string signature per the plan spec (the verification gate calls `security.collect('/tmp')`). `collect_all()` was updated accordingly to extract `p["root"]`.
- Added `violations_security` key to the return shape (plan spec includes it); the stub had not included it.

## Surprises / notes

- OSV-Scanner exits non-zero when vulnerabilities are found — this is expected behavior per OSV-Scanner docs. The implementation treats any non-zero exit as acceptable as long as stdout is valid JSON.
- Semgrep telemetry disabled via `SEMGREP_SEND_METRICS=off` env var to keep runs deterministic and privacy-respecting.
- CVSS score-to-bucket mapping implemented via float threshold (≥9.0=critical, ≥7.0=high, ≥4.0=medium, else low) as OSV-Scanner output may contain vector strings or numeric scores.
