# A new repo

The branch for a repo with little or no code. There is no debt to measure, so there is no plan: the gate is at its cheapest now. Every rule goes on at once, and the agent writes the first feature under it.

## No code yet

No manifest of a stack, or a manifest and no source file. Stop before step 1: a config no tool has read is a guess (a 0 from a run that read nothing proves nothing), and a rule that names an owner module needs the module.

The report says what comes first: the _walking skeleton_, the smallest version of the project that runs end to end with no feature in it:

- the stack's manifest, with its toolchain pinned;
- the modules that will own a capability, empty or nearly: output and logging, process spawns, configuration and the environment;
- one test, and CI running the build and the test;

and that this skill runs on it, in the change after it.

Done when the report names the skeleton and nothing in the repo changed.

## A walking skeleton

Code, and no site in step 2 but the owner modules' own uses of their capability (the `print` of the module that owns output), which step 3 turns into their one exception each.

1. **Steps 1 and 2 as written.** The knobs have no curve to read: each takes the reference value, which costs 0 today, and the measure records that.
2. **Step 3 asks only the decisions.** First read the repo's decisions (`docs/adr/`, or the folder its docs name). Each owner a decision names becomes the setting of its Capability rule: the module that keeps the one exception, written as a per-file setting of the config with the decision's id as its reason. Each convention it sets is kept, and a gate property it contradicts is a `decision`, as in step 5. Ask only what the decisions leave open, each with a recommendation that costs nothing today: a module to own the capability, named now. With nobody to answer, take the recommendations, marked `default taken`. Each answer goes where the repo records decisions (a new ADR, in its form, when it keeps them), or else in the lint gate block of the agent doc.
3. **Step 5 flips the whole target**: every rule at error with no debt list, every tool pinned, in the local gate and in CI, the lint gate block in the agent doc, and the fast loop: the per-edit hook in the form of the agent the repo uses (its own docs say how), or, with none known, the command on the changed files, the hook then an item of Phase 0. The one gate command is written now, not left to a Phase 0. A rule that names an owner module that does not exist yet names its path; the module comes with the first change that needs the capability.
4. **Step 6 only for what is left.** With every row of the references `on`, there is no plan. There is never a record: an owner's exception is not debt. A row left open (a tool that needs a binary download, an exit no check closes yet, a decision waiting on the developer) goes in a plan of one phase, Phase 0, from the same template: the Coverage table and that phase, the other sections `none — a walking skeleton`, with the scripts' copy beside it so `rows.py check` runs.
5. **Step 7** reports the gate, each decision with its source (the ADR, the answer, or `default taken`), and the call to action: the next change is the first feature, under the gate.

Done when the gate is green with every rule of the target at error, each Capability rule names its owner from a decision or a recorded answer, and the agent doc names the gate.

## Some debt already

A few sites: the main steps. The sites are paid by Fix then flip in the change that flips them, and a plan of one phase is enough.
