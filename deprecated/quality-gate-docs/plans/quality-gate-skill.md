# Quality Gate skill - Staged Execution Plan

<!-- scaffolded 2026-05-12 via staged-plan/lib/scaffold.py -->

## Execution model (READ FIRST)
Staged subagent execution (prompt chaining + gate checks). Do NOT run as one linear task.

0. **Pre-execution placeholder gate** (mandatory, before launching any stage). Run:
   ```
   python3 -c "import sys; sys.path.insert(0,'docs/plans'); from _verify import V; V.assert_no_placeholders('docs/plans/quality-gate-skill.md'); sys.exit(V.summarize())"
   ```
   If non-zero, abort and surface the offending lines. Fix or delete the flagged blocks; do NOT bypass.
1. **Parent** reads this plan end-to-end (orchestration needs the full picture).
   **Subagents** read only the sections their hand-off prompt names — never
   other stages' blocks. This split is a deliberate token optimization.
2. Run Stage 0 (Pre-flight). If any gate is red on the baseline, abort.
3. For each Stage N >= 1, launch a fresh subagent (see `## Executor adapter`):
   - prompt: the verbatim Hand-off prompt block for that stage
   - description: the stage title
   - foreground, sequential, `model` selected per Tier/Effort (see `## Executor adapter` mapping table)
4. On return, verify: build + gates clean, commit SHA present in `git log`,
   post-stage report written, scope respected (only declared files touched).
5. Green -> Mode handling:
   - autonomous: launch Stage N+1 immediately.
   - semi-autonomous: post the post-stage summary + `Resume? [y / edit / abort]`
     and wait. `y` -> launch Stage N+1; `edit` -> user adjusts the next
     hand-off then `y`; `abort` -> stop (committed work is preserved).
   Red -> apply the `## Execution policy` retry rule.
6. After the final stage, run `## End-to-end verification`, run the
   `## Reviewer gate` if not `none`, and emit the
   stage -> SHA -> report-path summary table.

Parent responsibilities (not delegable): launching stages in order, verifying
green between stages, running end-to-end verification, running the reviewer
gate if configured, producing the summary.

Resuming after a red stage: each hand-off prompt only assumes prior commits
exist in `git log`, not that they came from subagents. If Stage K was fixed
manually, relaunch Stage K+1 unchanged. Never re-run committed stages.

### Resource selection vocabulary (read before launching each stage)

Each stage declares `Tier:` (cognitive load) and `Effort:` (reasoning budget).
The executor at runtime maps these to the cheapest viable resource on its
platform that meets BOTH dimensions. The plan does NOT name models — that is
the executor's responsibility (it knows its own lineup and pricing).

**Tier:**
- `mechanical` — literal execution of a well-specified hand-off (rename, move,
  apply pattern from list). Smallest model that can follow the instruction.
- `standard` — typical coding within the declared file list, light judgment.
- `judgment` — scope decisions, semantic synthesis, non-obvious refactors.
- `critical` — security, public contract, data migration, irreversible changes.

**Effort:**
- `minimal` — no extended reasoning; cheapest setting.
- `standard` — default reasoning budget.
- `extended` — maximum reasoning budget the executor offers.

**Selection rule:** pick the cheapest model × reasoning combo on your platform
that meets or exceeds the declared Tier and Effort. Do NOT auto-promote on
retry — if a `mechanical` stage fails twice, the classification was wrong;
STOP and replan rather than silently escalating to a bigger model.

**Role defaults** (apply when not overridden by a stage block):
- Parent / orchestrator: `standard / standard`
- Stage 0 (pre-flight gates): `mechanical / minimal`
- Reviewer gate: `critical / extended`
- Stage N >= 1: declared per stage; absence defaults to `standard / standard`

## Execution policy (fixed defaults unless user overrode)
- Mode: autonomous
- Commit authorization: per-stage-direct
- On red: auto-retry-up-to-2 — cap of 2 retries; each retry passes the prior failure excerpt and narrows the instruction to the same file list. NEVER retry on scope violations, pre-commit hook rejections, or hook bypass attempts (escalate immediately). On exhaustion: stop and surface.
- Working-tree policy: clean-required — per-state behavior is described inline in `## Stage 0`.
- Reviewer: light  # 7 stages (>=5) triggers light reviewer auto-recommendation

## Plan landing commit (mandatory before Phase 2)
Before launching Stage 1, the planner (NOT a subagent) makes a single commit
that lands this plan and its support artifacts. This is plan setup, not
feature work — isolating it here keeps Stage 0 and Stage 1+ scope-clean.

**Pre-check (mandatory):** before staging anything, inspect `/home/corcino/.claude/skills/.gitignore`.
The Plan landing commit assumes `docs/plans/` is **trackable**. Two cases:

- If `.gitignore` ignores `docs/plans/` wholesale (e.g. a `docs/plans/` line),
  **narrow the rule to ignore only logs**: replace that line with
  `docs/plans/logs/`. The plan file, `_verify.py`, and verify scripts MUST be
  versioned; only gate logs are excluded. Do NOT use `git add -f` to bypass —
  the rule itself needs fixing.
- If `.gitignore` does not ignore `docs/plans/`, just append `docs/plans/logs/`
  if not already present.

The landing commit MUST contain:
1. `/home/corcino/.claude/skills/docs/plans/quality-gate-skill.md` — this plan file.
2. `/home/corcino/.claude/skills/docs/plans/_verify.py` — vendored verify primitives; the planner
   copies this from the staged-plan skill source as part of Phase 1.5 if not
   already present in the repo. Stage scripts import it via
   `sys.path.insert(0, 'docs/plans'); from _verify import V`.
3. `/home/corcino/.claude/skills/docs/plans/_report-template.md` — scaffolded alongside the plan;
   subagents copy it as the starting structure for post-stage reports.
4. Any `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-verify-stage-N.py` and
   `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-verify-e2e.py` scripts the plan declares.
5. `/home/corcino/.claude/skills/.gitignore` with the narrowed/added rule from the pre-check above
   (plus the report-ignoring pattern when report-policy = `gitignored`).

Suggested subject:
`chore(plans): land quality-gate-skill staged plan + verify scripts`

After this commit, working tree is clean and Phase 2 starts.

## Logs policy
Gate execution logs are written to `/home/corcino/.claude/skills/docs/plans/logs/<prefix>-<ts>.log`
on every `run_gate()` call. They are **local evidence artifacts, not
versioned**: `docs/plans/logs/` is gitignored via the Plan landing commit.
Reports (committed alongside each stage) capture the deviations and
judgments needed for PR review; raw logs are kept locally for forensics.

## Executor adapter

Each stage runs in a fresh context window via whatever delegated-agent
mechanism the executor provides (Claude Code: `Agent` tool with
`subagent_type: general-purpose`, foreground, sequential; Codex / others: the
equivalent fresh-window mechanism, or inline in a clean session if no delegate
mechanism exists).

**Model & effort selection:** the plan declares `Tier:` and `Effort:` per stage
(see `## Execution model` § Resource selection vocabulary). The executor maps
those to its own model lineup, picking the cheapest viable combo. The plan
itself names no model — only the executor knows what's available and what it
costs.

**Mapping for Claude Code** (pass as `model` argument to the `Agent` tool):

| Tier / Effort | `model` |
|---|---|
| mechanical / minimal | `haiku` |
| mechanical / standard | `haiku` |
| standard / minimal | `sonnet` |
| standard / standard | `sonnet` |
| standard / extended | `sonnet` or `opus` |
| judgment / standard | `opus` |
| judgment / extended | `opus` |
| critical / * | `opus` |

Do NOT omit `model` (omission inherits the parent's model and defeats the
cost-tiering — every stage would silently run on the parent's model). For
Codex / other executors, apply the same vocabulary against their lineup.

Roles when no stage-level override is present:
- Parent / orchestrator: `standard / standard`
- Stage 0: `mechanical / minimal`
- Reviewer gate: `critical / extended`
- Stage N >= 1: as declared; default `standard / standard`

## Hand-off conventions (apply to every stage)

**Authorization:**
- MAY commit directly after all verifications pass.
- MAY NOT push.
- MAY NOT modify files outside the stage's declared file list.
- MAY NOT touch pre-existing unrelated working-tree edits.
- MAY NOT skip gates or use --no-verify / bypass hooks.
- MAY NOT spawn nested subagents (no Agent calls inside this stage).

**Scope discipline:**
- If the stage appears to require files outside the declared list, STOP and
  report. Do NOT silently expand scope.
- If pre-existing test/build failure is unrelated to this stage, STOP and
  report. Do NOT fix it.

**Failure protocol:**
- Gate fails within declared scope -> fix within scope and re-run the gate.
- Any STOP condition above -> return to parent with a clear reason.

**Return to parent:**
- Per-file summary with actual grep-found locations.
- Gate results (pass/fail + snippets).
- Commit SHA + subject.
- Deviations from the plan, if any.
- Path to the post-stage report written to disk.

## Context
Build a new skill `quality-gate` at `/home/corcino/.claude/skills/quality-gate/` whose design was finalized in a `/grill-me` session in May 2026. The skill enforces a ratchet rule (quality can only stay or improve) across Python, Go, Rust, and BunJS projects, runs locally pre-PR, is deterministic, and is diagnostic-only (no auto-fix, no auto-loop).

**Constraints (locked by the grill-me session):**
- Baseline lives in the target repo at `.quality-gate/baseline.json` (JSON, committed). Report at `.quality-gate/report.md` (Markdown, gitignored).
- All language runners are Python (no shell scripts) and produce a canonical JSON output per `schema/language_metrics.schema.json`.
- Baseline read via `git show <main>:.quality-gate/baseline.json`; writes require `--update-baseline` and being on the configured main branch.
- Exit codes: 0=PASSED, 1=FAILED, 2=PASSED_WITH_GAPS, 3=NO_BASELINE, 4=TOOL_MISSING_REGRESSION, 10=CONFIG_ERROR, 20=INTERNAL_ERROR.
- Ratchet rules: zero-tolerance integer counters; 0.05% tolerance for percentages; lint errors must always be 0; vuln criticals must always be 0.
- Determinism: alphabetical ordering, 2-decimal rounding, `report_hash` at end of report computed over data only.
- Skill design rule (memory): keep skill general; do not encode target-specific rules in the harness — runtime decisions are the LLM's job.

**In scope (this plan):** SKILL.md, CLI (`python -m quality_gate` with subcommands init/run/status/update-baseline/to-backlog), schemas (baseline/language_metrics/config), lib modules (detect, baseline_io, config, ratchet, report, triage, validate_language, security, backlog), language packs (Python, Go, Rust, BunJS), security pack (OSV-Scanner + Semgrep CE), references docs.

**Out of scope (deferred):** SonarQube integration, git hooks, CI templates, historical graphs, auto-install of tools, additional languages beyond the 4 initial ones.

## Global conventions
- Build gate: `PYTHONPATH=/home/corcino/.claude/skills python3 -c "import quality_gate, quality_gate.cli"` — package must import without error.
- Lint/test gates: `python3 -m py_compile $(find /home/corcino/.claude/skills/quality-gate -name '*.py')` (must exit 0) and `for f in /home/corcino/.claude/skills/quality-gate/schema/*.json /home/corcino/.claude/skills/quality-gate/languages/*/tools.json /home/corcino/.claude/skills/quality-gate/languages/*/metadata.json; do python3 -m json.tool "$f" > /dev/null; done` (must exit 0).
- Invariants: (1) all runners are Python — `find /home/corcino/.claude/skills/quality-gate/languages -name '*.sh'` must return zero results; (2) `quality-gate/SKILL.md` has YAML frontmatter starting with `---\nname: quality-gate`; (3) every `languages/<lang>/run.py` output must validate against `schema/language_metrics.schema.json` via `lib/validate_language.py`.
- Commit style: ONE commit per stage that includes BOTH the code changes AND
  the post-stage report file. The report is staged alongside code; there is
  no separate "report commit". Trailer:
  `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL`
  (substituted by the executor at commit time, e.g.
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`).
- Report content: do NOT include the stage's own commit SHA in the report
  body (impossible: the file is part of the commit). The parent emits the
  canonical stage->SHA mapping in the End-to-end summary table.
- Staging: only files the stage declares PLUS the stage's own
  `quality-gate-skill-stage-{N}-report.md`, by explicit path; never `git add -A`.

## Stage 0 - Pre-flight (mandatory, no feature work, no commit, no versioned report)
**Tier:** mechanical
**Effort:** minimal
Purpose: record baseline state and apply the working-tree policy so later
failures cannot be blamed on prior repo state. Plan support artifacts
(`_verify.py`, verify scripts, the plan file) are already committed via the
Plan landing commit before Phase 2 began.

**No versioned report:** Stage 0 must NOT write `quality-gate-skill-stage-0-report.md`
under `docs/plans/` — that would leave the working tree dirty and conflict
with `clean-required`. Baseline evidence goes to the gitignored logs dir;
the human-readable summary is returned to the parent.

1. Capture `git status` and the current HEAD SHA. Write them to
   `/home/corcino/.claude/skills/docs/plans/logs/quality-gate-skill-stage-0-baseline.log` (gitignored) and
   return the same summary to the parent.
2. Apply the working-tree policy from `## Execution policy`:
   - clean-required: tree must be clean; if not, abort.
   - stash-authorized: `git stash push -u -m "staged-plan-quality-gate-skill-pre"`; record stash ref in the log + parent summary.
   - integrate-existing: leave changes in place; list them in the log + parent summary.
   - abort-until-clean: abort the plan; user resolves manually.
3. Run every gate (build, lint, tests, etc.) on the resulting baseline.
   `run_gate()` already writes its own per-command log under `docs/plans/logs/`.
4. Red -> abort. Green -> working tree must still be clean (or match the
   integrate-existing manifest); proceed to Stage 1.

<!-- BEGIN STAGE 1 -->
## Stage 1 - Core skeleton (SKILL.md, schemas, lib, cli, _template, stub runners)
<!-- STAGE 1: tier-effort -->
**Tier:** judgment         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** extended       <!-- minimal | standard | extended -->
<!-- STAGE 1: tier-rationale -->
**Tier rationale:** This stage materializes the canonical JSON schemas, lib module interfaces, ratchet rule table, and CLI subcommand contract that Stages 2-6 consume. Schema-level decisions are hard to revise once language packs depend on them, so the executor needs reasoning headroom to land them correctly the first time.
<!-- STAGE 1: items -->
**Items:** QG-CORE-1
<!-- STAGE 1: scope -->
**Scope:** Materialize the `quality-gate/` skill folder with initial SKILL.md (happy path + inviolable rules + reference stubs), the three JSON Schemas, all `lib/` modules (real implementations for the orchestration core; stubs only for `lib/security.py`), the CLI with all subcommands wired, the `languages/_template/` contract, and stub `run.py`/`tools.json`/`metadata.json` for each of the 4 target languages.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 1: files -->
**Files:**
- `quality-gate/SKILL.md` - initial SKILL.md with YAML frontmatter (`name: quality-gate`, description), happy-path section, inviolable rules section, and stub links to `references/` (Stage 7 fills the targets).
- `quality-gate/__init__.py` - empty package marker.
- `quality-gate/__main__.py` - dispatches `python -m quality_gate` to `cli.main()`.
- `quality-gate/cli.py` - argparse with subcommands `init`, `run`, `status`, `update-baseline`, `to-backlog`; flags `--language`, `--only`, `--update-baseline`, `--force`, `--main-branch`; exit codes per the spec table; orchestrates detect → per-project run.py → security.collect → ratchet → report → triage.
- `quality-gate/schema/baseline.schema.json` - JSON Schema for `.quality-gate/baseline.json` matching the sketch in Context (schema_version, generated_at, commit, main_branch, tools_versions, projects map).
- `quality-gate/schema/language_metrics.schema.json` - JSON Schema for the output every `languages/<lang>/run.py` must produce (language, root, tools_used, tools_missing, coverage, duplication, violations, vulnerabilities, files).
- `quality-gate/schema/config.schema.json` - JSON Schema for optional `.quality-gate/config.json` (projects array with language + root + soft/hard limits overrides).
- `quality-gate/lib/__init__.py` - empty package marker.
- `quality-gate/lib/detect.py` - detect projects from manifests (`pyproject.toml`, `go.mod`, `Cargo.toml`, `package.json`+`bun.lockb`); honor `config.json` override; return list of `{language, root, project_key}`.
- `quality-gate/lib/baseline_io.py` - read baseline via `git show <main-branch>:.quality-gate/baseline.json` (fall back to working tree if main equals current branch); write baseline only when `--update-baseline` AND branch == main (or `--force`).
- `quality-gate/lib/config.py` - load and validate `.quality-gate/config.json` against `config.schema.json`; provide defaults for soft/hard limits per language.
- `quality-gate/lib/ratchet.py` - compare current vs baseline per the rule table (integer counters: zero-tolerance; percentages: 0.05% tolerance; lint errors: must be 0; vuln criticals: must be 0; per-file: baseline-listed files cannot grow); return list of regressions with `metric`, `project`, `file?`, `baseline`, `current`, `delta`, `severity`.
- `quality-gate/lib/report.py` - render deterministic `report.md` with: separated Metadata block (timestamp, commit, tool versions), Summary, per-project tables (coverage/duplication/violations/vulnerabilities), Regressions table, alphabetical ordering everywhere, percentages rounded to 2 decimals, `report_hash` computed over the data sections (excluding Metadata) appended at end.
- `quality-gate/lib/triage.py` - classify each regression as `caused_by_pr` (file in `git diff --name-only <base>...HEAD`) or `pre_existing`; expose the split for `to-backlog`.
- `quality-gate/lib/validate_language.py` - JSON Schema validator that checks a run.py output against `language_metrics.schema.json`; usable as module or CLI (`python -m quality_gate.lib.validate_language PATH`).
- `quality-gate/lib/security.py` - STUB returning `{"vulnerabilities": {"critical":0,"high":0,"medium":0,"low":0}, "tools_used": [], "tools_missing": ["osv-scanner","semgrep"]}` per project. Stage 6 replaces with real implementation.
- `quality-gate/lib/backlog.py` - `to-backlog` impl: parse last `report.md`, filter `pre_existing` regressions, emit one markdown file per issue under `<target-repo>/docs/backlogs/quality-gate-<slug>.md` following the `to-issues` skill format (tracer-bullet vertical slices).
- `quality-gate/languages/__init__.py` - empty package marker.
- `quality-gate/languages/_template/run.py` - documented template showing the contract (accepts `--root`, `--output`, writes schema-valid JSON; declares `REQUIRED_TOOLS` list; checks availability; emits `tools_missing` for absent ones).
- `quality-gate/languages/_template/tools.json` - manifest schema example with one tool entry (`name`, `purpose`, `detect_command`, `install_command`, `docs_url`).
- `quality-gate/languages/_template/metadata.json` - example metadata (`language`, `manifests`, `extensions`, `soft_limits`, `hard_limits`).
- `quality-gate/languages/python/run.py` - STUB: returns schema-valid empty output (`coverage` nulls, empty `files`, `tools_missing` lists ruff/pytest-cov/bandit/radon/jscpd). Replaced in Stage 2.
- `quality-gate/languages/python/tools.json` - STUB: declares tools but no install commands (Stage 2 fills).
- `quality-gate/languages/python/metadata.json` - real metadata (language=python, manifests=[pyproject.toml, setup.py, requirements.txt], extensions=[.py], soft_limit=300, hard_limit=800).
- `quality-gate/languages/go/run.py` - STUB analogous to python.
- `quality-gate/languages/go/tools.json` - STUB.
- `quality-gate/languages/go/metadata.json` - real metadata (language=go, manifests=[go.mod], extensions=[.go], soft_limit=500, hard_limit=1000).
- `quality-gate/languages/rust/run.py` - STUB.
- `quality-gate/languages/rust/tools.json` - STUB.
- `quality-gate/languages/rust/metadata.json` - real metadata (language=rust, manifests=[Cargo.toml], extensions=[.rs], soft_limit=400, hard_limit=900).
- `quality-gate/languages/bunjs/run.py` - STUB.
- `quality-gate/languages/bunjs/tools.json` - STUB.
- `quality-gate/languages/bunjs/metadata.json` - real metadata (language=bunjs, manifests=[package.json + bun.lockb], extensions=[.ts,.tsx,.js,.jsx], soft_limit=300, hard_limit=800).

<!-- STAGE 1: order -->
**Order of operations:**
1. Create `quality-gate/` directory and all subdirectories (`schema/`, `lib/`, `languages/_template/`, `languages/python/`, `languages/go/`, `languages/rust/`, `languages/bunjs/`).
2. Write the three JSON Schemas (baseline, language_metrics, config). Validate each via `python3 -m json.tool`.
3. Write `lib/__init__.py` and the eight lib modules. Implement real logic for detect, baseline_io, config, ratchet, report, triage, validate_language, backlog; STUB only for security.
4. Write `cli.py` with all five subcommands wired through the lib modules. Implement exit codes exactly per spec.
5. Write `__init__.py` and `__main__.py` for the package.
6. Write `languages/_template/` (run.py + tools.json + metadata.json) as the canonical contract reference.
7. Write each `languages/<lang>/` triplet with stub run.py (returns schema-valid empty output), stub tools.json, real metadata.json.
8. Write initial `SKILL.md` with YAML frontmatter, happy-path, inviolable rules, and reference stubs.
9. Run inline gates: package import, py_compile across all .py, json.tool across all .json, validate_language against each stub's empty output.
10. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 1: verification -->
**Verification:** generate `docs/plans/quality-gate-skill-verify-stage-1.py` importing `_verify`. The script must:
1. `assert_only_files_touched` matches the declared file list (all under `quality-gate/`).
2. `run_gate("PYTHONPATH=/home/corcino/.claude/skills python3 -c 'import quality_gate; import quality_gate.cli; import quality_gate.lib.ratchet; import quality_gate.lib.report; import quality_gate.lib.detect; import quality_gate.lib.baseline_io; import quality_gate.lib.validate_language'")` exits 0.
3. `run_gate("python3 -m py_compile $(find /home/corcino/.claude/skills/quality-gate -name '*.py')")` exits 0.
4. `run_gate("for f in /home/corcino/.claude/skills/quality-gate/schema/*.json /home/corcino/.claude/skills/quality-gate/languages/*/tools.json /home/corcino/.claude/skills/quality-gate/languages/*/metadata.json; do python3 -m json.tool \"$f\" > /dev/null; done")` exits 0.
5. `run_gate("PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help")` exits 0 and stdout contains all five subcommands.
6. `run_gate("! find /home/corcino/.claude/skills/quality-gate/languages -name '*.sh'")` — no shell scripts under languages/.
7. Each stub `run.py` invocable as `python3 /home/corcino/.claude/skills/quality-gate/languages/<lang>/run.py --root /tmp --output /tmp/out.json`; output validates against `language_metrics.schema.json` via `lib/validate_language.py`.

<!-- STAGE 1: manual -->
**Manual verification (if any):** none

<!-- STAGE 1: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-1-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 1: handoff -->
**Hand-off prompt for Stage 1:**
> You are executing Stage 1 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 1 -->` and `<!-- END STAGE 1 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules (if it exists). Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: this is the first feature stage; no prior stage commits exist beyond Stage 0 baseline.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 1 only - Core skeleton (SKILL.md, schemas, lib, cli, _template, stub runners). Items: QG-CORE-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 1 -->
---

<!-- BEGIN STAGE 2 -->
## Stage 2 - Python language pack
<!-- STAGE 2: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE 2: tier-rationale -->
**Tier rationale:** Apply the language-pack contract defined in Stage 1: invoke well-known OSS tools (ruff, pytest+coverage, bandit, radon, jscpd), parse their JSON outputs, and normalize into the canonical schema. Standard coding with light judgment on the output mapping.
<!-- STAGE 2: items -->
**Items:** QG-PY-1
<!-- STAGE 2: scope -->
**Scope:** Replace the Python language-pack stubs (`run.py`, `tools.json`) with real implementations that invoke ruff (lint), pytest+coverage.py (tests + coverage), bandit (security patterns local), radon (complexity / max_depth), and jscpd (duplication); normalize all outputs into the `language_metrics.schema.json` shape; ship a sample-output fixture validated by the schema validator.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 2: files -->
**Files:**
- `quality-gate/languages/python/run.py` - real implementation: detect available tools per `tools.json`, run each with stable seeds (e.g. `pytest -p no:randomly`), parse outputs (ruff JSON, coverage XML/JSON, bandit JSON, radon JSON, jscpd JSON), normalize to canonical schema (`coverage` from coverage.py, `violations.errors`/`violations.warnings` from ruff+bandit, `files[*].max_depth` from radon, `duplication` from jscpd, per-file `lines`/`bytes` from filesystem stat for files crossing `soft_limit`).
- `quality-gate/languages/python/tools.json` - real manifest: ruff (`pip install ruff`), pytest+coverage (`pip install pytest pytest-cov coverage`), bandit (`pip install bandit`), radon (`pip install radon`), jscpd (`npm install -g jscpd`). Each entry has `name`, `purpose`, `detect_command`, `install_command`, `docs_url`.
- `quality-gate/languages/python/sample-output.json` - canonical example of a valid run.py output (used by Stage 2 verify and by future debugging). Must validate against `language_metrics.schema.json`.

<!-- STAGE 2: order -->
**Order of operations:**
1. Read `quality-gate/schema/language_metrics.schema.json` and `quality-gate/languages/_template/run.py` to confirm the contract before editing.
2. Implement `run.py`: argparse for `--root` and `--output`; for each tool in `tools.json`, run detection (`detect_command`), collect availability into `tools_used`/`tools_missing`; for available tools, run them under the project root and parse JSON outputs.
3. Normalize into the canonical schema; ensure deterministic ordering (sorted file list, sorted tool list) and 2-decimal rounding for percentages.
4. Replace `tools.json` with the real manifest.
5. Create `sample-output.json` reflecting a realistic small Python project.
6. Run `lib/validate_language.py sample-output.json` — must validate.
7. Inline gates: py_compile run.py; json.tool tools.json + sample-output.json; validate sample-output.json against schema.
8. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 2: verification -->
**Verification:**
1. `python3 -m py_compile /home/corcino/.claude/skills/quality-gate/languages/python/run.py` exits 0.
2. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/python/tools.json` exits 0.
3. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/python/sample-output.json` exits 0.
4. `PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language /home/corcino/.claude/skills/quality-gate/languages/python/sample-output.json` exits 0.

<!-- STAGE 2: manual -->
**Manual verification (if any):** none

<!-- STAGE 2: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-2-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 2: handoff -->
**Hand-off prompt for Stage 2:**
> You are executing Stage 2 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 2 -->` and `<!-- END STAGE 2 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..1 committed (confirm with `git log --oneline -1`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -1` and `git diff HEAD~1 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 2 only - Python language pack. Items: QG-PY-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 2 -->
---

<!-- BEGIN STAGE 3 -->
## Stage 3 - Go language pack
<!-- STAGE 3: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE 3: tier-rationale -->
**Tier rationale:** Mirror of Stage 2 against the Go toolchain. Standard work: invoke `go test -cover`, `golangci-lint` (with cyclomatic + max-depth linters enabled), `gocyclo`, `jscpd`, parse outputs, normalize. Light judgment on which `golangci-lint` linters map to errors vs warnings.
<!-- STAGE 3: items -->
**Items:** QG-GO-1
<!-- STAGE 3: scope -->
**Scope:** Replace the Go language-pack stubs with real implementations driving `go test -coverprofile`, `golangci-lint run --out-format json`, `gocyclo`, `jscpd`; normalize outputs to the canonical schema.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 3: files -->
**Files:**
- `quality-gate/languages/go/run.py` - real implementation: invokes Go-toolchain tools via subprocess, parses outputs, normalizes to canonical schema. Coverage from `go test -coverprofile=... && go tool cover -func`; violations from `golangci-lint run --out-format json` (errors = severity error, warnings = severity warning); per-file `max_depth` from `gocyclo`; duplication from `jscpd`.
- `quality-gate/languages/go/tools.json` - real manifest: golangci-lint (`go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest`), gocyclo (`go install github.com/fzipp/gocyclo/cmd/gocyclo@latest`), jscpd (`npm install -g jscpd`); `go` itself detected via `go version`.
- `quality-gate/languages/go/sample-output.json` - canonical example output validated by the schema.

<!-- STAGE 3: order -->
**Order of operations:**
1. Read `schema/language_metrics.schema.json` and `languages/_template/run.py`.
2. Implement `run.py` with tool detection, subprocess invocation, JSON parsing, normalization.
3. Replace `tools.json` with the real manifest.
4. Create `sample-output.json`.
5. Inline gates as per Verification.
6. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 3: verification -->
**Verification:**
1. `python3 -m py_compile /home/corcino/.claude/skills/quality-gate/languages/go/run.py` exits 0.
2. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/go/tools.json` exits 0.
3. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/go/sample-output.json` exits 0.
4. `PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language /home/corcino/.claude/skills/quality-gate/languages/go/sample-output.json` exits 0.

<!-- STAGE 3: manual -->
**Manual verification (if any):** none

<!-- STAGE 3: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-3-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 3: handoff -->
**Hand-off prompt for Stage 3:**
> You are executing Stage 3 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 3 -->` and `<!-- END STAGE 3 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..2 committed (confirm with `git log --oneline -2`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -2` and `git diff HEAD~2 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 3 only - Go language pack. Items: QG-GO-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 3 -->
---

<!-- BEGIN STAGE 4 -->
## Stage 4 - Rust language pack
<!-- STAGE 4: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE 4: tier-rationale -->
**Tier rationale:** Mirror of Stage 2 for Rust. Invoke `cargo llvm-cov` (coverage), `cargo clippy --message-format=json` (lint+complexity), `jscpd` (duplication). Standard work; minor judgment on clippy lint severity mapping.
<!-- STAGE 4: items -->
**Items:** QG-RS-1
<!-- STAGE 4: scope -->
**Scope:** Replace the Rust language-pack stubs with real implementations driving `cargo llvm-cov`, `cargo clippy`, `jscpd`; normalize outputs to the canonical schema.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 4: files -->
**Files:**
- `quality-gate/languages/rust/run.py` - real implementation: invokes `cargo llvm-cov --json` for coverage, `cargo clippy --message-format=json -- -W clippy::all` for violations (errors = `level=error`, warnings = `level=warning`), `jscpd` for duplication; per-file `lines`/`bytes` from filesystem stat for files crossing soft_limit.
- `quality-gate/languages/rust/tools.json` - real manifest: cargo (`detect: cargo --version`), cargo-llvm-cov (`cargo install cargo-llvm-cov`), clippy (`rustup component add clippy`), jscpd (`npm install -g jscpd`).
- `quality-gate/languages/rust/sample-output.json` - canonical example output validated by the schema.

<!-- STAGE 4: order -->
**Order of operations:**
1. Read `schema/language_metrics.schema.json` and `languages/_template/run.py`.
2. Implement `run.py`.
3. Replace `tools.json` with the real manifest.
4. Create `sample-output.json`.
5. Inline gates as per Verification.
6. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 4: verification -->
**Verification:**
1. `python3 -m py_compile /home/corcino/.claude/skills/quality-gate/languages/rust/run.py` exits 0.
2. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/rust/tools.json` exits 0.
3. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/rust/sample-output.json` exits 0.
4. `PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language /home/corcino/.claude/skills/quality-gate/languages/rust/sample-output.json` exits 0.

<!-- STAGE 4: manual -->
**Manual verification (if any):** none

<!-- STAGE 4: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-4-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 4: handoff -->
**Hand-off prompt for Stage 4:**
> You are executing Stage 4 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 4 -->` and `<!-- END STAGE 4 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..3 committed (confirm with `git log --oneline -3`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -3` and `git diff HEAD~3 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 4 only - Rust language pack. Items: QG-RS-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 4 -->
---

<!-- BEGIN STAGE 5 -->
## Stage 5 - BunJS language pack
<!-- STAGE 5: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE 5: tier-rationale -->
**Tier rationale:** Mirror of Stage 2 for BunJS. Invoke `bun test --coverage`, `biome check --reporter=json` (or oxlint as fallback), `jscpd`. Standard work; light judgment on biome vs oxlint preference per `tools.json` (prefer biome — single-tool lint+format).
<!-- STAGE 5: items -->
**Items:** QG-BUN-1
<!-- STAGE 5: scope -->
**Scope:** Replace the BunJS language-pack stubs with real implementations driving `bun test --coverage`, `biome check --reporter=json`, `jscpd`; normalize outputs to the canonical schema.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 5: files -->
**Files:**
- `quality-gate/languages/bunjs/run.py` - real implementation: invokes `bun test --coverage --reporter=junit` (parses LCOV/coverage output), `biome check --reporter=json` (or oxlint if biome absent — declared in tools.json fallback order), `jscpd`; per-file `lines`/`bytes` from filesystem stat for files crossing soft_limit; max_depth via biome's complexity rules or skipped if unavailable.
- `quality-gate/languages/bunjs/tools.json` - real manifest: bun (`detect: bun --version`, `install: curl -fsSL https://bun.sh/install | bash`), biome (`bun add -d @biomejs/biome`, primary), oxlint (`bun add -d oxlint`, fallback), jscpd (`bun add -d jscpd`).
- `quality-gate/languages/bunjs/sample-output.json` - canonical example output validated by the schema.

<!-- STAGE 5: order -->
**Order of operations:**
1. Read `schema/language_metrics.schema.json` and `languages/_template/run.py`.
2. Implement `run.py` with biome-primary, oxlint-fallback detection.
3. Replace `tools.json` with the real manifest.
4. Create `sample-output.json`.
5. Inline gates as per Verification.
6. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 5: verification -->
**Verification:**
1. `python3 -m py_compile /home/corcino/.claude/skills/quality-gate/languages/bunjs/run.py` exits 0.
2. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/bunjs/tools.json` exits 0.
3. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/languages/bunjs/sample-output.json` exits 0.
4. `PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language /home/corcino/.claude/skills/quality-gate/languages/bunjs/sample-output.json` exits 0.

<!-- STAGE 5: manual -->
**Manual verification (if any):** none

<!-- STAGE 5: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-5-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 5: handoff -->
**Hand-off prompt for Stage 5:**
> You are executing Stage 5 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 5 -->` and `<!-- END STAGE 5 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..4 committed (confirm with `git log --oneline -4`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -4` and `git diff HEAD~4 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 5 only - BunJS language pack. Items: QG-BUN-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 5 -->
---

<!-- BEGIN STAGE 6 -->
## Stage 6 - Security pack (OSV-Scanner + Semgrep CE)
<!-- STAGE 6: tier-effort -->
**Tier:** standard         <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** standard       <!-- minimal | standard | extended -->
<!-- STAGE 6: tier-rationale -->
**Tier rationale:** Replace the `lib/security.py` stub (delivered in Stage 1) with real cross-language security collection. Standard work: invoke OSV-Scanner (deps) and Semgrep CE (SAST) per project root, parse JSON outputs, populate the canonical `vulnerabilities` and `violations` fields. The ratchet rule for criticals (=0) is already encoded in Stage 1's `lib/ratchet.py`; Stage 6 only feeds it real data.
<!-- STAGE 6: items -->
**Items:** QG-SEC-1
<!-- STAGE 6: scope -->
**Scope:** Replace `lib/security.py` stub with real implementation invoking `osv-scanner` and `semgrep` per project root; merge results into per-project metrics; add a manifest declaring how to detect and install these two tools.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding. The ratchet rule table in `lib/ratchet.py` already handles vulnerabilities — do NOT modify it.

<!-- STAGE 6: files -->
**Files:**
- `quality-gate/lib/security.py` - real implementation: takes `project_root` and returns `{"vulnerabilities": {"critical":N,"high":N,"medium":N,"low":N}, "violations_security": {"errors":N, "warnings":N}, "tools_used": [...], "tools_missing": [...]}`. Invokes `osv-scanner --format json -r <root>` and `semgrep --json --config=auto <root>` via subprocess; falls back to empty results with `tools_missing` populated if either binary is absent (does NOT fail; the anti-cheat rule lives in `lib/ratchet.py` which checks baseline.tools_used vs current.tools_used).
- `quality-gate/lib/security_tools.json` - manifest declaring osv-scanner (`go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest` or binary download from releases) and semgrep (`pipx install semgrep`); each entry has `name`, `purpose`, `detect_command`, `install_command`, `docs_url`.
- `quality-gate/lib/security-sample-output.json` - canonical example of `security.collect()` output for documentation and validate-step reference.

<!-- STAGE 6: order -->
**Order of operations:**
1. Read `lib/security.py` stub (delivered in Stage 1) to confirm the expected return contract.
2. Read `lib/ratchet.py` to confirm vulnerability rule handling already lives there (must not modify).
3. Implement `security.py`: detect tool availability via `tools_used`/`tools_missing`; invoke each available tool; parse JSON; aggregate counts by severity.
4. Write `security_tools.json` manifest.
5. Write `security-sample-output.json`.
6. Inline gates: py_compile security.py; json.tool on both JSON files; assert ratchet.py unchanged via `git diff --quiet HEAD -- quality-gate/lib/ratchet.py`.
7. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 6: verification -->
**Verification:**
1. `python3 -m py_compile /home/corcino/.claude/skills/quality-gate/lib/security.py` exits 0.
2. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/lib/security_tools.json` exits 0.
3. `python3 -m json.tool /home/corcino/.claude/skills/quality-gate/lib/security-sample-output.json` exits 0.
4. `git diff --quiet HEAD -- quality-gate/lib/ratchet.py` exits 0 (ratchet untouched).
5. `PYTHONPATH=/home/corcino/.claude/skills python3 -c "from quality_gate.lib import security; out = security.collect('/tmp'); assert 'vulnerabilities' in out and 'tools_used' in out and 'tools_missing' in out"` exits 0.

<!-- STAGE 6: manual -->
**Manual verification (if any):** none

<!-- STAGE 6: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-6-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 6: handoff -->
**Hand-off prompt for Stage 6:**
> You are executing Stage 6 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 6 -->` and `<!-- END STAGE 6 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..5 committed (confirm with `git log --oneline -5`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -5` and `git diff HEAD~5 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 6 only - Security pack (OSV-Scanner + Semgrep CE). Items: QG-SEC-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 6 -->
---

<!-- BEGIN STAGE 7 -->
## Stage 7 - references/ docs and SKILL.md finalization
<!-- STAGE 7: tier-effort -->
**Tier:** mechanical       <!-- mechanical | standard | judgment | critical — see § Resource selection vocabulary -->
**Effort:** minimal        <!-- minimal | standard | extended -->
<!-- STAGE 7: tier-rationale -->
**Tier rationale:** Pure documentation. Write the four reference markdown files and polish SKILL.md links/wording. No design decisions, no code, no contract changes.
<!-- STAGE 7: items -->
**Items:** QG-DOCS-1
<!-- STAGE 7: scope -->
**Scope:** Author the four `references/` documents (bootstrap, missing-tools, monorepo, adding-language) and polish SKILL.md so the happy-path text plus links to references are coherent and complete.
**Scope discipline:** stay within the declared file list; if the stage requires
touching files outside it, STOP and report instead of silently expanding.

<!-- STAGE 7: files -->
**Files:**
- `quality-gate/SKILL.md` - polish only: confirm YAML frontmatter, finalize happy-path wording, ensure all `references/*.md` links resolve, ensure inviolable rules list matches the implementation, add the to-backlog escalation note.
- `quality-gate/references/bootstrap.md` - explains `quality-gate init` flow: when to use, that it only runs on main, what gets committed (`.quality-gate/baseline.json` + `.quality-gate/.gitignore` + optional `.quality-gate/config.json`), and the bootstrap-only "no comparison" semantics.
- `quality-gate/references/missing-tools.md` - protocol for handling missing tools: how the skill detects them via each `tools.json`, the difference between `PASSED_WITH_GAPS` and `TOOL_MISSING_REGRESSION`, install commands sourced from manifests, and the anti-cheat rule (baseline tool ausência = FAIL).
- `quality-gate/references/monorepo.md` - autodetect heuristic (manifests at root vs subdirectories), `.quality-gate/config.json` schema with examples, per-project baseline namespacing, and how `--language` / `--only` flags scope to one project.
- `quality-gate/references/adding-language.md` - step-by-step contract for a new language: copy `languages/_template/`, fill `tools.json`/`metadata.json`/`run.py`, produce schema-valid output, validate with `lib/validate_language.py`, ship `sample-output.json`.

<!-- STAGE 7: order -->
**Order of operations:**
1. Write each `references/*.md` file in turn.
2. Read current `SKILL.md` and polish it: fix any reference stub links to point at the new files; tighten happy-path wording; verify inviolable rules list.
3. Inline gates: every link in SKILL.md to `references/*.md` must resolve to a file that exists; SKILL.md must still have valid YAML frontmatter starting with `---\nname: quality-gate`.
4. Gates pass -> write the post-stage report -> stage code files AND the
   report file together -> commit. (One commit per stage; report is committed
   alongside the code.)

<!-- STAGE 7: verification -->
**Verification:**
1. All four files exist: `test -f /home/corcino/.claude/skills/quality-gate/references/bootstrap.md && test -f /home/corcino/.claude/skills/quality-gate/references/missing-tools.md && test -f /home/corcino/.claude/skills/quality-gate/references/monorepo.md && test -f /home/corcino/.claude/skills/quality-gate/references/adding-language.md` exits 0.
2. SKILL.md frontmatter check: `head -1 /home/corcino/.claude/skills/quality-gate/SKILL.md | grep -q '^---$' && grep -q '^name: quality-gate$' /home/corcino/.claude/skills/quality-gate/SKILL.md` exits 0.
3. Every relative reference link in SKILL.md resolves: `python3 -c "import re,os,sys; p='/home/corcino/.claude/skills/quality-gate/SKILL.md'; t=open(p).read(); base=os.path.dirname(p); missing=[l for l in re.findall(r'\\(references/[^)]+\\)', t) if not os.path.exists(os.path.join(base, l[1:-1]))]; sys.exit(1 if missing else 0)"` exits 0.

<!-- STAGE 7: manual -->
**Manual verification (if any):** none

<!-- STAGE 7: report -->
**Post-stage report:** write `/home/corcino/.claude/skills/docs/plans/quality-gate-skill-stage-7-report.md`. Copy `docs/plans/_report-template.md` as the starting structure; leave the `Commit:` slot as `_filled by parent_` — the End-to-end summary table is the canonical source for that mapping.

<!-- STAGE 7: handoff -->
**Hand-off prompt for Stage 7:**
> You are executing Stage 7 of Quality Gate skill at /home/corcino/.claude/skills/docs/plans/quality-gate-skill.md.
> From that plan file, read ONLY: (a) `## Execution model`, (b) `## Execution policy`,
> (c) `## Hand-off conventions`, (d) `## Global conventions`, (e) `## Critical files`,
> and (f) your own stage block between `<!-- BEGIN STAGE 7 -->` and `<!-- END STAGE 7 -->`.
> Do NOT read other stages' blocks — they are not your context. Then read
> /home/corcino/.claude/skills/CLAUDE.md for repo-wide rules. Your authoritative spec is the stage block.
>
> Repo root: /home/corcino/.claude/skills
> Branch: feat/quality-gate (confirm with `git rev-parse --abbrev-ref HEAD`)
> Platform: linux  (bash syntax, forward slashes)
>
> Status: Stages 1..6 committed (confirm with `git log --oneline -6`).
> Prior stages' work is reflected in: (1) the actual code state — run
> `git log --oneline -6` and `git diff HEAD~6 HEAD --stat` if you need
> to see what changed; (2) `## Critical files` in the plan (cross-stage index);
> (3) prior stage reports under `docs/plans/<slug>-stage-K-report.md` if you
> need detail on a specific surprise or deviation. Do NOT read other stages'
> BEGIN/END blocks for prior context — git is the source of truth.
>
> Line-number hints in the plan may be stale after prior stages; grep for symbols.
>
> Your scope: Stage 7 only - references/ docs and SKILL.md finalization. Items: QG-DOCS-1.
>
> Spec is your stage block (Files, Order of operations, Verification, Report
> path). Gates/invariants/commit style: `## Global conventions`. Working-tree
> policy: `## Execution policy`. Authorization/scope/failure/return-to-parent:
> `## Hand-off conventions`.
>
> Commit step: after gates pass, copy `docs/plans/_report-template.md` to the
> report path declared in your stage block (leave the `Commit:` slot as
> `_filled by parent_`), then stage code files AND the report together by
> explicit path and commit with the
> `Co-Authored-By: $EXECUTOR_NAME $EXECUTOR_EMAIL` trailer. One commit per stage.
>
> Begin now.

<!-- END STAGE 7 -->
---

## Reviewer gate (only if Reviewer != none)
**Tier:** critical
**Effort:** extended
After the final stage commits green:
- reviewer: light -> small subagent validates scope, diff vs. plan, gate
  results, post-stage reports, and obvious risk. Does NOT replan.
- reviewer: deep -> same plus security/perf/maintainability lens for
  stack-relevant best practices.

Reviewer returns a verdict in
`pass | pass-with-notes | fail | blocked`
plus a findings list (each: `file:line`, severity, description).
Reviewer never edits code and never replans.
If a `reviewer` skill is available in the executor, prefer it; otherwise use
an inline QA prompt that takes the plan + diff range as input.

### Arbiter (run only if findings list is non-empty)
**Tier:** critical / **Effort:** focused
Reads the reviewer verdict + findings + diff range. For each finding,
applies this decision tree verbatim:

1. Is this a real defect? (correctness, security, contract, data integrity)
   - No  -> classify `nice-to-have`.
   - Yes -> step 2.
2. Is the fix mechanical (one obvious right answer, no design choice)
   AND fully inside the plan's declared file list?
   - Yes -> classify `must-fix`.
   - No  -> classify `human-judgment`.

Arbiter records both answers per finding in the output md (auditable).
Arbiter does NOT edit code and does NOT replan.

### Fix round (run only if any `must-fix` exists; HARD MAX = 1 round)
**Tier:** standard / **Effort:** focused
Fix-subagent receives only the `must-fix` items + their target files.
- Applies fixes within those files only.
- For each item: writes a `fix note` -- what changed, line(s), and one
  sentence linking the change to the original finding.
- If a `must-fix` proves to require out-of-scope work or a design choice,
  reclassify it as `human-judgment` and skip it. Do NOT block sibling fixes.
After the round: re-run every declared gate (build/lint/test/etc.). Gate
failure does NOT trigger another fix round -- the failure goes into the
pending list and the verdict degrades.

### Re-review (conditional)
Run a second reviewer pass (same level: light/deep) only if EITHER:
- The plan's Tier was `critical`, OR
- The fix round modified files outside the declared scope of the
  originating `must-fix` finding (scope-creep signal).

Any *new* finding from re-review goes straight to the pending list of the
next sequence file. Re-review does NOT trigger another fix round.

### Output file (always written when this gate runs)
Path: `docs/plans/reports/quality-gate-skill_reviewer_<seq>.md`
- `<seq>` is a zero-padded 3-digit counter starting at `001`, incremented
  for each run of this gate against the same plan.
- Each sequence file is **immutable** once written. Re-runs produce a
  new file, never overwrite.

Top of file: final verdict in
`pass | pass-with-notes | pass-with-fixes | pass-with-pending | fail | blocked`

Body sections (in order):
- `## Reviewer verdict` -- raw reviewer output, verbatim.
- `## Arbiter classification` -- table per finding: `file:line`, severity,
  class (must-fix / nice-to-have / human-judgment), decision-tree answers
  (defect? yes/no -- mechanical+in-scope? yes/no), 1-line reason.
- `## Fixes applied` -- one entry per `must-fix` corrected, with the fix
  note (what changed, lines, link to finding).
- `## Pending` -- every `human-judgment` finding + every `must-fix`
  reclassified to `human-judgment` during the fix round + any new finding
  from re-review. Each entry:
  - `file:line`
  - reviewer's original finding (short quote)
  - arbiter's reason for human classification
  - suggested action (may be "decide whether to address")

Verdict mapping:
- `pass` / `pass-with-notes` -- reviewer's original verdict, no findings
  needed fixing.
- `pass-with-fixes` -- all `must-fix` corrected, no pending items.
- `pass-with-pending` -- corrections completed (or none needed), but
  `Pending` section is non-empty.
- `fail` / `blocked` -- reviewer's verdict was `fail`/`blocked`, OR gates
  failed after the fix round. Parent stops the plan and surfaces the md
  file path to the user.

## Critical files (cross-stage index)
| File | Stages | Notes |
|---|---|---|
| `quality-gate/SKILL.md` | S1 (initial), S7 (polish) | YAML frontmatter must remain valid across both stages |
| `quality-gate/cli.py` | S1 | Touched only by S1; subsequent stages depend on its subcommand contract |
| `quality-gate/schema/baseline.schema.json` | S1 | Read by every other stage; never modified after S1 |
| `quality-gate/schema/language_metrics.schema.json` | S1 | Validated against by S2–S6 |
| `quality-gate/schema/config.schema.json` | S1 | Read by S7 docs |
| `quality-gate/lib/ratchet.py` | S1 | Full rule table including vulns; S6 does NOT modify it |
| `quality-gate/lib/validate_language.py` | S1 | Invoked by S2–S6 verification gates |
| `quality-gate/lib/security.py` | S1 (stub), S6 (real impl) | Only place where Stage 6 modifies S1 output |
| `quality-gate/languages/_template/` (run.py, tools.json, metadata.json) | S1 | Reference contract; S2–S5 read but do not modify |
| `quality-gate/languages/python/{run.py,tools.json}` | S1 (stub), S2 (real) | metadata.json fixed in S1 |
| `quality-gate/languages/go/{run.py,tools.json}` | S1 (stub), S3 (real) | metadata.json fixed in S1 |
| `quality-gate/languages/rust/{run.py,tools.json}` | S1 (stub), S4 (real) | metadata.json fixed in S1 |
| `quality-gate/languages/bunjs/{run.py,tools.json}` | S1 (stub), S5 (real) | metadata.json fixed in S1 |
| `quality-gate/references/*.md` | S7 | Created only in S7; S1 SKILL.md references them as forward links |

## End-to-end verification (after final stage)
Generate `docs/plans/quality-gate-skill-verify-e2e.py` importing `_verify`. The script must:
1. Package import: `PYTHONPATH=/home/corcino/.claude/skills python3 -c "import quality_gate, quality_gate.cli, quality_gate.lib.ratchet, quality_gate.lib.report, quality_gate.lib.detect, quality_gate.lib.baseline_io, quality_gate.lib.validate_language, quality_gate.lib.security, quality_gate.lib.backlog, quality_gate.lib.triage, quality_gate.lib.config"` exits 0.
2. Compile all Python: `python3 -m py_compile $(find /home/corcino/.claude/skills/quality-gate -name '*.py')` exits 0.
3. Validate every JSON file: `for f in $(find /home/corcino/.claude/skills/quality-gate -name '*.json'); do python3 -m json.tool "$f" > /dev/null; done` exits 0.
4. CLI surface: `PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help` exits 0 and stdout contains `init`, `run`, `status`, `update-baseline`, `to-backlog`.
5. Each language pack's `sample-output.json` validates against `language_metrics.schema.json` via `lib/validate_language.py` (S2–S5 fixtures).
6. Invariant: no shell scripts under `languages/` — `find /home/corcino/.claude/skills/quality-gate/languages -name '*.sh' | wc -l` returns `0`.
7. SKILL.md links resolve: every `references/*.md` link in SKILL.md points at a file that exists.
8. Ratchet rule table sanity: `PYTHONPATH=/home/corcino/.claude/skills python3 -c "from quality_gate.lib import ratchet; assert hasattr(ratchet, 'compare')"` exits 0.

## End-to-end summary (parent fills after final stage)
| Stage | Title | Tier | Effort | Model used | Commit SHA | Status | Report |
|-------|-------|------|--------|------------|------------|--------|--------|
<!-- one row per stage. `Model used` is what the executor actually selected
on its platform for the declared Tier/Effort (the executor fills this — the
plan never prescribes model names). Used post-hoc to audit whether the
platform mapping is well-calibrated. If <40% of rows are mechanical/standard,
the decomposition is suspect — too many stages classified as judgment/critical
defeats the cost-savings purpose. -->
