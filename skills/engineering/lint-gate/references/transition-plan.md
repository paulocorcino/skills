# Transition plan

The shape of the plan step 5 writes. The plan is read cold by an agent that does not have this skill, so everything it needs is in the plan itself: commands, fix recipes, exception forms, done criteria. The scripts of the skill (`tally.py`, `drift.py`, `debt.py`, `rows.py`) sit next to the plan, so its measure commands run as written.

Fill every section; a section with nothing to say holds `none — <why>`.

## Sections

### Target

One paragraph: the end state of the gate (every rule an error, pinned tools, one local command that CI mirrors, exceptions inline with reasons, counts only go down). Then the knobs as the developer set them:

| Knob | End state | Pace | Curve at the end state | Reason (or `default taken`) |
|---|---|---|---|---|

Then the target configs in full, as they will be when the last phase closes.

### Measured

The commit SHA, the date, each tool and its version, and every command used to measure, with its `tally.py` invocation. Then the debt table, largest first:

| Rule | Tool | Class | Production | Test | Scopes | Strategy | Phase |
|---|---|---|---|---|---|---|---|

Then the rules that are `n/a` with their reasons, and the existing suppressions per form.

### Decisions for the human

Each `decision`: the rule, the question, the options with what each costs, and the phase it holds. A phase held by a decision starts once the answer is recorded here.

### Phases

In the order of `## Phase order` of the skill, restated here with the reason for this repo's order. Phase 0 is the gate itself when it is not yet complete. Each phase:

- **Rules**: the rules it takes to error, and the strategy of each.
- **Measure first**: the commands that re-count its sites at the start of the phase. The code has moved since the plan was written; the slices follow the new count.
- **Slices**: one row per slice (scope, sites per rule), each small enough for one review, each leaving the gate green.
- **How a site is fixed**: the recipe of each rule's class (§ Fix discipline), plus what a rule needs beyond it, and when the exception form is allowed.
- **Ratchet**: the baseline or count it adds or lowers, and the test that checks it.
- **Agent docs**: the lines of the canonical agent doc that change in the commit that turns the rule on: the `advice` line it now checks becomes the behavior, and the recipe of its class joins the lint gate block when it is the first rule of that class. No rule name, number or version goes in.
- **Done when**: the rule is at error in the real config, or the ceiling is at its new value, or the baseline file is deleted; the re-measure shows 0 sites (or only marked exceptions, counted); the whole gate is green.

### One-way doors

The shapes the next change will copy: the debt list (the group on, each rule with sites off under a `debt: N sites` comment on its own line, held by `debt.py shrink`), the exception syntax per stack, the baseline file and its format, where each config lives, the ratchet tests' names. Each with the alternative rejected and the property that rejected it.

### Fix discipline

Copy this section into the plan as it is:

- A fix keeps the behavior. A behavior change is its own commit, outside the lint work.
- Each rule has a class, and the class gives the fix:
  - **Dropped value** (an ignored error or `Result`, a floating Promise, a blind `except`, a value never read): the value reaches its caller or a log line. The commit body names each site where a failure became visible.
  - **Fail fast** (a fallback that hides a failure): the fallback goes; the failure surfaces at the boundary that can act on it.
  - **Escape hatch** (`any`, a cast, `!`, `unwrap`, a bare ignore): parse, don't validate: narrow the value once, at the boundary, into a type the checker reads.
  - **Capability** (`print`/`console`, a spawn, `exit`, an environment write outside the module that owns it): the call goes through the owning module, which carries the one exception with its reason.
  - **Shape** (complexity, depth, arguments, size): let the data structure the program: guard clauses and early returns, a table of cases, a `match`/`switch` over a tuple, an iterator in place of a loop with state, or a split along a responsibility the code already has. A file over the size limit is a god file, a function over the complexity limit a god function: split each by the responsibilities it already carries, one module or function per responsibility. Don't patch bad code, rewrite it: helpers that follow no responsibility are not a fix. A clone: one rule written twice becomes one function or constant named for the rule; two rules that only look alike stay two, and the clone carries the ignore marker with the reason they change for different reasons.
  - **Surface** (format, naming, imports): the tool's own command, in a commit of its own.
- An exception is the last resort: inline, the rule named, and a reason that names where the rule's approximation is wrong here (the false positive), or the design fact that makes compliance impossible. "To pass the check" is not a reason. Each exception is counted by a ratchet.
- A test is never weakened, skipped or deleted to turn the gate green, and a hook is never bypassed.
- A baseline or a ratchet constant only goes down, in the commit that removed the sites.
- Each slice leaves the whole gate green.

### Coverage

The output of `rows.py list <references read>`, each row with its verdict (`on`, `sites N`, `phase N`, `closed by <check>`, `open`, `decision — <Dn>`, `n/a — <why>`, `out — <why>`). `rows.py check` holds it: a row with no verdict fails.

### Progress

One line per closed phase or slice: date, commit, the new counts.
