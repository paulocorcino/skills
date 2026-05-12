---
name: quality-gate
description: Enforce a ratchet rule (quality can only stay or improve) across Python, Go, Rust, and BunJS projects. Runs locally pre-PR, deterministic, diagnostic-only — no auto-fix, no auto-loop. Detects projects from manifests, runs per-language packs, compares to a committed baseline, emits a markdown report, and can spin pre-existing regressions out to per-issue backlog files.
---

# Quality Gate

Local, deterministic, diagnostic quality enforcement. The harness is intentionally
general-purpose; runtime decisions (what to fix, when to update the baseline,
how to prioritize a pre-existing regression) are the LLM's job, not the tool's.

## Happy path

```bash
# 1. Initialize in a target repo (creates .quality-gate/{config.json,.gitignore}).
python -m quality_gate --cwd /path/to/repo init

# 2. From the main branch, capture a baseline.
git checkout main
python -m quality_gate --cwd /path/to/repo update-baseline

# 3. Commit the baseline (report.md is gitignored).
git add .quality-gate/baseline.json && git commit -m "chore(qg): baseline"

# 4. On a feature branch, run the gate before opening a PR.
git checkout -b feat/x
python -m quality_gate --cwd /path/to/repo run
#   exit 0 = clean; 1 = regression; 2 = passed with missing tools;
#   3 = no baseline; 4 = tool present in baseline now missing.

# 5. Optional: spin pre-existing regressions out to backlog markdown.
python -m quality_gate --cwd /path/to/repo to-backlog
```

## Subcommands

| Command            | Purpose                                                          |
|--------------------|------------------------------------------------------------------|
| `init`             | Scaffold `.quality-gate/` in the target repo                     |
| `run`              | Detect projects, run language packs, ratchet, write `report.md`  |
| `status`           | Print the Summary block from the last report                     |
| `update-baseline`  | Write `.quality-gate/baseline.json` (only from main, or `--force`)|
| `to-backlog`       | Emit one markdown issue per pre-existing regression              |

Flags: `--cwd PATH`, `--language {python|go|rust|bunjs}`, `--only KEY,KEY`,
`--main-branch NAME`, `--force` (update-baseline only).

## Inviolable rules

- **Baseline is committed; report is not.** `.quality-gate/baseline.json` is
  versioned in the target repo; `.quality-gate/report.md` is gitignored.
- **Baseline reads via `git show <main>:.quality-gate/baseline.json`.** The
  working-tree copy is a fallback only when the current branch IS main.
- **Writes require main + flag.** `update-baseline` refuses to write from a
  non-main branch unless `--force` is passed.
- **All language runners are Python.** No shell scripts under `languages/`.
- **Determinism.** Alphabetical ordering, 2-decimal rounding, `report_hash`
  computed over data sections only (Metadata block excluded).
- **Ratchet rules.** Integer counters: zero-tolerance. Percentages: 0.05
  point tolerance. Lint errors must always be 0. Vulnerability criticals
  must always be 0. Per-file metrics for baseline-listed files cannot grow.
- **No auto-fix, no auto-loop.** The tool diagnoses; humans (or LLMs as
  agents) decide what to do.
- **Skill stays general.** Target-specific rules belong in the target's
  `.quality-gate/config.json`, not in the harness.

## Exit codes

| Code | Meaning                            |
|------|------------------------------------|
| 0    | PASSED                             |
| 1    | FAILED — at least one regression   |
| 2    | PASSED_WITH_GAPS — tools missing   |
| 3    | NO_BASELINE                        |
| 4    | TOOL_MISSING_REGRESSION            |
| 10   | CONFIG_ERROR                       |
| 20   | INTERNAL_ERROR                     |

## References

Detailed documentation on using and extending Quality Gate:

- [Bootstrap](references/bootstrap.md) — getting started with `init`, baseline capture, and updates.
- [Missing tools](references/missing-tools.md) — handling missing or unavailable tools, exit codes, and tool-loss safeguards.
- [Monorepo configuration](references/monorepo.md) — autodetect heuristic, per-project baselines, and config.json.
- [Adding a language pack](references/adding-language.md) — contract, schema, and step-by-step guide for new languages.

## Layout

```
quality-gate/
├── SKILL.md
├── __init__.py
├── __main__.py
├── cli.py
├── schema/
│   ├── baseline.schema.json
│   ├── language_metrics.schema.json
│   └── config.schema.json
├── lib/
│   ├── detect.py
│   ├── baseline_io.py
│   ├── config.py
│   ├── ratchet.py
│   ├── report.py
│   ├── triage.py
│   ├── validate_language.py
│   ├── security.py        # stub in Stage 1; real in Stage 6
│   └── backlog.py
└── languages/
    ├── _template/         # canonical contract reference
    ├── python/            # stub in Stage 1; real in Stage 2
    ├── go/                # stub in Stage 1; real in Stage 3
    ├── rust/              # stub in Stage 1; real in Stage 4
    └── bunjs/             # stub in Stage 1; real in Stage 5
```
