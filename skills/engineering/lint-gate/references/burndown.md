# Burndown

The mode for a repo that already has a lint transition plan this skill wrote. It measures again what the plan measured and reports what is left: a _burndown_, one dated point per run, against the record the plan was cut from. It writes the point and nothing else: no lint config, no site, no plan section but Progress. The phases change the code; the burndown tells where they stand.

The record is `lint-record.json` beside the plan (written by step 6), its history `lint-record.history.jsonl`, and the drafts its commands read in `lint-drafts/`. The scripts are the plan's copy of `scripts/`.

## Steps

1. **Read** the plan, and list the runs to repeat: `progress.py commands <record>`.

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

5. **Phases.** A phase with no rule (Phase 0) is read by its Done when. `point` gives each other phase `closed`, `ready to flip`, `in progress`, `not started` or `regressed`. A phase held by a decision with no answer in the plan adds `held by <Dn>` to its state (`regressed, held by D1`).

6. **Progress.** Add the line `point` printed to the plan's Progress section, in the form of the lines already there. With the user's authorization, commit it with the history file, in a commit of its own.

7. **Report**: the regressions first (`up`, `off in the repo`, the erosion of step 2), then the scope, then the rules ready to flip, the phases, and the line of totals. End on the call to action of step 7 of the skill, built from this point: the regressions to answer, the flips ready, the phases that can start now, one per lane.

Done when every run of the record was measured again; `point` ran with `--append`; each `up` and `off in the repo` names the commit or edit that caused it, or `not found`; each scope rule is in the plan or listed for the human; every phase has a state; the Progress line is in the plan; and the report ends on the call to action.

## A plan with no record

A plan written before the record existed. The first burndown adopts it: the plan's copy of `scripts/` is refreshed from this skill (it may lack `progress.py`), in a commit of its own; the drafts are the configs of the plan's Target section, or the repo's own config when the plan measured with it (a flag such as `--enable-only <the debt rules>` turning the debt on), copied into `lint-drafts/`; the commands are those of its Measured section, pointed at them; the phases come from its debt table, each rule named as `tally.py` prints it. `progress.py record` writes the record at HEAD, and `point --append` takes the first point, flat against the record. The report compares the record with the plan's numbers: exact when the code is the plan's commit, marked approximate when it moved.
