# Bootstrap: Getting started with Quality Gate

## When to use `quality-gate init`

The `init` subcommand scaffolds a new Quality Gate setup in a target repository. Run it once per repo, on the main branch:

```bash
python -m quality_gate --cwd /path/to/repo init
```

## What gets created

`init` creates a `.quality-gate/` directory with:

- **`.quality-gate/baseline.json`** — the committed baseline snapshot. This file is **versioned**; it records the project names, commit hash, main branch name, tool versions at baseline time, and per-project metrics (coverage, violations, etc.).
- **`.quality-gate/.gitignore`** — tells Git to ignore the report (reports are local working artifacts, not versioned).
- **`.quality-gate/config.json`** (optional) — per-project overrides if you have a monorepo with language-specific limits or project mappings. Only needed if the default autodetect does not work for your layout.

## Baseline-only semantics

During `init`, no comparison is performed. The baseline is created from the current state of the repo and marked with the current commit hash and branch name. This establishes the "zero point" for all future ratchet checks.

**Key invariant:** `init` only writes from the main branch, or with `--force`. This prevents accidental baseline capture from feature branches.

## After init: commit and use

```bash
# Commit the baseline to version control
git add .quality-gate/baseline.json .quality-gate/.gitignore
git commit -m "chore(qg): initialize quality gate baseline"

# On feature branches, run the gate before submitting PRs
git checkout -b feat/x
python -m quality_gate --cwd /path/to/repo run
```

Each `run` compares the current metrics against the baseline and emits `.quality-gate/report.md` (gitignored). If any regression is detected, exit code is 1 (FAILED).

## Updating the baseline

To update the baseline after improvements land on main:

```bash
git checkout main
python -m quality_gate --cwd /path/to/repo update-baseline
git add .quality-gate/baseline.json
git commit -m "chore(qg): update baseline"
```

The `update-baseline` subcommand:
- Reads the current metrics
- Writes them to `.quality-gate/baseline.json` with a new timestamp and commit hash
- Only succeeds from main (or with `--force`)
- Does NOT overwrite `.gitignore`

## FAQ

**Q: Can I run `init` multiple times?**
A: Yes, it is idempotent. Re-running init on an existing setup will not corrupt the baseline; it will rebuild the scaffold.

**Q: What if I want different limits per project in a monorepo?**
A: Use `.quality-gate/config.json` to override `soft_limit` and `hard_limit` per language and project. See `references/monorepo.md`.

**Q: How do I know what the baseline metrics are?**
A: After `init`, inspect `.quality-gate/baseline.json` directly. The structure mirrors the report format.
