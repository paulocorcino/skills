---
name: staged-plan
description: Design a self-contained multi-stage plan for autonomous (default) or semi-autonomous execution, where each stage runs as a subagent in its own context window, gated green-to-green between stages. The plan is the operational contract - it declares working-tree policy, executor adapter, optional reviewer gate, retry rule, and per-stage hand-offs. Use when the user wants a large track subdivided into independently-executable, contextually-isolated stages with minimal intervention. Typical invocations - "staged plan", "autonomous execution", "run stages in subagents", "plan in stages", "each stage in a fresh window", "semi-autonomous staged plan".
---

# Staged Plan

A pattern for executing large tracks as a chain of autonomous subagents, each in its own fresh context window, with the parent gating green-to-green. The plan markdown is **the operational contract** — anyone (or any executor) opening it cold should be able to run it correctly.

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

Enter plan mode first (`EnterPlanMode`) if not already active.

**Investigation discipline (mandatory before writing the plan):** read every file that will appear in the cross-stage `## Critical files` index **end-to-end**, not just grep snippets. Plans built from excerpts produce stages with stale line numbers, missed callers, and hidden dependencies. If a file is too large to read fully, that's a signal the stage decomposition is wrong — split further.

**Fixed defaults — do NOT prompt the user for these:**

1. **Mode:** `autonomous` — stages run end-to-end with no pause between them.
2. **Commit authorization:** `per-stage-direct` — each subagent commits after green gates.
3. **Failure handling:** `auto-retry-up-to-2` — re-launch the stage with the failure excerpt, max 2 retries, then pause. Scope violations never auto-retry.
4. **Working-tree policy:** `clean-required` if `git status` is clean (the common case).
5. **Reviewer gate:** `none` unless risk signals trigger an auto-recommendation (see below).

These defaults must be recorded verbatim under `## Execution policy` in every plan. Only deviate from them if the user explicitly overrides in the current conversation.

**The one allowed question:** when `git status` is **not clean** at plan time, the working-tree policy cannot be defaulted safely. Briefly summarize the dirty state and ask Paulo to choose between `stash-authorized`, `integrate-existing`, or `abort-until-clean` (see Working-tree policy below). Single question, not a menu of unrelated decisions.

**Auto-recommend reviewer gate** (write the recommendation directly into the plan; user can edit before `ExitPlanMode`):
- `reviewer: deep` recommended when ≥2 of: ≥5 stages, public/cross-repo contract change, Docker/CI changes, auth or data migration, multi-repo touch.
- `reviewer: light` recommended when exactly 1 of those signals is present.
- `reviewer: none` otherwise (default).

State the recommendation **with the reason** so Paulo can override in one edit:
```
Reviewer: deep — recommended by: 7 stages + public contract + multi-repo. Override with `Reviewer: none` to skip.
```

**Plan output location:** `<repo>/docs/plans/<plan-slug>.md` (inside the current git repo). Post-stage reports also go in `<repo>/docs/plans/` as `<plan-slug>-stage-{N}-report.md`. Fall back to `~/.claude/plans/` only when not inside a git repo. **Never** write to `<repo>/.claude/plans/` — that path triggers permission prompts for subagents and is deprecated.

**Scaffold first, then fill** (mandatory): once you have decided slug, title, and the list of stage titles, do NOT hand-write the markdown. Run the scaffold script — it deterministically renders ~60% of the plan (Execution model, Execution policy, Executor adapter, Stage 0, hand-off template per stage, End-to-end block, Reviewer gate when applicable) so you only edit the cognitive parts (per-stage scope, files, order of operations, hand-off specifics, Context, Alternatives, Open questions). This saves substantial output tokens per plan.

```bash
python3 ~/.claude/skills/staged-plan/lib/scaffold.py \
  --slug <plan-slug> \
  --title "<Plan Title>" \
  --stage "<Stage 1 title>" \
  --stage "<Stage 2 title>" \
  ... \
  --mode autonomous \
  --working-tree clean-required \
  --reviewer none \
  --include alternatives,open-questions \
  > <repo>/docs/plans/<plan-slug>.md
```

Flags:
- `--mode`: `autonomous` (default) or `semi-autonomous`.
- `--working-tree`: `clean-required` (default) | `stash-authorized` | `integrate-existing` | `abort-until-clean`. Match what you decided in the working-tree assessment.
- `--reviewer`: `none` (default) | `light` | `deep`. If non-`none`, also pass `--reviewer-reason "<short reason>"` so the recommendation is auditable.
- `--include`: comma-separated optional sections — `alternatives` (≥5 stages or multi-repo), `open-questions` (when planner has unresolved items).

After scaffolding, **edit** the file with the Edit tool to fill every `<FILL: ...>` placeholder with the stage-specific content. The scaffold is a starting point — modify freely. Do NOT re-run scaffold after editing; it will overwrite your work.

**At the end of Phase 1, always print** (so the IDE renders a clickable link):
```
Plan file: [<plan-slug>.md](/absolute/path/to/docs/plans/<plan-slug>.md#L1)
```

#### Plan structure

The plan must be **self-describing**: anyone opening the file in a fresh context window (without this skill loaded) should be able to execute it correctly. The `## Execution model` block is mandatory.

```
# <Track name> - Staged Execution Plan

## Execution model (READ FIRST)
Staged subagent execution (prompt chaining + gate checks). Do NOT run as one linear task.

1. Read this plan end-to-end.
2. Run Stage 0 (Pre-flight). If any gate is red on the baseline, abort.
3. For each Stage N >= 1, launch a fresh subagent (see `## Executor adapter`):
   - prompt: the verbatim Hand-off prompt block for that stage
   - description: the stage title
   - foreground, sequential, inherit model
4. On return, verify: build + gates clean, commit SHA present in `git log`,
   post-stage report written, scope respected (only declared files touched).
5. Green -> Mode handling:
   - autonomous: launch Stage N+1 immediately.
   - semi-autonomous: post the post-stage summary + `Resume? [y / edit / abort]`
     and wait. `y` -> launch Stage N+1; `edit` -> user adjusts the next
     hand-off then `y`; `abort` -> stop (committed work is preserved).
   Red -> apply the `## Execution policy` retry rule.
6. After the final stage, run `## End-to-end verification`, run the
   `## Reviewer gate` if not `none`, and emit the
   stage -> SHA -> report-path summary table.

Parent responsibilities (not delegable): launching stages in order, verifying
green between stages, running end-to-end verification, running the reviewer
gate if configured, producing the summary.

Resuming after a red stage: each hand-off prompt only assumes prior commits
exist in `git log`, not that they came from subagents. If Stage K was fixed
manually, relaunch Stage K+1 unchanged. Never re-run committed stages.

## Execution policy (fixed defaults unless user overrode)
- Mode: autonomous           # or: semi-autonomous
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2
- Working-tree policy: clean-required   # or: stash-authorized | integrate-existing | abort-until-clean
- Reviewer: none                        # or: light | deep — see `## Reviewer gate`

## Executor adapter
- **Claude Code**: use the `Agent` tool, one stage per subagent,
  `subagent_type: general-purpose`, foreground, omit `model`, omit `run_in_background`.
- **Codex / other executors**: execute each Hand-off prompt inline in a fresh context
  window, or via the executor's own delegated-agent mechanism if available.
  The plan does not depend on Claude-specific tooling beyond this section.

## Context
<Why this track. Constraints. Items in scope. Items out of scope / blocked externally.>

## Alternatives considered (optional - recommended for >=5 stages or multi-repo)
<1-2 stage decompositions that were rejected, with the reason. Helps the
reviewer (and future-you) understand why this shape over others.>

## Open questions (optional)
<Items the planner could not resolve from the codebase alone. Each item:
- Question.
- Default assumed (so execution can proceed if unanswered).
- Stage(s) affected.
If the user does not respond before `ExitPlanMode`, the defaults stand.>

## Global conventions
- Build gate: <cmd>
- Lint/test gates: <cmds>
- Invariants: <e.g. no GPL in main binary, vendor-neutral i18n, tracing only, English only>
- Commit style: one per stage; trailer `Co-Authored-By: <model> <noreply@anthropic.com>`
- Staging: only files the stage declares, by explicit path; never `git add -A`

## Stage 0 - Pre-flight (mandatory, no feature work, no commit)
Purpose: record baseline state, vendor verify primitives, apply the
working-tree policy so later failures cannot be blamed on prior repo state.
1. Capture `git status` and the current HEAD SHA in the post-stage report.
2. **Vendor verify primitives** (only if any stage uses verify scripts):
   if `<repo>/docs/plans/_verify.py` does not exist, copy it from
   `~/.claude/skills/staged-plan/lib/verify.py`. Commit it as part of Stage 0
   ONLY if the working-tree policy allows; otherwise leave untracked and let
   the first feature stage stage it alongside its own changes.
3. Apply the working-tree policy from `## Execution policy`:
   - clean-required: tree must be clean; if not, abort.
   - stash-authorized: `git stash push -u -m "staged-plan-<slug>-pre"`; record stash ref.
   - integrate-existing: leave changes in place; declare them in the report; subagents
     must not stage files they did not modify.
   - abort-until-clean: abort the plan; user resolves manually.
4. Run every gate (build, lint, tests, i18n, etc.) on the resulting baseline.
5. Red -> abort. Green -> proceed to Stage 1.

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
<If gates are >3 commands OR require grep of invariants OR reuse verify
primitives, generate `docs/plans/<plan-slug>-verify-stage-1.py` (Python 3
stdlib only, cross-platform) and call it here. The script imports primitives
from `<repo>/docs/plans/_verify.py` (vendored in Stage 0). Otherwise inline.>

**Manual verification (if any):** <user-side, deferred if agent can't execute>

**Post-stage report:** write `<repo>/docs/plans/<plan-slug>-stage-1-report.md`
with: files changed, gate results, commit SHA, deviations, surprises.
Do NOT write to `<repo>/.claude/plans/` - that path is deprecated.

**Hand-off prompt for Stage 1:**
> <SELF-CONTAINED prompt - see template below>

---

## Stage 2 - ...

---

## Reviewer gate (only if Reviewer != none)
After the final stage commits green:
- reviewer: light -> small subagent validates scope, diff vs. plan, gate
  results, post-stage reports, and obvious risk. Does NOT replan.
- reviewer: deep -> same plus security/perf/maintainability lens for
  stack-relevant best practices.
Reviewer returns one of: `pass`, `pass-with-notes`, `fail`, `blocked`.
Reviewer never edits code and never replans. On `fail`/`blocked`, stop and
surface to the user.
If a `reviewer` skill is available in the executor, prefer it; otherwise use
an inline QA prompt that takes the plan + diff range as input.

## Critical files (cross-stage index)
<table of file -> stages that touch it>

## End-to-end verification (after final stage)
<commands + manual smoke. If >3 commands OR invariants to grep, generate
`docs/plans/<plan-slug>-verify-e2e.py` (Python 3 stdlib, importing _verify).>
```

#### Stage sizing

- One logical deliverable per stage, 1-3 backlog items
- Order by blast radius: internal/pure-refactor first, public-API/UI last, external-blocked last
- Isolate externally-blocked work in its own trailing stage
- Target stage duration: 3-15 minutes of subagent wall time; if longer, split
- **Scope discipline over numeric budgets.** Token/tool-call counters are not exposed to the subagent at runtime, so numeric budgets cannot be mechanically enforced. Instead, rely on an **explicit file list per stage** and the anti-scope-expansion rule: the subagent must STOP and report if the stage appears to require files outside the list.

#### Working-tree policy details

The four states declared in `## Execution policy`:

- **`clean-required`** — `git status` must be empty. Default when tree is clean. Subagents may commit freely.
- **`stash-authorized`** — recommended when there are uncommitted changes **unrelated** to this track. Stage 0 stashes them; the final summary reminds the user to `git stash pop`.
- **`integrate-existing`** — recommended when current uncommitted changes **are part of this work** (e.g., user started something then asked for a staged plan to finish it). Stage 0 records them in the report. Subagents must stage only files THEY modify; existing dirty files are folded into the natural stage that owns them.
- **`abort-until-clean`** — when state is ambiguous and the user wants to resolve manually before any plan runs.

#### Verify-script trigger

Generate `docs/plans/<plan-slug>-verify-stage-N.py` (or `-verify-e2e.py`) when **any** condition holds:
- The stage has more than 3 gate commands.
- The stage requires `grep` of invariants (e.g., "no `import OldLib`", "no `console.log`", "i18n keys exist for every UI string").
- The stage benefits from the standard primitives (`assert_clean_tree`, `assert_commit_present`, `assert_only_files_touched`, `assert_report_exists`).

Otherwise keep gates inline in the markdown — script overhead is not justified for `bun test` + `bun run build`.

**Why Python, not bash:** scripts must run unchanged on Linux, macOS, and Windows native (no WSL/Git-Bash dependency). Python 3 stdlib is the cross-platform denominator and is available on every dev box.

**Vendoring:** the primitives live at `~/.claude/skills/staged-plan/lib/verify.py` (the canonical copy) and are vendored into each repo at `<repo>/docs/plans/_verify.py` during Stage 0. Generated stage scripts import from the vendored copy, so any executor (Claude, Codex, human dev) can run `python docs/plans/<slug>-verify-stage-N.py` without the skill being installed.

**Generated script shape:**
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _verify import V

V.assert_clean_tree()
V.assert_commit_present(r"^feat: add B-backed impl")
V.assert_only_files_touched(["src/y_v2.ts"], base_sha="HEAD~1")
V.run_gate("bun run build")
V.run_gate("bun test src/y_v2.test.ts")
V.assert_grep_zero(r"\bimport.*from ['\"]lib-a['\"]", ["src/"])
V.assert_report_exists("docs/plans/migration-x-stage-1-report.md")
sys.exit(V.summarize())
```

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

Working tree: per `## Execution policy` working-tree policy = `{policy}`.
- clean-required / stash-authorized: tree is clean at stage start; stage only
  files YOU modify, by explicit path; never `git add -A`.
- integrate-existing: pre-existing dirty files listed in Stage 0 report MAY be
  part of your declared file list; if so, stage them; otherwise leave untouched.

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

The Execution policy in the plan declares Mode, retry, working tree, and reviewer; the parent reads them and proceeds without further prompting (except for the semi-autonomous between-stage checkpoint).

1. **Launch each stage** per `## Executor adapter` in the plan:
   - Claude Code: `Agent` tool, `subagent_type: general-purpose`, `model` omitted, `run_in_background` omitted, `description` = stage title, `prompt` = the Hand-off prompt (optionally appended with runtime context such as current branch state).
   - Other executors: follow the adapter section.

2. **On completion, verify green:** build passed, gates clean, commit SHA in `git log`, post-stage report written, scope respected.
   - **autonomous**: green -> launch next stage immediately.
   - **semi-autonomous**: green -> post a structured checkpoint and wait:
     ```
     ✓ Stage N done — {sha} "{subject}"
     Files: {path} ({+adds} {-dels}), ...
     Gates: build ✓ test ✓ ...
     Report: docs/plans/<slug>-stage-N-report.md
     Next: Stage N+1 — {title} ({k files})

     Resume? [y / edit / abort]
     ```
     - `y` -> launch Stage N+1 unchanged.
     - `edit` -> user adjusts the next stage's Hand-off (e.g., adds a callsite found in this stage's report) before launching.
     - `abort` -> stop. Committed work is preserved.
   - Red (any mode) -> apply the retry rule.

3. **Retry rule (auto-retry mode only):**
   - Up to **2 auto-retries** per stage.
   - Each retry passes the prior run's failure excerpt back into the hand-off and narrows the instruction to "fix the reported failure only, within the same file list".
   - **No retry on:** scope violations (subagent touched files outside the list), pre-commit hook rejections, or attempts to bypass hooks. These are escalated immediately.
   - On exhaustion: stop, surface the failure chain to the user, wait.
   - If the plan says "pause on first red", skip retries entirely.

4. **After the final stage:**
   - Run the end-to-end verification block.
   - If `Reviewer: light` or `deep`, run the reviewer gate. On `fail` / `blocked`, stop and surface; do NOT replan automatically.
   - Emit the stage -> commit SHA -> status -> report-path table.
   - List any externally-blocked items still open, with reopen criteria.
   - If working-tree policy was `stash-authorized`, remind the user to `git stash pop` (or list the stash ref).

## Subagent trace / auditability

Each subagent leaves these durable traces:
- Git commits - one per stage; `git log` / `git diff` between commits
- Disk changes - file modifications persist
- Returned summary to the parent - surfaced to the user between stages
- Backlog status flips - versioned in `docs/backlog.md` or equivalent
- **Post-stage report** at `<repo>/docs/plans/<plan-slug>-stage-{N}-report.md` - **mandatory**. It is the only trace of surprises, deviations, and judgment calls that git alone does not capture; required so an autonomous run remains reviewable after the fact. Both plan and reports live under `docs/plans/` so they are versioned and reviewable in PRs. Do NOT use `<repo>/.claude/plans/` - deprecated.

## Optional hardening (per-plan, not baked in)

- **Hooks for gate enforcement** (`.claude/settings.json` PostToolUse / PreCommit). Prompt-level gates can be ignored by a confused subagent; hooks cannot. Configure via the `update-config` skill.
- **Reviewer gate** (see `## Reviewer gate` block in the plan template). Auto-recommended when risk signals trigger; otherwise opt-in.
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
- **Do NOT** prompt the user for a menu of execution policy choices - defaults are fixed; the only allowed planning question is the working-tree policy when `git status` is dirty
- **Do NOT** let the reviewer gate replan or edit code - it returns a verdict only

## Minimal example

```
# Migration X - Staged Execution Plan

## Execution model (READ FIRST)
Staged subagent execution. One subagent per stage via the executor adapter, in
order, foreground, inherited model. Verify green (build + commit SHA) between
stages.

## Execution policy
- Mode: autonomous
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2
- Working-tree policy: clean-required
- Reviewer: none

## Executor adapter
- Claude Code: `Agent` tool, `subagent_type: general-purpose`, foreground.
- Codex: execute each Hand-off prompt inline in a fresh context.

## Context
Migrate module Y from lib A to lib B. 7 files, 3 public callsites.

## Global conventions
- Build: `<cmd>`
- Tests: `<cmd>`
- Commit style: one per stage, trailer Co-Authored-By.
- Staging: explicit paths only.

## Stage 0 - Pre-flight
Record HEAD + git status. Vendor `_verify.py` from skill lib if absent.
Apply clean-required policy. Run build + tests on HEAD; abort if red.

## Stage 1 - Add B-backed implementation alongside A
**Files:** `src/y_v2.ext` (new)
**Order:** add file, export, build, commit.
**Hand-off for Stage 1:** <self-contained prompt>

## Stage 2 - Port callsites
**Files:** `src/caller1.ext`, `src/caller2.ext`, `src/caller3.ext`
**Order:** swap imports, build, tests, commit.
**Hand-off for Stage 2:** <self-contained prompt>

## Stage 3 - Remove A-backed implementation
**Files:** `src/y.ext` (delete), `Cargo.toml` / `package.json` (drop dep)
**Order:** delete, remove dep, build, `grep "<A>"` returns zero, commit.

## End-to-end verification
Full test suite; grep for residual references to A.
```
