---
name: staged-plan
description: 'Design a multi-stage plan for a chain of fresh-context subagents, gated green-to-green, whose markdown is the full execution contract. Planning only: produces the plan and stops; execution follows the plan file, not this skill. Use when the user wants to decompose a large track into stages or scaffold a staged execution plan.'
---

# Staged Plan

A pattern for executing large tracks as a chain of autonomous subagents, each in its own fresh context window, with the parent gating green-to-green. The plan markdown is **the operational contract** — anyone (or any executor) opening it cold runs it correctly.

## Skill scope — planning only

This skill produces a plan: investigate the codebase (read-only), design stages, run the scaffold, fill the markdown, make the Phase 1.5 landing commit (plan + verify scripts + `.gitignore` rule — no feature work). Then stop, even outside plan mode.

When the user asks to "execute the plan" or "run Stage N", point them to the plan file: its `## Execution model` and hand-off prompts carry everything the executor (the user or another agent) needs.

## When this applies

This is **prompt chaining with sectioning + gate checks** in Anthropic's effective-agents taxonomy: subtasks pre-planned, run strictly sequentially, each gate passing before the next. It fits when:

- the track is too large for one session but splits into 3-7 deliverables knowable at plan time;
- each stage benefits from contextual isolation;
- there are meaningful gates between steps — the green-to-green audit is the main value.

A track that fits one session runs inline; a track whose subtask shape is only knowable at runtime belongs to orchestrator-workers.

## Workflow

| Phase | Owner | What happens |
|---|---|---|
| 1. Plan design | Planner | Investigate → decompose → write checks → approval gate → `scaffold.py` → fill every `<FILL>` |
| 1.5. Plan landing commit | Planner | Commit plan + `_verify.py` + verify scripts + `.gitignore` rule |
| 2. Execution | Parent + subagents | Driven by the plan file's `## Execution model` |

## Phase 1 — Plan design

### 1. Investigate (read-only)

- **Read every Critical file end-to-end**, not grep snippets. Plans built from excerpts produce stages with stale line numbers, missed callers, and hidden dependencies. A file too large to read fully signals the decomposition is wrong — split further.
- **Symbol-fallout scan** (when the plan removes, renames, or changes the signature of an exported symbol): `grep -rn '<symbol>' <repo>` for each one. Every hit outside the declaring file lands in some stage's scope — patched, or deferred with a `// TODO(slice-N)` shim. The backlog specifies *intent*, the grep specifies *fallout*; scaffold only once every call-site is placed.
- **Requirements sweep:** walk the nine themes the source rarely states — validation, failure modes, idempotency/retry, authorization, concurrency/ordering, data lifecycle, external-dependency failure, state transitions, observability. Each lands on a check, on `existing: <where the code already enforces it>`, or on `not in scope — <why>`; the answers fill the plan's `## Swept`. Raising a theme is free; growing scope is the user's call, so a theme that would grow the work goes into the approval summary.
- **One-way doors:** list the choices whose reversal costs more than a refactor — persisted schema, a contract someone else consumes, a new dependency, a data backfill, a pattern the codebase does not have yet. Each gets its literal shape and the alternative rejected, named with the property that disqualified it. A forced choice records the constraint that forced it; a door with a live alternative goes into the approval summary. Decomposition inside an existing convention is reversible and is not a door.
- **Real commands:** read the package manifest, task runner, and CI workflows; prefer commands CI already runs. When nothing exists for what a check needs, ask — a proof that cannot run is worse than none.

### 2. Decompose into stages

- **One observable outcome per stage**, 1-3 backlog items. Every stage commit is green, revertable on its own, and shippable: incomplete user-visible behaviour sits behind a flag or stays unwired. An outcome is never split across stages — the next stage would inherit half of it.
- **Size by reading, not by minutes:** `wc -c` / 4 over the files the stage reads, written on its `**Size:**` line. Keep a stage under ~60k tokens of reading so the rest of the window absorbs iteration (test output, fixes, retries); above ~100k, split. Cut where the code surface changes — the next stage reads different code anyway, so nothing is read twice.
- **Too small to stage:** when the stages' summed `Size` stays under ~30k tokens, the whole track fits one session and staging adds only overhead. The approval summary then leads with that recommendation — `cancel`, and do the work directly without a staged plan — and offers the staged plan as the alternative. A non-interactive caller already asked for a plan: scaffold anyway and say so in the final message.
- **Order by blast radius:** internal/pure-refactor first, public API/UI last, externally-blocked work isolated in a trailing stage. **Risk first overrides it:** an unproven assumption (feasibility, library behaviour, performance) gets a spike stage at the front, so a failure surfaces before later stages invest in it.
- **`Depends on:`** defaults to the previous stage; set it to the real prerequisites when a stage needs fewer. Execution stays sequential — the parent uses it only to tell the user which remaining stages a red stage does not block.
- **Scope by file list:** each stage declares its files explicitly; the subagent STOPs and reports when the work needs a file outside the list. This replaces numeric budgets, which no subagent can observe at runtime.
- **Tier and Effort** per stage, with a mandatory 1-2 line `Tier rationale:` naming the decision or risk that justifies it. The scaffold seeds `standard / standard`:

| Stage shape | Classification |
|---|---|
| 1 file, linear order-of-ops, mechanical edits (rename, move, apply listed pattern) | `mechanical / minimal` |
| 2-5 files, typical coding with light judgment inside the file list | `standard / standard` |
| Decision about scope, callsite discovered mid-work, semantic refactor, non-obvious ordering invariant | `judgment / extended` |
| Security, public/cross-repo contract, data migration, irreversible change | `critical / extended` |

Classify at the cheapest tier that fits: promotion has cost, demotion is free, and >40% of stages should land at `mechanical` or `standard`. The plan names tiers, never models — the executor maps them to its own lineup.

### 3. Write the checks

Every stage carries a `**Checks:**` list — the stage's acceptance bar, fixed for the whole stage and audited row by row in its report, by the parent, and by the reviewer:

```
- C3.1 — POST /tasks with an empty title returns 422 · Proof: `pytest tests/api/test_tasks.py::test_empty_title_422 -v`
- C3.2 — no import of lib-a remains under src/ · Proof: `V.assert_grep_zero(r"from ['\"]lib-a['\"]", ["src/"])`
```

- **One claim per check** — a claim that needs "and" is two checks.
- **A concrete value** — a status code, a field, a bound; never "gracefully", "properly", or "fast".
- **The proof names a specific test or command**, never a whole suite: a green suite settles no single claim.
- **The proof reaches the claim's level:** a claim about a status code or response shape needs a proof that crosses that boundary; a claim over N cases needs a proof over all N (one table-driven test may stand for the set, with its size stated).
- **Refuse rather than guess:** a claim with no nameable proof is too vague to write. Resolve it from the source or the code; when it stays vague, it becomes the single question of the approval gate.

### 4. Reviewer recommendation

- `reviewer: deep` — when ≥2 of: ≥5 stages, public/cross-repo contract change, Docker/CI changes, auth or data migration, multi-repo touch.
- `reviewer: light` — when exactly 1 of those signals is present.
- `reviewer: none` — otherwise (default).

Pass it to `scaffold.py` via `--reviewer` (plus `--reviewer-reason` when not `none`) and state it with the reason so the user can override in one edit:

```
Reviewer: deep — recommended by: 7 stages + public contract + multi-repo. Override with `Reviewer: none` to skip.
```

### 5. Pre-scaffold approval gate (mandatory, both modes)

Phase 1 investigation is **read-only by contract**: no file edits, no `scaffold.py`, no file-creating shell command until the user approves the materialization. The gate lives in the skill so behaviour is identical in every agent, with or without a plan mode.

Present a short summary — slug, title, stage list, mode, working-tree, reviewer + reason, report-policy, plus any sweep theme that would grow scope and any one-way door with a live alternative, each with your recommendation — and request approval through **exactly one** gate. First run `echo "${STAGED_PLAN_NONINTERACTIVE:-0}"`; a gate tool your agent loads on demand counts as available once loaded.

- **Non-interactive** (the echo prints `1` — set explicitly by the calling harness, e.g. `backlog-claude-runner` running a headless session): no human can answer, so scope-growing themes and live doors take your recommendation, recorded in the plan; scaffold and fill straight away. `scaffold.py` prints the `<<PRE_SCAFFOLD_SUMMARY>>` block itself; **open your final message with that same block**, since a headless run (`claude -p`, `codex exec`) typically writes only the final message to stdout. Enter this mode only when the caller set the variable.
- **Plan mode active, with a plan-approval tool** (Claude Code: `ExitPlanMode`): submit the summary through it. Its approval is the gate. The summary is a few lines; the scaffold renders the full plan.
- **Interactive, with a structured-question tool** (Claude Code: `AskUserQuestion`): ask with the summary and options `[scaffold / adjust / cancel]`. `scaffold` → proceed; `adjust` → revise and re-gate; `cancel` → stop. The gate runs even when the plan looks obvious — it is the user's only checkpoint before the landing commit.
- **No gate tool** (an agent without one, or a headless run without the variable): end your turn with the summary as the final message, closing with `Reply scaffold / adjust / cancel`. The user's next message is the gate; nothing is written before it.

### Fixed defaults — recorded verbatim under `## Execution policy`

1. **Mode:** `autonomous` — stages run end-to-end with no pause between them.
2. **Commit authorization:** `per-stage-direct` — each subagent commits after green gates.
3. **Failure handling:** `auto-retry-up-to-2` — re-launch with the failure excerpt and the abandoned approaches, then pause. Scope violations never auto-retry.
4. **Working-tree policy:** `clean-required` when `git status` is clean. Other states: `references/working-tree.md`.
5. **Reviewer gate:** per the recommendation above.
6. **Report policy:** `committed`, or `gitignored` when `.gitignore` already excludes report files (e.g. `*-report.md`, `docs/plans/*-report.md`). Read `.gitignore` to decide.

Deviate only when the user explicitly overrides in the current conversation.

**The one allowed question:** when `git status` is **not clean**, summarize the dirty state and ask the user to choose `stash-authorized`, `integrate-existing`, or `abort-until-clean` (see `references/working-tree.md`). Every other unresolved point goes into the approval summary as a recommendation, so the plan ships with every answer baked in — it is an executable contract, not a discussion document.

### 6. Plan output location (mandatory pre-check)

Run `git rev-parse --show-toplevel` before invoking `scaffold.py`:

- **Fails** (cwd outside a git repo): stop and ask the user to re-invoke from inside the target repo. Phase 1.5 (vendoring `_verify.py`, narrowing `.gitignore`, landing commit) needs a repo.
- **Succeeds:** the canonical output is `<that-path>/docs/plans/<plan-slug>.md`; post-stage reports go beside it. A calling harness may mandate another in-repo location (e.g. `backlog-claude-runner` → `.agents/...`), in which case it sets `STAGED_PLAN_NONINTERACTIVE=1` and passes the absolute path. `<repo>/.claude/plans/` is deprecated — it triggers permission prompts for subagents.

`scaffold.py` enforces this: `--output` must resolve inside a git repo (exit 4 otherwise, unless `--allow-outside-repo`), and a plan at the repo root is rejected. Every boilerplate reference to the plan dir is rewritten from `--output`.

### 7. Scaffold, then fill

The scaffold is the single source of the plan skeleton: it renders ~60% of the plan deterministically (Execution model, Execution policy, Plan landing commit, Executor adapter, Hand-off conventions, Stage 0, per-stage blocks and hand-offs, Reviewer gate, End-to-end summary). You write only the cognitive parts.

`<skill-dir>` is the directory holding this `SKILL.md` — wherever your agent loaded it from (user, project, or plugin install). Use `python` where `python3` is absent (common on Windows).

```bash
python3 <skill-dir>/lib/scaffold.py \
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

Flags: `--mode autonomous|semi-autonomous` · `--working-tree clean-required|stash-authorized|integrate-existing|abort-until-clean` · `--reviewer none|light|deep` (+ `--reviewer-reason`) · `--report-policy committed|gitignored`. The script refuses to overwrite an existing file (exit 3) unless `--force` — run it once, then edit; a re-run destroys the fill.

Fill rules:

1. Replace every `<FILL: ...>`; fill or delete every `<FILL-OR-DELETE: ...>` block (you decide, not the user). The pre-execution gate (`assert_no_placeholders`) refuses to launch Stage 1 while any survives.
2. Use the per-stage HTML anchors (`<!-- STAGE 3: checks -->`) plus the FILL line as the match target of each edit — unique matches without large context, even across 6+ identical stage blocks.
3. `<repo>` is already substituted with the absolute repo root. A literal `<repo>` survives only under `--allow-outside-repo`; substitute it by hand before the landing commit.

Section-by-section guidance, including the hand-off prompt: `references/plan-structure.md`. When to generate a verify script: `references/verify-scripts.md`. A filled example of the cognitive parts: `examples/migration-x.md`.

### End of Phase 1

Always print (the IDE renders a clickable link):

```
Plan file: [<plan-slug>.md](/absolute/path/to/docs/plans/<plan-slug>.md#L1)
```

## Phase 1.5 — Plan landing commit

After approval, the **planner** (not a subagent) makes one commit landing the plan, `_verify.py` and `_report-template.md` (both written by the scaffold), any verify scripts, and the `.gitignore` rule. The procedure — including the `.gitignore` pre-check — is rendered into the plan's `## Plan landing commit` section; follow it there. Afterwards the working tree is clean and Phase 2 can start.

## Phase 2 — Execution

Phase 2 runs from the plan file alone: `## Execution model`, `## Execution policy`, and the per-stage hand-offs, all rendered by the scaffold. The design rationale behind them and the optional hardening (hooks, run log) live in `references/execution.md` — reach for it when changing the execution contract itself.

## Invariants every plan holds

- Each stage reaches its subagent fully formed: the subagent executes, the planner already planned.
- Hand-off prompts stand alone — they point to the plan, git, and prior reports, never to a previous conversation.
- One stage per subagent, with no nested subagents: contextual isolation and the green-to-green audit are the point.
- Hand-offs stage files by explicit path and tell the subagent to grep for symbols, since line numbers drift once Stage 1 lands.
- The parent re-runs every proof itself; a subagent's report is a claim, not evidence.
