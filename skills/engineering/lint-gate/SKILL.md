---
name: lint-gate
description: Tighten a repo's linters to a hard gate for agent-written code, and plan the transition when the lint debt is large. Use when the user wants to audit a repo's lint setup, adopt strict linters, pay down lint debt with a ratchet, track the burndown of a plan it wrote, start a new repo under the gate, or refresh this skill's references.
---

# Lint gate

Correctness is not merely what the compiler accepts. Agents write code the way a junior on a deadline does: they take whatever path the tooling lets through. A rule written only in a doc is _advice_; a rule a tool checks is a _gate_. The gate makes the wrong thing hard to do: it says no the same way on every change. This skill takes a repo to the hard gate: it measures the _debt_ (the _sites_ each target rule fails on today), sets the tightness with the developer, flips every rule with zero debt to error, and writes a transition plan for the rest. The end state is tight: every rule an error, no baseline left, each remaining exception inline with its reason and counted by a _ratchet_.

## The gate

The seven properties of the end state, and the yardstick of every step:

1. **Every rule is an error.** No warn level: a warning that does not fail the gate is noise nobody reads.
2. **Every tool runs at a pinned version**, and CI checks the binary by checksum. A version bump is its own commit, re-measured.
3. **The local gate is the CI gate.** One command runs every check; CI runs the same checks, and a test fails when a CI step has no local twin.
4. **Every exception says why**, inline, next to the code it excuses. An exception with no reason fails; one that suppresses nothing fails.
5. **Every rule in the agent docs has a check** (`AGENTS.md`, `CLAUDE.md`, contributing guides). A rule with no check is advice.
6. **A count only goes down**: a baseline, a list of exceptions, a count of a forbidden pattern. A move is not a rise: a count of exceptions rises only in the commit that takes at least as many sites off a debt list (a lint off for the workspace becomes a named exception per crate: the sites stay, each now under an exception with its reason), with both counts in the commit message.
7. **Shift left.** Each check runs at the leftmost point it can afford: the fast linters in the agent's edit loop (the editor reads the same config; a per-edit hook runs them on the changed files and hands the output back), the whole set in the local gate, the slow ones (mutation, the platform matrix) in CI. The agent sees the failure before it says done.

Every tool approximates: no checker decides a semantic property exactly, so each rule trades false positives for false negatives. A site of a heuristic rule is a _smell_: a sign to read the code there, not proof of a defect. A 0 from a heuristic rule means no site matched its pattern, not that the property holds; an exception is the place where the rule's approximation is wrong.

One tool per property. When two tools cover one property (oxlint and ESLint, mypy and pyright, two complexity scores), the repo keeps the one it has. A switch is a `decision` backed by a measure on this repo: the run time of each, and the sites each finds that the other misses. A tool's merits come from that measure, never from memory.

**A rule earns its place by the defect it prevents**, and its class (§ Rule classes) names that defect. A rule that prevents none, a choice between forms that behave the same, is a Convention: the repo chooses it in step 3, the target does not impose it. Hard where there is a defect, asked where there is only a taste. On every other class the target only moves up: a target rule that is pure noise for this repo is turned off in the config with its reason beside it, and listed for the human as a `decision`.

**Close the exits.** An exit is a way to turn the gate green without fixing the code: a warn level, a bypass flag, an unasked edit to a config or a debt list, a blanket suppression, a path no check reads, a skipped or weakened test. Each exit gets a check (`references/repo.md` § Exits); an exit no tool can close is listed for the human, never left silent.

**A script decides what a script can decide.** Counting, the debt list, the shrink check, the drift check, the evidence held to the record and the phases that can start are the scripts' (`scripts/`): run them, and copy their output instead of retyping it. Judgment goes where only judgment can work: a fix recipe at one site, and the decisions the human owns.
## Steps

A repo with a lint transition plan this skill wrote (its record `lint-record.json` beside it, or the plan alone) runs `references/burndown.md` instead of these steps, unless the user asks for a fresh diagnosis. A repo with no code yet, or whose measure in step 2 finds no site but an owner module's use of its own capability, follows `references/skeleton.md`. A request to refresh the references runs `references/maintenance.md`.

### 1. Inventory

For each stack in the repo: its tools, their versions and whether each is pinned, the config files, and where each check runs (local command, CI step). Map every CI check to its local command. Find the canonical agent doc and the files that point at it or copy it. Map every rule of the agent docs to the check that enforces it. Each `advice` rule a tool could check goes up the ladder of `references/repo.md` § Agent docs; the ones whose cheapest rung is an ast-grep rule are its candidates.

The stacks with a target are Rust, TypeScript, Python and Go. Any other stack gets the gate properties and `references/repo.md`, and the report says it has no target reference.

An optional family whose measure brings outside code into the scratch folder (anti-slop: `references/typescript.md` § Optional family) is named to the user now, with its source and the commit to fetch, so step 2 can measure it: the fetch waits for their yes. With nobody to answer, nothing is fetched, and its rows read `not measured — no yes to fetch outside code`.

Done when every stack has a row, every CI check is `local: <command>` or `CI only`, every agent-doc rule is `checked by <check>` or `advice`, and each family that fetches code has the user's yes or no.

### 2. Measure

Read `references/repo.md` and `references/<stack>.md` for each stack present.

**Refresh the reference first.** A reference is a cache: its `As of` line names the date and the versions it was checked against, and the tool at its current version is the source of truth. Run `scripts/drift.py age` over the references that name tools (`repo.md`, each `<stack>.md` present, and `ast-grep-guide.md` when ast-grep is in the run): it asks the registries for each tool's latest stable release. Pin each tool at that release unless the repo pins a newer one.

- `research: required` (an old date, a newer major, a registry that did not answer): do the research of `references/maintenance.md` before the drafts. It finds what no rule list shows: a new tool for a property, a tool abandoned, a default changed.
- A pin newer than the `As of` version: run `drift.py diff` over the rule lists of both versions and `drift.py check` over each draft:

- a name the tool does not know, or marks removed: its successor from the changelog, or out of the draft;
- a deprecated name: its successor;
- an added rule: into the draft when it belongs to a class (§ Rule classes), measured like the rest; one with no class stays out, listed.

Each drift found, from `diff`, `check` or the research, is a line of `<scratch>/reference-drift.md` in the form of `references/maintenance.md`. **Germline and soma:** the skill's references and scripts are the germline, read-only in every run; the repo's configs and the plan's copy of the scripts are the soma, which fits this repo. The report points at the harvest file, and maintenance carries what proved itself into the germline.

Write each target config as a _draft_ in a scratch directory outside the repo, run the tool over the repo with the draft and machine-readable output, and tally it:

```
python <this skill>/scripts/tally.py <format> <tool output> --json <scratch>/<tool>.json --scope-depth <N>
```

`--help` lists the formats and modes. `tally.py diff A.json B.json` gives the sites of B that are not in A: it splits test sites from production when the tool cannot. The repo's own configs stay untouched in this step.

For each knob (§ Knobs), measure its _curve_, the debt at each candidate value: run the tool once with the limit set very low (complexity 1, arguments 0) and read it with `tally.py curve`; file size and line width come from `tally.py sizes`.

- A count of 0 is evidence only when the run demonstrably checked the code: the same run reports other sites, or its file count matches the inventory. A run that built nothing, or matched no files, also exits 0. A `warning:` from `tally.py` means part of the code was never checked.
- A draft outside the repo can read paths from its own folder: check that the draft run read the same files as the repo's own run, and no more (a vendored directory counted is the usual sign).
- **Auto-fix**: where the tool reports its own fix, `tally.py` splits each rule's sites into `safe` (the fix keeps behavior), `unsafe` (it may change it) and the rest, which need a hand.
- Existing suppressions are debt too: count them (each stack reference names its forms).
- Each exit of `references/repo.md` § Exits is `closed by <check>` or `open`.
- Record the commit SHA, every tool version and every command: the plan repeats them.

Done when `drift.py age` ran over every reference read, and each `research: required` has its harvest lines; `drift.py check` passes on every draft; every row of every reference read, and every added rule taken in, has one of the verdicts `rows.py` accepts (`sites N`, `on`, `phase N`, `closed by <check>`, `open`, `decision — <question>`, `n/a — <why>`, `out — <why>`), sites split production and test, per scope; and every knob has its curve, an optional family included: its curve is its counts, rule by rule. Run `tally.py` from the repo root: it makes paths relative to the current folder, and `--scope-depth` groups by them. `scripts/rows.py list <this skill's SKILL.md> <references read>` prints those rows, the knobs first, as the Coverage table of the plan; a row is never skipped in silence, and a knob or a family is never a `decision` with no count: the question carries its data.

### 3. Set the tightness

Interview the developer in one round, after the measure, so every question carries its data:

- **A knob** shows its curve, the reference value as the recommendation, and the tightest value that costs nothing today. It asks two things apart: the _end state_ and the _pace_. A large debt is a pace answer (a ceiling in steps), not a reason for a looser end state; an end state looser than the reference goes in the plan with its reason.
- **An optional family** shows its counts rule by rule, and the question is which of its rules go on, each with its class.
- **A decision** names the options and what each costs, with a recommendation.
- **The conventions**, one question for all of them: a table of each Convention rule with sites, its count, and how many of them are `safe`. The question says what a convention buys: one form for every reader, never a defect avoided. The recommendation: on, as Fix by command, when every site is `safe`, and its fix command then runs in the fast loop beside the formatter, so the agent never spends a turn on it; off otherwise, under `noise: convention (<Dn>)`. The developer may take them one by one.
- **ast-grep**, two questions (`references/repo.md` § ast-grep): for the agent's navigation, in every repo, with the measured gain; for gate rules, when step 1 found candidates, each draft rule with its sites and its probe count.
- The seven gate properties are the gate itself, not knobs: they stay out of the interview.

With nobody to answer (a headless run), take the reference values and the recommendations, mark each `default taken` in the plan, and list beside each knob the tightest value that costs nothing, for the developer to take later. The answers land in the drafts; the plan's Target section records each choice with its reason. Measure again every rule whose knob moved.

Done when every knob has an end state and a pace, every decision has an answer or `default taken`, every Convention rule with sites is on or off, and the counts match the chosen values.

### 4. Classify

Give each rule with sites one class (§ Rule classes), one strategy (§ Strategies) and a phase (§ Phase order).

Done when no rule with sites is left without all three.

### 5. Flip zero debt

On a branch of its own: copy `scripts/` whole into the repo beside where the plan will live, under a name of its own (`docs/lint-scripts/`; the gate's `debt.py shrink` needs it now) and add `python <the copy>/gate.py --tests` to the gate and to CI; and pin each unpinned tool, the language toolchain included, at the release step 2 measured with (a toolchain with known vulnerabilities is pinned at the first release that fixes them, re-measured); set every 0-site rule to error in the real config, raise each `warn` whose count is 0 to error, and add each missing tool with 0 findings to the local gate and to CI: a tool the stack's own lockfile installs (a dev dependency, a Go tools module) goes in now; one that needs a binary download checked by checksum goes to the plan's `gate` lane. An approved ast-grep goes in pinned (`references/repo.md` § ast-grep); with gate rules, their tests join it, the rules at 0 sites at `error`, the others in the plan. It also brings the agent's guide, from `references/ast-grep-guide.md`, checked against ast-grep's own docs for agents at the pin, with each command in it run once on this repo. A repo with no single gate command gets it as Phase 0 of the plan; this step then adds its checks to the configs and to CI, and the agent doc names the CI steps to run until the command exists.

- **A group goes on with its debt list.** For a lint group or category (`pedantic`, `rust_2018_idioms`, an oxlint category, a new plugin), `scripts/debt.py` prints the block (`oxlint`, `clippy`, `golangci`, `ruff`, `mypy`): the group on, and each rule with sites off under a `debt: N sites` comment, each noise rule under `noise: <reason>`. Paste the block as printed; the target's own off-list (the reference's noise rules) goes in through `--noise`, so one block holds both. A new plugin also brings its rules of the categories already on; `debt.py` counts them. `debt.py oxlint` takes the draft (`--draft`): a rule comes on with the options the draft gives it, and a rule or category the config holds at `warn` comes on like the rest.
- **The list only shrinks.** Add `debt.py shrink` against the base branch to the gate and to CI, for every config that holds a debt list. On the change that brings the first list the base has none, and `shrink` passes.
- **New code meets the whole target.** A rule on the debt list is off for every line, the new ones too, so without this check its debt grows unseen until a burndown. Copy the drafts into `lint-drafts/` beside the plan, and add to the gate and to CI a draft run followed by `tally.py added <format> <output> --base <merge base>` (`git merge-base HEAD origin/<default branch>`, or the local default branch when there is no remote): a site on a line the change adds fails, debt rule or not. A line the change only moves stays the plan's: `added` passes an added line whose text, layout apart, the change also removes, so a file split or a reformat carries its sites along and adds none. The draft run leaves the copy of the scripts out by path: a draft passed as the tool's config replaces the config the copy ships. It exits 1 when it finds sites, so that step fails only on another code (a crash). `--ignore` leaves out the rules that report a line the change did not write (complexity and size, held by their baselines).
- **The edit keeps the file as the repo writes it**: its line endings, and each `debt:` and `noise:` comment on its own line (a repo's own reader of the config may strip only whole-line comments; `debt.py shrink` reads both forms).
- **A gate property that contradicts an accepted decision** (an ADR, a documented convention) is not flipped: it goes to the plan as a `decision`, with the decision it would amend.

Run the whole gate (with no gate command yet, every check this step put in CI, run locally in its order). A rule that turns it red was mis-measured: revert that rule, measure it again, and classify it.

Then write the lint gate block into the canonical agent doc, from `references/agent-docs.md`, for the gate as this step leaves it. Commit when the user has authorized commits, on the step's branch (or the branch the user named), in this order: the copy of the scripts and the drafts; one commit per tool whose version moves from the one the repo pinned or locked, with both versions in its message; the tools added, with the gate and CI wiring; the flips with their debt lists and the agent doc. Otherwise leave the diff for review.

Done when the gate is green with every 0-site rule at error, `debt.py shrink` and the copy's `gate.py --tests` run in the gate and in CI, the flipped rules are listed, and the agent doc names the gate, the fast loop, the recipe of each class that has a rule on, and a pointer to each guide installed, with no rule, number or version in it.

### 6. Write the transition plan

When any target rule is not yet an error, write the plan and its evidence from `references/transition-plan.md`, in the language of the repo's docs, at `docs/lint-transition.md` (the evidence `docs/lint-evidence.md` beside it) or the repo's folder for plans when that folder is versioned: the debt comments in the configs point at the plan, so the plan is versioned with them. The copy of `scripts/` that step 5 made sits beside it, so its commands run without this skill. The copy is gated, not excluded: its tests run in the gate, ruff reads the `ruff.toml` it ships, and the clone count reads it like any code. A repo linter that cannot take the copy's own config (mypy, a second Python linter) leaves the folder out, with the reason that `gate.py` holds it. The plan's own code blocks are excluded from the clone count, with the reason (`repo.md` § Exits).

Write the record beside the plan, the base of every burndown (`references/burndown.md`): the drafts are in `lint-drafts/` (step 5; configs no tool of the gate reads as code), each measure command pointed at them and run from the repo root (a draft that resolves paths from its own folder reads the repo's: golangci-lint `run.relative-path-mode: wd`; the draft run reads the same files as the repo's run); a path to the scratch folder in a command is written `$SC`, the variable `progress.py commands` tells its reader to set; only a run whose tool the repo pins goes in the record, the others are named in the evidence as not tracked; write the phases as JSON, each rule with sites named as `tally.py` prints it, to its phase id as the plan's heading names it, and the layout (`transition-plan.md` § The state); and run `progress.py record lint-record.json --sha <the measured commit> --date <date> --phases <phases.json> --layout <layout.json> --run <tool> <tally json> "<command>" ... --tool <tool>=<version> ... --draft <each draft>`. Add `progress.py check <record> --plan <plan>` and `rows.py check <evidence> --record <record>` to the gate and to CI: with no reference named, `rows.py check` reads only the repo's files and holds the evidence to the record. When Phase 0's Done when already holds, close it, so the lanes are open from the first day: `progress.py close <record> 0 "<what holds, in a line>" --date <date>`.

Done when `rows.py check <evidence> <this skill's SKILL.md> <references read> --record <record>` and `progress.py check <record> --plan <plan>` pass, and `rows.py keys <stack references> --in <the repo's configs> <the drafts> <plan>` names every key of the target configs; `progress.py next <record>` lists Phase 0 as closed, or names what it still lacks; every rule not yet on sits in exactly one phase with its count, strategy, fix recipe and done criterion; every `decision` is listed for the human; and the plan runs cold, by an agent that does not have this skill.

### 7. Report

Tell the user: the knobs as set, the rules flipped, the ten largest rows of the debt table outside Convention, then the conventions in one line (rules on, rules off, sites) (the rest are in the plan), the plan's path, the decisions waiting on them, the verdict counts, then the block `rows.py check` prints under `outside the gate`, pasted whole (each `n/a`, `out`, `not measured` and `open` row with its reason is the human's to read, and a count hides them), and the drift found against the references (versions, names added, renamed, removed, tools found), with the path of `reference-drift.md`.

End on the call to action, copied from `progress.py next <record>`: the open decisions that hold a phase, the earliest held first, and the phases that can start, each with its first `Measure first` command. Then offer to open the execution track in the repo's tracker, in the language of the plan: one issue per phase, and one per decision that holds a phase or a slice; a phase's issue names its blockers: the phases its Lane field waits for, and each decision that holds it or one of its slices; a decision that holds nothing stays in the plan. An issue is a handle, and the plan stays the source of truth: its body links the plan's section and repeats the done criterion (a decision's: its question and options), never the counts or the slices, which go stale with the next commit. Opening the issues publishes outside the repo, so it waits for the user's yes; with nobody to answer, or no tracker the agent can reach, the report carries each issue as a draft (title and body) for the human to open. Each issue opened goes in the history: `progress.py issue <record> <phase or Dn> <url>`.

Done when the report names the first move and every issue is opened or drafted.

## Knobs

The numeric limits and the optional families: the part of the target the developer tunes in step 3. The reference is the recommendation.

| Knob | Reference | Curve |
|---|---|---|
| Function complexity | 10 | `curve` of the complexity rule of each stack, run at limit 1 |
| Nesting depth | 3 (Go: revive `max-control-nesting`; nestif scores blocks apart) | `curve` of the depth rule, run at limit 0, where its message carries the depth (oxlint, ESLint); elsewhere its count at 2, 3 and 4 |
| Arguments | 5 (Rust, Python, Go), 4 (TypeScript) | `curve` of the argument rule, run at limit 0 |
| File size | 500 non-blank lines | `sizes` |
| Line width | 100; not asked for Go, where gofmt owns layout | `sizes` |
| Clone size | 50 tokens and 5 lines (`minTokens`, `minLines` of jscpd) | `curve` of the jscpd run at `--min-tokens 30` |
| Inline test block | no reference | a count of test blocks per size |
| Coverage of the diff | no reference | the coverage tool's report on the last changes, or `not measured — <why>` when it needs a toolchain change |
| Optional family: `clippy::pedantic` | on, with its debt list; its Convention rules go to the conventions question | the count of each of its lints |
| Optional family: docs on the public API | on for a published library only | the count of the missing docs on its public items |
| Optional family: `indexing_slicing` in parsing code | on in the crates that parse outside data | the count per crate |
| Optional family: anti-slop (TypeScript) | the targets of `typescript.md` § Optional family, rule by rule | the count of each rule, once step 1 has the yes to fetch it |
| Optional family: mutation testing on the diff | on in CI for the changed code | the missed mutants of a run on the last changes |

## Rule classes

A rule's class carries its fix recipe, so the plan writes one recipe per class instead of one per rule:

- **Dropped value**: a value whose flow ends before any reader sees it: an ignored `Result` or error, an error passed up without the context or the identity its caller matches on (`wrapcheck`, `err113`), a floating Promise, a blind `except`, an assignment never read, a write whose outcome nobody checks. Fix: the value reaches its caller or a log line.
- **Fail fast**: code that hides a failure behind a fallback (a default on a missing value, a condition the types already rule out, a catch that recovers into a wrong state). Fix: remove the fallback; the failure surfaces at the boundary that can act on it.
- **Escape hatch**: the checker is told to look away: `any`, a cast, a non-null `!`, `unwrap`, a bare `type: ignore`, a missing annotation the checker reads as `Any`. Fix: parse, don't validate: narrow the value once, at the boundary, into a type the checker reads.
- **Capability**: a call allowed in one place only: `print` or `console` outside the output or logging module, a process spawn outside the module that owns spawns, `exit` outside `main`, the environment written outside startup. A command-line script owns its own stdout: its `print` is the output, allowed by a per-file setting with its reason. Fix: route the call through the module that owns it; that module carries the one exception, with its reason. When no module owns the capability yet, the rule is `decision first`.
- **Shape**: complexity, nesting depth, argument count, file size, a duplicated block. Fix: the cause of the smell, never just its number: let the data structure the program (a table of cases, a `match` on a tuple), guard clauses, a split along a responsibility the code already has. A file over the size limit is a god file and a function over the complexity limit a god function: each is split by the responsibilities it already carries, one module or function per responsibility. Don't patch bad code, rewrite it. A clone is one rule written twice, or two rules that only look alike: one rule becomes one function or constant named for that rule; two rules stay two, and the clone carries the tool's ignore marker with the reason they change for different reasons.
- **Surface**: format, naming, import order, the scope of a name (a global, a shadowed variable, a named return): a form a reader can misread. Fix: the tool's own command, or a rename or move at the site with no behavior change.
- **Waste**: a cost paid for nothing: an allocation, a copy or a pass the cheaper form avoids (a clone where a borrow serves in Rust, a spread of the accumulator inside a loop in TypeScript, a list built by `append` in a loop in Python, `fmt.Sprintf` for a plain conversion in Go). The result stays the same; only the cost moves. Fix: the cheaper form at the site; a fix that changes a public signature is `decision first`.
- **Convention**: a choice between forms that behave the same and cost the same: `to_owned()` or `to_string()` on a `&str` in Rust, `arr.at(-1)` or `arr[arr.length - 1]` in TypeScript, `dict()` or `{}` in Python, `for i := range n` or a counted loop in Go. The test of the class: no reader, human or agent, writes a bug because the other form is there, and no run pays more for it. A rule that fails the test has another class (`curly` does: a line added under a brace-less `if` runs every time). A stack reference names the conventions of each group its target turns on whole, so their class is the same in every run; any other rule goes by the test, from the tool's own description. Its gain is consistency, so the repo chooses it (step 3). Fix: the tool's own command, which then runs beside the formatter.

## Strategies

- **On now.** 0 sites: step 5 flips it. A group goes on now as a whole, with its debt list: the rules with no site are on from that commit, and each later fix only deletes a line.
- **Fix by command.** The `safe` sites: the tool's own fix, one commit per rule with the command in its message, the gate green after it (with no gate command yet, the tests and the draft run). The whole draft stays on and only the fix narrows (ruff: `--fix --unfixable ALL --fixable <rule>`): a run with one rule selected reads every other suppression as unused and deletes it. Fixes interact (a rewrite leaves an import unused): run the draft again after each, and the sites it adds are the next command's. A fix moves lines, so compare per-rule counts, not `tally.py diff`. The `unsafe` sites go to Fix then flip: the fix is a draft, each diff read against the class recipe, and the recipe wins where they differ (an unsafe fix that deletes a `print` where Capability routes it to the log, or renames an unused value to `_x`, which hides a dropped value).
- **Fix then flip.** Sites with a local fix (a rewrite at the site, no design change). Cut the sites into _slices_ by scope (a crate, a package, a directory) small enough for one review. When the slices of a phase repeat one recipe over several scopes, the first is a _tracer bullet_: a small scope taken end to end (the fix, the measure again, the `debt:` count lowered or the scope flipped, the agent doc line) before the other slices take the recipe, so a recipe that is wrong fails once. Where the config can scope a rule (overrides, per-file settings), flip it per scope as each scope reaches 0, so the gain is locked early. Where one table governs every scope (a workspace lint table), measure with the draft and flip once, in the slice that removes the last site.
- **Baseline ratchet.** Sites whose fix is a redesign: complexity, file size, type escapes. A committed baseline lists every offender by identity (path and name, never a line number) and value. The check fails when an offender is missing from the baseline, when a value rises above its entry, and when a value falls or an entry is gone and the baseline was not updated: the last rule makes each fix lower the baseline. A renamed or moved offender is new, so it must pass.
- **Count ratchet.** Sites whose identity moves when the code moves, such as the clones of a duplication tool. The check that refuses a new site stays (jscpd against the base branch), and the total is a constant that only goes down: `tally.py <format> <output> --expect N` fails above N and below N, so the change that removes a clone lowers N.
- **Ceiling in steps.** A numeric limit with a wide spread (complexity from 11 to 200). The baseline gets a ceiling that drops in steps (for a limit of 10: 50, 30, 20, 15, 10), each step one work item cut by file. A step has no date: a date pushes code into helpers with no responsibility. The last step deletes the baseline. The rule becomes a plain error, and whatever cannot reach the limit carries an inline exception with its reason, counted by a ratchet; a human reviews each one.
- **Decision first.** The rule needs a design choice a human owns: which module owns process spawns, the layer boundaries, how a test waits, the error type. It is a question in the plan, and its phase starts once the answer is in.

## Phase order

- **Phase 0 is what every lane stands on, and nothing more**: each tool pinned, the one local command, CI running the same command, no warn level. Every lane starts after it. When step 5 left all four true, Phase 0 is done on the day the plan is written: its section says so, and step 6 closes it in the record.
- **The rest of the gate work is a lane of its own, `gate`**: each row of `repo.md` that is not on yet (the per-edit hook, a checksum, a ratchet, the scheduled pin job, a tool that needs a binary download), cut into phases like any other. They edit the gate script and CI, so the stack lanes run beside them; the lane waits for Phase 0 as the others do. A row only someone outside the repo can deliver (a branch setting) is a `decision` that holds nothing.
- **A strategy whose every fix writes a shared file** (a baseline) runs first or alone: otherwise every other phase rewrites that file too.
- **Phases run in lanes.** A lane is the sequence of phases over the same files (a stack, a set of modules): inside a lane the order is fixed; lanes run side by side. A phase that touches every file (a reformat) is a lane of its own, and every other lane waits for it. A phase whose files cross lanes (file sizes over every stack) waits for the last phase of each lane it crosses, or splits into one phase per lane, each joining its lane. Two phases of different lanes that share some files, neither of them across lanes, run in the plan's order: the later waits for the earlier. A slice held by a decision waits alone: the rest of its phase goes on, and the next phase of the lane waits for it only when it edits files that phase touches (a repository setting or a threshold holds nothing after it). Integration is serial: one change lands at a time, rebased on the last; the debt lists and the ratchet constants are the hotspots every phase edits, taken from the base branch at each rebase.
- **A mass change made by a command** (a reformat, a fix by command) lands when no long branch is open, and is redone by the command instead of merged by hand.
- **Cheap phases go early**: few sites with a mechanical fix shrink the noise for the rest.
