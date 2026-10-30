#!/usr/bin/env python3
"""Scaffold a staged-plan markdown with all boilerplate blocks pre-rendered.

Usage:
    python scaffold.py --slug <slug> --title "<plan title>" \
        --stage "Stage 1 title" --stage "Stage 2 title" ... \
        --output <repo-root>/<plan-dir>/<slug>.md \
        [--mode autonomous|semi-autonomous] \
        [--working-tree clean-required|stash-authorized|integrate-existing|abort-until-clean] \
        [--reviewer none|light|deep] \
        [--reviewer-reason "<why this level>"] \
        [--report-policy committed|gitignored] \
        [--force]

`--output` may point to ANY path inside a git repo. The canonical convention
is `<repo-root>/docs/plans/<slug>.md`, but harness integrations (e.g.
`backlog-claude-runner`) may direct the plan to a different in-repo dir
(`.agents/tmp/...`, `.agents/plans/...`, etc.). The scaffold derives the
plan directory from `--output` and substitutes it everywhere the boilerplate
references the plan dir — so verify scripts, report templates, and the Plan
landing commit advice stay consistent regardless of the chosen location.

The planner runs this BEFORE filling in stage-specific content. Output contains
all repeated boilerplate (Execution model, Execution policy, Executor adapter,
Hand-off conventions, the one hand-off template, Reviewer gate, Stage 0,
End-to-end verification) so the planner only edits the cognitive parts:
Context, Swept, One-way doors, Procedures, the template's plan-level slots, and
per stage the size, scope, files, order of operations, and checks with their
proofs. Nothing is rendered once per stage that every stage shares: the parent
renders each stage's prompt from the template at launch (`_verify.py handoff`).

This file is the single source of truth for the plan skeleton. The skill's
references describe how to fill it, never a copy of it.

Safety:
- --output is required (no stdout redirect, which can truncate an existing
  file before Python decides whether to error).
- --output must resolve inside a git repo (or pass --allow-outside-repo for
  the rare no-repo planning fallback).
- If --output already exists, the script aborts with exit 3 unless --force is
  passed. This protects filled plans from being silently overwritten.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import textwrap
from datetime import date
from pathlib import Path


EXECUTION_MODEL = """## Execution model (READ FIRST)
Staged subagent execution over a dependency graph: parallel work, serial
integration, gate checks at every integration. Do NOT run as one linear task.
Run it as written — each stage in its own fresh subagent, the reviewer gate
as configured — whoever the parent is (a person's session or an agent running
it for its caller). Whether staging pays off was settled when the plan was
approved; a track that looks small still runs this way.

0. **Pre-execution gate** (mandatory, before launching any stage). Run:
   ```
   python3 -B docs/plans/_verify.py gate docs/plans/{slug}.md
   ```
   (Use `python` where `python3` is absent, common on Windows.) It checks
   placeholders, the stage graph, one proof per check, stage sizes, that the
   parent's part and every brief fit one read, and that no line passes 160
   characters; it ends with the stage index. If non-zero, abort and surface the offending lines. Fix or delete
   the flagged blocks; do NOT bypass. `[WARN]` lines do not block.
1. **Parent** reads the plan down to `## Stages` in one read, plus the stage
   index the gate prints in step 0 — enough to schedule the graph. It reads a
   stage's block when it launches or integrates that stage. **Subagents** read
   one document: the brief their prompt names (step 3), never the plan.
   **Run log:** `docs/plans/logs/{slug}-run.md` is the parent's memory of the
   run. Append one line per event:
   ```
   python3 -B docs/plans/_verify.py run-log docs/plans/{slug}.md <N> <event> "<detail>"
   ```
   Events: `launched` (tree, branch, brief path, and the executor's handle for the
   subagent — its id or output file), `returned`, `integrated` (SHA), `red`,
   `stalled`, `retry`, `halted`. After a compaction, a resume, or any doubt
   about what is in flight, read the run log and `git worktree list` before
   the next action; a conversation summary is not a source.
2. Run Stage 0 (Pre-flight) yourself — it is mechanical and needs no
   subagent. If any gate is red on the baseline, abort.
3. **Launch the frontier.** A stage is *ready* when every stage its
   `Depends on:` names is integrated green. Launch ready stages in plan order,
   never more in flight than `Concurrency` (`## Execution policy`), each as a
   fresh subagent (see `## Executor adapter`), and log `launched`:
   - prompt: the one line printed by
     `python3 -B docs/plans/_verify.py brief docs/plans/{slug}.md <N>`, passed
     verbatim. The command writes the stage's brief (`## Hand-off prompt`
     filled, the stage block, the plan sections the stage works under) to
     `docs/plans/logs/{slug}-stage-<N>-brief.md` (a retry gets `-brief-2.md`, and
     so on: one record per attempt); the line tells the subagent to read it
     in one read
   - description: the stage title
   - `model` selected per Tier/Effort (see `## Executor adapter` mapping table)
   - **in place** (foreground, the main working tree) when it is the only
     stage in flight at launch; otherwise **isolated**: background, in its own
     worktree of the current `HEAD` on a branch of its own
     (`staged/{slug}/stage-N` when you create it; whatever name the
     executor's isolation option reports otherwise — record it). Run
     `## Global conventions` § Worktree setup there first, and write the
     brief with `--workdir <worktree path>`.
   Before the first isolated launch, when the worktrees live inside the repo
   (some executors place them there), add their directory to
   `.git/info/exclude` so the clean-tree checks keep meaning something.
   The gate in step 0 guarantees two ready stages never declare the same file:
   a shared file forces a dependency between them.
4. On each return, **integrate** — one stage at a time, in plan order among
   the stages that have returned:
   - isolated: `git cherry-pick <stage SHA>` onto the main working tree. A conflict means
     the stage touched a file outside its list: `git cherry-pick --abort` and
     treat it as a scope violation.
   - then verify **independently** at the integrated `HEAD` — the subagent's
     reported results are a claim, not evidence. Re-run the stage's proofs
     yourself — its verify script, or every `Proof:` of its `**Checks:**` list
     run as its own command, never folded into one file-level run — and
     confirm each named test appears in the output as run — a filter
     matching nothing exits 0 on several runners. Then: build + every gate of
     `## Global conventions` clean (this is what catches two stages that edit
     different files but break each other), commit present in `git log`,
     post-stage report written, scope respected (only declared files touched).
   - red after the stage reported green: `git reset --keep HEAD~1` drops the
     pick, then the retry rule applies, from the current `HEAD`.
   - green: log `integrated`, copy `docs/plans/logs/` (and the stage report,
     when the report policy is `gitignored`) from the worktree into the main
     tree, then `git worktree remove --force <dir>` and
     `git branch -D <stage branch>` (`-d` refuses: the cherry-picked commit
     has a different SHA).
   - **stalled:** a stage is running only while its record shows activity —
     the executor's handle (transcript or output file) or its tree
     (`git log`, `git status`) changed within the `Stall window` of
     `## Execution policy`. Check both before reporting a stage as running.
     A parent that ends its turn to wait keeps a wake-up armed — a background
     command that ends after the window (`sleep 1200`, or the executor's
     timer), re-armed at each wake — so a silent stage still wakes it. Once no
     stage is in flight, stop the wake-up: left running, it holds the session
     open until the window ends.
     Past the window with no return, the stage is stalled: log `stalled` with
     its tree's new commits and `git diff --stat`, stop the subagent if the
     executor can, and treat the stage as red. Its uncommitted edits go with
     its worktree. When its commits pass the stage's gates at their tip, the
     retry starts from that tip; otherwise from the current `HEAD`. The retry
     prompt carries the partial report and the diff stat as
     `Tried and abandoned`.
5. Green -> Mode handling:
   - autonomous: recompute the ready stages and launch them (step 3).
   - semi-autonomous: Concurrency is 1. Post the post-stage summary +
     `Resume? [y / edit / abort]` and wait. `y` -> launch the next ready
     stage; `edit` -> user adjusts the next stage's block (its brief is written from it at launch) then `y`; `abort` -> stop
     (committed work is preserved).
   Red -> log `red`, then apply the `## Execution policy` retry rule (log
   `retry` at each relaunch, `halted` when execution stops for a human). A red stage holds only
   the stages that descend from it through `Depends on:`; the others keep
   launching.
6. After the final stage, stop any wake-up still armed, run `## End-to-end verification`, run the
   `## Reviewer gate` if not `none`, and fill `## End-to-end summary` (the
   `Commit SHA` column is the integrated SHA). Commit the filled plan and the
   reviewer output together as the closing commit
   `docs(plans): close {slug} with end-to-end summary`, so the tree ends
   clean. Then list any externally-blocked items still open (with reopen criteria) and,
   if the working-tree policy was `stash-authorized`, remind the user to
   `git stash pop` (name the stash ref).

Parent responsibilities (not delegable): launching ready stages, integrating
them one at a time, verifying green at every integration, running end-to-end
verification, running the reviewer gate if configured, producing the summary.
The parent alone writes to the main working tree while isolated stages run.

Resuming after a red stage or a lost session: read the run log first. Each
hand-off prompt only assumes prior commits exist in `git log`, not that they
came from subagents. If Stage K was fixed manually, its dependents become
ready unchanged. Never re-run integrated stages; remove the leftover worktrees
and branches of unintegrated stages (`git worktree list`) before relaunching.

### Resource selection vocabulary (read before launching each stage)

Each stage declares `Tier:` (cognitive load) and `Effort:` (reasoning budget).
The executor at runtime maps these to the cheapest viable resource on its
platform that meets BOTH dimensions. The plan does NOT name models — that is
the executor's responsibility (it knows its own lineup and pricing).

**Tier:**
- `mechanical` — literal execution of a well-specified hand-off (rename, move,
  apply pattern from list). Smallest model that can follow the instruction.
- `standard` — typical coding within the declared file list, light judgment.
- `judgment` — scope decisions, semantic synthesis, non-obvious refactors.
- `critical` — security, public contract, data migration, irreversible changes.

**Effort:**
- `minimal` — no extended reasoning; cheapest setting.
- `standard` — default reasoning budget.
- `extended` — maximum reasoning budget the executor offers.

**Selection rule:** pick the cheapest model × reasoning combo on your platform
that meets or exceeds the declared Tier and Effort. Do NOT auto-promote on
retry — if a `mechanical` stage fails twice, the classification was wrong;
STOP and replan rather than silently escalating to a bigger model.

**Role defaults** (apply when not overridden by a stage block):
- Parent / orchestrator: `standard / standard`
- Stage 0 (pre-flight gates): `mechanical / minimal`
- Reviewer gate: `critical / extended`
- Stage N >= 1: declared per stage; absence defaults to `standard / standard`
"""

_PLAN_LANDING_COMMIT_HEADER = """## Plan landing commit (mandatory before Phase 2)
Before launching Stage 1, the planner (NOT a subagent) makes a single commit
that lands this plan and its support artifacts. This is plan setup, not
feature work — isolating it here keeps Stage 0 and Stage 1+ scope-clean.

**Pre-check (mandatory):** before staging anything, inspect `<repo>/.gitignore`.
The Plan landing commit assumes `docs/plans/` is **trackable**. Two cases:

- If `.gitignore` ignores `docs/plans/` wholesale (e.g. a `docs/plans/` line),
  **narrow the rule to ignore only generated artifacts**: replace that line
  with `docs/plans/logs/` and `docs/plans/__pycache__/`. The plan file,
  `_verify.py`, and verify scripts MUST be versioned; only gate logs and the
  bytecode cache Python writes when a script imports `_verify` are excluded.
  Do NOT use `git add -f` to bypass — the rule itself needs fixing.
- If `.gitignore` does not ignore `docs/plans/`, append `docs/plans/logs/`
  and `docs/plans/__pycache__/` where not already covered — the cache would
  otherwise dirty the tree on the first verify run and fail `clean-required`.
- If `.gitignore` ignores report files (e.g. `docs/plans/*-report.md`) while
  this plan's `Report policy` is `committed`, STOP: re-scaffold with
  `--report-policy gitignored`, or remove the pattern if reports should be
  versioned. A mismatch fails `clean-required` after the first stage.
"""

_REPORT_POLICY_NOTE_GITIGNORED = """
**Report policy: `gitignored`** — this plan was scaffolded with
`--report-policy gitignored`. The Plan landing commit MUST also ensure
`.gitignore` covers report files (e.g. `docs/plans/*-report.md`). If absent,
add the pattern as part of this commit; otherwise post-stage reports will
leave the working tree dirty and fail the `clean-required` policy. Reports
are local-only artifacts; the durable audit trail is the End-to-end summary
table emitted by the parent.
"""

_PLAN_LANDING_COMMIT_BODY = """
The landing commit MUST contain:
1. `<repo>/docs/plans/{slug}.md` — this plan file.
2. `<repo>/docs/plans/_verify.py` — vendored verify primitives, written by
   `scaffold.py` (a missing or older copy is replaced; stage it even when the
   only change is the refresh). Stage scripts import it via
   `sys.path.insert(0, 'docs/plans'); from _verify import V`.
3. `<repo>/docs/plans/_report-template.md` — scaffolded alongside the plan;
   subagents copy it as the starting structure for post-stage reports.
4. Any `<repo>/docs/plans/{slug}-verify-stage-N.py` and
   `<repo>/docs/plans/{slug}-verify-e2e.py` scripts the plan declares.
5. `<repo>/.gitignore` with the narrowed/added rule from the pre-check above
   (plus the report-ignoring pattern when report-policy = `gitignored`).

Suggested subject:
`chore(plans): land {slug} staged plan + verify scripts`

After this commit, working tree is clean and Phase 2 starts.

## Logs policy
Gate execution logs are written to `<repo>/docs/plans/logs/<prefix>-<ts>.log`
on every `run_gate()` call. They are **local evidence artifacts, not
versioned**: `docs/plans/logs/` is gitignored via the Plan landing commit.
{report_logs_note}

## Executor adapter

Each stage runs in a fresh context window via whatever delegated-agent
mechanism the executor provides. Claude Code: `Agent` tool with
`subagent_type: general-purpose`; an isolated stage adds `isolation: "worktree"`
and runs in the background — launch every ready stage in one message so they
run concurrently, and take the worktree path and branch from the tool's
result. Codex / others: the equivalent fresh-window mechanism plus
`git worktree add <dir> -b staged/<slug>/stage-N HEAD`. Record the worktree
path, branch, and the subagent's handle (Claude Code: the agent id and its
output file) in the run log at launch. An executor without
background delegation or without worktrees runs at Concurrency 1: in place,
one stage at a time, inline in a clean session if no delegate mechanism
exists.

**The parent's own context:** the parent holds the run for hours of background
stages. Where the executor compacts an idle conversation on its own, turn that
off for the run (Claude Code: `"idleCompaction": false` in `settings.json`).
After any compaction, the run log comes before the next action
(`## Execution model` step 1).

**Model & effort selection:** the plan declares `Tier:` and `Effort:` per stage
(see `## Execution model` § Resource selection vocabulary). The executor maps
those to its own model lineup, picking the cheapest viable combo. The plan
itself names no model — only the executor knows what's available and what it
costs.

**Mapping for Claude Code** (pass as `model` argument to the `Agent` tool):

| Tier / Effort | `model` |
|---|---|
| mechanical / minimal | `haiku` |
| mechanical / standard | `haiku` |
| standard / minimal | `sonnet` |
| standard / standard | `sonnet` |
| standard / extended | `sonnet` or `opus` |
| judgment / standard | `opus` |
| judgment / extended | `opus` |
| critical / * | `opus` |

Do NOT omit `model` (omission inherits the parent's model and defeats the
cost-tiering — every stage would silently run on the parent's model). For
Codex / other executors, apply the same vocabulary against their lineup.

Roles when no stage-level override is present:
- Parent / orchestrator: `standard / standard`
- Stage 0: `mechanical / minimal`
- Reviewer gate: `critical / extended`
- Stage N >= 1: as declared; default `standard / standard`
"""

_REPORT_LOGS_NOTE_COMMITTED = (
    "Reports (committed alongside each stage) capture the deviations and\n"
    "judgments needed for PR review; raw logs are kept locally for forensics."
)
_REPORT_LOGS_NOTE_GITIGNORED = (
    "Reports (local-only, gitignored) capture the deviations and judgments\n"
    "for the executor; the End-to-end summary table is the durable audit\n"
    "trail in the PR."
)


def render_plan_landing_commit(slug: str, report_policy: str) -> str:
    parts = [_PLAN_LANDING_COMMIT_HEADER]
    if report_policy == "gitignored":
        parts.append(_REPORT_POLICY_NOTE_GITIGNORED)
    logs_note = (
        _REPORT_LOGS_NOTE_GITIGNORED
        if report_policy == "gitignored"
        else _REPORT_LOGS_NOTE_COMMITTED
    )
    parts.append(_PLAN_LANDING_COMMIT_BODY.format(slug=slug, report_logs_note=logs_note))
    return "".join(parts)

_PARALLEL_CONVENTIONS = """\
- Worktree setup: <FILL: command an isolated stage runs once in its fresh worktree before any gate (e.g. `npm ci`),
  plus every untracked file the gates need and where it is copied from (never committed); `none` when the checkout alone suffices>
- Shared runtime: <FILL: ports, database files, containers or caches the proofs bind, and how two stages in flight
  avoid colliding (e.g. port and database path taken from env per worktree); `none` when no proof binds a shared resource>
"""


def render_global_conventions(slug: str, report_policy: str, concurrency: int = 1) -> str:
    body = _global_conventions_body(slug, report_policy)
    return body + _PARALLEL_CONVENTIONS if concurrency > 1 else body


def _global_conventions_body(slug: str, report_policy: str) -> str:
    if report_policy == "gitignored":
        return f"""## Global conventions
- Build gate: <FILL: cmd>
- Lint/test gates: <FILL: cmds>
- Invariants: <FILL: e.g. no GPL in main binary, vendor-neutral i18n, English only>
- Commit style: ONE commit per stage with **only the code changes**. The
  post-stage report is written locally and **NOT committed** (reports are
  gitignored in this repo per `--report-policy gitignored`). Trailer:
  `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL`
  (substituted by the executor at commit time, e.g.
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`).
- Reports: local-only artifacts under
  `docs/plans/{slug}-stage-{{N}}-report.md` (gitignored, not versioned).
  The `Commit:` slot in each report stays as `_filled by parent_`; the
  End-to-end summary table is the durable audit trail in the PR.
- Staging: only files the stage declares, by explicit path; never `git add -A`.
  The report file MUST NOT be staged.
"""
    return f"""## Global conventions
- Build gate: <FILL: cmd>
- Lint/test gates: <FILL: cmds>
- Invariants: <FILL: e.g. no GPL in main binary, vendor-neutral i18n, English only>
- Commit style: ONE commit per stage that includes BOTH the code changes AND
  the post-stage report file. The report is staged alongside code; there is
  no separate "report commit". Trailer:
  `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL`
  (substituted by the executor at commit time, e.g.
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`).
- Report content: do NOT include the stage's own commit SHA in the report
  body (impossible: the file is part of the commit). The parent emits the
  canonical stage->SHA mapping in the End-to-end summary table.
- Staging: only files the stage declares PLUS the stage's own
  `{slug}-stage-{{N}}-report.md`, by explicit path; never `git add -A`.
"""

STAGE_0 = """## Stage 0 - Pre-flight (mandatory, no feature work, no commit, no versioned report)
**Tier:** mechanical
**Effort:** minimal
Purpose: record baseline state and apply the working-tree policy so later
failures cannot be blamed on prior repo state. Plan support artifacts
(`_verify.py`, verify scripts, the plan file) are already committed via the
Plan landing commit before Phase 2 began.

**No versioned report:** Stage 0 must NOT write `{slug}-stage-0-report.md`
under `docs/plans/` — that would leave the working tree dirty and conflict
with `clean-required`. Baseline evidence goes to the gitignored logs dir;
the human-readable summary is returned to the parent.

1. Capture `git status` and the current HEAD SHA. Write them to
   `<repo>/docs/plans/logs/{slug}-stage-0-baseline.log` (gitignored) and
   return the same summary to the parent.
2. Apply the working-tree policy from `## Execution policy`:
   - clean-required: tree must be clean; if not, abort.
   - stash-authorized: `git stash push -u -m "staged-plan-{slug}-pre"`; record stash ref in the log + parent summary.
   - integrate-existing: leave changes in place; list them in the log + parent summary.
   - abort-until-clean: abort the plan; user resolves manually.
3. Run every gate (build, lint, tests, etc.) on the resulting baseline.
   `run_gate()` already writes its own per-command log under `docs/plans/logs/`.
4. Red -> abort. Green -> working tree must still be clean (or match the
   integrate-existing manifest); proceed to Stage 1.
"""

REVIEWER_GATE = """## Reviewer gate (only if Reviewer != none)
**Tier:** critical
**Effort:** extended
After the final stage commits green, the **parent** dispatches a fresh
reviewer subagent — never a stage subagent, never a child of one — over the
whole plan: diff range `<plan landing commit>..HEAD` and **every** check of
every stage block, whoever wrote them.
- reviewer: light -> accounts for every check: the proof ran green at `HEAD`
  and the assertion that settles it is located (`file:line` + the assertion
  expression, targeting the value the check names). A check without a located
  assertion counts as not proven. Plus scope, diff vs. plan, post-stage
  reports, `## Swept` / `## One-way doors` honoured, and obvious risk.
- reviewer: deep -> same plus a security/perf/maintainability lens for
  stack-relevant best practices, plus **fault injection**: in a scratch
  worktree (`git worktree add <scratch> HEAD`; never `git stash`), inject one
  behaviour-level fault per distinct assertion surface (flip a condition,
  change a returned value, shift a bound by one; cap 5), run the narrowest
  covering proof, confirm it FAILS, discard the scratch. A surviving mutant is
  a finding.

Reviewer returns a verdict in
`pass | pass-with-notes | fail | blocked`
plus a check table (check id, proof run, `file:line` evidence, result) and a
findings list (each: `file:line`, severity, description).
Reviewer never edits code and never replans.
If a `reviewer` skill is available in the executor, prefer it; otherwise use
an inline QA prompt that takes the plan + diff range as input.

### Arbiter (run only if findings list is non-empty)
**Tier:** critical / **Effort:** standard
Reads the reviewer verdict + findings + diff range. For each finding,
applies this decision tree verbatim:

1. Is this a real defect? (correctness, security, contract, data integrity)
   - No  -> classify `nice-to-have`.
   - Yes -> step 2.
2. Is the fix mechanical (one obvious right answer, no design choice)
   AND fully inside the plan's declared file list?
   - Yes -> classify `must-fix`.
   - No  -> classify `open`.

Arbiter records both answers per finding in the output md (auditable).
Arbiter does NOT edit code and does NOT replan.

### Fix round (run only if any `must-fix` exists; HARD MAX = 1 round)
**Tier:** standard / **Effort:** standard
Fix-subagent receives only the `must-fix` items + their target files.
- Applies fixes within those files only.
- For each item: writes a `fix note` -- what changed, line(s), and one
  sentence linking the change to the original finding.
- If a `must-fix` proves to require out-of-scope work or a design choice,
  reclassify it as `open` and skip it. Do NOT block sibling fixes.
After the round: re-run every declared gate (build/lint/test/etc.). Gate
failure does NOT trigger another fix round -- the failure goes into the
pending list and the verdict degrades.

### Re-review (conditional)
Run a second reviewer pass (same level: light/deep) only if EITHER:
- The plan's Tier was `critical`, OR
- The fix round modified files outside the declared scope of the
  originating `must-fix` finding (scope-creep signal).

Any *new* finding from re-review is resolved as below, in the next sequence
file. Re-review does NOT trigger another fix round.

### Resolve before escalating (parent)
Every `open` finding, and every question the reviewer leaves open, is the
parent's to answer first — the code, the plan, the repo's docs and git
history usually hold the answer. Record each answer with its evidence under
`## Resolved by the parent`; an answer that turns into a mechanical in-scope
fix is applied and re-gated like a fix-round item.
A finding reaches a human only when acting on it risks one of:
- a regression for someone who depends on today's behaviour;
- loss or corruption of data;
- a high-risk or irreversible change (security, public contract, migration);
- context nothing in the repo or plan provides.
Those become `human-required`, each naming its criterion. When unsure, the
cost of a wrong guess decides: one of the four above goes to the human,
anything cheaper to reverse stays with the parent.

### Output file (always written when this gate runs)
Path: `docs/plans/reports/<plan-slug>_reviewer_<seq>.md`
- `<seq>` is a zero-padded 3-digit counter starting at `001`, incremented
  for each run of this gate against the same plan.
- Each sequence file is **immutable** once written. Re-runs produce a
  new file, never overwrite.

Top of file: final verdict in
`pass | pass-with-notes | pass-with-fixes | pass-with-pending | fail | blocked`

Body sections (in order):
- `## Reviewer verdict` -- raw reviewer output, verbatim.
- `## Arbiter classification` -- table per finding: `file:line`, severity,
  class (must-fix / nice-to-have / open), decision-tree answers
  (defect? yes/no -- mechanical+in-scope? yes/no), 1-line reason.
- `## Fixes applied` -- one entry per `must-fix` corrected, with the fix
  note (what changed, lines, link to finding).
- `## Resolved by the parent` -- every `open` finding the parent answered:
  the question, the answer, its evidence (`file:line`, command + output),
  and what changed if anything.
- `## Pending` -- every `human-required` item. Each entry:
  - `file:line`
  - reviewer's original finding (short quote)
  - the criterion that needs a human (regression / data loss / high-risk /
    missing context) and what the parent already established
  - the decision the human is asked to make

Verdict mapping:
- `pass` / `pass-with-notes` -- reviewer's original verdict, no findings
  needed fixing.
- `pass-with-fixes` -- all `must-fix` corrected, no pending items.
- `pass-with-pending` -- corrections completed (or none needed), but
  `Pending` holds `human-required` items.
- `fail` / `blocked` -- reviewer's verdict was `fail`/`blocked`, OR gates
  failed after the fix round. Parent stops the plan and surfaces (to the
  user, or to its caller when it runs autonomously) the md
  file path to the user.
"""

SWEPT = """## Swept (requirements the source did not state)
Each theme resolves to the check ids that cover it, to `existing: <where the
code already enforces it>`, or to `not in scope — <why>`. Every theme gets an
answer; none is passed over in silence.
- validation: <FILL>
- failure modes: <FILL>
- idempotency / retry: <FILL>
- authorization: <FILL>
- concurrency / ordering: <FILL>
- data lifecycle: <FILL>
- external-dependency failure: <FILL>
- state transitions: <FILL>
- observability: <FILL>
"""

ONE_WAY_DOORS = """## One-way doors
Choices whose reversal costs more than a refactor: a persisted schema, a
contract someone else consumes, a new dependency, a data backfill, a pattern
the codebase does not have yet. Each row: the literal shape the next person
will copy, and the alternative rejected — named with the property that
disqualified it ("cannot express the next state", never "cleaner"). Stages
build to these rows; a stage that finds a new door records it in its report.

<FILL: table `| Door | Literal shape | Alternative rejected |` while rows fit 160 characters, else one list item per door;
or the single line `None — (why nothing in this track is hard to reverse)`>
"""

HANDOFF_CONVENTIONS = """## Hand-off conventions (apply to every stage)

**Authorization:**
- MAY commit directly after all verifications pass — on the worktree's
  branch when the prompt names a `Working directory:`.
- MAY NOT push.
- MAY NOT write outside your working tree — the worktree, when the prompt
  names one; the main working tree belongs to the parent while stages run in
  parallel.
- MAY NOT modify files outside the stage's declared file list.
- MAY NOT touch pre-existing unrelated working-tree edits.
- MAY NOT skip gates or use --no-verify / bypass hooks.
- MAY NOT spawn nested subagents (no Agent calls inside this stage).
- MAY NOT weaken an assertion, delete a test, or skip one to turn a gate
  green. The stage's `**Checks:**` are the bar you build under, fixed for the
  whole stage: if a check or an existing test is genuinely wrong, STOP and
  report.

**Checks and proofs:**
- Tests assert what the check says, never what the code happens to do —
  write each new proof from the check, not by reading the implementation.
- A proof that is a new test: write it first and watch it fail for the right
  reason (red), then implement until it passes.
- Every `Proof:` must be seen to run: the named test appears in the runner
  output as executed and passed, not just a green suite.
- Re-run a command only after the code changed since its last green run; a
  repeat on unchanged code adds no information.
- Wait for a long command with one foreground run whose timeout covers it, or
  with its completion notification. The parent reads a record silent past the
  stall window of the run (20 min by default) as a dead stage.

**Scope discipline:**
- If the stage appears to require files outside the declared list, STOP and
  report. Do NOT silently expand scope.
- If pre-existing test/build failure is unrelated to this stage, STOP and
  report. Do NOT fix it.
- Improvements noticed outside the stage: list them under `Noticed, not
  touched` in the report and leave the code as it is.

**One-way doors found mid-stage:** a hard-to-reverse choice the plan's
`## One-way doors` does not cover (persisted schema, a contract someone else
consumes, a new dependency, a pattern the codebase does not have yet) is
yours to decide: record it under `Decisions` in the report — literal shape +
the alternative rejected and the property that disqualified it — **before**
writing the code that closes it. A choice that contradicts a door the plan
already fixed is a STOP.

**Failure protocol:**
- Gate fails within declared scope -> fix within scope and re-run the gate.
- Any STOP condition above -> return to parent with a clear reason.
- Context compacted mid-stage -> re-read your stage block and `git diff`
  before continuing.

**Return to parent:**
- Per-file summary with actual grep-found locations.
- Check results: check id -> proof run -> pass/fail.
- Gate results (pass/fail + snippets).
- Commit SHA + subject.
- Deviations from the plan, if any.
- Tried and abandoned: approaches discarded and why (mandatory on a red
  return — the parent passes it into the retry so the next attempt starts
  past the dead ends).
- Path to the post-stage report written to disk.
"""

REPORT_TEMPLATE_CONTENT = """\
# Stage <N> — <title> — Post-stage report

**Backlog items:** <ids>
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** <plan-slug>.md

## Files changed
<!-- list each file with a brief description of the change -->

## Checks
<!-- one row per check in the stage block; every check gets a row -->
| Check | Proof run | Result |
|---|---|---|
| C<N>.1 | `<command>` — test seen in output | pass |

## Gate results
<!-- build: pass/fail, tests: pass/fail, lint: pass/fail, etc. -->

## Decisions
<!-- one-way doors decided during the stage, written BEFORE the code that
closes them: door | literal shape | alternative rejected (+ the property that
disqualified it). "None" if the stage closed no new door. -->

## Deviations from plan
<!-- any differences from the planned order of operations or file list -->

## Tried and abandoned
<!-- approaches tried and discarded, with the reason. Neither the code nor the
plan preserves these. "None" if nothing was abandoned. -->

## Noticed, not touched
<!-- improvements spotted outside the stage's scope; candidates for the backlog -->

## Surprises / notes
<!-- discoveries made during execution that may affect later stages -->
"""

HANDOFF_TEMPLATE = """## Hand-off prompt
One brief serves every stage. At launch the parent runs
`python3 -B docs/plans/_verify.py brief docs/plans/{slug}.md <N>` (plus
`--workdir` and the worktree path for an isolated stage). It writes the stage's
brief to `docs/plans/logs/` — this prompt with `{{N}}`, `{{TITLE}}` and
`{{ITEMS}}` filled, then the stage block, then the plan sections the stage works
under — and prints the one-line prompt the parent passes to the subagent.

<!-- BEGIN HANDOFF TEMPLATE -->
```text
You are executing Stage {{N}} of <FILL: plan title>.
This brief is your whole hand-off, in one document: this prompt, then your stage
block (your authoritative spec), then the sections of the plan
<FILL: absolute plan path> you work under, copied when you were launched. The plan
file itself is the parent's; everything you need from it is below. Then read the
repo's agent instruction files for repo-wide rules, whichever exist:
`<repo>/AGENTS.md`,
`<repo>/CLAUDE.md`,
or your executor's equivalent.

Repo root: <FILL: absolute path>
Branch: <FILL: branch>
Your working tree is `git rev-parse --show-toplevel` from where you start. When it
differs from the repo root above (or this prompt ends with a `Working directory:`
line), you are in an isolated worktree: that path replaces the repo root everywhere,
and you commit on the branch checked out there.
Platform: <FILL: os>  (Windows: use bash syntax, forward slashes)

Status: every stage your block's `Depends on:` names, and their own prerequisites,
is integrated green at your starting `HEAD` (`none`: you build on the plan landing
commit). Other stages may be integrated or still running elsewhere: build only on what
your dependencies wrote. Prior work is in `git log --oneline` and
`git show --stat <sha>`, in `Critical files` below, and, for a specific surprise or
deviation, in `docs/plans/{slug}-stage-K-report.md`. Git is the source of truth.
Line-number hints in the plan may be stale; grep for symbols.

Your scope: Stage {{N}} only - {{TITLE}}. Items: {{ITEMS}}.

Run your block's Order of operations; a step naming a procedure runs that recipe from
`Procedures` below on the input the step gives. Then every proof of its Checks and
every gate of `Global conventions` passes, and the commit step below closes the stage.
Authorization, scope, failure and return-to-parent: `Hand-off conventions` below.

{commit_step}

Begin now.
```
<!-- END HANDOFF TEMPLATE -->
"""

_COMMIT_STEP_COMMITTED = """\
Commit step: copy `docs/plans/_report-template.md` to
`docs/plans/{slug}-stage-{{N}}-report.md` and fill it (leave the `Commit:` slot as
`_filled by parent_`), then stage the code files AND the report together by explicit
path and commit with the `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer.
One commit per stage."""

_COMMIT_STEP_GITIGNORED = """\
Commit step: copy `docs/plans/_report-template.md` to
`docs/plans/{slug}-stage-{{N}}-report.md` and fill it (leave the `Commit:` slot as
`_filled by parent_`), then stage ONLY the code files by explicit path (the report is
gitignored and MUST NOT be staged) and commit with the
`Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage."""


def render_handoff_template(slug: str, report_policy: str) -> str:
    step = _COMMIT_STEP_GITIGNORED if report_policy == "gitignored" else _COMMIT_STEP_COMMITTED
    # `{{N}}` stays literal: `_verify.py brief` fills it per stage.
    return HANDOFF_TEMPLATE.replace("{commit_step}", step).replace("{slug}", slug)


PROCEDURES = """## Procedures
<FILL-OR-DELETE: recipes two or more stages share — one `### <name>` heading per recipe, then its numbered steps.
A stage's Order of operations names the recipe and the input it runs on (`1. Procedure <name> over the sites of <command>`)
and keeps only its own steps. Delete this block when no steps repeat across stages.>
"""


STAGES_HEADER = """## Stages
<!-- STAGES: the parent's one-pass read ends above. Each block below is read
when its stage is launched or integrated, and copied into that stage's brief. -->
"""


def render_stage(n: int, title: str, slug: str) -> str:
    # Left unfilled on purpose: a pre-filled previous stage anchors the
    # planner to a chain. `assert_stage_graph` validates the filled set; the
    # parent reads it to tell the user which stages a red stage does NOT block.
    depends_on = (
        "none" if n <= 1 else
        "<FILL: earlier stages this stage builds on, e.g. `Stage 1, Stage 3`; `none` when it builds only on the landing commit>"
    )

    return f"""<!-- BEGIN STAGE {n} -->
## Stage {n} - {title}
<!-- STAGE {n}: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE {n}: tier-rationale -->
**Tier rationale:** <FILL: 1-2 lines: the decision or risk that justifies this Tier/Effort; for mechanical work, say so>
<!-- STAGE {n}: size -->
**Size:** <FILL: ~Nk tokens = `wc -c` / 2.5 over the files this stage reads; a floor. The gate fails a stage past ~100k>
**Depends on:** {depends_on}
<!-- STAGE {n}: items -->
**Items:** <FILL: atomic IDs>
<!-- STAGE {n}: scope -->
**Scope:** <FILL: one sentence>

<!-- STAGE {n}: files -->
**Files:**
- `<FILL: path>` - <FILL: what changes and why>

<!-- STAGE {n}: order -->
**Order of operations:**
1. <FILL: this stage's own steps, up to its proofs; name a `## Procedures` recipe instead of repeating its steps>

<!-- STAGE {n}: checks -->
**Checks:**
- C{n}.1 — <FILL: claim> · Proof: `<FILL: specific test id or command>`
<FILL-OR-DELETE: replace with `Verify script: docs/plans/{slug}-verify-stage-{n}.py` when ANY of ≥4 distinct proof or
gate commands, ≥2 grep invariants, ≥2 `_verify` primitives (in doubt, generate it); delete it when the proofs stay inline
(see `references/verify-scripts.md`)>

<!-- STAGE {n}: manual -->
**Manual verification (if any):** <FILL or "none">
<!-- END STAGE {n} -->
---
"""


def _wrap_items(text: str, width: int = 100) -> str:
    """Wrap each over-long `- ` list item at `width`, continuing two spaces in.

    A plan's lines stay under the gate's width limit (`_verify.py`); the
    policy items are the boilerplate's one long-prose list.
    """
    out = []
    for line in text.split("\n"):
        if line.startswith("- ") and len(line) > width:
            out.extend(textwrap.wrap(line, width, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False))
        else:
            out.append(line)
    return "\n".join(out)


def render_execution_policy(mode: str, working_tree: str, reviewer: str, reviewer_reason: str, concurrency: int) -> str:
    if concurrency > 1:
        concurrency_line = (
            f"- Concurrency: {concurrency} — at most {concurrency} ready stages in flight; "
            "a stage alone in flight runs in place, the others each in an isolated worktree. "
            "Integration stays one stage at a time."
        )
    else:
        concurrency_line = "- Concurrency: 1 — one stage at a time, in place."
    reviewer_line = f"- Reviewer: {reviewer}"
    if reviewer != "none" and reviewer_reason:
        reviewer_line += f"  # {reviewer_reason}"
    mode_extra = ""
    if mode == "semi-autonomous":
        mode_extra = (
            "\n  Between-stage checkpoint posted by parent — format:\n"
            "    `✓ Stage N done — {sha} \"{subject}\" | Files: ... | Gates: build ✓ test ✓ ... | Report: {report path}`\n"
            "    `| Next: Stage K — {title} (next ready stage) | Resume? [y / edit / abort]`\n"
            "    `y` -> launch next; `edit` -> user adjusts the next stage's block; `abort` -> stop (committed work preserved)."
        )
    return _wrap_items(f"""## Execution policy (fixed defaults unless user overrode)
- Mode: {mode}{mode_extra}
{concurrency_line}
- Commit authorization: per-stage-direct (an isolated stage commits on its worktree branch; the parent cherry-picks it)
- On red: auto-retry-up-to-2 — cap of 2 retries; each retry passes the prior failure excerpt plus the subagent's `Tried and abandoned` list, and narrows the instruction to the same file list; an isolated retry starts from a fresh worktree of the current `HEAD`. NEVER retry on scope violations, pre-commit hook rejections, test-weakening, or hook bypass attempts (escalate immediately). Never promote the stage's Tier on retry: a `mechanical` stage failing twice means the classification was wrong — stop and replan. On exhaustion: stop launching the red stage's descendants, keep running and integrating the stages that do not descend from it, and surface once nothing else can run.
- Stall window: 20 min — longer than the longest single command an executor runs in the foreground; a stage whose record and tree stay unchanged past it is stalled (`## Execution model` step 4).
- Working-tree policy: {working_tree} — per-state behavior is described inline in `## Stage 0`.
{reviewer_line}
- Human-interaction stops: an escalation (scope violation, hook bypass, dirty tree, reviewer `fail`/`blocked`) launches nothing new — the stages in flight return and integrate, then execution halts; retry exhaustion halts once nothing else can run (see On red). Whenever execution halts awaiting a human decision (reviewer verdict `fail`/`blocked` after fix round; retry exhausted; scope violation / hook-bypass escalation; dirty-tree mid-run), the executor MUST send a push notification BEFORE yielding control (Claude Code: `PushNotification`; otherwise the executor's equivalent). Message format: `"Plan <slug>: <reason> — see <report-or-file path>"`, under ~120 chars. With no notification tool, print the same message inside a `<<HUMAN_REQUIRED>>` ... `<<END>>` block so an outer harness can grep for it; an autonomous parent (an agent running this plan for its own caller) ends its final message with that block, so the caller sees it. `pass-with-pending` is not a stop: the run completes, and the `human-required` items travel in the final message. Do NOT notify on normal between-stage transitions or successful completion.
""")


def scaffold(args: argparse.Namespace) -> str:
    parts: list[str] = []
    parts.append(f"# {args.title} - Staged Execution Plan\n")
    parts.append(f"<!-- scaffolded {date.today().isoformat()} via staged-plan/lib/scaffold.py -->\n")
    parts.append(EXECUTION_MODEL.replace("{slug}", args.slug))
    parts.append(render_execution_policy(args.mode, args.working_tree, args.reviewer, args.reviewer_reason, args.concurrency))
    parts.append(render_plan_landing_commit(args.slug, args.report_policy))
    parts.append(HANDOFF_CONVENTIONS)
    parts.append("## Context\n<FILL: why this track. Constraints. In scope. Out of scope / blocked externally.>\n")
    parts.append(SWEPT)
    parts.append(ONE_WAY_DOORS)

    parts.append("## Alternatives considered\n<FILL-OR-DELETE: 1-2 stage decompositions rejected, with reason. Delete this block if you only considered one decomposition.>\n")

    parts.append(render_global_conventions(args.slug, args.report_policy, args.concurrency))
    parts.append(PROCEDURES)
    parts.append(render_handoff_template(args.slug, args.report_policy))
    parts.append(STAGE_0.replace("{slug}", args.slug))

    if args.reviewer != "none":
        parts.append(REVIEWER_GATE.replace("<plan-slug>", args.slug))

    parts.append("## Critical files (cross-stage index)\n<FILL: table of file -> stages that touch it>\n")
    parts.append(f"""## End-to-end verification (after final stage)
<FILL: commands + manual smoke. If >3 commands OR invariants to grep,
generate `docs/plans/{args.slug}-verify-e2e.py` importing `_verify`.>

## End-to-end summary (parent fills after final stage)
| Stage | Title | Tier | Effort | Model used | Checks proven | Commit SHA | Status | Report |
|-------|-------|------|--------|------------|---------------|------------|--------|--------|
<!-- one row per stage. `Model used` is what the executor actually selected
on its platform for the declared Tier/Effort (the executor fills this — the
plan never prescribes model names). Used post-hoc to audit whether the
platform mapping is well-calibrated. `Checks proven` is `proven/total` from
the parent's independent re-run of the stage's proofs. If <40% of rows are mechanical/standard,
the decomposition is suspect — too many stages classified as judgment/critical
defeats the cost-savings purpose. -->
""")

    # Everything above is the parent's, read in one pass; the stage blocks
    # below are read one at a time, at launch and at integration.
    parts.append(STAGES_HEADER)
    for i, title in enumerate(args.stage, start=1):
        parts.append(render_stage(i, title, args.slug))

    rendered = "\n".join(parts)
    # Substitute the canonical plan-dir literal 'docs/plans' with the actual
    # plan directory (relative to repo root) derived from --output. When the
    # planner chose the canonical location, plan_dir_rel == 'docs/plans' and
    # this is a no-op. When a harness directed the plan elsewhere
    # (e.g. '.agents/tmp/backlog-claude-runner'), every boilerplate reference
    # to the plan dir — verify-script paths, report-template paths, logs dir,
    # reviewer-output dir, .gitignore narrowing advice — is rewritten in one
    # pass so the Plan landing commit and Phase 2 gates stay coherent.
    plan_dir_rel = getattr(args, "plan_dir_rel", None)
    if plan_dir_rel and plan_dir_rel != "docs/plans":
        rendered = rendered.replace("docs/plans", plan_dir_rel)
    # Substitute literal '<repo>' with the absolute repo root when known.
    # When None (--allow-outside-repo with no repo found), leave '<repo>' in
    # place so the planner fills it; do NOT crash here.
    repo_root = getattr(args, "repo_root", None)
    if repo_root:
        rendered = rendered.replace("<repo>", repo_root)
    return rendered


PROGRAM_EXECUTION_MODEL = """## Execution model (READ FIRST)
This plan is a program: one entry point over phase plans. Each phase plan is a staged plan of
its own, with its stages, gate, briefs and run log. One parent runs the whole program from this
file; whoever called it runs nothing else.

0. **Program gate** (mandatory, before any phase starts). Run:
   ```
   python3 -B docs/plans/_verify.py gate docs/plans/{slug}.md
   ```
   (Use `python` where `python3` is absent.) It checks this file, the phase graph, and every
   phase plan's own gate, then prints each phase's stage index. Non-zero: abort and surface it.
1. **Read** this file in one read. A phase plan is read down to its `## Stages` when its phase
   starts, as its own `## Execution model` step 1 says.
   **Program run log:** `docs/plans/logs/{slug}-run.md`. Append one line per phase event:
   ```
   python3 -B docs/plans/_verify.py run-log docs/plans/{slug}.md <phase id> <event> "<detail>"
   ```
   Events: `phase-started`, `phase-closed` (with its closing commit or summary), `halted`.
   After a compaction, a resume, or any doubt: read this run log, then the run log of each
   started phase, before the next action.
2. **Phase frontier.** A phase is *ready* when every phase its `Depends on:` names is closed.
   Start ready phases in table order: log `phase-started`, then run that phase plan's own
   `## Execution model` as its parent, from this same session.
   Phases ready together run side by side: their ready stages form one frontier, never more
   in flight than `Concurrency` below, and each stage is launched, integrated and verified as
   its own phase plan says, in its own phase's tree.
3. **Phase close.** A phase is closed when its plan's last step is done (end-to-end
   verification, reviewer gate, summary). Log `phase-closed`, then recompute the ready phases.
   A closed phase lives on in git, its run log and its summary; its plan is not read again.
4. **Red.** A phase that halts for a human holds only the phases that depend on it; the others
   go on. Once nothing can run, stop with the halted phase's own message and notification.
5. **After the last phase**, fill `## Program summary` and list what is left for a human (the
   pull requests to open, and their merge order from `## Context`).
"""


def render_program(args: argparse.Namespace) -> str:
    rows = "\n".join(
        f"| {pid} | `{plan}` | <FILL: backlog ids> | <FILL: earlier phase ids, or none> |"
        for pid, plan in args.phase_rows
    )
    summary = "\n".join(f"| {pid} | `{plan}` | | |" for pid, plan in args.phase_rows)
    rendered = "\n".join([
        f"# {args.title} - Staged Program\n",
        f"<!-- scaffolded {date.today().isoformat()} via staged-plan/lib/scaffold.py --program -->\n",
        PROGRAM_EXECUTION_MODEL.replace("{slug}", args.slug),
        "## Execution policy\n"
        f"- Concurrency: {args.concurrency} — stages in flight across every phase that runs; each phase\n"
        "  plan's own policy governs its stages (retries, stall window, working tree, reviewer).\n",
        "## Context\n<FILL: why this work is split into phases, what each phase delivers, and the merge order\n"
        "of the pull requests a human opens.>\n",
        "## Phases\n| Phase | Plan | Items | Depends on |\n|---|---|---|---|\n" + rows + "\n",
        "## Program summary (parent fills after the last phase)\n"
        "| Phase | Plan | Closing commit | Status |\n|---|---|---|---|\n" + summary + "\n",
    ])
    # The same plan-dir rewrite `scaffold` applies (see there).
    plan_dir_rel = getattr(args, "plan_dir_rel", None)
    if plan_dir_rel and plan_dir_rel != "docs/plans":
        rendered = rendered.replace("docs/plans", plan_dir_rel)
    return rendered


def render_summary(args: argparse.Namespace, out: Path) -> str:
    """The <<PRE_SCAFFOLD_SUMMARY>> block for non-interactive callers.

    Printed by the script itself so the block exists whether or not the
    planner remembers to emit it; the planner repeats it in its final message,
    the only text `claude -p` writes to stdout.
    """
    stages = "\n".join(f"  - {title}" for title in args.stage) or "\n".join(
        f"  - phase {pid}: {plan}" for pid, plan in getattr(args, "phase_rows", []))
    reason = args.reviewer_reason.strip() or "—"
    return (
        "<<PRE_SCAFFOLD_SUMMARY>>\n"
        f"slug: {args.slug}\n"
        f"title: {args.title}\n"
        f"stages:\n{stages}\n"
        f"mode: {args.mode}\n"
        f"working-tree: {args.working_tree}\n"
        f"reviewer: {args.reviewer}  reason: {reason}\n"
        f"concurrency: {args.concurrency}\n"
        f"report-policy: {args.report_policy}\n"
        f"output: {out}\n"
        "<<END>>"
    )


_VERSION_RX = re.compile(r"^VERSION = (\d+)", re.MULTILINE)


def _verify_version(text: str) -> int:
    # Copies vendored before versioning carry no VERSION line: treat as 0.
    m = _VERSION_RX.search(text)
    return int(m.group(1)) if m else 0


def vendor_verify(plan_dir: Path) -> str:
    """Write or refresh <plan_dir>/_verify.py from this skill's verify.py.

    A missing or older vendored copy is replaced; an equal or newer one is
    left alone. Returns a one-line status for the planner.
    """
    source = Path(__file__).resolve().parent / "verify.py"
    target = plan_dir / "_verify.py"
    source_text = source.read_text(encoding="utf-8")
    current = _verify_version(source_text)
    if target.exists():
        vendored = _verify_version(target.read_text(encoding="utf-8", errors="replace"))
        if vendored >= current:
            return f"_verify.py v{vendored} already current, skipping: {target}"
        action = f"refreshed v{vendored} -> v{current}"
    else:
        action = f"vendored v{current}"
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(source_text)
    return f"_verify.py {action}: {target}"


def main() -> int:
    # The summary echoes stage titles; a Windows console code page (cp1252)
    # cannot encode every character in them and would crash the run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Scaffold a staged-plan markdown.")
    p.add_argument("--slug", required=True, help="plan slug (e.g. migration-x)")
    p.add_argument("--title", required=True, help="plan title (e.g. 'Migrate module Y from A to B')")
    p.add_argument("--stage", action="append", default=[], help="stage title (repeat for each stage)")
    p.add_argument("--program", action="store_true", help="scaffold a program entry plan over phase plans")
    p.add_argument("--phase", action="append", default=[], metavar="ID=PLAN.md",
                   help="with --program: a phase id and its phase plan file, beside the entry plan (repeat)")
    p.add_argument("--output", required=True, help="output path (e.g. docs/plans/migration-x.md). Aborts if file exists unless --force.")
    p.add_argument("--mode", default="autonomous", choices=["autonomous", "semi-autonomous"])
    p.add_argument(
        "--working-tree",
        default="clean-required",
        choices=["clean-required", "stash-authorized", "integrate-existing", "abort-until-clean"],
    )
    p.add_argument("--reviewer", default="none", choices=["none", "light", "deep"])
    p.add_argument("--reviewer-reason", default="", help="why this reviewer level was chosen")
    p.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="max ready stages in flight at once (default 3; 1 = strictly sequential). Semi-autonomous mode always runs at 1.",
    )
    p.add_argument(
        "--report-policy",
        default="committed",
        choices=["committed", "gitignored"],
        help=(
            "How post-stage reports are persisted. "
            "'committed' (default): each report is staged and committed alongside its "
            "stage's code changes (one commit, full audit trail in PR). "
            "'gitignored': reports are written locally only — the repo's .gitignore "
            "must already (or will) cover the report path. Use this when the repo "
            "convention keeps planning artifacts out of version control."
        ),
    )
    p.add_argument("--force", action="store_true", help="overwrite --output if it exists (DESTRUCTIVE)")
    p.add_argument(
        "--repo-root",
        default=None,
        help=(
            "Absolute repo root path. Substituted for the literal string '<repo>' "
            "in the rendered plan (boilerplate paths like '<repo>/docs/plans/...'). "
            "Auto-detected from --output's containing git repo when omitted; if no "
            "repo is found and --allow-outside-repo is set, '<repo>' is left as a "
            "FILL placeholder for the planner to substitute."
        ),
    )
    p.add_argument(
        "--allow-outside-repo",
        action="store_true",
        help="ESCAPE HATCH: permit --output outside any git repo (only for genuine no-repo planning sessions; never use for repo work).",
    )
    args = p.parse_args()

    if args.program:
        args.phase_rows = [tuple(s.split("=", 1)) for s in args.phase]
        if not args.phase_rows or any(len(r) != 2 or not all(r) for r in args.phase_rows):
            print("error: --program needs one or more --phase ID=PLAN.md", file=sys.stderr)
            return 2
    elif len(args.stage) < 1:
        print("error: at least one --stage required", file=sys.stderr)
        return 2

    if args.concurrency < 1:
        print("error: --concurrency must be at least 1", file=sys.stderr)
        return 2
    # The semi-autonomous checkpoint is a human look between stages; parallel
    # stages would return past it.
    if args.mode == "semi-autonomous":
        args.concurrency = 1

    if args.reviewer != "none" and not args.reviewer_reason.strip():
        print(
            f"error: --reviewer={args.reviewer} requires --reviewer-reason "
            f"so the recommendation is auditable.",
            file=sys.stderr,
        )
        return 2

    out = Path(args.output).resolve()

    # Location guard: --output must resolve inside a git repo. Any in-repo path
    # is accepted; the scaffold derives the plan dir from --output and rewrites
    # boilerplate paths accordingly. The previous hard requirement that the
    # parent be exactly <repo>/docs/plans/ was dropped: harness integrations
    # (e.g. backlog-claude-runner) legitimately need other in-repo locations,
    # and the deterministic boilerplate is the load-bearing value here, not
    # the specific directory name. The canonical convention remains
    # <repo>/docs/plans/<slug>.md — deviate only when a harness mandates it.
    repo_root = None
    for ancestor in [out.parent, *out.parent.parents]:
        if (ancestor / ".git").exists():
            repo_root = ancestor
            break
    if repo_root is None and not args.allow_outside_repo:
        print(
            f"error: --output ({out}) is not inside a git repo. Staged plans "
            "for repo work MUST be created somewhere under a git repository "
            "root (canonical: <repo-root>/docs/plans/<slug>.md). "
            "Re-invoke from inside the target repo, or pass --allow-outside-repo "
            "for the rare no-repo planning fallback.",
            file=sys.stderr,
        )
        return 4

    # Derive plan_dir_rel — the path of out.parent relative to repo_root, in
    # POSIX form. Used by scaffold() to rewrite every literal 'docs/plans'
    # reference in the rendered boilerplate. When out lives directly under the
    # repo root, plan_dir_rel == '.' — surface that as an error since landing
    # the plan in the repo root would pollute it.
    plan_dir_rel = None
    if repo_root is not None:
        try:
            plan_dir_rel = out.parent.relative_to(repo_root).as_posix()
        except ValueError:
            plan_dir_rel = None
        if plan_dir_rel == ".":
            print(
                f"error: --output ({out}) would land the plan directly at the "
                "repo root. Choose a subdirectory (canonical: docs/plans/).",
                file=sys.stderr,
            )
            return 4
    args.plan_dir_rel = plan_dir_rel

    # Resolve repo_root for <repo> substitution: explicit --repo-root wins;
    # otherwise use the auto-detected one (None when --allow-outside-repo).
    if args.repo_root is None and repo_root is not None:
        args.repo_root = str(repo_root)

    if out.exists() and not args.force:
        print(
            f"error: {out} already exists. Refusing to overwrite. "
            f"Pass --force to overwrite (this destroys the existing plan).",
            file=sys.stderr,
        )
        return 3

    # Printed on every run: a delegated planner opens its final message with
    # it whether or not the caller could set STAGED_PLAN_NONINTERACTIVE.
    print(render_summary(args, out), flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: stage in a sibling temp file, then os.replace into place.
    # Prevents partial files on interruption and matches POSIX atomic-rename
    # semantics (also works on Windows since Python 3.3).
    fd, tmp_name = tempfile.mkstemp(
        prefix=out.name + ".", suffix=".tmp", dir=str(out.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render_program(args) if args.program else scaffold(args))
        os.replace(tmp_name, out)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    print(f"Plan scaffolded: {out.resolve().as_posix()}")

    print(vendor_verify(out.parent))

    # Write _report-template.md alongside the plan (skip if already present —
    # the user may have customised it for this repo).
    template_path = out.parent / "_report-template.md"
    if not template_path.exists():
        with open(template_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(REPORT_TEMPLATE_CONTENT)
        print(f"Report template: {template_path.resolve()}")
    else:
        print(f"Report template already present, skipping: {template_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
