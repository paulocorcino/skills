# Branch modes: `extend` vs `replace`

Every branch declares its intent against main before the gate can run. The choice determines which baseline the ratchet compares against and what happens to that baseline when the PR merges.

## TL;DR

| You're... | Use | What happens |
|---|---|---|
| Adding a feature, fixing a bug, paying down debt incrementally | **`extend`** | Gate ratchets against the baseline at the merge-base with main. Nothing in main's baseline changes when you merge. |
| Refactoring an architecture, replacing a subsystem, "main is legacy for this work" | **`replace`** | Gate captures a snapshot now as your branch's baseline. When you merge, main's baseline is replaced by yours. |

## `extend` — the default

This is the right mode for ~95% of branches. You're adding to main without claiming to redefine the floor.

**Semantics:**

- Gate reads baseline from `git show <merge-base(HEAD, main)>:.quality-gate/baseline.json`.
- Comparison is against the state of main at the point your branch diverged — not against the current main HEAD. Improvements in main while your branch is open do not retroactively raise the bar for your branch.
- To pick up improvements in main, sync (rebase or merge) — that advances the merge-base.
- Your branch never writes `.quality-gate/baseline.json`. If a stale one is present from a prior `establish --mode replace`, `establish --mode extend --force` deletes it.

**Use when:**

- Adding new functionality to an existing module.
- Fixing bugs.
- Migrating a single file or small set of files to a new pattern.
- Adding tests, refactoring a function, renaming.
- Anything where you'd be embarrassed if your branch's metrics were worse than main's.

## `replace` — for architectural work

You're proposing that the baseline itself should change. The metrics on your branch don't compare meaningfully to main's because you've reshaped what's being measured.

**Semantics:**

- `establish --mode replace` captures a snapshot of current metrics into `.quality-gate/baseline.json` in your branch.
- Gate reads from that file (your branch's working tree).
- When your PR merges, your `baseline.json` becomes main's `baseline.json`. The diff is visible in the PR — reviewer explicitly approves the substitution.

**Use when:**

- Rewriting a service in a different language.
- Replacing a subsystem (storage backend, auth flow, API surface) with a fundamentally different approach.
- Tearing out a chunk of code that's being deprecated; the new floor for those files is just "they don't exist anymore".
- The current baseline's per-file metrics no longer make sense because the files no longer exist.

**Use sparingly.** `replace` is a strong claim — you're asking reviewers to accept a new floor for the entire repo. The PR diff includes `baseline.json`, which makes the change visible, but it's still a serious shift.

## Choosing between them — heuristic

Ask: "If my branch lands, should the metrics that were enforced before still be enforced after?"

- **Yes (most of the time)** → `extend`. Main's bar stays.
- **No (rarely)** → `replace`. Your branch sets the new bar.

If you're not sure, default to `extend`. If `extend` produces noise — failures that don't reflect real regressions because the code being compared no longer exists — that's a signal that `replace` might be the right tool.

## Switching modes mid-branch

`establish --force` lets you change modes. The transition table is in [SKILL.md](../SKILL.md#establish---force-behavior):

- **`extend → replace`** with `--force`: branch.json is overwritten, baseline.json is captured (new snapshot).
- **`replace → extend`** with `--force`: branch.json is overwritten, baseline.json is **deleted** (extend mode reads from merge-base, not the working tree).

Switching modes is a deliberate act. The `--force` flag and the visible diff in the PR make sure the reviewer sees it.

## Merge scenarios

### `extend` merging to main

Nothing changes in main's baseline. The branch never claimed to redefine the floor; it just rode the existing one. Post-merge cleanup: `branch.json` lands in main as part of the merge commit. The gate ignores it on main and emits a warning ("branch.json should not exist on main — likely leaked from a merge"). Clean up with `git rm .quality-gate/branch.json` in a follow-up commit, or rely on the `.gitignore` convention if your team adds one.

### `replace` merging to main

Main's `baseline.json` is replaced by the branch's snapshot. This is the entire point of `replace` mode — the new floor lands with the merge. Reviewer should examine the baseline diff in the PR.

### Two `replace` branches in flight simultaneously

This is the conflict-prone scenario.

Setup:
- Branch A (replace) has its own `baseline.json`. PR open.
- Branch B (replace) has its own `baseline.json`. PR open.
- A merges first → main's `baseline.json` is now A's.
- B tries to merge → git conflict on `baseline.json`.

Resolution: the second branch normally syncs with main (rebase or merge), then re-runs `establish --mode replace --force`. This captures a fresh snapshot over the now-updated main state. The conflict is resolved by the same primitive that created the situation.

There is no special tooling for this — git's merge conflict handling is the source of truth. Doing otherwise would mean the gate quietly overrides git's view of "which version of the file is right", which is bad.

If two replace branches are touching genuinely incompatible parts of the codebase, the conflict is informative: the second author should review whether their `replace` was actually warranted, or whether the work should be split.

## Common mistakes

**"I'll just use `replace` so I don't have to think about regressions."**

`replace` lowers the bar for your branch. If you do this gratuitously you're erasing accumulated quality. The reviewer should push back on a `replace` PR that doesn't justify why main's existing floor doesn't apply.

**"I'll use `extend` because it's default, even though my refactor reshaped 30 files."**

If `extend` is causing the gate to report regressions on files that no longer exist (because you moved/renamed them), the comparison is no longer meaningful. Switch to `replace` and recapture.

**"I made the branch.json modification automatically — `establish` was implicit."**

`establish` is the only writer of `branch.json`. Editing the file by hand bypasses the validation and the snapshot logic. Always go through the command.

## Reference

- [SKILL.md](../SKILL.md) — overview, inviolable rules, exit codes.
- [bootstrap.md](bootstrap.md) — first-time setup, per-branch flow, migration.
- [ADR 0002](../../../docs/adr/0002-quality-gate-branch-intent.md) — rationale for the branch-intent design.
