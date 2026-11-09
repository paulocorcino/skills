# Burndown

The mode for a repo that already has a lint transition plan this skill wrote. It measures again what the plan measured and reports what is left: a _burndown_, one dated point per run, against the record the plan was cut from. It appends the point to the history and nothing else: no lint config, no site, no line of the plan. The phases change the code; the burndown tells where they stand.

The record is `lint-record.json` beside the plan (written by step 6), its history `lint-record.history.jsonl`, and the drafts its commands read in `lint-drafts/`. The scripts are the plan's copy of `scripts/`.

## Steps

1. **Read** the plan and its state, and list the runs to repeat: `progress.py log <record>`, `progress.py commands <record>`.

2. **Erosion.** What step 5 put in place is still there:
   - the whole gate runs green (each failure listed with its check); with no gate command yet, the checks the plan names, run as CI runs them;
   - each config that holds a debt list passes `debt.py shrink <scratch>/base <config>`, the base being the same config at the record's commit (`git show <record sha>:<config> > <scratch>/base`): it also fails on an entry added with no `debt:` or `noise:` comment;
   - each CI step of the record's commit is still in CI (`git diff <record sha> -- <the CI folder>`), and the gate command still runs it; a repo with no CI has nothing to check here, and the report says so.

3. **Measure.** Run each command of the record from the repo root, its output written to the scratch folder, at the version the record names for its tool (the repo's pin; a pin moved since the record is named in step 4 with `--tool`), and tally each output with `tally.py <format> <output> --json <scratch>/<run>.json`. A count of 0 is evidence only as step 2 of the skill says: the run checked the code.

4. **Point.** `progress.py point <record> --run <name> <scratch>/<run>.json ... --tool <name>=<version> ... --config <each config with a debt list> --sha <HEAD> --date <today> --append`. Its tables are the report; copy them.
   - `up`: the debt grew while the rule is off. Name the commits since the last point that added the sites (`git log <last point sha>.. -- <the files of the new sites>`).
   - `off in the repo`: the plan had the rule on, and it is off now. Find the edit (`git log -p <record sha>.. -- <the configs>`). It is an exit (`repo.md` § Exits): report it for the human, with the edit; this mode turns nothing back on.
   - `scope`: a rule the record never measured, brought by a version bump or a draft change. It goes to the plan as an addition (its class, strategy and phase, dated), and the record is written again at HEAD with `progress.py record` once the plan holds it; the history stays, so the trend runs across the move.
   - `ready to flip`: the rule is at 0 and still listed as debt. Deleting its entry is the next change of its phase.
   - `debt comment above the count`: the config's `debt: N` is higher than the sites left. The next change of its phase lowers it; this mode leaves it.

5. **Phases.** A phase with no rule (Phase 0) is read by its Done when. `point` gives each other phase `closed`, `ready to flip`, `in progress`, `not started` or `regressed`. A phase held by a decision `log` shows open adds `held by <Dn>` to its state (`regressed, held by D1`).

6. **Progress.** `point --append` wrote the point to the history. With the user's authorization, commit the history file in a commit of its own.

7. **Report**: the regressions first (`up`, `off in the repo`, the erosion of step 2), then the scope, then the rules ready to flip, the phases, and the line of totals. End on the call to action of step 7 of the skill, built from this point: the regressions to answer, the flips ready, the phases that can start now, one per lane.

Done when every run of the record was measured again; `point` ran with `--append`; each `up` and `off in the repo` names the commit or edit that caused it, or `not found`; each scope rule is in the plan or listed for the human; every phase has a state; the point is in the history; and the report ends on the call to action.

## A plan with no record

A plan written before the record existed. The first burndown adopts it: the plan's copy of `scripts/` is refreshed from this skill (it may lack `progress.py`), in a commit of its own; the drafts are the configs of the plan's Target section, or the repo's own config when the plan measured with it (a flag such as `--enable-only <the debt rules>` turning the debt on), copied into `lint-drafts/`; the commands are those of its Measured section, pointed at them; the phases come from its debt table, each rule named as `tally.py` prints it; a rule with no site left at HEAD stays out of the phases file (the record holds only rules with sites), and its phase is still in the layout, read by its Done when. A plan whose whole debt is paid gets a record with no rule: each later point then holds the gate at 0, and the phases still open are those whose Done when does not hold. `progress.py record` writes the record at HEAD, and `point --append` takes the first point, flat against the record. The report compares the record with the plan's numbers: exact when the code is the plan's commit, marked approximate when it moved.

## A plan of the older shape

A plan with Measured, Coverage or Progress in its own file, or a record with no layout. The first burndown moves it to the shape of `transition-plan.md`, in a commit of its own before the point: Measured and Coverage move, as they are, to the evidence beside the plan, and Coverage gains a line, with its verdict, for each row the references added since; each Progress line becomes a `progress.py note` with its date (a line with none takes the date of the commit that added it: `git log -1 --format=%as -S '<the line>' -- <plan>`), an issue line a `progress.py issue`, an answer recorded in the plan a `progress.py decide`; the Progress section goes; the section Working this plan and the end marker are added; each phase heading takes the form `### Phase <id> — <title>`; each phase gains its Lane field; `progress.py check <record> --plan <plan>` joins the gate and CI; and the record is written again with `--layout`, its `--sha` and `--date` the ones it already holds (the code it measured did not move). The layout comes from the plan's own order: a phase waits for each phase the plan puts before it on the same files or names as its prerequisite; a plan that names no lanes is one lane, each phase after the one before, and Phase 0 waits for nothing; a decision holds the phases its text names, and nothing when it names none. Every line the move does not name stays as it is. A move is a cut and a paste, made by a script that writes the new files whole and then checks them: `progress.py check <record> --plan <plan>` and `rows.py check <evidence> <references read>` pass, and no line is lost: each line of the old Measured and Coverage is in the evidence, each Progress line in the history, and each other line in the plan, a renamed heading by its new form.
