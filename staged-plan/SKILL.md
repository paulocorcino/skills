---
name: staged-plan
description: Design a self-contained multi-stage plan whose markdown is the operational contract — every execution detail (Execution model, Hand-off conventions, retry rule, working-tree policy, reviewer gate, pre-execution placeholder gate) is encoded in the plan file itself. This is a PLANNING skill: it produces a plan and stops. Use when the user wants to design, scaffold, or decompose work into a staged subagent track. Typical invocations - "design a staged plan", "decompose this into stages", "scaffold a multi-stage plan", "plan in stages", "create a staged execution plan". Do NOT invoke during Phase 2 execution — the plan markdown is self-sufficient and re-invoking the skill is redundant.
---

# Staged Plan

A pattern for executing large tracks as a chain of autonomous subagents, each in its own fresh context window, with the parent gating green-to-green. The plan markdown is **the operational contract** — anyone (or any executor) opening it cold should be able to run it correctly.

## Skill scope — planning only

This skill produces a plan. It does **not** execute code changes, run stages, or modify source files. Even when invoked outside plan mode, behave as a planner: investigate the codebase (read-only), design stages, run the scaffold, fill the markdown, optionally make the Phase 1.5 landing commit (plan + verify scripts + `.gitignore` rule only — no feature work). Stop there. Phase 2 is driven by the plan markdown, not by re-invoking this skill.

If the user asks to "execute the plan" or "run Stage N" while this skill is active, the answer is: the plan file already contains the Execution model and hand-off prompts needed; the user (or another agent) follows the plan directly. Do not start launching subagents from inside this skill.

## Pattern taxonomy

This is **prompt chaining with sectioning + gate checks** in Anthropic's effective-agents taxonomy — NOT orchestrator-workers. Subtasks are pre-planned, run strictly sequentially, and each gate must pass before advancing. Choose this when the decomposition is knowable at plan time (typical for coding tracks). Cost scales roughly linearly with stage count; justified when a single session can't carry the track or contextual isolation between stages materially improves quality.

## When this applies

- User asks to **design** a staged plan, **decompose** a track into subagent stages, or **scaffold** a multi-stage execution plan
- A track is too large for one session but splits cleanly into 3-7 independent deliverables
- Each stage benefits from contextual isolation
- The user has pre-authorized commits (or wants gated commits between stages)

## When NOT to use

- Track fits comfortably in one session — execute inline
- Subtask shape is unknowable until runtime — use orchestrator-workers
- No meaningful gates between steps — the green-to-green audit is the main value
- **Phase 2 (execution) is already underway** — the plan markdown is the contract; do NOT re-invoke this skill to "remember" how to launch stages, verify green, or apply retries. Read the plan's `## Execution model` block instead.

## Two-phase workflow (overview)

| Phase | Owner | What happens |
|---|---|---|
| 1. Plan design | Planner (in plan mode) | Investigate, decide defaults, scaffold, fill, exit plan mode |
| 1.5. Plan landing commit | Planner | Commit plan + `_verify.py` + verify scripts + `.gitignore` rule |
| 2. Execution | Parent + subagents | Pre-execution gate, launch stages, verify green, retry, end-to-end + reviewer |

Detailed Phase 1.5 + Phase 2 mechanics: see `references/execution.md`.

## Phase 1 — Plan design (in plan mode)

Enter plan mode first (`EnterPlanMode`) if not already active.

**Investigation discipline (mandatory before writing the plan):** read every file that will appear in the cross-stage `## Critical files` index **end-to-end**, not just grep snippets. Plans built from excerpts produce stages with stale line numbers, missed callers, and hidden dependencies. If a file is too large to read fully, that's a signal the stage decomposition is wrong — split further.

### Fixed defaults — do NOT prompt the user for these

1. **Mode:** `autonomous` — stages run end-to-end with no pause between them.
2. **Commit authorization:** `per-stage-direct` — each subagent commits after green gates.
3. **Failure handling:** `auto-retry-up-to-2` — re-launch the stage with the failure excerpt, max 2 retries, then pause. Scope violations never auto-retry.
4. **Working-tree policy:** `clean-required` if `git status` is clean (the common case). Other states detailed in `references/working-tree.md`.
5. **Reviewer gate:** `none` unless risk signals trigger an auto-recommendation (see below).
6. **Report policy:** `committed` unless `.gitignore` already excludes report files (e.g., `*-report.md`, `docs/plans/*-report.md`), in which case use `gitignored`. Detect during investigation by inspecting `.gitignore`; do not ask the user.

These defaults must be recorded verbatim under `## Execution policy` in every plan. Only deviate if the user explicitly overrides in the current conversation.

### The one allowed question

When `git status` is **not clean** at plan time, the working-tree policy cannot be defaulted safely. Briefly summarize the dirty state and ask the user to choose between `stash-authorized`, `integrate-existing`, or `abort-until-clean` (see `references/working-tree.md`). Single question, not a menu of unrelated decisions.

### Auto-recommend reviewer gate

Write the recommendation directly into the plan; user can edit before `ExitPlanMode`.

- `reviewer: deep` — recommended when ≥2 of: ≥5 stages, public/cross-repo contract change, Docker/CI changes, auth or data migration, multi-repo touch.
- `reviewer: light` — recommended when exactly 1 of those signals is present.
- `reviewer: none` — otherwise (default).

State the recommendation **with the reason** so the user can override in one edit:

```
Reviewer: deep — recommended by: 7 stages + public contract + multi-repo. Override with `Reviewer: none` to skip.
```

### Plan output location

`<repo>/docs/plans/<plan-slug>.md` (inside the current git repo). Post-stage reports also go in `<repo>/docs/plans/` as `<plan-slug>-stage-{N}-report.md`. Fall back to `~/.claude/plans/` only when not inside a git repo.

**Legacy path migration:** `<repo>/.claude/plans/` is deprecated (it triggers permission prompts for subagents). If the repo already has plans there, `git mv` them to `<repo>/docs/plans/` as part of the Phase 1.5 landing commit (same commit that lands the new plan). New plans must never be written to `<repo>/.claude/plans/`.

### Scaffold first, then fill (mandatory)

Once you have decided slug, title, and the list of stage titles, do NOT hand-write the markdown. Run the scaffold script — it deterministically renders ~60% of the plan (Execution model, Execution policy, Executor adapter, Stage 0, hand-off template per stage, End-to-end block, Reviewer gate when applicable) so you only edit the cognitive parts (per-stage scope, files, order of operations, hand-off specifics, Context, Alternatives, Open questions).

```bash
python3 ~/.claude/skills/staged-plan/lib/scaffold.py \
  --slug <plan-slug> \
  --title "<Plan Title>" \
  --stage "<Stage 1 title>" \
  --stage "<Stage 2 title>" \
  ... \
  --output <repo>/docs/plans/<plan-slug>.md \
  --mode autonomous \
  --working-tree clean-required \
  --reviewer none \
  --report-policy committed
```

**Safety:** `--output` is required. The script refuses to overwrite an existing file (exit 3) unless `--force` is passed — this protects filled plans from accidental rescaffold.

Flags:
- `--mode`: `autonomous` (default) | `semi-autonomous`.
- `--working-tree`: `clean-required` (default) | `stash-authorized` | `integrate-existing` | `abort-until-clean`.
- `--reviewer`: `none` (default) | `light` | `deep`. If non-`none`, also pass `--reviewer-reason "<short reason>"`.
- `--report-policy`: `committed` (default) | `gitignored`. Decide during investigation by inspecting `.gitignore`; surface alongside reviewer in the recommendation block.

### After scaffolding — fill rules

1. Every `<FILL: ...>` placeholder must be replaced with real content before `ExitPlanMode`. No `<FILL>` survives in the final plan.
2. `<FILL-OR-DELETE: ...>` blocks — fill if you have content; delete the entire block if you don't. The planner decides, not the user:
   - `## Alternatives considered`: fill if you genuinely considered >1 stage decomposition; delete otherwise.
   - `## Open questions`: fill if items couldn't be resolved from the codebase; delete if fully determined. Runtime surprises are already handled by hand-off "STOP and report" + reviewer gate.

The scaffold is a starting point — modify freely. Do NOT re-run scaffold after editing; it will overwrite your work.

### End of Phase 1

Always print (so the IDE renders a clickable link):

```
Plan file: [<plan-slug>.md](/absolute/path/to/docs/plans/<plan-slug>.md#L1)
```

### Plan structure, hand-off prompt, verify scripts

- Full plan markdown skeleton + Stage 0 template + stage block layout: see `references/plan-structure.md`.
- Per-stage hand-off prompt template: see `references/handoff-template.md`.
- When to generate a verify script and what it looks like: see `references/verify-scripts.md`.
- A fully-filled minimal example: see `examples/migration-x.md`.

## Phase 1.5 — Plan landing commit

After `ExitPlanMode`, the **planner** (not a subagent) makes a single commit landing the plan + `_verify.py` + any verify scripts + the `.gitignore` rule for `docs/plans/logs/` (and `docs/plans/*-report.md` if report-policy is `gitignored`). Pre-check `.gitignore` first — full procedure in `references/execution.md`.

After the landing commit, working tree is clean and Phase 2 starts.

## Phase 2 — Execution

The Execution policy in the plan declares Mode, retry, working tree, and reviewer; the parent reads them and proceeds without further prompting (except the semi-autonomous between-stage checkpoint).

1. **Pre-execution gate:** run `assert_no_placeholders` against the plan file. If non-zero, abort and surface the offending lines — do NOT launch any stage.
2. **Launch each stage** per `## Executor adapter` in the plan.
3. **On completion, verify green** — autonomous: launch next; semi-autonomous: post checkpoint and wait `[y / edit / abort]`; red: apply retry rule.
4. **Retry:** up to 2 auto-retries; never on scope violations or hook bypasses.
5. **After final stage:** end-to-end verification, reviewer gate (if configured), summary table.

Full mechanics, retry exclusions, semi-autonomous checkpoint format: see `references/execution.md`.

## Subagent trace / auditability

Each subagent leaves these durable traces:
- Git commits — one per stage; `git log` / `git diff` between commits
- Disk changes — file modifications persist
- Returned summary to the parent — surfaced to the user between stages
- Backlog status flips — versioned in `docs/backlog.md` or equivalent
- **Post-stage report** at `<repo>/docs/plans/<plan-slug>-stage-{N}-report.md` — **mandatory**. The only trace of surprises, deviations, and judgment calls that git alone does not capture; required so an autonomous run remains reviewable after the fact. Both plan and reports live under `docs/plans/` so they are versioned and reviewable in PRs.

**Report structure:** subagents copy `docs/plans/_report-template.md` (landed by the Plan landing commit) as a starting point. The template has a `Commit: _filled by parent_` slot — subagents leave it as-is. The parent fills the canonical `stage → SHA` mapping in the End-to-end summary table.

## Optional hardening (per-plan, not baked in)

- **Hooks for gate enforcement** (`.claude/settings.json` PostToolUse / PreCommit). Prompt-level gates can be ignored by a confused subagent; hooks cannot. Configure via `update-config`.
- **Reviewer gate** — auto-recommended when risk signals trigger; otherwise opt-in.
- **Accumulated run log**: a `Stop` hook appending each subagent's summary into one `<repo>/docs/plans/<plan-slug>-run.md`.

## Anti-patterns

- **Do NOT** ask the subagent to plan — pass a fully-formed, executable stage description.
- **Do NOT** let hand-off prompts reference "the previous conversation" or prior-stage internals — they must stand alone.
- **Do NOT** batch multiple stages into one subagent — contextual isolation is the entire point.
- **Do NOT** retry a red stage **unboundedly or with the same prompt** — retries are capped by the Execution policy and each retry must narrow the instruction.
- **Do NOT** use `git add -A` / `git add .` in hand-off prompts — always explicit paths.
- **Do NOT** rely on literal line numbers from the plan when writing stages N>=2 — instruct "grep for symbols, line numbers have drifted".
- **Do NOT** override the subagent model unless the user explicitly asks — inherit from parent by omitting `model`.
- **Do NOT** allow stages to spawn their own subagents — nested `Agent` calls defeat contextual isolation and the green-to-green audit.
- **Do NOT** prompt the user for a menu of execution policy choices — defaults are fixed; the only allowed planning question is the working-tree policy when `git status` is dirty.
- **Do NOT** let the reviewer gate replan or edit code — it returns a verdict only.
