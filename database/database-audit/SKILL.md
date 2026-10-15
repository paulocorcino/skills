---
name: database-audit
description: Audit a database and the code that uses it for cost and common problems, ranked High / Medium / Low with measured evidence, then deepen the finding the user picks.
disable-model-invocation: true
---

Find where a database and its code spend the most — CPU, reads, time — and where they carry the common problems that cost money or correctness, then hand the user a ranked report and deepen the finding they pick. Two leading words carry the audit:

- **Follow the cost.** Start from what the engine already records about its own spending, trace the costliest statements to the code that issues them, and sweep that hot code first. Cold code earns attention only for correctness problems.
- **Evidence** comes in three kinds, and every finding names its kind: **measured** (the engine's statistics or a plan show it), **structural** (the catalog or the code shows it), **speculative** (a heuristic suggests it). A gain is claimed only from measured evidence.

Standing rules:

- **Numbers, never values.** Every live read goes through the measurement tool (`measure_<dialect>.py`, step 1): it reports counts, times, reads, and plan shapes, with query text normalized (literals → `?`) and parameter values never printed. Query results, row samples, and compiled parameter values stay out of the conversation and the report.
- **Read-only.** The audit changes nothing in the database — no index created, no statistic updated, no setting changed, wherever the evidence points. When the adoption's extractor is present, its `probe` classifies the account first; a write-capable account pauses for the user's acceptance, as in the adoption. The measurement tool's `run` executes a statement, so it runs only on a copy of the database, or in production with the user's authorization for that statement and window.
- **References read-only.** The tools this skill ships in `scripts/` are copied into the project and evolve there; a copy that ends ahead of the reference is reported as a harvest candidate, carried into the skill only in maintenance outside the run.
- **Delegation.** Where the agent can dispatch subagents and choose their model, mechanical work — running a tool and summarizing its numbers, searching the code for a problem's pattern, locating the code that issues a statement — goes to the smallest capable model, returning conclusions, not dumps. Judgment stays in the main session: severity, evidence kind, the report, anything put to the user.

## 1. Scope and sources

Establish what the audit can read. The repo: the application code (any path the user points at), and the `db-schema/` kit when it exists. The database: the connection recipe in `.env`, and the engine. Copy the reference measurement tool for that engine from `scripts/` into the project (`db-schema/tools/` when the kit exists, `.scratch/audit/tools/` otherwise); when no reference covers the engine, build its port from [`COST-SOURCES.md`](COST-SOURCES.md) and the reference's porting contract, by trial and error against the live database. Run `sources`.

Done when the user knows which branches run — the static sweep always, the live branch when a cost source is readable — and the window the numbers cover (Query Store retention, time since the server started). When no cost source is readable, say which permission or setting would open one (`COST-SOURCES.md`) and run the static branch; that recommendation is itself a finding.

## 2. Follow the cost (live branch)

Run `top --by cpu` and `top --by reads`, then `indexes`, then `plan` for each of the costliest statements (the top ten, or every statement above 5% of total CPU or reads). Read the plans for the problems [`COMMON-PROBLEMS.md`](COMMON-PROBLEMS.md) names: scans where a seek fits, implicit conversions, missing indexes, estimated-versus-actual row gaps, single-use plans, a statement whose duration spreads widely across plans.

Done when every statement above the threshold has its numbers and its plan summary.

## 3. From cost to code

Trace each costly statement to the code that issues it: a stored routine by its object name, application code by the statement's normalized shape, the ORM call that generates it, or the loop that repeats it — **every costly statement traced, or flagged *origin unknown***. Then sweep the code for the problems in `COMMON-PROBLEMS.md`: the hot code first, the rest only for the problems marked as correctness risks. With no live branch, the sweep covers the code and the carved DDL, prioritized by structural signals — request handlers, loops, report and batch paths.

Done when every costly statement has its origin or its flag, and the checklist has been swept across the hot code.

## 4. Classify

Give every finding a severity, an evidence kind, and a location, using the rules in `COMMON-PROBLEMS.md`:

- **High** — a measured large share of the cost (by default ≥ 20% of CPU or reads in the window), or a correctness risk (selling stock that doesn't exist, money in binary floating point, a dirty read deciding a write, a protected rule without its guard, SQL built by concatenating input).
- **Medium** — a measured moderate share (5–20%), or a structural problem with a likely impact on a hot path.
- **Low** — hygiene, or a cost under 5%.

A speculative performance finding is never High. State the thresholds you used in the report.

Done when every finding carries its severity, evidence kind, and location (file and line, or database object).

## 5. Report

Write `docs/db-model/audit/YYYY-MM-DD.md` (`docs/audit/` when the repo has no model docs): the window and sources the numbers cover; a summary — how many High, Medium, Low; **one top recommendation** — what to do first if only one thing gets done, and why; then one card per finding, High first:

```markdown
### H1 — <problem, in the domain's words>
- **Severity / evidence:** High / measured
- **Numbers:** <cpu share, executions, per-execution cpu / reads / time, rows>
- **Where:** <file:line or object> — <how the cost reaches it>
- **Problem:** <what goes wrong, in plain words>
- **Proposed change:** <the change, not yet applied>
- **Expected benefit:** <measured, or "unproven until measured">
- **Risk and reversibility:** <what could break; how to undo>
- **Route:** <modeling decision · ticket · protected change sequence · ADR>
```

Leave the report staged for the user to commit. Done when the report is written and the user is asked which card to deepen.

## 6. Deepen the chosen card

- **A performance change** is proven before it is proposed as a ticket: the plan before and after on a copy of the database carrying the change (an index, a rewritten predicate), and `run` measurements on that copy — or in production only with the user's authorization. The card's expected benefit becomes measured, or the card says it stayed unproven.
- **A modeling problem** goes to the `database-modeling` grill, on the theme it touches.
- **A rule tagged [protected]** changes only through the change sequence in `docs/db-model/calc/README.md`.
- **A code fix** becomes a ticket carrying its card.

The audit proposes; DDL lands through `db-schema/` and its migrations, code through its own review.
