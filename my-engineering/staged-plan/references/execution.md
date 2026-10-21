# Execution design notes

The operational Phase 2 contract is rendered into every plan by `lib/scaffold.py` (`## Execution model`, `## Execution policy`, `## Hand-off conventions`, `## Reviewer gate`). This file holds the reasons behind it and the optional hardening — read it when changing that contract, not when running a plan.

## Why the parent re-runs every proof

A subagent's "gates green" is a self-report. The parent re-runs the stage's proofs at `HEAD` and requires each named test to appear in the runner output, because several runners exit 0 when a filter matches nothing (`passWithNoTests` and equivalents) — a green check with no test behind it. `V.run_proof(cmd, expect=[...])` encodes both halves.

## Why the reviewer is dispatched by the parent

A fresh context is not independence on its own: whoever writes the reviewer's brief sets its scope. A reviewer spawned by the last stage's subagent would be pointed at that stage's diff, and a pass over four checks reads exactly like a pass over forty. So the parent dispatches it over `<plan landing commit>..HEAD` with every check of every stage, and the verdict comes back to the parent and the user — never to an author deciding about its own work.

## Why retries carry "Tried and abandoned"

A retry that only sees the failure excerpt tends to walk back into the approach that just failed. The discarded approaches exist nowhere else — not in the code, not in the plan — so the red subagent returns them and the parent passes them into the retry.

## Why one-way doors are recorded before the code

An alternative is only knowable while you are still choosing between them. Written after the code, the rejected option becomes a justification of what was already built. Writing the literal shape and the rejected alternative first is also the one check that can expose a bad decision with nobody else in the loop.

## Semi-autonomous `edit`

The between-stage checkpoint's `edit` option exists for what the finished stage's report surfaced: a callsite found mid-work, a door decided, an item in `Noticed, not touched` that belongs to the next stage. The user adjusts the next hand-off, then resumes.

## Notification examples

- `"Plan 008-outbound-reliability: reviewer BLOCKED (4 findings) — see docs/plans/reports/008-outbound-reliability_reviewer_001.md"`
- `"Plan migration-x: Stage 3 retry exhausted; Stage 5 does not depend on it — see docs/plans/migration-x-stage-3-report.md"`
- `"Plan migration-x: Stage 2 scope violation (touched files outside list) — escalated, no retry"`

## Optional hardening (per plan, not baked in)

- **Hooks for gate enforcement** (`.claude/settings.json` PostToolUse / PreCommit): a confused subagent can ignore a prompt-level gate, never a hook. Configure via `update-config`.
- **Accumulated run log:** a `Stop` hook appending each subagent's summary to `<repo>/docs/plans/<plan-slug>-run.md`.
