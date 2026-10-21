# Filling the plan

`lib/scaffold.py` is the single source of the plan skeleton — every boilerplate section and the exact wording subagents read. To see it, scaffold into a scratch repo. This file covers only what the planner writes into each `<FILL>`.

## Context

Why this track exists, the constraints, what is in scope, and what is out of scope or blocked externally. A reader opening the plan cold learns *why* here and *what* in the stage blocks.

## Swept

Nine fixed themes, each answered on its own line — check ids, `existing: <file or mechanism>`, or `not in scope — <why>`:

```
- validation: C2.1, C2.2
- authorization: existing: `requireRole("admin")` guard on the router
- data lifecycle: not in scope — nothing new is persisted
```

A theme with no honest answer is a gap in the investigation, not a line to skip.

## One-way doors

Table `| Door | Literal shape | Alternative rejected |`, one row per hard-to-reverse choice:

```
| `task.status` gains `archived` | enum value, not null, existing rows backfilled to `active` | a boolean `is_archived` — cannot express the next state |
```

The rejected alternative carries the property that disqualified it; for a new pattern it is the convention already in the code. Where the choice was forced, name the constraint instead. With no door, write the single line `None — <why nothing here is hard to reverse>`. When the repo keeps ADRs or a decision log, mirror the rows that outlive the track there during Phase 1.5.

## Alternatives considered

Rejected stage *decompositions* (design choices live in One-way doors). Fill when you genuinely weighed more than one decomposition; delete the block otherwise.

## Global conventions

Build, lint, and test gates exactly as CI runs them, plus repo-wide invariants (e.g. English only, no GPL in the main binary). These run in every stage on top of its checks.

## Stage block

| Field | What to write |
|---|---|
| `Tier` / `Effort` / `Tier rationale` | Per the classification table in `SKILL.md`; the rationale names the specific decision or risk. |
| `Size` | `~Nk tokens` = `wc -c` / 4 over the files the stage reads. A floor: it ranks stages correctly even though iteration adds more. |
| `Depends on` | Pre-filled with the previous stage; narrow it to the real prerequisites. |
| `Items` / `Scope` | Backlog ids; one sentence naming the observable outcome. |
| `Files` | Every file the stage creates, edits, or deletes, each with what changes and why. This list is the scope boundary. |
| `Order of operations` | Concrete steps up to, not including, the rendered final step (proofs + gates → report → commit). Where a proof is a new test, its step comes before the implementation step. |
| `Checks` | Per `SKILL.md` § Write the checks. Number them `C<stage>.<k>`. |
| `Verify script` line | Keep and generate the script, or delete the line — see `verify-scripts.md`. |
| `Manual verification` | User-side checks the agent cannot run, or `none`. |

## Hand-off prompt

The scaffold renders the hand-off; fill its `<FILL>` slots — plan title, absolute plan path, repo root, branch, platform, stage title, items. The prompt points to `## Hand-off conventions`, `## Global conventions`, and the stage block instead of repeating them, so the stage's specifics belong in the stage block, not in the prompt. At launch the parent may append runtime context (current branch state, a callsite found by an earlier stage).

## Critical files

Table `| File | Stages |` — every file any stage touches, with the stages that touch it. A file appearing in several stages marks a shared surface: double-check the ordering there.

## End-to-end verification

Commands and manual smoke run after the final stage — typically the full suite plus a grep for residue of whatever the track removed. With more than 3 commands or any grep invariants, generate `<plan-slug>-verify-e2e.py`.
