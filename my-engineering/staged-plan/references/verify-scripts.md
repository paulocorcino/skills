# Verify scripts

## Trigger

Generate `docs/plans/<plan-slug>-verify-stage-N.py` (or `-verify-e2e.py`) when **any** condition holds:
- The stage has **≥4 distinct proof/gate commands** across its `**Checks:**` and the global gates.
- The stage has **≥2 grep-based invariant checks** (e.g. "no import of `lib-a` under `src/`").
- The stage uses **≥2 `_verify` primitives** (`assert_clean_tree`, `assert_only_files_touched`, `assert_report_exists`, `assert_grep_zero`, ...).

**When in doubt, generate the script** — ~20 lines, rerun unchanged by every retry and by the parent's independent re-run. Inline proofs suit only simple stages (one or two test commands).

## Proofs: `run_proof`, not `run_gate`

Each check's proof runs through `V.run_proof(cmd, expect=[...], check="C<N>.<k>")`: it passes only when the command exits 0 **and** every name in `expect` appears in the runner's output. Pass a runner flag that prints per-test names (`pytest -v`, `jest --verbose`, `go test -v`, `cargo test -- --nocapture`). `run_gate` stays for whole-project gates (build, lint) where exit code alone is the claim.

## Why Python, not bash

Scripts must run unchanged on Linux, macOS, and Windows native (no WSL/Git-Bash dependency). Python 3 stdlib is the cross-platform denominator.

## Vendoring

The primitives live in this skill's `lib/verify.py` and are vendored into each repo at `<repo>/docs/plans/_verify.py`, so any executor (Claude, Codex, CI, a human) runs `python docs/plans/<slug>-verify-stage-N.py` without the skill installed. `scaffold.py` writes the copy and refreshes one whose `VERSION` is older (a copy with no `VERSION` line counts as 0); the Plan landing commit carries it. Bump `VERSION` whenever a primitive is added or changes behaviour, and only ever add primitives — older plans in the same repo keep running against the refreshed copy.

## Logs policy

`run_gate()` and `run_proof()` always write a timestamped log to `<repo>/docs/plans/logs/<prefix>-<ts>.log`. These are local evidence, **not versioned**: the Plan landing commit adds `docs/plans/logs/` to `.gitignore`. Reports carry deviations and judgments for PR review; raw logs are forensic-only.

## Generated script shape

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _verify import V

V.assert_clean_tree()
V.assert_commit_present(r"^feat: add B-backed impl")
V.assert_only_files_touched(
    ["src/y_v2.ts", "src/y_v2.test.ts", "docs/plans/migration-x-stage-1-report.md"],
    base_sha="HEAD~1",
)
V.run_gate("bun run build")
V.run_proof("bun test src/y_v2.test.ts", expect=["parses ISO dates with offset"], check="C1.1")
V.run_proof("bun test src/y_v2.test.ts", expect=["rejects empty input"], check="C1.2")
V.assert_grep_zero(r"\bimport.*from ['\"]lib-a['\"]", ["src/y_v2.ts"])
V.assert_report_exists("docs/plans/migration-x-stage-1-report.md")
sys.exit(V.summarize())
```
