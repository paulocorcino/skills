---
name: quality-gate
description: Enforce a ratchet rule (quality can only stay or improve) across Python, Go, Rust, and BunJS projects. Runs locally pre-PR, deterministic, diagnostic-only — no auto-fix, no auto-loop. Detects projects from manifests, runs per-language packs, compares to a committed baseline, emits a markdown report, and can spin pre-existing regressions out to per-issue backlog files.
---

# Quality Gate

Local, deterministic, diagnostic quality enforcement. The harness is intentionally
general-purpose; runtime decisions (what to fix, when to update the baseline,
how to prioritize a pre-existing regression) are the LLM's job, not the tool's.

## Invocation

The module lives at `~/.claude/skills/quality-gate/`. Python must be able to
resolve the `quality_gate` package, so the **parent directory** of `quality-gate/`
must be on `PYTHONPATH`:

```bash
PYTHONPATH=~/.claude/skills python -m quality_gate --cwd /path/to/repo <subcommand>
```

All examples below use `python -m quality_gate` for brevity; prepend the
`PYTHONPATH` assignment when running from outside the skills directory.

## Branch intent (extend vs replace)

Every branch declares how it relates to main before the gate runs:

- **`extend`** — branch extends main; ratchet against the baseline at the
  **merge-base** between HEAD and main. Default for feature work.
- **`replace`** — branch replaces main's baseline; captures its own snapshot
  that becomes main's new floor when merged. Use for refactors where main
  is legacy.

The declaration lives in `.quality-gate/branch.json`, is committed in the
branch, and is required on any branch other than main. Without it, `run`
returns `NO_INTENT` (exit 5).

## Happy path

```bash
# 1. Initialize in a target repo (creates .quality-gate/{config.json,.gitignore}).
python -m quality_gate --cwd /path/to/repo init

# 2. From main, capture the initial baseline.
git checkout main
python -m quality_gate --cwd /path/to/repo establish --mode replace
git add .quality-gate/baseline.json && git commit -m "chore(qg): initial baseline"

# 3. On a feature branch, declare intent.
git checkout -b feat/x
python -m quality_gate --cwd /path/to/repo establish --mode extend
git add .quality-gate/branch.json && git commit -m "chore(qg): declare intent"

# 4. Run the gate before opening a PR.
python -m quality_gate --cwd /path/to/repo run
#   exit 0 = clean; 1 = regression; 2 = passed with missing tools;
#   3 = no baseline; 4 = tool present in baseline now missing;
#   5 = no intent declared on this branch.

# 5. Optional: spin pre-existing regressions out to backlog markdown.
python -m quality_gate --cwd /path/to/repo to-backlog
```

For refactors where main is legacy:

```bash
git checkout -b refactor/new-architecture
python -m quality_gate --cwd /path/to/repo establish --mode replace
git add .quality-gate/branch.json .quality-gate/baseline.json
git commit -m "chore(qg): declare replace intent"
```

## Subcommands

| Command       | Purpose                                                          |
|---------------|------------------------------------------------------------------|
| `init`        | Scaffold `.quality-gate/` in the target repo                     |
| `establish`   | Declare branch intent (`--mode extend|replace`); writes `branch.json` and, in replace mode, captures `baseline.json` |
| `run`         | Detect projects, run language packs, ratchet, write `report.md`  |
| `status`      | Print the Summary block from the last report                     |
| `to-backlog`  | Emit one markdown issue per pre-existing regression              |

Flags: `--cwd PATH`, `--debug` (traceback on internal errors; also via `QG_DEBUG=1`),
`--language {python|go|rust|bunjs}`, `--only KEY,KEY`, `--main-branch NAME`,
`--preview` (run only; collect+render, no baseline read, no ratchet),
`--mode {extend|replace}` (establish), `--anchor-ref REF` (establish),
`--rationale TEXT` (establish), `--force` (establish only).

### `establish --force` behavior

`establish` is one-shot per branch by default. `--force` reasserts the branch
state, writing `branch.json` (and `baseline.json` when applicable) to match
the new mode:

| Transition | `branch.json` | `baseline.json` |
|---|---|---|
| `extend` (first time) | created | (not touched) |
| `replace` (first time) | created | created (snapshot now) |
| `--force` `replace → extend` | overwritten | **deleted** |
| `--force` `extend → replace` | overwritten | created (snapshot now) |
| `--force` `replace → replace` | overwritten | **re-snapshotted** |
| `--force` `extend → extend` | overwritten | (n/a) |
| `establish --mode replace` on main | (not created) | created/overwritten |
| `establish --mode extend` on main | **REJECTED** | — |

## Inviolable rules

- **Intent declared per branch.** Every branch other than main must commit
  `.quality-gate/branch.json` via `establish` before `run` is allowed. No
  silent defaults.
- **Baseline is committed; report is not.** `.quality-gate/baseline.json`
  (and `branch.json` on feature branches) is versioned in the target repo;
  `.quality-gate/report.md` is gitignored.
- **Baseline reads are mode-driven.** `extend` reads at `merge-base(HEAD,
  anchor_ref)`; `replace` reads the working tree of the branch; on main, the
  working tree is read directly.
- **`establish` is the only writer.** `branch.json` and `baseline.json` are
  written exclusively by `establish` (atomic). Never edit them by hand.
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

| Code | Meaning                                                          |
|------|------------------------------------------------------------------|
| 0    | PASSED                                                           |
| 1    | FAILED — at least one regression                                 |
| 2    | PASSED_WITH_GAPS — tools missing                                 |
| 3    | NO_BASELINE — mode declared but target ref has no baseline       |
| 4    | TOOL_MISSING_REGRESSION                                          |
| 5    | NO_INTENT — branch != main has no `branch.json` declared         |
| 10   | CONFIG_ERROR                                                     |
| 20   | INTERNAL_ERROR                                                   |

## References

Detailed documentation on using and extending Quality Gate:

- [Bootstrap](references/bootstrap.md) — getting started with `init`, `establish`, baseline capture, and migration from v1.
- [Branch modes](references/branch-modes.md) — `extend` vs `replace`, merge semantics, conflict handling.
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
│   ├── branch.schema.json
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
│   ├── validate_branch.py
│   ├── security.py
│   └── backlog.py
└── languages/
    ├── _template/         # canonical contract reference
    ├── python/            # stub in Stage 1; real in Stage 2
    ├── go/                # stub in Stage 1; real in Stage 3
    ├── rust/              # stub in Stage 1; real in Stage 4
    └── bunjs/             # stub in Stage 1; real in Stage 5
```
