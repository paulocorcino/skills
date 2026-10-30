# Execution design notes

The operational Phase 2 contract is rendered into every plan by `lib/scaffold.py` (`## Execution model`, `## Execution policy`, `## Hand-off conventions`, `## Hand-off prompt`, `## Reviewer gate`). This file holds the reasons behind it and the optional hardening — read it when changing that contract, not when running a plan.

## Why the parent re-runs every proof

A subagent's "gates green" is a self-report. The parent re-runs the stage's proofs at `HEAD` and requires each named test to appear in the runner output, because several runners exit 0 when a filter matches nothing (`passWithNoTests` and equivalents) — a green check with no test behind it. `V.run_proof(cmd, expect=[...])` encodes both halves.

## Why the reviewer is dispatched by the parent

A fresh context is not independence on its own: whoever writes the reviewer's brief sets its scope. A reviewer spawned by the last stage's subagent would be pointed at that stage's diff, and a pass over four checks reads exactly like a pass over forty. So the parent dispatches it over `<plan landing commit>..HEAD` with every check of every stage, and the verdict comes back to the parent and the user — never to an author deciding about its own work.

## Why the parent answers the reviewer's questions first

Most open findings are questions the repository already answers — is this path reachable, does a caller depend on that value, what did the ADR decide. Sending them to a human costs a round-trip and teaches the human to skim the pending list. The parent holds the plan, the diff, and the tools to look, so it answers with evidence; what reaches a human is what a wrong guess would make expensive or unknowable: a regression, data loss, a high-risk or irreversible change, or context that lives outside the repo. The criteria name the stakes and leave the investigation to the parent's judgment.

## Why delegated planning returns `<<PLAN_READY>>`

An orchestrator that hands planning to a subagent sees only the subagent's final message, and it decides from that message whether to execute. A fixed block with the plan path, landing commit, gate result, and widest wave makes that decision mechanical; prose would make it a judgment call on every run. The planner stops at the block, so the caller becomes the parent and the stage subagents stay one level deep.

## Why retries carry "Tried and abandoned"

A retry that only sees the failure excerpt tends to walk back into the approach that just failed. The discarded approaches exist nowhere else — not in the code, not in the plan — so the red subagent returns them and the parent passes them into the retry.

## Why parallel work, serial integration

Stages in flight never see each other's code, so the green each one reports was measured against a `HEAD` that is no longer current. Green-to-green holds only if it is measured where the code finally lands: the parent cherry-picks one stage at a time onto the main tree and re-runs that stage's proofs plus every global gate there. Disjoint file lists make the pick conflict-free; the re-run catches what file lists cannot — two stages that edit different files but break each other. A pick that goes red is dropped with `git reset --keep HEAD~1` and the stage retries from the new `HEAD`, so the main tree only ever holds integrated, green commits.

## Why the worktree path is appended to the prompt

The hand-off carries the absolute repo root. A subagent running in a worktree that follows it literally edits the main tree — under the parent's feet and outside its own branch. The `Working directory:` line rebinds the root for that stage; the `MAY NOT write outside your working tree` rule backs it.

## Why worktree setup and shared runtime are declared

A fresh worktree holds only tracked files: no installed dependencies, no untracked env file, no local database. The setup command makes a worktree able to run the gates. Two stages in flight also share the machine: proofs that bind the same port or open the same database file collide and fail in ways neither stage caused. Declaring them at plan time lets each worktree take its own port and database path from env.

## Why a shared file implies a dependency

A stage that edits a file another stage also edits reads what that stage wrote, whatever `Depends on:` claims. An undeclared edge makes the red-stage message lie: it offers the user a stage to run that sits on top of the broken one. `assert_stage_graph` rejects the pair; that same guarantee is what lets two ready stages run in parallel without conflicting. The waves it prints show how much of the plan runs side by side — a widest wave of 1 on a plan with independent backlog items usually means a hotspot the decomposition left shared.

## Why each reader gets one read

A reader that takes its instructions in fragments holds them in fragments. Measured on 2026-10-30, one call of Claude Code's Read tool returns at most 25,000 tokens (a file over 256 KB is refused outright), and Rust, TypeScript, and plan markdown all ran at ~2.5 bytes per token. The 33-stage plan that shaped these rules was ~117k tokens: neither its parent nor any stage could read its instructions whole. Its stage subagent assembled them from a grep and five offset reads, one of them the parent's own Execution model.

So the plan is split by reader, not by section. The parent's part — everything above `## Stages` — is one read; on that plan, rebuilt in this layout, it measures ~22k tokens. Each stage gets a **brief**, generated at launch: the rendered prompt, its stage block, and the sections it works under, and nothing of the parent's. That plan's largest brief measures ~12k tokens, 282 lines, read whole in one call. The gate fails either reader's document past 25k and warns past 20k. The plan stays the single source; a brief is never edited, and each launch writes its own file in `logs/` — a retry does not overwrite the first attempt — so it is the record of what that attempt was handed — which matters once the `edit` checkpoint changes the plan mid-run.

The prompt itself is the same text for every stage but three fields. Stored once per stage, it was a third of that plan (95 KB of 284); one template plus a renderer in the vendored `_verify.py` keeps it single and lets the plan run without the skill.

## Why the parent keeps a run log

The conversation that drives a run is not durable: a compaction replaces it with a summary, a crash ends it. What is in flight — tree, branch, the executor's handle for each subagent, the last integrated SHA — has to survive both, so it lives in `logs/<slug>-run.md`, and the parent reads that file, not its memory of the run, before acting after any break.

## Why a stall window

A subagent can end without a return, and a parent that only waits for the return waits forever. In the run that set this rule, the parent's idle conversation was compacted while a stage ran in the background; a minute later the stage subagent went silent mid-command, no completion ever arrived, and ninety minutes on the parent still reported the stage as working. Activity is observable from outside — the executor's record of the subagent and the stage's tree — and 20 minutes is longer than any single command an executor runs in the foreground, so silence past it is not a long gate. The check needs something to wake the parent: a parent idle between notifications is woken only by an event, and a dead subagent sends none — hence the armed wake-up.

## Why stage size is a gate

The ~100k bound existed as advice and a 33-stage plan shipped with ten stages past it; the one at ~109k grew to ~309k tokens of context before it died. A bound the gate enforces is a bound the plan keeps. Those sizes were counted at 4 bytes per token; at the measured ~2.5, the same stage reads ~174k, so the formula now divides by 2.5 and the bounds mean what they say.

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
- **Subagent summaries in the run log:** a `Stop` hook appending each subagent's final message to `logs/<plan-slug>-run.md`, beside the parent's events.
