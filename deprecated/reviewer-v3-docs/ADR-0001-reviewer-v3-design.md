# ADR-0001: Reviewer v3 Design

Status: proposed
Date: 2026-05-01
Supersedes: reviewer (v1), reviewer-v2 (after validation; see Migration)

## Context

Two prior iterations exist: `reviewer` (v1) and `reviewer-v2`. Both were
benchmarked against the same target (`baileys2api_bun`, branch `feat/dev-setup`)
in `reviewer-v2/ADR-0001-reviewer-v2-benchmark.md` (Runs A–F).

Empirical findings from that matrix:

- v1 (Runs A, B): a 590-line procedural SKILL with 4 phases, multi-tier plans
  (S/M/L/XL), token-cap arithmetic, supersede/dedup hashing, and three
  always-on subagents pushed the model toward protocol compliance over review
  judgment. Tweaks made it worse (B regressed against A). Did not execute
  declared checks well; missed red CI and executable failures.
- v2 (Runs E, F): a short main prompt with a 884-line Python harness and five
  always-on evidence lanes produced the best standardized output yet. The
  harness encoded target-specific patterns (Bun, Docker, compose, `.npmrc`,
  `bunfig.toml`, `GH_TOKEN_PKG`, `release|setup|build` regexes), violating the
  project rule that skills must stay general. Five fixed lanes raised cost on
  small/medium reviews. Operational/spec lanes overreached without
  cross-context (`SESSION_DIR`, `drain()`, credential leakage). Calibration
  oscillated between sensitive (E) and recall-suppressed (F). Praise leaks
  persisted despite explicit rules.
- Native reviews (Runs C, D) won on recall when given autonomy; lost on
  standardized output and over-classified one or two recurring items.

Cross-benchmark conclusion: the value of a multi-agent reviewer over a strong
native review is small unless multi-agent buys (a) parallelism that fits in
context budget, (b) standardized output, or (c) grounded executed checks.
Everything else is overhead.

Project constraint (from auto-memory): skills must stay general; runtime
decisions belong to the LLM, not to harness regex.

## Decision

Build `reviewer-v3` around four principles:

1. **Native-driven**. The LLM begins with its own tools (git, file reads,
   command execution) and decides what to read, what to run, and when to
   parallelize.
2. **Audit-validated**. A deterministic, project-agnostic audit at the end
   compares the LLM's declared coverage against a ground-truth file list. Gaps
   surface to the LLM as a *provocation* — "consider these too, or move them
   to `not-reviewed` with reason; ignore if they don't make sense" — never as
   forced re-review or forced verdict. The model remains the judge.
3. **Subagents are capabilities, not tiers**. Three LLM-invokable subagents
   exist (`defect-hunter`, `test-auditor`, `verifier`); the LLM chooses when to
   spawn them. No auto-trigger by file count or threshold.
4. **Calibration centralized**. The HIGH-gate, severity rubric, OPEN_QUESTION
   rules, and anti-praise rules live in `SKILL.md`. Subagents emit evidence
   with a `severity_signal` (sugestion); the main reviewer adjudicates final
   severity.

## Detailed Decisions

### D1. Identity and migration
v3 lives at `skills/reviewer-v3/` during validation, with a description that
does **not** match generic "code review" requests — only explicit
`/reviewer-v3` invocation triggers it. After Run G passes acceptance criteria
(see Validation), v3 renames to `reviewer`; v1 and v2 are removed from active
skills (preserved in git history and ADRs as benchmark baselines).

### D2. No plan tier
v1's S/M/L/XL plan table and v2's always-on five-lane fan-out are both removed.
Pre-determining scope by file count is a limiter that contradicted benchmark
evidence (Run C won by being free). The LLM sizes its own work.

### D3. Three subagents, all LLM-invokable

| Subagent | Soul | When to invoke (LLM judgment, suggestive) |
|---|---|---|
| `defect-hunter` | "I read the code while imagining the system failing under real users, real data, and hostile states. A finding deserves to exist only when there is an execution path, concrete impact, and a plausible fix." | Large diff or multi-package change where parallelism on correctness/security passes adds throughput without losing context. |
| `test-auditor` | "I do not count tests; I weigh evidence. For every assertion, I ask what lie it would let pass and what truth it would punish. My enemy is false confidence." | Dense or critical test suites where the TDD-discrimination mode pays off (security, financial, data integrity, contract). |
| `verifier` | "I turn suspicion into executable facts with the smallest command that actually answers something. I do not hide what I did not run, because verification limits are part of the truth." | Heavy or risky verification sweeps (multi-package typecheck, integration suite, docker build, CI parsing) that benefit from isolated context and explicit not-exercised reporting. |

Subagents emit `EVIDENCE` lines with a `severity_signal=<high|medium|low|info>`
(advisory, not verdict). All files referenced by subagent findings count
toward the audit's reviewed-set. Cost is zero when not invoked.

### D4. Audit at the end

`fact_pack.sh` runs at the end (not at the start) and produces the ground
truth set of material files for comparison against the main reviewer's declared
`## Coverage` section.

### D5. Coverage section format (Option F)

The `## Coverage` section declares only what was **not done at the expected
level**. Everything else is implicitly reviewed.

```
## Coverage
excluded:
  - bun.lock (lockfile)
  - dist/bundle.js (generated)
not-reviewed:
  - src/legacy/big.ts (file >2000 lines, scope cap)
  - infra/terraform/main.tf (out of expertise; partial scope)
```

Audit rules:

```
1. material_set := fact_pack.material_files
2. claimed_excluded ⊆ fact_pack.excluded_files
3. inferred_reviewed := material_set − explicit_not_reviewed
4. ∀ finding: file ∉ explicit_not_reviewed ∧ file ∉ claimed_excluded
5. ∀ file ∈ material_set: file ∈ inferred_reviewed ∨ file ∈ explicit_not_reviewed
6. explicit_not_reviewed ≠ ∅ ⇒ scope := partial(<reasons>)
```

A failure of rules 1–5 surfaces the unmatched files as a **provocation** to
the LLM: *"these material files are not in your coverage — review them or
move them to `not-reviewed` with a reason; ignore if they don't make sense
for this review."* The LLM does a second pass and judges. If after the
second pass every material file is placed into `reviewed`, `not-reviewed`
(with reason), or `excluded`, the audit accepts and the report stands (with
`scope: partial` if `not-reviewed` is non-empty). The audit never adds
findings, never edits severity, never forces a verdict — it surfaces what
was missed and lets the model decide. One re-emission cycle is the cap;
beyond that, unaddressed files are annotated and `scope: partial` is set.

### D6. Audit mechanics: Stop hook with provocation

The audit runs as a Stop hook configured in `.claude/settings.json`. On the
LLM's stop event, the hook invokes `audit.sh` against the emitted report's
`## Coverage` section.

- **No gap**: hook approves stop. The verbatim audit output is appended to
  the report's `audit_output:` trailer by the hook (post-emission).
- **Gap detected**: hook blocks stop and injects the gap list as a
  provocation message to the LLM. The LLM does a second pass — review the
  surfaced files and add findings, or move them to `not-reviewed` with a
  one-phrase reason. The LLM re-emits the report; hook re-runs.
- **Persistent gap after second pass**: hook approves stop with
  `scope: partial`; unaddressed files are annotated in `## Coverage` by
  the hook before stop is approved. One re-emission cycle is the cap —
  beyond that the hook releases stop to avoid forcing the model.

The hook never forces severity, verdict, or finding count. Its only role is
to ensure no material file leaves the review without an explicit decision
from the model. The SKILL prompt does **not** mandate the LLM to invoke
`audit.sh` — that is the hook's job. Single-layer ownership keeps the prompt
focused on review craft and removes the dual-mandate redundancy of earlier
drafts.

### D7. Calibration centralized in SKILL

`SKILL.md` is the single locus for:

- HIGH gate (one of: red declared check reproduced this run; runtime
  correctness bug with proven execution path; security defect in a touched
  flow; explicit spec violation; test where a non-conformant target can pass
  on changed behavior).
- OPEN_QUESTION rule (when proof depends on unverified context).
- Conflicting-spec rule (cite both, name controlling clause; otherwise
  OPEN_QUESTION).
- Severity rubric (HIGH / MEDIUM / LOW / INFO).
- Scope rule (findings on changed lines or unchanged lines made worse by the
  change).
- The two TDD questions (can a non-conformant target pass? can a conformant
  target fail?).
- Anti-praise enforcement.

Subagents emit `severity_signal` only; the main reviewer applies the rubric to
produce final severity. The main reviewer may downgrade a subagent signal but
**may not promote** above its declared signal — defense against subagent
over-severity in isolated context.

### D8. Defaults registered (six smaller decisions)

| Decision | Default | Justification |
|---|---|---|
| Final report template | Inherits `reviewer-v2/templates/final_report.md` shape; adds `## Coverage` section and an `audit_output:` trailer populated by the Stop hook (LLM does not write it) | v2 shape works; minimal change |
| EVIDENCE shape (subagents) | Single-line v2 shape, but `severity=` replaced with `severity_signal=` | Reflects D7 |
| Anti-praise enforcement | The `## Notes` placeholder in the template states verbatim: `Notes accepts only: scope limits, skipped checks, adjudication caveats, evidence caveats. Praise, "strong positives", strengths, and positive summaries are forbidden.` | Structural placement at the point of writing |
| Invocation form | Free-form only. The user describes the target, references files/branches/SHAs/specs anywhere in the message; the main reviewer extracts signals natively. No structured `/reviewer-v3 [target] base= spec=` form. | Structured form duplicates what the LLM already does well from message context; one path is simpler to teach and to maintain. |
| Visibility markers | Removed (no `[reviewer] phase X` markers) | v1 had them because of phases; v3 has no phases |
| Spec discovery | Native LLM discovery; `fact_pack.sh` only **lists** candidate spec directories that exist on disk. No keyword scoring, no recency ranking. | Ranking was a source of false-positive selection in v1/v2 |

## Skill Structure

```
reviewer-v3/
  ADR-0001-reviewer-v3-design.md      this document
  SKILL.md                            ~80–100 lines: soul, calibration,
                                      subagent guidance, output shape
                                      (no audit mandate — hook owns it)
  scripts/
    fact_pack.sh                      ~80 lines bash, project-agnostic; emits
                                      ground-truth JSON
    audit.sh                          ~50 lines bash, applies audit rules
                                      D5; emits structured pass/gap output
    run_check.sh                      optional helper: timeout-bounded command
                                      execution with captured output
  hooks/
    stop_audit.sh                     ~30 lines bash; Stop-hook wrapper that
                                      runs fact_pack + audit, blocks-or-approves
                                      stop, appends audit_output trailer
  subagents/
    defect-hunter.md                  ~50 lines: soul + scope + EVIDENCE shape
    test-auditor.md                   ~50 lines: soul + two-questions + shape
    verifier.md                       ~50 lines: soul + safe-command policy
  templates/
    final_report.md                   header + Findings + Coverage +
                                      Open Questions + Verification + Notes;
                                      anti-praise structural placeholder
```

## Workflow

```
1. User invokes /reviewer-v3 with a free-form message describing the
   target. Files, branches, SHAs, PR numbers, and spec references may
   appear anywhere in the message.
2. Main reviewer (LLM) extracts target/base/spec signals from the message
   and resolves them via git natively. No pre-built fact pack at start.
3. Main reviewer reviews. May:
   - read any files needed
   - run any declared checks (typecheck, lint, tests, build)
   - spawn defect-hunter / test-auditor / verifier subagents at its discretion
4. Main reviewer composes final report including ## Coverage section, then
   stops. The LLM does not invoke audit.sh — that is the hook's job.
5. Stop hook runs fact_pack.sh + audit.sh against the emitted report.
6. If audit detects gap → hook blocks stop and injects a provocation
   listing the missing files: "review them or move them to not-reviewed
   with reason; ignore if they don't make sense". LLM does a second pass
   and re-emits.
7. Hook re-runs. On pass or partial, hook appends audit_output trailer
   to the report and approves stop. One re-emission cycle is the cap.
```

## SKILL.md Contract (sketch)

Sections, in order:

1. **Description (frontmatter)** — narrow during validation; broad after
   promotion.
2. **Soul of the main reviewer** — quoted verbatim from the GENERAL Purpose
   the user provided ("When the context is too large, I make the world
   smaller without lying about what was left outside…"). Strips legacy
   four-phase language.
3. **What good review looks like** — findings-first, no praise, cite
   `file:line`/command output/spec clause, no inflated severity.
4. **Calibration rules** (D7).
5. **Subagent guidance** (D3 table + suggestive triggers, never thresholds).
6. **Output shape** — pointer to template + structural rules (`## Coverage`
   format F; `audit_output:` trailer is appended by the Stop hook, not by
   the LLM).
7. **Hard rules** — read-only on source/specs; never invent a finding;
   never include praise.

The SKILL prompt says nothing about invoking `audit.sh`. The hook owns it.

Target length: 80–100 lines.

## fact_pack.sh Contract

Inputs:
- `--repo <path>` (default `.`)
- `--target <ref-or-path>` (default `working-tree`)
- `--base <ref>` (default `origin/main` → `origin/master` → `main` → `master`)

Output: JSON to stdout, with these top-level keys:

```json
{
  "generated_at": "...",
  "repo": "...",
  "target": "...",
  "base": "...",
  "head": "...",
  "branch": "...",
  "material_files": ["src/foo.ts", "src/bar.ts", "tests/foo.test.ts"],
  "excluded_files": [
    {"path": "bun.lock", "reason": "lockfile"},
    {"path": "dist/bundle.js", "reason": "generated"}
  ],
  "spec_directories": ["docs/adr", "docs/specs"],
  "manifests": ["package.json", "bun.lock", "Dockerfile"],
  "package_roots": [".", "packages/x"]
}
```

Exclusion rules (canonical, project-agnostic):

- **Lockfiles** (canonical list): `package-lock.json`, `yarn.lock`,
  `pnpm-lock.yaml`, `bun.lock`, `Cargo.lock`, `poetry.lock`, `Pipfile.lock`,
  `composer.lock`, `go.sum`.
- **Generated**: first-line marker `// @generated` or `# Code generated`.
- **Build/dist paths**: `dist/`, `build/`, `out/`, `.next/`, `coverage/`,
  `node_modules/`, `vendor/`, `__pycache__/`, `target/`.
- **Binary**: fails UTF-8 decode of first 4 KB.

The script does not classify files as "operational" or "test" or "manifest"
beyond what the LLM can derive from the path. It does not score, rank, or
recommend. **It does not auto-exclude by size or line count** — large files
remain in `material_files`; the LLM decides whether to move them to
`not-reviewed` with a `scope cap` reason.

## audit.sh Contract

Inputs:
- `--coverage <path-to-coverage-block-extracted-from-llm-output>` OR stdin
- `--fact-pack <path-to-fact-pack-json>`

Behavior: applies rules 1–5 from D5. Output to stdout:

```
audit: pass
material: 47
excluded: 8
not_reviewed: 0
gap: none
```

or

```
audit: gap
material: 47
excluded: 8
not_reviewed: 0
gap: src/auth/session.ts, src/api/users.ts
```

or

```
audit: partial
material: 47
excluded: 8
not_reviewed: 2 (src/legacy/big.ts: scope cap; infra/terraform/main.tf: out of expertise)
gap: none
```

Exit codes: 0 if `pass` or `partial`; 2 if `gap` (the Stop hook reads exit
code to decide whether to block stop and surface a provocation).

## Stop Hook Contract

`hooks/stop_audit.sh` is registered in `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "<skill-dir>/hooks/stop_audit.sh"}
        ]
      }
    ]
  }
}
```

Behavior:

1. Read the LLM's last assistant message (the emitted report).
2. Extract the `## Coverage` block.
3. Run `fact_pack.sh` and `audit.sh`.
4. If `audit` exit = 2 (gap): emit `decision: block` with a `reason`
   carrying the provocation text + gap list. The LLM resumes, re-emits
   the report.
5. If `audit` exit = 0 (pass or partial): append the verbatim audit output
   under an `audit_output:` trailer to the report and approve stop.
6. Re-emission cycle is capped at 1 via a temp marker in the working
   directory keyed to the conversation. Past the cap the hook approves
   stop, annotates unaddressed files in `## Coverage`, and marks
   `scope: partial`. The model is provoked once, not pestered.

The hook is project-agnostic: it does not parse findings, severities, or
verdicts; it only reconciles file-set coverage.

## Subagent Contracts

Each subagent file has the same shape:

1. **Soul** (verbatim from user-provided souls).
2. **Scope** — what files / inputs the subagent operates on.
3. **Method** — short, suggestive, not procedural.
4. **EVIDENCE shape** (single-line, `severity_signal` instead of `severity`).
5. **Allowed non-finding lines**: `NOT_EXERCISED`, `NO_EVIDENCE`,
   `OPEN_QUESTION` (same vocabulary as v2).
6. **Hard rules**: never invent; cite `file:line`/command/spec clause; no
   praise; emit `severity_signal` only (main classifies).

`verifier` additionally:
- Runs only commands declared in manifests, package scripts, Makefiles, or
  the user's invocation message — never invented commands.
- Per-tool timeout limits (typecheck 90s, lint 60s, focused tests 180s,
  build 300s) declared in the prompt; overridable per-invocation.
- Captures and reports red exits, suspicious greens (zero tests, all-skipped
  suites), timeouts, and missing prerequisites.

## Final Report Template

```
# Review — <target>

verdict: <BLOCKED | APPROVED-WITH-FIXES | APPROVED>
scope: <full | partial(<one-phrase reason>)>
base: <base>
checks: <executed summary>
not exercised: <checks/lanes/runtime surfaces with reasons, or none>

## Findings

1. [HIGH|MEDIUM|LOW] <file:line | spec-ref | command> — <problem>
   impact: <why it matters>
   fix: <concrete fix>

## Coverage

excluded:
  - <path> (<reason>)

not-reviewed:
  - <path> (<reason>)

## Open Questions

- <question, or omit section if empty>

## Verification

- <command/check>: <pass|fail|not run> — <short evidence or reason>

## Notes

<Notes accepts only: scope limits, skipped checks, adjudication caveats,
 evidence caveats. Praise, "strong positives", strengths, and positive
 summaries are forbidden. Omit section if empty.>

audit_output: |
  <appended verbatim by Stop hook — LLM does not write this trailer>
```

The `audit_output:` trailer is populated by the Stop hook after the LLM
emits the report. The LLM does not write it; the hook treats it as a
trailer and appends the verbatim `audit.sh` output. The LLM's emission
is considered complete without this field.

## Migration Plan

1. Create `skills/reviewer-v3/` with all files described above (including
   `hooks/stop_audit.sh`).
2. Add the Stop hook entry to user-scope `.claude/settings.json` pointing
   at `skills/reviewer-v3/hooks/stop_audit.sh`. The hook is gated to fire
   only when the active skill is `reviewer-v3` (matched via env var or a
   marker file the SKILL prompt sets on entry) so it does not run on
   unrelated stops.
3. v1 (`skills/reviewer/`) and v2 (`skills/reviewer-v2/`) remain untouched
   during validation.
4. v3 description in frontmatter narrows trigger to explicit `/reviewer-v3`
   invocation only — no overlap with v1/v2 dispatch.
5. Run validation benchmark (Run G in `reviewer-v2/benchmark-matrix.md`
   matrix).
6. If acceptance criteria met (see Validation), v3 renames to `reviewer`;
   v1 and v2 directories are removed from active `skills/` (preserved in git
   history and the v2 ADR as benchmark baselines). Stop hook path is
   updated to match the renamed skill directory.

## Validation Plan

Reuse the same benchmark target as the v2 ADR:

- Target: `baileys2api_bun`, branch `feat/dev-setup`
- Spec input: `/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md`
- Brief: `docs/briefs/dev-setup/baileys2api_bun.md`
- ADRs: ADR-0011, ADR-0016, ADR-0017, ADR-0018, ADR-0019, ADR-0003

Run G is added to the matrix. Acceptance:

**Recall (must catch):**
- red `bun run test:unit` (E, F)
- false-green `triggerInbound`/`triggerOutbound` hooks (E lost in F)
- `bun.lockb*` vs `bun.lock` lockfile mismatch (E)
- `docker:build` restore-on-failure risk (E)
- duplicate `WA_STORE_BACKEND` in `docker-compose.yml` (D, E)
- stale top-level `docker-compose.yml`/script drift (A)
- `$GH_TOKEN_PKG` vs `${GH_TOKEN_PKG}` syntax (D, F)

**Precision (must not over-classify as HIGH):**
- `SESSION_DIR` derivation from `DATA_DIR` (must be OPEN_QUESTION)
- `natsClient.close()` vs `drain()` (must adjudicate against transport)
- credential leakage claims without proof of `.dockerignore` + Dockerfile +
  variable-flow path (must be OPEN_QUESTION or MEDIUM)

**Format:**
- `## Notes` contains zero positive notes / strong-positives / praise.
- `audit_output:` trailer present (appended by hook) and consistent with
  `## Coverage`.
- `not exercised:` line present and accurate.

**Cost:**
- Lower token usage than reviewer-v2 on small/medium reviews (no fan-out).
- Comparable token usage to reviewer-v2 on large reviews (subagents invoked
  on demand, not always-on).

If Run G meets all four (recall, precision, format, cost), v3 is promoted.
If recall or precision fails, iterate on calibration in SKILL.md (single
locus). If format fails, iterate on the template's structural placeholders.
If cost fails, examine subagent invocation guidance for over-eager spawning.

## Consequences

Positive:

- Single locus of calibration (D7) makes tuning fast and consistent.
- Project-agnostic harness (D8 spec discovery; fact_pack lists, doesn't
  classify or auto-exclude by size) makes the skill safe to use on any
  repository in any language.
- Audit (D4–D6) gives deterministic teeth without limiting LLM judgment —
  it provokes; the model judges.
- Subagents-as-capabilities (D3) preserves throughput option without
  always-on cost.
- Coverage format F (D5) keeps reports honest and concise.
- Anti-praise structural placement (D8) raises the cost of leaking
  positive notes from "rule violation" to "format defect".
- Stop-hook ownership of audit removes dual-mandate redundancy and keeps
  the SKILL prompt short and craft-focused.

Negative:

- Main reviewer carries more responsibility (sizing, spawning, classifying,
  auditing) — quality of v3 depends more on main reviewer prompt clarity
  than v1/v2 did.
- No `verification-runner`, `operational-review`, or `spec-conformance`
  always-on lane means high-confidence operational findings depend on the
  main reviewer remembering to read operational surfaces. Mitigation: SKILL
  explicitly names "operational surfaces touched by the diff" as a must-read
  category.
- Audit step is one extra bash call per run (now via Stop hook). Cost is
  negligible but adds a point of failure if the script regresses.
- Stop hook adds infra-state to the skill: it must be installed in
  `.claude/settings.json`. If absent, the audit safety net is gone (the LLM
  is unconstrained but the harness loses its teeth). Mitigation: SKILL
  description states the hook requirement; install step in Migration.

Risks:

- LLM may declare files `not-reviewed` cheaply to avoid work. Audit catches
  missing files but cannot judge whether the *reason* is legitimate. Soul of
  the main reviewer (verbatim quoted in SKILL) is the only counter-pressure.
- Subagents may be under-invoked or over-invoked depending on prompt phrasing.
  Tuning happens after Run G; if subagents add no signal, they retire.
- Single-locus calibration could become a maintenance hotspot if many
  domain-specific calibrations are added. The rule is to keep the rubric
  domain-agnostic; domain rules belong in CLAUDE.md or in user invocation,
  not in SKILL.md.

## Open Questions

- Whether `verifier` subagent should accept user-provided commands beyond
  declared ones (with explicit `--allow=<cmd>` flag). Default: no — keeps the
  declared-only invariant from v1.
- Whether the final report should include a per-subagent line ("invoked: 0",
  "invoked: defect-hunter (3 findings), verifier (2 findings)") for cost
  attribution. Default: yes, in `## Notes`.
- Whether the Stop hook should be skill-local or user-scope. Default:
  user-scope `.claude/settings.json` during validation, with a marker-file
  guard so it only fires in `/reviewer-v3` invocations; revisit once skill
  loader supports per-skill hooks.
- Whether the re-emission cap of 1 is enough on adversarial gaps. If Run G
  shows the LLM repeatedly resurfacing the same gap, raise the cap or
  short-circuit to `partial`.

## Definition of Done

v3 is benchmark-ready when:

- It reproduces high-confidence findings from C/D/E (recall list above).
- It avoids the recurring overreaches from C/E (precision list above).
- It catches A's stale compose/script drift.
- It does not regress to B's protocol-compliance softening.
- `## Notes` is praise-free.
- `audit_output:` trailer is present (appended by hook) and consistent
  with `## Coverage`.
- Token cost on a representative S/M target is below v2.
- The benchmark matrix in `reviewer-v2/benchmark-matrix.md` gains a Run G
  entry summarizing the result.
