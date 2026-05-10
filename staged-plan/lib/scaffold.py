#!/usr/bin/env python3
"""Scaffold a staged-plan markdown with all boilerplate blocks pre-rendered.

Usage:
    python scaffold.py --slug <slug> --title "<plan title>" \
        --stage "Stage 1 title" --stage "Stage 2 title" ... \
        --output docs/plans/<slug>.md \
        [--mode autonomous|semi-autonomous] \
        [--working-tree clean-required|stash-authorized|integrate-existing|abort-until-clean] \
        [--reviewer none|light|deep] \
        [--reviewer-reason "<why this level>"] \
        [--report-policy committed|gitignored] \
        [--force]

The planner runs this BEFORE filling in stage-specific content. Output contains
all repeated boilerplate (Execution model, Execution policy, Executor adapter,
Reviewer gate, Stage 0, hand-off template, End-to-end verification) so the
planner only edits the cognitive parts: per-stage scope, files, order of
operations, and hand-off prompts.

Safety:
- --output is required (no stdout redirect, which can truncate an existing
  file before Python decides whether to error).
- If --output already exists, the script aborts with exit 3 unless --force is
  passed. This protects filled plans from being silently overwritten.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path


EXECUTION_MODEL = """## Execution model (READ FIRST)
Staged subagent execution (prompt chaining + gate checks). Do NOT run as one linear task.

0. **Pre-execution placeholder gate** (mandatory, before launching any stage). Run:
   ```
   python3 -c "import sys; sys.path.insert(0,'docs/plans'); from _verify import V; V.assert_no_placeholders('docs/plans/{slug}.md'); sys.exit(V.summarize())"
   ```
   If non-zero, abort and surface the offending lines. Fix or delete the flagged blocks; do NOT bypass.
1. **Parent** reads this plan end-to-end (orchestration needs the full picture).
   **Subagents** read only the sections their hand-off prompt names — never
   other stages' blocks. This split is a deliberate token optimization.
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
  **narrow the rule to ignore only logs**: replace that line with
  `docs/plans/logs/`. The plan file, `_verify.py`, and verify scripts MUST be
  versioned; only gate logs are excluded. Do NOT use `git add -f` to bypass —
  the rule itself needs fixing.
- If `.gitignore` does not ignore `docs/plans/`, just append `docs/plans/logs/`
  if not already present.
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
2. `<repo>/docs/plans/_verify.py` — vendored verify primitives; the planner
   copies this from the staged-plan skill source as part of Phase 1.5 if not
   already present in the repo. Stage scripts import it via
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
mechanism the executor provides (Claude Code: `Agent` tool with
`subagent_type: general-purpose`, foreground, sequential; Codex / others: the
equivalent fresh-window mechanism, or inline in a clean session if no delegate
mechanism exists).

**Model & effort selection:** the plan declares `Tier:` and `Effort:` per stage
(see `## Execution model` § Resource selection vocabulary). The executor maps
those to its own model lineup, picking the cheapest viable combo. The plan
itself names no model — only the executor knows what's available and what it
costs.

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

def render_global_conventions(slug: str, report_policy: str) -> str:
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
"""

HANDOFF_CONVENTIONS = """## Hand-off conventions (apply to every stage)

**Authorization:**
- MAY commit directly after all verifications pass.
- MAY NOT push.
- MAY NOT modify files outside the stage's declared file list.
- MAY NOT touch pre-existing unrelated working-tree edits.
- MAY NOT skip gates or use --no-verify / bypass hooks.
- MAY NOT spawn nested subagents (no Agent calls inside this stage).

**Scope discipline:**
- If the stage appears to require files outside the declared list, STOP and
  report. Do NOT silently expand scope.
- If pre-existing test/build failure is unrelated to this stage, STOP and
  report. Do NOT fix it.

**Failure protocol:**
- Gate fails within declared scope -> fix within scope and re-run the gate.
- Any STOP condition above -> return to parent with a clear reason.

**Return to parent:**
- Per-file summary with actual grep-found locations.
- Gate results (pass/fail + snippets).
- Commit SHA + subject.
- Deviations from the plan, if any.
- Path to the post-stage report written to disk.
"""

REPORT_TEMPLATE_CONTENT = """\
# Stage <N> — <title> — Post-stage report

**Backlog items:** <ids>
**Commit:** _filled by parent in the End-to-end summary table_
**Plan:** <plan-slug>.md

## Files changed
<!-- list each file with a brief description of the change -->

## Gate results
<!-- build: pass/fail, tests: pass/fail, lint: pass/fail, etc. -->

## Acceptance criteria audit
<!-- tick off each acceptance criterion from the plan -->

## Deviations from plan
<!-- any differences from the planned order of operations or file list -->

## Surprises / notes
<!-- discoveries made during execution that may affect later stages -->
"""

_HANDOFF_HEADER = """**Hand-off prompt for Stage {n}:**
> You are executing Stage {n} of <FILL: plan title> at <FILL: absolute plan path>.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE {n} -->` and `<!-- END STAGE {n} -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> <repo>/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: <FILL: absolute path>
> Branch: <FILL: branch>
> Platform: <FILL: os>  (Windows: use bash syntax, forward slashes)
>
{prior_status}>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>"""

_PRIOR_STATUS_FIRST = "> Status: this is the first feature stage; no prior stage commits exist beyond Stage 0 baseline.\n"
_PRIOR_STATUS_LATER = (
    "> Status: Stages 1..{prev} committed (confirm with `git log --oneline -{prev}`).\n"
    "> Prior stages' work is reflected in: (1) the actual code state — run\n"
    "> `git log --oneline -{prev}` and `git diff HEAD~{prev} HEAD --stat` if you need\n"
    "> to see what changed; (2) `## Critical files` in the plan (cross-stage index);\n"
    "> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you\n"
    "> need detail on a specific surprise or deviation. Do NOT read other stages'\n"
    "> BEGIN/END blocks for prior context — git is the source of truth.\n"
)


def _handoff_header(n: int) -> str:
    if n <= 1:
        prior = _PRIOR_STATUS_FIRST
    else:
        prior = _PRIOR_STATUS_LATER.format(prev=n - 1)
    return _HANDOFF_HEADER.format(n=n, prior_status=prior)


_HANDOFF_BODY_PRELUDE = """
> Your scope: Stage {n} only - <FILL: title>. Items: <FILL: IDs>.
>
> Critical rules (from CLAUDE.md):
> - Build check: <FILL: cmd>
> - Other gates: <FILL: list>
> - Invariants: <FILL: list>
>
> Working tree: per `## Execution policy` working-tree policy = `<FILL: policy>`.
> - clean-required / stash-authorized: tree is clean at stage start; stage only
>   files YOU modify, by explicit path; never `git add -A`.
> - integrate-existing: pre-existing dirty files listed in the Stage 0 baseline
>   summary MAY be part of your declared file list; if so, stage them; otherwise
>   leave them untouched.
>
> Files to modify:
> 1. `<FILL: path>` - <FILL: intent>
>
> Order of operations:
> 1. <FILL>
"""

_HANDOFF_LAST_STEP_COMMITTED = """\
> N. Gates pass -> write the post-stage report (copy `docs/plans/_report-template.md`
>    as a starting point; leave the `Commit:` slot as `_filled by parent_` —
>    the parent fills it in the End-to-end summary table)
>    -> stage code files AND the report file together by explicit path
>    -> commit with HEREDOC including the
>    `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer.
>    (One commit per stage; report is part of that commit.)
"""

_HANDOFF_LAST_STEP_GITIGNORED = """\
> N. Gates pass -> write the post-stage report locally to
>    `docs/plans/{slug}-stage-{n}-report.md` (copy `docs/plans/_report-template.md`
>    as a starting point; leave the `Commit:` slot as `_filled by parent_` —
>    the parent fills it in the End-to-end summary table)
>    -> stage **only** the code files by explicit path (the report file is
>    gitignored and must NOT be staged)
>    -> commit with HEREDOC including the
>    `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer.
>    (One commit per stage; report is local-only, not part of any commit.)
"""

_HANDOFF_BODY_TAIL = """\
>
> Conventions: see `## Hand-off conventions` in this plan — it covers
> Authorization, Scope discipline, Failure protocol, and Return-to-parent
> format. They apply to this stage.
>
> Begin now.
"""


def render_handoff_body(n: int, slug: str, report_policy: str) -> str:
    last_step = (
        _HANDOFF_LAST_STEP_GITIGNORED.format(slug=slug, n=n)
        if report_policy == "gitignored"
        else _HANDOFF_LAST_STEP_COMMITTED
    )
    return _HANDOFF_BODY_PRELUDE.format(n=n) + last_step + _HANDOFF_BODY_TAIL


def render_stage(n: int, title: str, slug: str, report_policy: str) -> str:
    if report_policy == "gitignored":
        order_last = (
            "N. Gates pass -> write the post-stage report locally (gitignored)\n"
            "   -> stage ONLY the code files -> commit. The report stays in the\n"
            "   working tree but is not committed."
        )
        report_block = (
            f"**Post-stage report:** write `<repo>/docs/plans/{slug}-stage-{n}-report.md` "
            f"locally (gitignored, NOT committed). Copy `docs/plans/_report-template.md` "
            f"as the starting structure; leave the `Commit:` slot as `_filled by parent_` "
            f"— the End-to-end summary table is the canonical source for that mapping."
        )
    else:
        order_last = (
            "N. Gates pass -> write the post-stage report -> stage code files AND the\n"
            "   report file together -> commit. (One commit per stage; report is committed\n"
            "   alongside the code.)"
        )
        report_block = (
            f"**Post-stage report:** write `<repo>/docs/plans/{slug}-stage-{n}-report.md`. "
            f"Copy `docs/plans/_report-template.md` as the starting structure; leave the "
            f"`Commit:` slot as `_filled by parent_` — the End-to-end summary table is the "
            f"canonical source for that mapping."
        )

    return f"""<!-- BEGIN STAGE {n} -->
## Stage {n} - {title}
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
**Tier rationale:** <FILL: 1-2 lines justifying this Tier/Effort. If the stage is mechanical apply-pattern work, say so; if judgment, name the specific decision the executor must make. The executor uses this to choose the cheapest viable model.>
**Items:** <FILL: atomic IDs>
**Scope:** <FILL: one sentence>
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

**Files:**
- `<FILL: path>` - <FILL: what changes and why>

**Order of operations:**
1. <FILL>
{order_last}

**Verification:** <FILL: per-stage commands + expected outcomes>
<Generate `docs/plans/{slug}-verify-stage-{n}.py` when ANY of:
  - ≥4 distinct shell commands in this Verification block
  - ≥2 grep-based invariant assertions ("must return 0 matches", "must still find X")
  - ≥2 _verify primitives used (assert_clean_tree, assert_only_files_touched, etc.)
When in doubt, generate the script — it costs ~20 lines and survives retries.
Otherwise keep gates inline.>

**Manual verification (if any):** <FILL or "none">

{report_block}

{_handoff_header(n)}{render_handoff_body(n, slug, report_policy)}
<!-- END STAGE {n} -->
---
"""


def render_execution_policy(mode: str, working_tree: str, reviewer: str, reviewer_reason: str) -> str:
    reviewer_line = f"- Reviewer: {reviewer}"
    if reviewer != "none" and reviewer_reason:
        reviewer_line += f"  # {reviewer_reason}"
    mode_extra = ""
    if mode == "semi-autonomous":
        mode_extra = (
            "\n  Between-stage checkpoint posted by parent — format:\n"
            "    `✓ Stage N done — {sha} \"{subject}\" | Files: ... | Gates: build ✓ test ✓ ... | Report: <path> | Next: Stage N+1 — {title} | Resume? [y / edit / abort]`\n"
            "    `y` -> launch next; `edit` -> user adjusts next hand-off; `abort` -> stop (committed work preserved)."
        )
    return f"""## Execution policy (fixed defaults unless user overrode)
- Mode: {mode}{mode_extra}
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2 — cap of 2 retries; each retry passes the prior failure excerpt and narrows the instruction to the same file list. NEVER retry on scope violations, pre-commit hook rejections, or hook bypass attempts (escalate immediately). On exhaustion: stop and surface.
- Working-tree policy: {working_tree} — per-state behavior is described inline in `## Stage 0`.
{reviewer_line}
"""


def scaffold(args: argparse.Namespace) -> str:
    parts: list[str] = []
    parts.append(f"# {args.title} - Staged Execution Plan\n")
    parts.append(f"<!-- scaffolded {date.today().isoformat()} via staged-plan/lib/scaffold.py -->\n")
    parts.append(EXECUTION_MODEL.replace("{slug}", args.slug))
    parts.append(render_execution_policy(args.mode, args.working_tree, args.reviewer, args.reviewer_reason))
    parts.append(render_plan_landing_commit(args.slug, args.report_policy))
    parts.append(HANDOFF_CONVENTIONS)
    parts.append("## Context\n<FILL: why this track. Constraints. In scope. Out of scope / blocked externally.>\n")

    parts.append("## Alternatives considered\n<FILL-OR-DELETE: 1-2 stage decompositions rejected, with reason. Delete this block if you only considered one decomposition.>\n")
    parts.append("## Open questions\n<FILL-OR-DELETE: items the planner could not resolve from the codebase alone. Each: question, default assumed, stage(s) affected. Delete this block if there are none.>\n")

    parts.append(render_global_conventions(args.slug, args.report_policy))
    parts.append(STAGE_0.replace("{slug}", args.slug))

    for i, title in enumerate(args.stage, start=1):
        parts.append(render_stage(i, title, args.slug, args.report_policy))

    if args.reviewer != "none":
        parts.append(REVIEWER_GATE)

    parts.append("## Critical files (cross-stage index)\n<FILL: table of file -> stages that touch it>\n")
    parts.append(f"""## End-to-end verification (after final stage)
<FILL: commands + manual smoke. If >3 commands OR invariants to grep,
generate `docs/plans/{args.slug}-verify-e2e.py` importing `_verify`.>

## End-to-end summary (parent fills after final stage)
| Stage | Title | Tier | Effort | Model used | Commit SHA | Status | Report |
|-------|-------|------|--------|------------|------------|--------|--------|
<!-- one row per stage. `Model used` is what the executor actually selected
on its platform for the declared Tier/Effort (the executor fills this — the
plan never prescribes model names). Used post-hoc to audit whether the
platform mapping is well-calibrated. If <40% of rows are mechanical/standard,
the decomposition is suspect — too many stages classified as judgment/critical
defeats the cost-savings purpose. -->
""")

    return "\n".join(parts)


def main() -> int:
    p = argparse.ArgumentParser(description="Scaffold a staged-plan markdown.")
    p.add_argument("--slug", required=True, help="plan slug (e.g. migration-x)")
    p.add_argument("--title", required=True, help="plan title (e.g. 'Migrate module Y from A to B')")
    p.add_argument("--stage", action="append", required=True, help="stage title (repeat for each stage)")
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
    args = p.parse_args()

    if len(args.stage) < 1:
        print("error: at least one --stage required", file=sys.stderr)
        return 2

    if args.reviewer != "none" and not args.reviewer_reason.strip():
        print(
            f"error: --reviewer={args.reviewer} requires --reviewer-reason "
            f"so the recommendation is auditable.",
            file=sys.stderr,
        )
        return 2

    out = Path(args.output)
    if out.exists() and not args.force:
        print(
            f"error: {out} already exists. Refusing to overwrite. "
            f"Pass --force to overwrite (this destroys the existing plan).",
            file=sys.stderr,
        )
        return 3

    out.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: stage in a sibling temp file, then os.replace into place.
    # Prevents partial files on interruption and matches POSIX atomic-rename
    # semantics (also works on Windows since Python 3.3).
    fd, tmp_name = tempfile.mkstemp(
        prefix=out.name + ".", suffix=".tmp", dir=str(out.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(scaffold(args))
        os.replace(tmp_name, out)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    print(f"Plan scaffolded: {out.resolve()}")

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
