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
import sys
from datetime import date


EXECUTION_MODEL = """## Execution model (READ FIRST)
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
"""

EXECUTOR_ADAPTER = """## Executor adapter
- **Claude Code**: use the `Agent` tool, one stage per subagent,
  `subagent_type: general-purpose`, foreground, omit `model`, omit `run_in_background`.
- **Codex / other executors**: execute each Hand-off prompt inline in a fresh context
  window, or via the executor's own delegated-agent mechanism if available.
  The plan does not depend on Claude-specific tooling beyond this section.
"""

GLOBAL_CONVENTIONS = """## Global conventions
- Build gate: <FILL: cmd>
- Lint/test gates: <FILL: cmds>
- Invariants: <FILL: e.g. no GPL in main binary, vendor-neutral i18n, English only>
- Commit style: one per stage; trailer `Co-Authored-By: <model> <noreply@anthropic.com>`
- Staging: only files the stage declares, by explicit path; never `git add -A`
"""

STAGE_0 = """## Stage 0 - Pre-flight (mandatory, no feature work, no commit)
Purpose: record baseline state, vendor verify primitives, apply the
working-tree policy so later failures cannot be blamed on prior repo state.
1. Capture `git status` and the current HEAD SHA in the post-stage report.
2. **Vendor verify primitives** (only if any stage uses verify scripts):
   if `<repo>/docs/plans/_verify.py` does not exist, copy it from
   `~/.claude/skills/staged-plan/lib/verify.py`.
3. Apply the working-tree policy from `## Execution policy`:
   - clean-required: tree must be clean; if not, abort.
   - stash-authorized: `git stash push -u -m "staged-plan-{slug}-pre"`; record stash ref.
   - integrate-existing: leave changes in place; declare them in the report.
   - abort-until-clean: abort the plan; user resolves manually.
4. Run every gate (build, lint, tests, etc.) on the resulting baseline.
5. Red -> abort. Green -> proceed to Stage 1.
"""

REVIEWER_GATE = """## Reviewer gate (only if Reviewer != none)
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

_HANDOFF_HEADER = """**Hand-off prompt for Stage {n}:**
> You are executing Stage {n} of <FILL: plan title> at <FILL: absolute plan path>.
> Read that plan file first, then read <repo>/CLAUDE.md for repo-wide rules.
>
> Repo root: <FILL: absolute path>
> Branch: <FILL: branch>
> Platform: <FILL: os>  (Windows: use bash syntax, forward slashes)
>
{prior_status}>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>"""

_PRIOR_STATUS_FIRST = "> Status: this is the first feature stage; no prior stage commits exist beyond Stage 0 baseline.\n"
_PRIOR_STATUS_LATER = "> Status: Stages 1..{prev} committed (confirm with `git log --oneline -{prev}`).\n"


def _handoff_header(n: int) -> str:
    if n <= 1:
        prior = _PRIOR_STATUS_FIRST
    else:
        prior = _PRIOR_STATUS_LATER.format(prev=n - 1)
    return _HANDOFF_HEADER.format(n=n, prior_status=prior)


_HANDOFF_BODY = """
> Your scope: Stage {n} only - <FILL: title>. Items: <FILL: IDs>.
>
> Critical rules (from CLAUDE.md):
> - Build check: <FILL: cmd>
> - Other gates: <FILL: list>
> - Invariants: <FILL: list>
>
> Working tree: per `## Execution policy` working-tree policy.
> Stage only files YOU modify, by explicit path; never `git add -A`.
>
> Files to modify:
> 1. `<FILL: path>` - <FILL: intent>
>
> Order of operations:
> 1. <FILL>
> N. Gates pass -> write the post-stage report -> stage code files AND the
>    report file together -> commit with HEREDOC + Co-Authored-By.
>    (One commit per stage; report is committed alongside the code.)
>
> Authorization:
> - MAY commit directly after all verifications pass.
> - MAY NOT push.
> - MAY NOT modify files outside the list above.
> - MAY NOT touch pre-existing unrelated working-tree edits.
> - MAY NOT skip gates or use --no-verify / bypass hooks.
> - MAY NOT spawn nested subagents (no Agent calls inside this stage).
>
> Scope discipline:
> - If the stage appears to require files outside the declared list, STOP and
>   report. Do NOT silently expand scope.
> - If pre-existing test/build failure is unrelated to this stage, STOP and
>   report. Do NOT fix it.
>
> Failure protocol:
> - Gate fails within declared scope -> fix within scope and re-run the gate.
> - Any STOP condition above -> return to parent with a clear reason.
>
> Return to parent:
> - Per-file summary with actual grep-found locations.
> - Gate results (pass/fail + snippets).
> - Commit SHA + subject.
> - Deviations from the plan, if any.
> - Path to the post-stage report written to disk.
>
> Begin now.
"""


def render_stage(n: int, title: str, slug: str) -> str:
    return f"""## Stage {n} - {title}
**Items:** <FILL: atomic IDs>
**Scope:** <FILL: one sentence>
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

**Files:**
- `<FILL: path>` - <FILL: what changes and why>

**Order of operations:**
1. <FILL>
N. Gates pass -> commit.

**Verification:** <FILL: per-stage commands + expected outcomes>
<If gates >3 cmds OR grep of invariants OR reuses primitives, generate
`docs/plans/{slug}-verify-stage-{n}.py` importing `_verify`.>

**Manual verification (if any):** <FILL or "none">

**Post-stage report:** write `<repo>/docs/plans/{slug}-stage-{n}-report.md`
with: files changed, gate results, commit SHA, deviations, surprises.

{_handoff_header(n)}{_HANDOFF_BODY.format(n=n)}
---
"""


def render_execution_policy(mode: str, working_tree: str, reviewer: str, reviewer_reason: str) -> str:
    reviewer_line = f"- Reviewer: {reviewer}"
    if reviewer != "none" and reviewer_reason:
        reviewer_line += f"  # {reviewer_reason}"
    return f"""## Execution policy (fixed defaults unless user overrode)
- Mode: {mode}
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2
- Working-tree policy: {working_tree}
{reviewer_line}
"""


def scaffold(args: argparse.Namespace) -> str:
    parts: list[str] = []
    parts.append(f"# {args.title} - Staged Execution Plan\n")
    parts.append(f"<!-- scaffolded {date.today().isoformat()} via staged-plan/lib/scaffold.py -->\n")
    parts.append(EXECUTION_MODEL)
    parts.append(render_execution_policy(args.mode, args.working_tree, args.reviewer, args.reviewer_reason))
    parts.append(EXECUTOR_ADAPTER)
    parts.append("## Context\n<FILL: why this track. Constraints. In scope. Out of scope / blocked externally.>\n")

    parts.append("## Alternatives considered\n<FILL-OR-DELETE: 1-2 stage decompositions rejected, with reason. Delete this block if you only considered one decomposition.>\n")
    parts.append("## Open questions\n<FILL-OR-DELETE: items the planner could not resolve from the codebase alone. Each: question, default assumed, stage(s) affected. Delete this block if there are none.>\n")

    parts.append(GLOBAL_CONVENTIONS)
    parts.append(STAGE_0.replace("{slug}", args.slug))

    for i, title in enumerate(args.stage, start=1):
        parts.append(render_stage(i, title, args.slug))

    if args.reviewer != "none":
        parts.append(REVIEWER_GATE)

    parts.append("## Critical files (cross-stage index)\n<FILL: table of file -> stages that touch it>\n")
    parts.append(f"""## End-to-end verification (after final stage)
<FILL: commands + manual smoke. If >3 commands OR invariants to grep,
generate `docs/plans/{args.slug}-verify-e2e.py` importing `_verify`.>
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
    p.add_argument("--force", action="store_true", help="overwrite --output if it exists (DESTRUCTIVE)")
    args = p.parse_args()

    if len(args.stage) < 1:
        print("error: at least one --stage required", file=sys.stderr)
        return 2

    from pathlib import Path
    out = Path(args.output)
    if out.exists() and not args.force:
        print(
            f"error: {out} already exists. Refusing to overwrite. "
            f"Pass --force to overwrite (this destroys the existing plan).",
            file=sys.stderr,
        )
        return 3

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(scaffold(args))
    print(f"Plan scaffolded: {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
