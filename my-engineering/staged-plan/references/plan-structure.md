# Filling the plan

`lib/scaffold.py` is the single source of the plan skeleton — every boilerplate section and the exact wording subagents read. To see it, scaffold into a scratch repo. This file covers only what the planner writes into each `<FILL>`.

## Program (an entry plan over phase plans)

Rendered by `scaffold.py --program`. The planner fills two things:
- `## Context`: why the work is phased, what each phase delivers, and the merge order of the pull requests a human
  opens afterwards.
- `## Phases`: one row per phase plan — ``| A | `<slug>-a.md` | #815, #808 | none |`` — its backlog ids and the
  earlier phases it builds on. A phase depends on another when it starts from that phase's branch tip or needs a
  file it changes; phases on separate branches whose shared files meet only at merge do not.

Each phase plan is an ordinary staged plan and is filled as the rest of this file describes. Its `## Context`
names the phases it builds on and the files it shares with phases that run beside it.

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

One entry per hard-to-reverse choice. Table `| Door | Literal shape | Alternative rejected |` while every row fits 160 characters:

```
| `task.status` gains `archived` | enum value, not null, rows backfilled to `active` | boolean `is_archived` — cannot express the next state |
```

Past that, one list item per door, its parts labelled and wrapped:

```
- **`task.status` gains `archived`** — shape: enum value, not null, existing rows backfilled to `active`.
  Rejected: a boolean `is_archived` — cannot express the next state.
```

The rejected alternative carries the property that disqualified it; for a new pattern it is the convention already in the code. Where the choice was forced, name the constraint instead. With no door, write the single line `None — <why nothing here is hard to reverse>`. When the repo keeps ADRs or a decision log, mirror the rows that outlive the track there during Phase 1.5.

## Alternatives considered

Rejected stage *decompositions* (design choices live in One-way doors). Fill when you genuinely weighed more than one decomposition; delete the block otherwise.

## Global conventions

Build, lint, and test gates exactly as CI runs them, plus repo-wide invariants (e.g. English only, no GPL in the main binary). These run in every stage on top of its checks, and again at every integration.

With concurrency above 1 the block also carries:
- **Worktree setup** — what a fresh checkout needs before the gates run: the install command, and every untracked file the gates read (an env file, a local config) with where it is copied from. Copied files stay untracked.
- **Shared runtime** — every port, database file, container, or cache a proof binds, and how two worktrees avoid colliding: usually a port and database path read from env, set per worktree in the setup.

## Procedures

Recipes two or more stages share, one `### <name>` heading each, followed by its numbered steps: the same refactor applied to different files, the same fix over different sites. A stage's Order of operations names the recipe and its input — ``1. Procedure split-to-limit over the sites of `sites.py ts-rule b complexity` `` — and keeps only the steps unique to it. When the work is a list the repo can compute (lint sites, functions over a limit), the input is the command that lists it, not the list. Delete the block when no steps repeat.

## Stage block

| Field | What to write |
|---|---|
| `Tier` / `Effort` / `Tier rationale` | Per the classification table in `SKILL.md`; the rationale names the specific decision or risk. |
| `Size` | `~Nk tokens` = `wc -c` / 2.5 over the files the stage reads. A floor: it ranks stages correctly even though iteration adds more. The gate fails a stage past ~100k. |
| `Depends on` | Per `SKILL.md` § Decompose into stages. Stage 1 is pre-filled `none`. |
| `Items` / `Scope` | Backlog ids; one sentence naming the observable outcome. |
| `Files` | Every file the stage creates, edits, or deletes, each with what changes and why. This list is the scope boundary. |
| `Order of operations` | The stage's own steps up to its proofs; the hand-off template closes every stage with proofs + gates → report → commit. Where a proof is a new test, its step comes before the implementation step. A step a `## Procedures` recipe already holds is named, not repeated. |
| `Checks` | Per `SKILL.md` § Write the checks: one claim with a concrete value each, a proof naming one test or command. Number them `C<stage>.<k>`. |
| `Verify script` line | Keep and generate the script, or delete the line — see `verify-scripts.md`. |
| `Manual verification` | User-side checks the agent cannot run, or `none`. |

## Hand-off prompt

One template, under `## Hand-off prompt`, serves every stage. Fill its plan-level slots once — plan title, absolute plan path, repo root, branch, platform. At launch the parent runs `_verify.py brief`, which fills `{{N}}`, `{{TITLE}}`, and `{{ITEMS}}` and writes the stage's **brief**: the prompt, the stage block, then Hand-off conventions, Global conventions, the `## Procedures` recipes the block names, One-way doors, and Critical files. A stage's specifics belong in its block. A stage that runs in a tree other than the repo root (a track, a worktree) gets it through `--workdir`. The parent may append runtime context to the brief's prompt (current branch state, a callsite found by an earlier stage).

Every brief carries the shared sections whole, so they set the floor of every brief's size. Detail only some stages use — a table of fixes for one family of stages — belongs in a `## Procedures` recipe those stages name, which reaches only their briefs, rather than in `## Global conventions`, which reaches all of them.

## Critical files

Table `| File | Stages |` — every file any stage touches, with the stages that touch it. A file appearing in several stages marks a shared surface: double-check the ordering there, and treat one listed by three or more stages as a hotspot to give a single owner (`SKILL.md` § Decompose into stages).

## End-to-end verification

Commands and manual smoke run after the final stage — typically the full suite plus a grep for residue of whatever the track removed. With more than 3 commands or any grep invariants, generate `<plan-slug>-verify-e2e.py`.
