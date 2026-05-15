# Bootstrap: Getting started with Quality Gate

## TL;DR

Two commands run once per repo + one command per branch:

```bash
# Repo-level setup (once per repo, on main)
python -m quality_gate --cwd /path/to/repo init
python -m quality_gate --cwd /path/to/repo establish --mode replace
git add .quality-gate/ && git commit -m "chore(qg): bootstrap"

# Per-branch (every feature branch, before first run)
git checkout -b feat/x
python -m quality_gate --cwd /path/to/repo establish --mode extend
git add .quality-gate/branch.json && git commit -m "chore(qg): declare intent"
```

After that, `quality_gate run` works on the branch.

## What `init` does

Scaffolds `.quality-gate/` in the target repo:

- `.quality-gate/config.json` — repo-level config (main branch name, optional project overrides).
- `.quality-gate/.gitignore` — ignores `report.md` and `tmp/`.

`init` is idempotent: re-running on an existing setup prints `already initialized` and does not overwrite anything.

`init` does **not** capture a baseline. That is what `establish` is for.

## What `establish` does

`establish` declares how a branch relates to main. It's required on every branch other than main before `run` will work.

**Modes:**

- **`--mode extend`** — this branch extends main. The gate reads the baseline at the merge-base between HEAD and the anchor ref (main by default) and ratchets against it. Use this for ordinary feature work.
- **`--mode replace`** — this branch replaces main's baseline. `establish` captures a fresh snapshot of current metrics into `.quality-gate/baseline.json`, and that snapshot becomes main's new baseline when the PR merges. Use this for refactors where main is legacy.

On main, only `--mode replace` is valid (anchoring main to itself is meaningless). It captures a fresh snapshot — this is how you refresh main's baseline after improvements land.

`establish` is one-shot per branch by default; re-running refuses unless `--force` is passed. See [SKILL.md](../SKILL.md#establish---force-behavior) for the `--force` transition table.

## First-time setup, step by step

```bash
# 1. Get on main and verify clean state
git checkout main
git pull

# 2. Scaffold .quality-gate/
python -m quality_gate --cwd /path/to/repo init

# 3. Capture the initial baseline
python -m quality_gate --cwd /path/to/repo establish --mode replace

# 4. Commit everything
git add .quality-gate/
git commit -m "chore(qg): bootstrap quality gate"
git push
```

## Per-branch flow

```bash
# Start a feature branch
git checkout -b feat/my-feature

# Declare intent (one-time per branch)
python -m quality_gate --cwd /path/to/repo establish --mode extend

# Commit the declaration
git add .quality-gate/branch.json
git commit -m "chore(qg): declare branch intent"

# Work normally...
# ...

# Before opening a PR
python -m quality_gate --cwd /path/to/repo run
```

If the gate fails, the report at `.quality-gate/report.md` shows what regressed. Fix and re-run.

## Refactor flow (main is legacy)

Some branches are not extending main — they are reshaping the codebase fundamentally. The metrics on this branch don't compare meaningfully to main's. For these cases use `--mode replace`:

```bash
git checkout -b refactor/new-architecture
python -m quality_gate --cwd /path/to/repo establish --mode replace
# captures the branch's current metrics as the new floor

git add .quality-gate/branch.json .quality-gate/baseline.json
git commit -m "chore(qg): declare replace intent — main is legacy for this work"
```

When the PR merges, main's `baseline.json` is replaced by the branch's snapshot. Reviewer sees the baseline diff in the PR and explicitly approves the substitution.

See [branch-modes.md](branch-modes.md) for deeper guidance on choosing `extend` vs `replace`.

## Updating main's baseline after improvements land

When coverage rises or violations drop on main, refresh the baseline:

```bash
git checkout main
git pull
python -m quality_gate --cwd /path/to/repo establish --mode replace
git add .quality-gate/baseline.json
git commit -m "chore(qg): refresh baseline"
git push
```

This sets a higher floor that future branches must meet (via `merge-base` in extend mode).

## Migration from v1

Repos that used the v1 gate (with `update-baseline`) need to declare intent on every in-flight feature branch:

```bash
# On each existing feature branch
git checkout feat/existing-branch
python -m quality_gate --cwd /path/to/repo establish --mode extend
git add .quality-gate/branch.json
git commit -m "chore(qg): declare intent (v2 migration)"
```

Until this runs on a branch, any `run` returns `NO_INTENT` (exit 5) with an instructional message. There is no legacy auto-extend mode — see [ADR 0002](../../../docs/adr/0002-quality-gate-branch-intent.md) for rationale.

`update-baseline` no longer exists. Its replacement is `establish --mode replace` (which captures a snapshot in addition to writing `branch.json` when on a feature branch).

## First-time tool installation: handling the "dirty baseline"

When you adopt quality-gate on a repo that has been growing without it, the first time
you install the actual analysis tools (`biome`, `jscpd`, `semgrep`, etc.) you will
typically see hundreds of findings. Some will be safe to autofix; many will not.

**Workflow that avoids painting yourself into a corner:**

```bash
# 1. Install tools (target-specific — see references/missing-tools.md for hints).

# 2. Run a preview to see what tools find without ratcheting against anything:
python -m quality_gate --cwd /path/to/repo run --preview

#    Output shows: violations counts, broken/missing tools, file hot-spots.
#    Exit 0 unless the harness itself errors.

# 3. Decide what to clean up *before* establishing the floor.
#    - Run safe autofix only (e.g. `biome check --write` — NEVER --unsafe blind).
#    - Verify the project still type-checks and tests pass.
#    - Manually triage anything left that you accept as floor.

# 4. Now establish (or re-establish) the baseline as the "accepted floor":
git checkout main
python -m quality_gate --cwd /path/to/repo establish --mode replace
git add .quality-gate/baseline.json
git commit -m "chore(qg): floor after first-run cleanup"
```

## Recommended target-side configs

The skill is **diagnostic-only**: it runs the linters/scanners as you have them
configured. A clean ratchet depends on those configs being sane. Two configs
that consistently bite first-time adopters of the BunJS pack:

### `biome.json` — exclude noise

`biome` by default scans every file it knows. In a typical TS monorepo, that
catches things you almost never want gated by the ratchet: generated HTML,
coverage output, `dist`, the gate's own state directory. Minimum recommended:

```json
{
  "files": {
    "ignore": [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/.next/**",
      "**/coverage/**",
      ".quality-gate/**",
      "**/*.html"
    ]
  }
}
```

If you also use `oxlint`, mirror these in `.oxlintrc.json`'s `ignorePatterns`.

### `.jscpd.json` — make duplication tractable

`jscpd` does an O(n²)-ish token comparison; on real monorepos it times out or
inflates the percentage with test scaffolding. Recommended starting point at
the repo root:

```json
{
  "min-tokens": 100,
  "min-lines": 10,
  "gitignore": true,
  "ignore": [
    "**/tests/**",
    "**/fixtures/**",
    "**/*.test.ts",
    "**/*.spec.ts",
    "**/coverage/**"
  ],
  "store": "leveldb"
}
```

See [missing-tools.md](missing-tools.md#jscpd-in-large-monorepos) for tuning notes.

**Pitfalls observed in practice:**

- **`--unsafe` autofix can break type-checks.** Reescritas equivalentes em runtime
  (e.g. `void | Error` → `undefined | Error`) podem invalidar assignability TS. Sempre
  rode `tsc --noEmit` (e os testes) depois de qualquer autofix `--unsafe` antes de
  commit.
- **Tool's own files inside `.quality-gate/`.** Some linters scan everything by default.
  `init` prints recommendations per detected linter — apply them, or `biome` /
  `ruff` may try to format `baseline.json` and tmp output.
- **A tool may be installed but broken.** The runner separates `tools_missing` (not on
  PATH) from `tools_broken` (ran, produced nothing usable). The latter shows up in a
  "Broken Tools" section in the report and a warning on stderr. Check stderr if a
  metric you expect is `—`.

## FAQ

**Q: Can I run `init` multiple times?**
A: Yes — idempotent. It prints `already initialized` and does not overwrite.

**Q: What if I want different limits per project in a monorepo?**
A: Use `.quality-gate/config.json` to override `soft_limit` and `hard_limit` per language and project. See [monorepo.md](monorepo.md).

**Q: Do I have to re-run `establish` after a rebase?**
A: No. `established_commit` is metadata only; the gate does not verify the branch's current HEAD matches it. Rebase freely.

**Q: My branch was created before the team adopted quality-gate. What now?**
A: Run `establish --mode extend` once on the branch, commit, and proceed. If your branch was created before the baseline was first committed in main (so the merge-base predates the baseline), the gate will return `NO_BASELINE` until you sync with main (rebase/merge), which advances the merge-base.

**Q: What if I'm in a hurry and want to skip the establish step?**
A: You can't. The gate exits with `NO_INTENT` (code 5) and refuses. Declaring intent takes ~10 seconds; the safety it preserves is worth the friction.
