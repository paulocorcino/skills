---
name: lint-gate
description: Tighten a repo's linters to a hard gate for agent-written code, and plan the transition when the lint debt is large. Use when the user wants to audit a repo's lint setup, adopt strict linters, pay down lint debt with a ratchet, or refresh this skill's references.
---

# Lint gate

Correctness is not merely what the compiler accepts. Agents write code the way a junior on a deadline does: they take whatever path the tooling lets through. A rule written only in a doc is _advice_; a rule a tool checks is a _gate_. The gate is the senior reviewer: it says no the same way on every change, and it never tires. This skill takes a repo to the hard gate: it measures the _debt_ (the _sites_ each target rule fails on today), sets the tightness with the developer, flips every rule with zero debt to error, and writes a transition plan for the rest. The end state is tight: every rule an error, no baseline left, each remaining exception inline with its reason and counted by a _ratchet_.

## The gate

The seven properties of the end state, and the yardstick of every step:

1. **Every rule is an error.** No warn level: a warning that does not fail the gate is noise nobody reads.
2. **Every tool runs at a pinned version**, and CI checks the binary by checksum. A version bump is its own commit, re-measured.
3. **The local gate is the CI gate.** One command runs every check; CI runs the same checks, and a test fails when a CI step has no local twin.
4. **Every exception says why**, inline, next to the code it excuses. An exception with no reason fails; one that suppresses nothing fails.
5. **Every rule in the agent docs has a check** (`AGENTS.md`, `CLAUDE.md`, contributing guides). A rule with no check is advice.
6. **A count only goes down**: a baseline, a list of exceptions, a count of a forbidden pattern.
7. **Shift left.** Each check runs at the leftmost point it can afford: the fast linters in the agent's edit loop (the editor reads the same config; a per-edit hook runs them on the changed files and hands the output back), the whole set in the local gate, the slow ones (mutation, the platform matrix) in CI. The agent sees the failure before it says done.

Every tool approximates: no checker decides a semantic property exactly, so each rule trades false positives for false negatives. A 0 from a heuristic rule means no site matched its pattern, not that the property holds; an exception is the place where the rule's approximation is wrong.

One tool per property. When two tools cover one property (oxlint and ESLint, mypy and pyright, two complexity scores), the repo keeps the one it has. A switch is a `decision` backed by a measure on this repo: the run time of each, and the sites each finds that the other misses. A tool's merits come from that measure, never from memory.

The target only moves up. A target rule that is pure noise for this repo is turned off in the config with its reason beside it, and listed for the human as a `decision`.

**Close the exits.** An exit is a way to turn the gate green without fixing the code: a warn level, a bypass flag, an unasked edit to a config or a debt list, a blanket suppression, a path no check reads, a skipped or weakened test. Each exit gets a check (`references/repo.md` § Exits); an exit no tool can close is listed for the human, never left silent.

**A script decides what a script can decide.** Counting, the debt list, the shrink check and the drift check are the scripts' (`scripts/`): run them, and copy their output instead of retyping it. Judgment goes where only judgment can work: a fix recipe at one site, and the decisions the human owns.

## Steps

A request to refresh the references runs `references/maintenance.md` instead of these steps.

### 1. Inventory

For each stack in the repo: its tools, their versions and whether each is pinned, the config files, and where each check runs (local command, CI step). Map every CI check to its local command. Find the canonical agent doc and the files that point at it or copy it. Map every rule of the agent docs to the check that enforces it. Each `advice` rule a tool could check goes up the ladder of `references/repo.md` § Agent docs; the ones whose cheapest rung is an ast-grep rule are its candidates.

The stacks with a target are Rust, TypeScript, Python and Go. Any other stack gets the gate properties and `references/repo.md`, and the report says it has no target reference.

Done when every stack has a row, every CI check is `local: <command>` or `CI only`, and every agent-doc rule is `checked by <check>` or `advice`.

### 2. Measure

Read `references/repo.md` and `references/<stack>.md` for each stack present.

**Refresh the reference first.** A reference is a cache: its `As of` line names the date and the versions it was checked against, and the tool at its current version is the source of truth. Run `scripts/drift.py age` over the references that name tools (`repo.md`, each `<stack>.md` present, and `ast-grep-guide.md` when ast-grep is in the run): it asks the registries for each tool's latest stable release. Pin each tool at that release unless the repo pins a newer one.

- `research: required` (an old date, a newer major, a registry that did not answer): do the research of `references/maintenance.md` before the drafts. It finds what no rule list shows: a new tool for a property, a tool abandoned, a default changed.
- A pin newer than the `As of` version: run `drift.py diff` over the rule lists of both versions and `drift.py check` over each draft:

- a name the tool does not know, or marks removed: its successor from the changelog, or out of the draft;
- a deprecated name: its successor;
- an added rule: into the draft when it belongs to a class (§ Rule classes), measured like the rest; one with no class stays out, listed.

Each drift found, from `diff`, `check` or the research, is a line of `<scratch>/reference-drift.md` in the form of `references/maintenance.md`. The run leaves the skill's own files as they are: the report points at that file, and maintenance applies it.

Write each target config as a _draft_ in a scratch directory outside the repo, run the tool over the repo with the draft and machine-readable output, and tally it:

```
python <this skill>/scripts/tally.py <format> <tool output> --json <scratch>/<tool>.json --scope-depth <N>
```

`--help` lists the formats and modes. `tally.py diff A.json B.json` gives the sites of B that are not in A: it splits test sites from production when the tool cannot. The repo's own configs stay untouched in this step.

For each knob (§ Knobs), measure its _curve_, the debt at each candidate value: run the tool once with the limit set very low (complexity 1, arguments 0) and read it with `tally.py curve`; file size and line width come from `tally.py sizes`.

- A count of 0 is evidence only when the run demonstrably checked the code: the same run reports other sites, or its file count matches the inventory. A run that built nothing, or matched no files, also exits 0. A `warning:` from `tally.py` means part of the code was never checked.
- A draft outside the repo can read paths from its own folder: check that the draft run read the same files as the repo's own run, and no more (a vendored directory counted is the usual sign).
- Existing suppressions are debt too: count them (each stack reference names its forms).
- Each exit of `references/repo.md` § Exits is `closed by <check>` or `open`.
- Record the commit SHA, every tool version and every command: the plan repeats them.

Done when `drift.py age` ran over every reference read, and each `research: required` has its harvest lines; `drift.py check` passes on every draft; every row of every reference read, and every added rule taken in, has one of: sites (production and test, per scope), `n/a — <why>`, or `decision — <question for the human>`; and every knob has its curve. `scripts/rows.py list <references read>` prints those rows as the Coverage table of the plan; a row is never skipped in silence.

### 3. Set the tightness

Interview the developer in one round, after the measure, so every question carries its data:

- **A knob** shows its curve, the reference value as the recommendation, and the tightest value that costs nothing today. It asks two things apart: the _end state_ and the _pace_. A large debt is a pace answer (a ceiling in steps), not a reason for a looser end state; an end state looser than the reference goes in the plan with its reason.
- **A decision** names the options and what each costs, with a recommendation.
- **ast-grep**, two questions (`references/repo.md` § ast-grep): for the agent's navigation, in every repo, with the measured gain; for gate rules, when step 1 found candidates, each draft rule with its sites and its probe count.
- The seven gate properties are the gate itself, not knobs: they stay out of the interview.

With nobody to answer (a headless run), take the reference values and the recommendations, mark each `default taken` in the plan, and list beside each knob the tightest value that costs nothing, for the developer to take later. The answers land in the drafts; the plan's Target section records each choice with its reason. Measure again every rule whose knob moved.

Done when every knob has an end state and a pace, every decision has an answer or `default taken`, and the counts match the chosen values.

### 4. Classify

Give each rule with sites one class (§ Rule classes), one strategy (§ Strategies) and a phase (§ Phase order).

Done when no rule with sites is left without all three.

### 5. Flip zero debt

On a branch of its own: pin each unpinned tool, set every 0-site rule to error in the real config, raise each `warn` whose count is 0 to error, and add each missing tool with 0 findings to the local gate and to CI. An approved ast-grep goes in pinned (`references/repo.md` § ast-grep); with gate rules, their tests join it, the rules at 0 sites at `error`, the others in the plan. It also brings the agent's guide, from `references/ast-grep-guide.md`, checked against ast-grep's own docs for agents at the pin, with each command in it run once on this repo. A repo with no single gate command gets it as Phase 0 of the plan; this step then edits only the configs.

- **A group goes on with its debt list.** For a lint group or category (`pedantic`, `rust_2018_idioms`, an oxlint category, a new plugin), `scripts/debt.py` prints the block: the group on, and each rule with sites off under a `debt: N sites` comment, each noise rule under `noise: <reason>`. Paste the block as printed. A new plugin also brings its rules of the categories already on; `debt.py` counts them.
- **The list only shrinks.** Add `debt.py shrink` against the base branch to the gate and to CI, for every config that holds a debt list. On the change that brings the first list the base has none, and `shrink` passes.
- **The edit keeps the file as the repo writes it**: its line endings, and every comment on its own line (a repo's own reader of the config may strip only whole-line comments).
- **A gate property that contradicts an accepted decision** (an ADR, a documented convention) is not flipped: it goes to the plan as a `decision`, with the decision it would amend.

Run the whole gate. A rule that turns it red was mis-measured: revert that rule, measure it again, and classify it.

Then write the lint gate block into the canonical agent doc, from `references/agent-docs.md`, for the gate as this step leaves it. Commit when the user has authorized commits, on the step's branch: one commit per tool added or bumped, then one for the flips and the agent doc; otherwise leave the diff for review. A tool that needs more than a pin (a new CI install, a new toolchain component) goes to Phase 0 of the plan.

Done when the gate is green with every 0-site rule at error, `debt.py shrink` runs in the gate and in CI, the flipped rules are listed, and the agent doc names the gate, the fast loop, the recipe of each class that has a rule on, and a pointer to each guide installed, with no rule, number or version in it.

### 6. Write the transition plan

When any target rule is not yet an error, write the plan from `references/transition-plan.md`, in the language of the repo's docs, at `docs/lint-transition.md` or the repo's folder for plans when that folder is versioned: the debt comments in the configs point at the plan, so the plan is versioned with them. Copy `scripts/` next to it, so its commands run without this skill.

Done when `rows.py check <plan> <references read>` passes, and `rows.py keys <stack references> --in <the repo's configs> <plan>` names every key of the target configs; every rule not yet on sits in exactly one phase with its count, strategy, fix recipe and done criterion; every `decision` is listed for the human; and the plan runs cold, by an agent that does not have this skill.

### 7. Report

Tell the user: the knobs as set, the rules flipped, the debt table (largest first), the plan's path, the decisions waiting on them, and the drift found against the references (versions, names added, renamed, removed, tools found), with the path of `reference-drift.md`.

## Knobs

The numeric limits and the optional families: the part of the target the developer tunes in step 3. The reference is the recommendation.

| Knob | Reference | Curve |
|---|---|---|
| Function complexity | 10 | `curve` of the complexity rule of each stack, run at limit 1 |
| Nesting depth | 3 | the count of the depth rule at 2, 3 and 4 |
| Arguments | 5 (Rust, Python, Go), 4 (TypeScript) | `curve` of the argument rule, run at limit 0 |
| File size | 500 non-blank lines | `sizes` |
| Line width | 100 | `sizes` |
| Clone size | 50 tokens and 5 lines (`minTokens`, `minLines` of jscpd) | `curve` of the jscpd run at `--min-tokens 30` |
| Inline test block | no reference | a count of test blocks per size |
| Coverage of the diff | no reference | the coverage tool's report on the last changes, or `not measured — <why>` when it needs a toolchain change |
| Optional families | `clippy::pedantic`; docs on a published library's public API; `indexing_slicing` in parsing code; the anti-slop rules (TypeScript); mutation testing on the diff | the counts from step 2 |

## Rule classes

A rule's class carries its fix recipe, so the plan writes one recipe per class instead of one per rule:

- **Dropped value**: a value whose flow ends before any reader sees it: an ignored `Result` or error, a floating Promise, a blind `except`, an assignment never read, a write whose outcome nobody checks. Fix: the value reaches its caller or a log line.
- **Fail fast**: code that hides a failure behind a fallback (a default on a missing value, a condition the types already rule out, a catch that recovers into a wrong state). Fix: remove the fallback; the failure surfaces at the boundary that can act on it.
- **Escape hatch**: the checker is told to look away: `any`, a cast, a non-null `!`, `unwrap`, a bare `type: ignore`. Fix: parse, don't validate: narrow the value once, at the boundary, into a type the checker reads.
- **Capability**: a call allowed in one place only: `print` or `console` outside the output or logging module, a process spawn outside the module that owns spawns, `exit` outside `main`, the environment written outside startup. Fix: route the call through the module that owns it; that module carries the one exception, with its reason. When no module owns the capability yet, the rule is `decision first`.
- **Shape**: complexity, nesting depth, argument count, file size, a duplicated block. Fix: let the data structure the program (a table of cases, a `match` on a tuple), guard clauses, a split along a responsibility the code already has. A file over the size limit is a god file and a function over the complexity limit a god function: each is split by the responsibilities it already carries, one module or function per responsibility. Don't patch bad code, rewrite it. A clone is one rule written twice, or two rules that only look alike: one rule becomes one function or constant named for that rule; two rules stay two, and the clone carries the tool's ignore marker with the reason they change for different reasons.
- **Surface**: format, naming, import order. Fix: the tool's own command.

## Strategies

- **On now.** 0 sites: step 5 flips it. A group goes on now as a whole, with its debt list: the rules with no site are on from that commit, and each later fix only deletes a line.
- **Fix then flip.** Sites with a local fix (a rewrite at the site, no design change). Cut the sites into _slices_ by scope (a crate, a package, a directory) small enough for one review. Where the config can scope a rule (overrides, per-file settings), flip it per scope as each scope reaches 0, so the gain is locked early. Where one table governs every scope (a workspace lint table), measure with the draft and flip once, in the slice that removes the last site.
- **Baseline ratchet.** Sites whose fix is a redesign: complexity, file size, type escapes. A committed baseline lists every offender by identity (path and name, never a line number) and value. The check fails when an offender is missing from the baseline, when a value rises above its entry, and when a value falls or an entry is gone and the baseline was not updated: the last rule makes each fix lower the baseline. A renamed or moved offender is new, so it must pass.
- **Count ratchet.** Sites whose identity moves when the code moves, such as the clones of a duplication tool. The check that refuses a new site stays (jscpd against the base branch), and the total is a constant that only goes down: `tally.py <format> <output> --expect N` fails above N and below N, so the change that removes a clone lowers N.
- **Ceiling in steps.** A numeric limit with a wide spread (complexity from 11 to 200). The baseline gets a ceiling that drops in steps (for a limit of 10: 50, 30, 20, 15, 10), each step one work item cut by file. A step has no date: a date pushes code into helpers with no responsibility. The last step deletes the baseline. The rule becomes a plain error, and whatever cannot reach the limit carries an inline exception with its reason, counted by a ratchet; a human reviews each one.
- **Decision first.** The rule needs a design choice a human owns: which module owns process spawns, the layer boundaries, how a test waits, the error type. It is a question in the plan, and its phase starts once the answer is in.

## Phase order

- **Phase 0 is the gate itself**: pinned versions, the one local command, CI running the same checks, no warn level.
- **A strategy whose every fix writes a shared file** (a baseline) runs first or alone: otherwise every other phase rewrites that file too.
- **Phases that touch the same files run in sequence**; phases over disjoint code may run side by side.
- **A mass change made by a command** (a reformat) lands when no long branch is open, and is redone by the command instead of merged by hand.
- **Cheap phases go early**: few sites with a mechanical fix shrink the noise for the rest.
