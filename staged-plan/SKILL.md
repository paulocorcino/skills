---
name: staged-plan
description: Design a multi-stage plan in plan mode where each stage executes autonomously as a subagent in its own context window, gated green-to-green between stages. Use when the user wants a large track subdivided into independently-executable, contextually-isolated stages with minimal intervention. Typical invocations - "staged plan", "autonomous execution", "run stages in subagents", "plan in stages", "each stage in a fresh window".
---

# Staged Plan

A pattern for executing large tracks as a chain of autonomous subagents, each in its own fresh context window, with the parent gating green-to-green.

## Pattern taxonomy

This is **prompt chaining with sectioning + gate checks** in Anthropic's effective-agents taxonomy - NOT orchestrator-workers. Subtasks are pre-planned (stages written up front), run strictly sequentially, and each gate must pass before advancing. Choose this when the decomposition is knowable at plan time (typical for coding tracks). Orchestrator-workers is for when subtask shape depends on runtime discovery.

Cost scales roughly linearly with stage count (each stage is a fresh subagent carrying its share of the track); far cheaper than dynamic multi-agent orchestration. Justified when a single session can't carry the track or contextual isolation between stages materially improves quality.

## When this applies

- User asks for "staged", "autonomous", "fresh context per stage", "subagent chain", or similar
- A track is too large for one session but splits cleanly into 3-7 independent deliverables
- Each stage benefits from contextual isolation
- The user has pre-authorized commits (or wants gated commits between stages)

## When NOT to use

- Track fits comfortably in one session - execute inline
- Subtask shape is unknowable until runtime - use orchestrator-workers
- No meaningful gates between steps - the green-to-green audit is the main value

## Two-phase workflow

### Phase 1 - Plan design (in plan mode)

Enter plan mode first (`EnterPlanMode`) if not already active. **Do NOT ask the user about commit authorization, failure handling, or pre-existing working-tree changes** - the policy defaults below are fixed and must be recorded verbatim under `## Execution policy` in every plan:

1. **Commit authorization:** `per-stage-direct` - each subagent commits after green gates. Autonomous end-to-end.
2. **Failure handling:** `auto-retry-up-to-2` - re-launch the stage with the failure excerpt as context, max 2 retries, then pause. Scope violations never auto-retry.
3. **Pre-existing working-tree changes:** `none` - assume `git status` is clean (verified in Stage 0). Subagents may commit freely.

Only deviate from these defaults if the user explicitly overrides them in the current conversation; otherwise do not prompt.

Produce the plan as markdown at `<repo>/docs/plans/<plan-slug>.md` (inside the current git repo). Post-stage reports also go in `<repo>/docs/plans/` as `<plan-slug>-stage-{N}-report.md`. Fall back to `~/.claude/plans/` only when not inside a git repo. **Never** write to `<repo>/.claude/plans/` or `<repo>/.claude/plans/reports/` - that path triggers permission prompts for subagents and is deprecated for this skill. Every stage MUST contain a self-contained hand-off prompt - the subagent executing it will NOT see this conversation.

#### Plan structure

The plan must be **self-describing**: anyone opening the file in a fresh context window (without this skill loaded) should be able to execute it correctly. The `## Execution model` block is mandatory.

```
# <Track name> - Staged Execution Plan

## Execution model (READ FIRST)
Staged subagent execution (prompt chaining + gate checks). Do NOT run as one linear task.

1. Read this plan end-to-end.
2. Run Stage 0 (Pre-flight). If any gate is red on the baseline, abort.
3. For each Stage N >= 1, launch a fresh subagent via the `Agent` tool:
   - subagent_type: general-purpose (unless stage specifies otherwise)
   - prompt: the verbatim Hand-off prompt block for that stage
   - model: OMIT (inherit from parent)
   - run_in_background: OMIT (stages are sequential; parent must wait)
   - description: the stage title
4. On return, verify: build + gates clean, commit SHA present in `git log`,
   post-stage report written, scope respected (only declared files touched).
5. Green -> launch Stage N+1. Red -> apply the `## Execution policy` retry rule.
6. After the final stage, run `## End-to-end verification` and emit the
   stage -> SHA -> report-path summary table.

Parent responsibilities (not delegable): launching stages in order, verifying
green between stages, running end-to-end verification, producing the summary.

Resuming after a red stage: each hand-off prompt only assumes prior commits
exist in `git log`, not that they came from subagents. If Stage K was fixed
manually, relaunch Stage K+1 unchanged. Never re-run committed stages.

## Execution policy (fixed defaults - do not prompt the user)
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2
- Pre-existing working-tree changes: none

## Context
<Why this track. Constraints. Items in scope. Items out of scope / blocked externally.>

## Global conventions
- Build gate: <cmd>
- Lint/test gates: <cmds>
- Invariants: <e.g. no GPL in main binary, vendor-neutral i18n, tracing only, English only>
- Commit style: one per stage; trailer `Co-Authored-By: <model> <noreply@anthropic.com>`
- Staging: only files the stage declares, by explicit path; never `git add -A`

## Stage 0 - Pre-flight (mandatory, no commit)
Purpose: clean-slate baseline so later failures cannot be blamed on prior repo state.
1. `git status` - working tree clean or accounted for by Execution policy.
2. Run every gate (build, lint, tests, i18n, etc.) on current HEAD.
3. Red -> abort the plan. Green -> proceed to Stage 1.

## Stage 1 - <title>
**Items:** <atomic IDs>
**Scope:** <one sentence>
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

**Files:**
- `<path>` - <what changes and why>

**Order of operations:**
1. ...
<last>. Gates pass -> commit.

**Verification:** <per-stage commands + expected outcomes>

**Manual verification (if any):** <user-side, deferred if agent can't execute>

**Post-stage report:** write `<repo>/docs/plans/<plan-slug>-stage-1-report.md`
with: files changed, gate results, commit SHA, deviations, surprises.
Do NOT write to `<repo>/.claude/plans/` - that path is deprecated.

**Hand-off prompt for Stage 2:**
> <SELF-CONTAINED prompt - see template below>

---

## Stage 2 - ...

---

## Critical files (cross-stage index)
<table of file -> stages that touch it>

## End-to-end verification (after final stage)
<commands + manual smoke>
```

#### Stage sizing

- One logical deliverable per stage, 1-3 backlog items
- Order by blast radius: internal/pure-refactor first, public-API/UI last, external-blocked last
- Isolate externally-blocked work in its own trailing stage
- Target stage duration: 3-15 minutes of subagent wall time; if longer, split
- **Scope discipline over numeric budgets.** Token/tool-call counters are not exposed to the subagent at runtime, so numeric budgets cannot be mechanically enforced. Instead, rely on an **explicit file list per stage** and the anti-scope-expansion rule: the subagent must STOP and report if the stage appears to require files outside the list.

#### Hand-off prompt template

Each stage's hand-off prompt MUST include the following. Replace `{placeholders}`; keep the structure.

```
You are executing Stage {N} of {plan title} at {absolute plan path}.
Read that plan file first, then read {repo}/CLAUDE.md for repo-wide rules.

Repo root: {absolute path}
Branch: {branch}
Platform: {os}  (Windows: use bash syntax, forward slashes)

Status: Stages 1..{N-1} committed:
- `{sha1}` - {subject1}
- `{sha2}` - {subject2}
Confirm with: `git log --oneline -{N-1}` (where the integer is the count of
prior stages, not the current stage number).

Line-number hints in the plan may be stale after prior stages; grep for symbols.

Your scope: Stage {N} only - {title}. Items: {IDs}.

Critical rules (from CLAUDE.md):
- Build check: {cmd}
- Other gates: {list}
- Invariants: {logging, i18n, vendor-neutrality, English-only, etc.}

Working tree: if the branch has pre-existing uncommitted changes UNRELATED
to this track, do NOT stage, touch, or commit them. Stage only files YOU
modify for Stage {N}, by explicit path. Never `git add -A`.

Files to modify:
1. `{path}` - {intent}
...

Order of operations:
1. ...
{last}. Gates pass -> stage files -> commit with HEREDOC + Co-Authored-By.

Authorization:
- MAY commit directly after all verifications pass.
- MAY NOT push.
- MAY NOT modify files outside the list above.
- MAY NOT touch pre-existing unrelated working-tree edits.
- MAY NOT skip gates or use --no-verify / bypass hooks.
- MAY NOT spawn nested subagents (no Agent calls inside this stage).

Scope discipline:
- If the stage appears to require files outside the declared list, STOP and
  report. Do NOT silently expand scope.
- If pre-existing test/build failure is unrelated to this stage, STOP and
  report. Do NOT fix it.

Failure protocol:
- Gate fails within declared scope -> fix within scope and re-run the gate.
- Any STOP condition above -> return to parent with a clear reason.

Return to parent:
- Per-file summary with actual grep-found locations.
- Gate results (pass/fail + snippets).
- Commit SHA + subject.
- Deviations from the plan, if any.
- Path to the post-stage report written to disk.

Begin now.
```

### Phase 2 - Execution (after ExitPlanMode)

The Execution policy in the plan uses fixed defaults (per-stage-direct / auto-retry-up-to-2 / none), so the parent proceeds without further prompting.

1. **Launch each stage via the `Agent` tool:**
   - `subagent_type`: `general-purpose` unless the plan overrides
   - `model`: OMIT (inherit from parent) unless the user explicitly chose a model
   - `run_in_background`: OMIT (foreground; stages are strictly sequential)
   - `description`: the stage title
   - `prompt`: the Hand-off prompt from the plan, optionally appended with runtime context (e.g., current branch state)

2. **On completion, verify green:** build passed, gates clean, commit SHA in `git log`, post-stage report written, scope respected.
   - Green -> launch next stage.
   - Red -> apply the retry rule from the plan's Execution policy (below).

3. **Retry rule (auto-retry mode only):**
   - Up to **2 auto-retries** per stage.
   - Each retry passes the prior run's failure excerpt back into the hand-off and narrows the instruction to "fix the reported failure only, within the same file list".
   - **No retry on:** scope violations (subagent touched files outside the list), pre-commit hook rejections, or attempts to bypass hooks. These are escalated immediately.
   - On exhaustion: stop, surface the failure chain to the user, wait.
   - If the plan says "pause on first red", skip retries entirely.

4. **After the final stage:**
   - Run the end-to-end verification block.
   - Emit the stage -> commit SHA -> status -> report-path table.
   - List any externally-blocked items still open, with reopen criteria.

## Subagent trace / auditability

Each subagent leaves these durable traces:
- Git commits - one per stage; `git log` / `git diff` between commits
- Disk changes - file modifications persist
- Returned summary to the parent - surfaced to the user between stages
- Backlog status flips - versioned in `docs/backlog.md` or equivalent
- **Post-stage report** at `<repo>/docs/plans/<plan-slug>-stage-{N}-report.md` - **mandatory**. It is the only trace of surprises, deviations, and judgment calls that git alone does not capture; required so an autonomous run remains reviewable after the fact. Both plan and reports live under `docs/plans/` so they are versioned and reviewable in PRs. Do NOT use `<repo>/.claude/plans/` - deprecated.

## Optional hardening (per-plan, not baked in)

- **Hooks for gate enforcement** (`.claude/settings.json` PostToolUse / PreCommit). Prompt-level gates can be ignored by a confused subagent; hooks cannot. Configure via the `update-config` skill.
- **Evaluator stage** between high-risk stages: a second subagent diff-reviews the prior commit against the plan criteria and returns pass/fail. Buys audit coverage that an absent user cannot provide.
- **Accumulated run log**: a `Stop` hook appending each subagent's summary into one `<repo>/docs/plans/<plan-slug>-run.md`. One file to skim, instead of N reports.

## Anti-patterns

- **Do NOT** ask the subagent to plan - pass a fully-formed, executable stage description
- **Do NOT** let hand-off prompts reference "the previous conversation" or prior-stage internals - they must stand alone
- **Do NOT** batch multiple stages into one subagent - contextual isolation is the entire point
- **Do NOT** retry a red stage **unboundedly or with the same prompt** - retries are capped by the Execution policy and each retry must narrow the instruction
- **Do NOT** use `git add -A` / `git add .` in hand-off prompts - always explicit paths
- **Do NOT** rely on literal line numbers from the plan when writing stages N>=2 - instruct "grep for symbols, line numbers have drifted"
- **Do NOT** override the subagent model unless the user explicitly asks - inherit from parent by omitting `model`
- **Do NOT** allow stages to spawn their own subagents - nested `Agent` calls defeat contextual isolation and the green-to-green audit

## Minimal example

```
# Migration X - Staged Execution Plan

## Execution model (READ FIRST)
Staged subagent execution. One subagent per stage via `Agent` tool, in order,
foreground, inherited model. Verify green (build + commit SHA) between stages.

## Execution policy
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2
- Pre-existing working-tree changes: none

## Context
Migrate module Y from lib A to lib B. 7 files, 3 public callsites.

## Global conventions
- Build: `<cmd>`
- Tests: `<cmd>`
- Commit style: one per stage, trailer Co-Authored-By.
- Staging: explicit paths only.

## Stage 0 - Pre-flight
Run build + tests on HEAD; abort if red.

## Stage 1 - Add B-backed implementation alongside A
**Files:** `src/y_v2.ext` (new)
**Order:** add file, export, build, commit.
**Hand-off for Stage 2:** <self-contained prompt>

## Stage 2 - Port callsites
**Files:** `src/caller1.ext`, `src/caller2.ext`, `src/caller3.ext`
**Order:** swap imports, build, tests, commit.
**Hand-off for Stage 3:** <self-contained prompt>

## Stage 3 - Remove A-backed implementation
**Files:** `src/y.ext` (delete), `Cargo.toml` / `package.json` (drop dep)
**Order:** delete, remove dep, build, `grep "<A>"` returns zero, commit.

## End-to-end verification
Full test suite; grep for residual references to A.
```
