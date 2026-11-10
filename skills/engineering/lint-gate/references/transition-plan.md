# Transition plan

The shape of what step 6 writes. The plan is read cold by an agent that does not have this skill, so everything it needs is beside it: commands, fix recipes, exception forms, done criteria. The scripts of the skill (`tally.py`, `drift.py`, `debt.py`, `rows.py`, `progress.py`) sit next to the plan, so its commands run as written.

Step 6 writes three things, one per reader, so the file an agent reads to work a phase stays small however large the repo:

- **The plan** (`lint-transition.md`), the contract: what to do and how. It is written once and changes only when the plan itself changes (a scope rule added, a phase cut again), in a commit of its own.
- **The evidence** (`lint-evidence.md`, beside it): Measured and Coverage, the audit of how the plan was cut. The burndown and the author read it; the agent working a phase does not.
- **The state**, in the record (`lint-record.json`: the counts, the phase of each rule, the layout) and its history (`lint-record.history.jsonl`: the points, the answers, the issues, the notes). The history only grows: `progress.py` appends one line per event, and nothing else writes it.

Fill every section; a section with nothing to say holds `none — <why>`.

## The plan

### Working this plan

Copy this section into the plan as it is, with the paths of this repo:

- Work one phase: `python <scripts>/progress.py show <record> <phase id> --plan <this plan>` prints its section with its state: the phases it waits for, its counts at the last point, the decisions that hold it.
- Record each change of state with its command, which appends to the history: a decision answered, `progress.py decide <record> <Dn> "<answer>" --date <date>`; an issue opened, `progress.py issue <record> <phase or Dn> <url> --date <date>`; a slice landed or a rule flipped, `progress.py note <record> "<what>" --date <date>`. `progress.py log <record>` prints the state.
- The plan's text changes only when the plan changes. `progress.py check <record> --plan <this plan>` runs in the gate: it fails on a section missing, a phase heading with no phase in the record or the reverse, and a plan whose last line is not the end marker.

### Target

One paragraph: the end state of the gate (every rule an error, pinned tools, one local command that CI mirrors, exceptions inline with reasons, counts only go down). Then the knobs as the developer set them:

| Knob | End state | Pace | Curve at the end state | Reason (or `default taken`) |
|---|---|---|---|---|

Then the target configs in full, as they will be when the last phase closes.

### Decisions for the human

Each `decision`, under its id (`D1`, `D2`): the rule, the question, the options with what each costs, and the phase or slice it holds. A held slice starts once the answer is recorded (`progress.py decide`); the rest of its phase does not wait for it.

### Phases

In the order of `## Phase order` of the skill, restated here with the reason for this repo's order, and the lanes: each lane, its phases in order, and the files they share. Phase 0 is the gate itself when it is not yet complete. Each phase sits under a heading `### Phase <id> — <title>`, its id as the record's layout names it, and holds:

- **Lane**: its lane and the phases it waits for (`Rust, after Phase 2`; the first of a lane: `Rust, after Phase 1`; a phase across lanes: `own lane, after Phases 4 and 8`). A phase starts when each phase it waits for is closed. A phase is closed when its Done when holds, or when all that is left of it is a slice held by a decision that edits no file of the waiting phase (a repository setting, a threshold): that slice stays open on its own and holds nothing after it.
- **Rules**: the rules it takes to error, and the strategy of each.
- **Measure first**: the commands that re-count its sites at the start of the phase. The code has moved since the plan was written; the slices follow the new count.
- **Slices**: one row per slice (scope, sites per rule), each small enough for one review, each leaving the gate green. When the slices repeat one recipe over several scopes, the first is the tracer bullet: the smallest scope that takes every part of the recipe end to end, listed first, and the others start after it lands. Slices that are distinct tasks (the items of Phase 0) have no tracer. Slices of one phase may be worked side by side and land one at a time, each rebased on the last.
- **How a site is fixed**: the recipe of each rule's class (§ Fix discipline), plus what a rule needs beyond it, and when the exception form is allowed.
- **Ratchet**: the baseline or count it adds or lowers, and the test that checks it.
- **Agent docs**: the lines of the canonical agent doc that change in the commit that turns the rule on: the `advice` line it now checks becomes the behavior, and the recipe of its class joins the lint gate block when it is the first rule of that class. No rule name, number or version goes in.
- **Done when**: the rule is at error in the real config, or the ceiling is at its new value, or the baseline file is deleted; the re-measure shows 0 sites (or only marked exceptions, counted); the whole gate is green.

### One-way doors

The shapes the next change will copy: the debt list (the group on, each rule with sites off under a `debt: N sites` comment on its own line, held by `debt.py shrink`), the exception syntax per stack, the baseline file and its format, where each config lives, the ratchet tests' names. Each with the alternative rejected and the property that rejected it.

### Fix discipline

Copy this section into the plan as it is:

- A fix keeps the behavior. A Dropped value or Fail fast fix changes only the failure path, by design: a failure that was hidden now reaches its caller, and the commit body names each such site. Any other behavior change is its own commit, outside the lint work.
- Each rule has a class, and the class gives the fix:
  - **Dropped value** (an ignored error or `Result`, a floating Promise, a blind `except`, a value never read): the value reaches its caller or a log line. The commit body names each site where a failure became visible.
  - **Fail fast** (a fallback that hides a failure): the fallback goes; the failure surfaces at the boundary that can act on it.
  - **Escape hatch** (`any`, a cast, `!`, `unwrap`, a bare ignore): parse, don't validate: narrow the value once, at the boundary, into a type the checker reads.
  - **Capability** (`print`/`console`, a spawn, `exit`, an environment write outside the module that owns it): the call goes through the owning module, which carries the one exception with its reason.
  - **Shape** (complexity, depth, arguments, size): let the data structure the program: guard clauses and early returns, a table of cases, a `match`/`switch` over a tuple, an iterator in place of a loop with state, or a split along a responsibility the code already has. A file over the size limit is a god file, a function over the complexity limit a god function: split each by the responsibilities it already carries, one module or function per responsibility. Don't patch bad code, rewrite it: helpers that follow no responsibility are not a fix. A clone: one rule written twice becomes one function or constant named for the rule; two rules that only look alike stay two, and the clone carries the ignore marker with the reason they change for different reasons.
  - **Surface** (format, naming, imports): the tool's own command, in a commit of its own.
  - **Waste** (a cost paid for nothing: an extra allocation, a clone, a copy): the cheaper form at the site, with the same result; a change to a public signature waits for its decision.
  - **Convention** (one of two forms that behave the same): the tool's own command, in a commit of its own, and the command then runs in the edit loop beside the formatter. It is a form, not a defect: a site of it is never a reason to rewrite the code around it.
- An exception is the last resort: inline, the rule named, and a reason that names where the rule's approximation is wrong here (the false positive), or the design fact that makes compliance impossible. "To pass the check" is not a reason. Each exception is counted by a ratchet.
- A test is never weakened, skipped or deleted to turn the gate green, and a hook is never bypassed.
- A baseline or a ratchet constant only goes down, in the commit that removed the sites. It rises only in a move: the commit takes at least as many sites off a debt list as it adds exceptions, and its message gives both counts.
- Each slice leaves the whole gate green.

### End marker

The plan's last line, after Fix discipline:

```
<!-- end of the plan: progress.py check reads this line -->
```

## The evidence

### Measured

The commit SHA, the date, each tool and its version, and every command used to measure, with its `tally.py` invocation; the commands read the drafts in `lint-drafts/`, and the record holds the same measure for the burndown. Then the debt table, by weight: the defect classes (Dropped value, Fail fast, Escape hatch, Capability) first, then Shape, Surface and Waste, then Convention, each group largest first:

| Rule | Tool | Class | Production | Test | Scopes | Strategy | Phase |
|---|---|---|---|---|---|---|---|

Then the rules that are `n/a` with their reasons, and the existing suppressions per form.

### Coverage

The output of `rows.py list <the skill's SKILL.md> <references read>`, the knobs first, each row with its verdict (`on`, `sites N`, `phase N`, `closed by <check>`, `open`, `decision — <Dn>`, `n/a — <why>`, `out — <why>`, `not measured — <why>`); a knob or an optional family that waits on a decision carries its count (`decision — D14, sites 197`). `rows.py check` holds it: a row with no verdict fails.

## The state

The layout, passed to `progress.py record --layout`: each phase of the plan by its id, with its lane and the phases it waits for (the Lane field), Phase 0 and the other phases with no rule included; and each decision with the phases it holds. Each issue opened, each answer and each slice landed goes in the history by its command (§ Working this plan); each burndown point by `progress.py point --append`.
