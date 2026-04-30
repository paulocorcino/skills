---
name: reviewer
description: Use when the user asks for a code review on a defined target — file, package, branch, or PR. Performs a four-phase rigorous review with TDD-expert lens, spec conformance (ADR/RFC/PRD/design-doc when present), security (OWASP Top 10), performance, maintainability, and stack-specific best practices. Outputs a verdict (BLOCKED | APPROVED-WITH-FIXES | APPROVED) and an action list ready to hand to an implementing agent. Triggered by `/reviewer` or explicit "review" / "code review" / "validate this delivery" requests on a defined target.
---

# reviewer

## Purpose

When the context is too large, I make the world smaller without lying about what was left outside. My rigor is not in reading everything, but in ensuring every important part has an owner, a boundary, and a purpose. My unforgivable failure is creating a feeling of completeness where there was only partial coverage.

A four-phase code review pipeline. Read-only. Outputs a prioritized action list with an explicit verdict.

Project-agnostic: works on any repository in any language. Spec conformance (ADR/RFC/PRD) is checked when specs exist; skipped otherwise without aborting.

Execution mode is runtime-dependent and neutral: when the runtime supports delegation and the user/policy permits it, parallelize subagents; otherwise sequential execution in the main agent is first-class, not a degraded mode. If delegation is unavailable (the runtime has no subagent feature) or disallowed (the executor or user policy forbids implicit delegation in this session), run the same reviewer passes sequentially in the main agent and report `subagents: fallback-main-agent` in the final report. Do not retry delegation against an explicit denial.

## Execution markers (visibility)

The skill must emit one-line markers so the user sees that it was invoked and which phase is running. Each marker is a single plain-text line. No decoration. No silence.

Required markers, in order:

| When | Emit |
|---|---|
| Skill invoked, before any work | `[reviewer] invoked — resolving target` |
| Phase 1 ends | `[reviewer] phase 1 done — plan: <S\|M\|L\|XL>, subagents: <list>, specs: <count or "none">` |
| Phase 2 starts (skipped in plan S) | `[reviewer] phase 2 — high-level review` |
| Phase 2 ends | `[reviewer] phase 2 done — <N> concerns` |
| Phase 3 starts | `[reviewer] phase 3 — spawning <N> subagent(s)` (or `[reviewer] phase 3 — fallback-main-agent` if no delegation) |
| Each subagent returns | `[reviewer] subagent <name> returned — <findings count> finding(s)` |
| Phase 4 starts | `[reviewer] phase 4 — aggregating` |
| After final report block | `[reviewer] done — verdict: <BLOCKED\|APPROVED-WITH-FIXES\|APPROVED>` |

All markers except the final `done` marker precede the final report block. The `done` marker is emitted *after* the final report so the verdict line confirms a completed run. Do not omit markers to save tokens.

## Invocation

Two forms are accepted. Phase 1 detects which form was used.

### Form A — structured

```
/reviewer [target] [spec=REF[,REF]]
```

- `target` — path, package directory, branch name, or PR number. If omitted: review the current git working tree.
- `spec=` — optional comma-separated spec references. Each reference is either a number (`0011`) or an explicit file path (`docs/adr/0011-foo.md`). Alias: `adr=` is accepted with identical semantics.

### Form B — free-form

The user describes what was delivered, pastes a summary, and references files, branches, commit SHAs, spec numbers, or PR numbers anywhere in the message. Phase 1 extracts target and specs from the message.

Free-form signals to recognize:

| Signal in user message | Extract as |
|---|---|
| `feat/...`, `fix/...`, `release/...`, `chore/...` token | branch name |
| 7+ hex chars looking like a SHA | commit SHA |
| `#NNN`, `PR NNN`, `pull/NNN` | PR number |
| explicit path (`packages/<name>/`, `src/<dir>/`, `internal/<pkg>/`, etc.) | target path |
| `ADR-NNNN`, `RFC-NNNN`, `PRD-NNNN`, `spec-NNNN`, or 4-digit number near "ADR"/"RFC"/"spec" | spec reference |
| pasted commit list with SHAs and titles | scope hint — use SHAs to compute the diff |
| phrases like "review this delivery", "validate", "code review" | review request signal |

If neither form yields a resolvable target, ask one question and stop.

## Token budget

Hard total cap: **150K tokens per execution**.

Per-phase caps:

| Phase | Cap |
|---|---|
| 1 (Context & Plan) | 8K |
| 2 (High-Level) | 6K |
| 3 (Deep Analysis, all subagents/handoffs combined) | 120K |
| 4 (Aggregation) | 6K |

Budgets are planning ranges, not a reason to stuff all context into one prompt. If a phase would exceed its cap, split by package/layer/file cluster and use sequential handoffs so later reviewers do not reread the same files for the same purpose.

Per-phase caps sum to 140K, leaving a ~10K buffer below the 150K hard total cap. The buffer absorbs orchestrator overhead (planning prompts, validation prompts, the final report itself) that is not counted in any phase cap.

## Hard rules

1. Never modify a source or spec file. Never write, edit, or delete. The skill is strictly read-only with one carve-out: when the `verifier` subagent runs declared test commands (Phase 3, plans L/XL), tests may write their own artifacts (snapshots, fixtures, coverage reports, log files) as a side effect of execution. The skill never edits source under review, never edits specs, and never invents commands — it only runs what is declared in stack manifests.
2. Never push to remote.
3. Never invent a finding. Citation rules per shape:
   - Defect findings (`BLOCKING` / `SHOULD-FIX` / `NICE-TO-HAVE` / `CRITICAL FOLLOW-UP`): cite a concrete `file:line` from content actually read.
   - `COVERAGE-GAP` entries: cite a spec ref (`<SPEC-REF> §X`) or an API symbol (`API: <symbol>`); they are gaps about *missing* tests, so a `file:line` does not always exist. If the gap maps to a specific changed source location, prefer adding `(see <file:line>)` to the summary.
   - Phase 2 `[CONCERN]` items: cite a spec clause (`<SPEC-REF> §X`) or `design`; when promoted into the final action list they must additionally cite the most relevant `file:line` from the review packet — if no concrete site exists, downgrade the concern to a follow-up rather than emitting a fileless action item.
   Every finding must be backed by content actually read; never fabricate.
4. Subagent output caps — truncation must never silently drop a preserved-severity line. **Preserved-severity lines** = every `BLOCKING`, every `CRITICAL FOLLOW-UP`, and every `COVERAGE-GAP` (the latter because Phase 4.3 may classify it as 🔴 BLOCKING).
   - **Defect lines:** preserve all preserved-severity lines unconditionally. When the total would exceed 30, drop `NICE-TO-HAVE` lines first; if still over cap, drop `SHOULD-FIX` lines next. If preserved-severity lines alone exceed 30, list every one and append exactly `incomplete: <M> lower-severity lines truncated` (where `<M>` is the count of dropped non-preserved lines, possibly 0).
   - **Handoff blocks:** capped at 40 lines total. Apply the same preservation rule within `findings_so_far`.
   - If the orchestrator receives an over-cap output where preserved-severity lines exceed 30, do **not** truncate — accept the over-length output, note `subagent output over cap: <N> lines (preserved-severity: <P>)` in Phase 4, and include all preserved-severity findings in aggregation.
5. Final action list cap: 🔴 BLOCKING items are never truncated or demoted — list every one even if the total exceeds 15. Only 🟡 / 🔵 items are moved to the "Follow-ups (not blocking)" section when the combined count of 🔴 + 🟡 + 🔵 exceeds 15. If the 🔴 count alone exceeds 15, emit all of them and note `action list exceeds cap: <N> blocking findings` immediately below the list.
6. If Phase 1 cannot resolve target unambiguously, ask the user one targeted question and stop.

---

## Phase 1 — Context & Plan (orchestrator, synchronous)

Execute these steps in order.

### 1.0 Parse invocation form

| Cue | Form |
|---|---|
| Message starts with `/reviewer` and has structured args | A |
| Anything else | B |

For Form B:
1. Scan the message for the signals listed above.
2. Build candidate sets: `{targets}`, `{specs}`, `{commit_shas}`, `{file_paths}`.
3. Resolve target by priority: explicit path > branch name > PR number > commit SHAs (union) > current working tree.
4. If multiple targets match, pick the most specific and confirm with one short question only if ambiguity is real.
5. Specs come from the message; if none found, follow step 1.3.
6. Pasted summaries (commit lists, stage tables) are evidence — use them to seed the intent paragraph in step 1.4 without re-deriving from `git log`.

### 1.1 Resolve target

| Input shape | Action |
|---|---|
| path (file or dir) | list files via `ls` / `find` |
| branch name | `git diff --stat <base>...<branch>` and `git log <base>..<branch> --oneline` (detect base via `git symbolic-ref refs/remotes/origin/HEAD`, fallback `main`, then `master`) |
| PR number (`#NNN` or `NNN`) | `gh pr diff <num>` and `gh pr view <num> --json title,body,headRefName,baseRefName` |
| commit SHA list | `git show --stat <sha>` for each, then union the diffs |
| empty | `git status --short`, `git diff --stat HEAD`, `git diff --cached --stat`, and `git ls-files --others --exclude-standard` |

Always build a review packet for the resolved target:

- changed file list, including untracked files when reviewing the working tree
- diff/patch hunks for changed tracked files
- full content of untracked files that are in scope
- deleted/renamed file metadata
- explicit specs content or relevant excerpts, when specs are in scope

Scope rule: findings should be on changed lines or on unchanged lines whose defect is introduced, exposed, or made materially worse by the change. Existing unrelated defects may be listed only as follow-ups.

**Security carve-out:** a security defect with user-visible impact discovered in a file in the review packet is BLOCKING when **any** of:
(a) it sits in the altered flow / touched code path,
(b) it is on a public surface introduced or modified by the change,
(c) it is directly exploitable independently of the change (e.g. hardcoded production secret, plain SQL injection on an existing endpoint that the change touches).
Otherwise it is reported as `CRITICAL FOLLOW-UP` (see Phase 4.6).

**Untracked files:** for files added but not yet tracked by git, the entire file content is the diff.

**Untracked file exclusions (apply before reading content):** skip any untracked path matching these classes — they are listed by name only and are not read into the review packet:

- binaries and media: any file whose extension is in `{png,jpg,jpeg,gif,webp,ico,pdf,mp4,mov,wav,mp3,zip,tar,gz,tgz,7z,wasm}` or that fails a UTF-8 read
- lockfiles: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lock`, `Cargo.lock`, `poetry.lock`, `Pipfile.lock`, `composer.lock`, `go.sum`
- generated / vendored: anything under `node_modules/`, `dist/`, `build/`, `out/`, `.next/`, `coverage/`, `vendor/`, `__pycache__/`, `target/`, or files with a top-line marker like `// @generated` / `# Code generated`
- snapshots: `__snapshots__/**`, `*.snap`
- size cap: any single untracked file > 2000 lines or > 200 KB — list as `<path> (skipped: oversized)` and read only the first/last 100 lines if a finding requires it

**Related-test inclusion (light):** when reviewing the working tree or a branch, also include sibling test files of every changed source file (e.g. `foo.ts` → `foo.test.ts`, `foo.spec.ts`, `foo_test.go`, `test_foo.py`) even if they are not in the diff. **Then** scan conventional test directories — `tests/`, `__tests__/`, `test/`, `spec/`, `e2e/`, `integration/` (at repo root and at any package root touched by the change) — and pull in test files whose name or top-level content references an exported symbol modified by the diff. Cap the conventional-dir additions at **10** files total; if more match, keep the 10 with strongest symbol overlap and note `test discovery cap reached (<N> additional matches not pulled)` in the brief. The tdd-validator needs these to map changed behavior to assertions. Do not pull broader test suites or unrelated callers into the packet.

### 1.2 Detect stacks

Read these files if present at the repository root or any package root touched by the target:

| File | Stack |
|---|---|
| `package.json` (with `bun` in scripts or `bun.lock` present) | Bun + TypeScript |
| `package.json` (no Bun marker) | Node + TypeScript/JavaScript |
| `deno.json` / `deno.jsonc` | Deno |
| `go.mod` | Go |
| `pyproject.toml` / `requirements.txt` / `Pipfile` / `setup.py` | Python |
| `Cargo.toml` | Rust |
| `Gemfile` | Ruby |
| `pom.xml` / `build.gradle` / `build.gradle.kts` | Java/Kotlin |
| `*.csproj` / `*.sln` | C#/.NET |
| `mix.exs` | Elixir |
| `pubspec.yaml` | Dart/Flutter |
| `composer.json` | PHP |
| `Dockerfile` / `compose.yaml` / `docker-compose.yml` | Container infra (additive) |
| `Makefile` | Build infra (additive) |
| `.tf` files | Terraform (additive) |

List every detected stack. All detected stacks are passed to subagents.

### 1.3 Resolve specs (optional)

Spec types include ADRs, RFCs, PRDs, design-docs, technical specs.

**Discovery** — probe every candidate directory below; collect all that exist with matching files. Do not stop at the first hit (in real repos, ADRs and RFCs and PRDs commonly coexist):

1. `docs/adr/`
2. `docs/architecture/decisions/`
3. `docs/decisions/`
4. `adr/`
5. `decisions/`
6. `architecture/decisions/`
7. `docs/rfc/` or `docs/rfcs/` or `rfcs/`
8. `docs/specs/` or `specs/`
9. `docs/prd/` or `prd/`
10. `docs/design/` or `design-docs/`

**Resolution logic:**

- If `spec=` (or `adr=`) was passed:
  - For each reference: if it is a path, read directly. If it is a number, search the discovered directories for a file matching `<NNNN>-*.md` or `<NNNN>.md`. Stop on first failure to resolve a reference.

- If no specs were referenced:
  - If at least one discovered directory exists: pool candidate specs across all discovered directories. Rank by (a) keyword overlap with target paths, packages, domain terms, PR title/body, or commit messages, then (b) recency (mtime / highest numbered first). Pick up to 3 strongest matches across the pooled set. If no credible match exists, proceed with `specs: none (no relevant spec inferred)`.
  - If no discovered directory exists: skip spec conformance entirely. Note in the context brief: `specs: none (no spec directory found)`.

**Spec provenance** (gates BLOCKING in Phase 4.3):

- `explicit` — spec resolved from `spec=` / `adr=`, or referenced by ID or path in the PR title/body, commit messages, or the user's free-form invocation message.
- `inferred` — spec selected by the keyword/recency heuristic above without an explicit reference anywhere in the input.

Record provenance with each spec in the brief. Only violations of `explicit` specs may be classified 🔴 BLOCKING. Violations of `inferred` specs are capped at 🟡 SHOULD-FIX in the action list — the heuristic match is context, not contract. (Phase 2 emits `[CONCERN]` for every spec in scope regardless of provenance; provenance only governs the final severity ceiling in Phase 4.3.)

### 1.4 Read intent

| Source | Action |
|---|---|
| branch / PR | read PR body and commit messages |
| working tree | read last 3 commit messages on current branch |
| any spec/brief/RFC/PRD/design-doc referenced in the message or the PR description | read it |

Synthesize one paragraph: what is this change trying to do?

### 1.5 Compute scope size

```
files_changed = <int>
specs_in_scope = <int>   # 0 if spec conformance is skipped
packages_touched = <int> # count of distinct package roots (package.json/go.mod/etc.) under changed paths
```

### 1.6 Choose plan (binary table — pick first matching row)

| Condition | Plan | Subagents | Phase 2 | Subagent budget |
|---|---|---|---|---|
| `packages_touched > 1` AND `files_changed > 50` | XL | one `(code, tdd)` chain per package (capped at 4 package chains) + one `verifier` | run | 12-18K per slice; verifier ≤ 15K |
| `files_changed > 50` OR `specs_in_scope >= 3` | L | `code` chain and `tdd` chain (split by layer/file cluster) + one `verifier` | run | 18-30K per slice; verifier ≤ 15K |
| `files_changed > 5` | M | 2 parallel: `code`, `tdd` | run | 12-18K each |
| else | S | 1 combined: `code+tdd` merged | skip | 8-12K |

**XL chain cap:** when the XL plan is selected and `packages_touched > 4`, review the 4 packages with the most changed files (tie-break: alphabetic by package root). Every uncovered package must be listed in `## Review notes` of the final report as `not reviewed: <package> (XL chain cap — packages_touched=<N>, cap=4)`. The cap is presentation; the verdict applies only to packages actually reviewed and the report makes the gap explicit.

### 1.7 Emit context brief

Format (plain text, no decoration, ≤ 500 tokens):

```
target: <resolved>
files: <count> changed, <added>+/<removed>-
stacks: <comma-separated>
specs:
  - <REF>: <title> (<path>) [explicit|inferred]
  - ...
  (or "none" if skipped)
review_packet: diff hunks + file list + specs/excerpts prepared
intent: <one paragraph>
plan: <S|M|L|XL>
subagents: <list>
phase2: <run|skip>
budget_per_subagent: <range>K tokens
notes:
  - <optional one-line annotations from Phase 1 — e.g. "test discovery cap reached (<N> additional matches not pulled)", "stack not detected", "spec inferred without strong match". Omit the `notes:` section entirely if there are none.>
```

Print the brief. Proceed to Phase 2 (or Phase 3 if plan=S).

---

## Phase 2 — High-Level Review (orchestrator, synchronous)

Skip if plan = S.

For each spec in scope, evaluate the change against:

1. **Architecture**: does the change honor the spec's invariants? Cite the clause violated.
2. **Performance & Scalability**: design-level concerns only — N+1, unbounded fan-out, blocking I/O on hot paths, lock contention.
3. **Test Strategy**: is there a test plan? Does it cover the spec's contract surface? Identify coverage gaps at the strategy level.

If no specs are in scope, evaluate only Performance & Scalability and Test Strategy at the architectural level (no spec conformance bullet).

Output: ≤ 5 concerns. Each item exactly:

```
[CONCERN] <one-sentence problem> — violates <SPEC-REF §X or "design"> — fix: <one sentence>
```

If none: emit `phase 2: no high-level concerns`.

Proceed to Phase 3.

---

## Phase 3 — Deep Analysis (parallel subagents)

### 3.1 Spawn

Use the available subagent/delegation feature for the current runtime (for example Claude Code Task/subagents, Codex `spawn_agent`, or another equivalent agent tool) **when supported and permitted by the runtime / user policy**; otherwise run sequentially in the main agent — both modes are first-class (consistent with the top-level execution stance). When delegating, spawn all independent subagents listed in the plan in parallel. If delegation is unavailable or disallowed, execute the same prompts sequentially in the main agent and mark `subagents: fallback-main-agent`. Do not retry delegation against an explicit denial.

For each subagent:

```
subagent_type: general-purpose
description: <reviewer subagent name>
prompt: <full prompt from subagents/<name>.md>
       + appended context brief from Phase 1
       + appended Phase 2 findings
       + appended review packet: explicit file list, diff hunks, untracked file content, and specs/excerpts
       + appended scope rule
       + appended budget reminder ("target ≤ 30 final lines and ≤ <range>K working budget; never drop a preserved-severity line — BLOCKING / CRITICAL FOLLOW-UP / COVERAGE-GAP — to fit the cap. To fit, drop NICE-TO-HAVE lines first; if still over cap, drop SHOULD-FIX lines next. If preserved-severity lines alone exceed 30, emit all of them and append `incomplete: <M> lower-severity lines truncated`.")
```

### 3.1.1 Large-scope handoff

A **chain** is a sequence of subagent slices linked by handoffs: every slice except the last emits a handoff instead of a final report; the last slice emits findings. Plans L and XL use chains; plans S and M do not.

For large targets, split work into sequential slices before asking any one reviewer to read too much:

1. Slice by package first, then feature area, then file cluster.
2. Each slice produces either findings or a handoff.
3. A handoff is not a summary for the user; it is context for the next reviewer.
4. The next reviewer must read the handoff before reading more files and must not reread files already marked complete unless needed to verify a specific cross-file defect.

Handoff format (≤ 40 lines, same preserved-severity rule as a final output — see Hard rule 4):

```
handoff_from: <subagent/slice>
files_completed:
  - <path>: <purpose read, key facts, no reread unless ...>
findings_so_far:
  - <severity> <file:line> — <defect> — fix: <fix>
  - CRITICAL FOLLOW-UP <file:line> — <defect> — fix: <fix>
  - COVERAGE-GAP <SPEC-REF §X | "API: <symbol>"> — <summary> — fix: <fix>
  - [CONCERN] <problem> — violates <SPEC-REF §X | design> — fix: <fix>
supersedes_findings:
  - file:<file:line>:<defect-class-or-short-hash>  # cancels a defect/CRITICAL FOLLOW-UP — class/hash is required so two distinct defects on the same line are not cancelled together
  - coverage:<SPEC-REF §X | API:<symbol>>:<normalized summary or short hash> # cancels a COVERAGE-GAP
  - concern:<SPEC-REF §X | design>:<short problem hash> # cancels a [CONCERN]
open_threads:
  - <question or cross-file concern> — next read: <files>
next_slice:
  - <files/directories>
```

**Finding identity by shape** (used uniformly for supersede in 3.1.1 and dedup in 4.2):
- defect / CRITICAL FOLLOW-UP → `(<file:line>, <defect-class-or-short-hash>)` — the line alone is too coarse: two distinct defects on `src/foo.ts:42` (e.g. SQL injection + missing null check) must not collide. The class/hash is required for both supersede and dedup; never reduce to `<file:line>` alone.
- COVERAGE-GAP → `(<ref>, <normalized summary>)` — the ref alone is too coarse: two distinct gaps under the same `API: parseConfig` (e.g. one for empty input, another for malformed input) must not collide. Normalize the summary by lowercasing and collapsing whitespace before comparing; a short stable hash of that normalized form is acceptable.
- [CONCERN] → `(<ref-or-design>, <short problem hash>)`

Phase 4.1 removes any finding whose identity matches an entry in a later handoff's `supersedes_findings` list.

### 3.2 Subagent files

| Subagent | Prompt file | Mandatory in plans |
|---|---|---|
| code-reviewer | `subagents/code-reviewer.md` | M, L, XL |
| tdd-validator | `subagents/tdd-validator.md` | M, L, XL |
| verifier | `subagents/verifier.md` | L, XL (skipped in S, M) |
| code+tdd combined | merge both prompt files into one prompt | S only |

The verifier runs in parallel with the code/tdd chains, not as part of any chain. It receives the context brief and the list of touched packages, and runs only commands declared in the stack manifests detected in Phase 1.2 — never invented commands. Per-tool timeouts: typecheck 90s, lint 60s, focused tests 180s. On timeout, the channel is reported as `not exercised: <tool> (timeout)`. The verifier never reads the review packet diff content; it operates on commands and their captured output.

When merging both prompt files for plan S, the orchestrator must append this override to the combined prompt so the subagent does not emit the per-axis sentinels:

```
Plan S override: you are running as the combined code+tdd subagent. Your output rules:
- Apply both axes (code review and TDD validation) in a single pass.
- Use only the finding shapes listed in the SKILL §3.3 (defects, COVERAGE-GAP, [CONCERN], handoff). Do not use the strings "code-reviewer:" or "tdd-validator:" anywhere in your output.
- If you find no defects across both axes, emit exactly one line: `code+tdd: no defects found`
```

### 3.3 Validation

When subagents return, apply the cap policy from Hard rule 4 exactly:

**Preserved-severity lines** (never truncated under any cap): every `BLOCKING`, every `CRITICAL FOLLOW-UP`, and every `COVERAGE-GAP`. `COVERAGE-GAP` is included because Phase 4.3 may classify it as 🔴 BLOCKING; the orchestrator must see all of them to decide.

**Final output (non-handoff):**
- Keep all preserved-severity lines unconditionally.
- If the total line count exceeds 30, drop `NICE-TO-HAVE` lines first; if still over cap, drop `SHOULD-FIX` lines next. If preserved-severity lines alone already exceed 30, keep all of them and append exactly one annotation line: `incomplete: <M> lower-severity lines truncated` (where `<M>` is the count of dropped non-preserved lines, possibly 0).
- If the orchestrator receives an over-cap output where preserved-severity lines exceed 30, accept it as-is and note `subagent output over cap: <N> lines (preserved-severity: <P>)` in Phase 4.

**Handoff output:**
- Same preservation rule applies within `findings_so_far`: never drop a preserved-severity entry. To fit ≤ 40 lines, drop `NICE-TO-HAVE` entries first; if still over cap, drop `SHOULD-FIX` entries next. If preserved-severity entries alone exceed the handoff cap, accept the over-length block and annotate `subagent output over cap` in Phase 4.

**Valid output shapes** (any one valid line / block keeps the subagent result):
- `BLOCKING|SHOULD-FIX|NICE-TO-HAVE <file:line> — <defect> — fix: <fix>`
- `CRITICAL FOLLOW-UP <file:line> — <defect> — fix: <fix>` (security carve-out, see 1.1)
- `COVERAGE-GAP <ref> — <summary> — fix: <fix>`
- `OPEN-QUESTION <file:line or symbol> — <classification depends on context not in this slice> — needs: <slice / file / contract / spec ref>` (cross-slice escalation; see 3.4 for routing)
- Phase 2 `[CONCERN] <problem> — violates <REF or "design"> — fix: <fix>`
- Handoff block beginning with `handoff_from:` and containing a `next_slice:` section (the section header may be followed by one or more `- <files/directories>` items, so it is not necessarily the literal last line of the block)
- `incomplete: <M> lower-severity lines truncated` — annotation emitted by subagent or orchestrator when lower-severity lines were dropped to preserve preserved-severity lines (BLOCKING / CRITICAL FOLLOW-UP / COVERAGE-GAP); not a finding, not malformed.
- `verifier: exercised=<comma-list> not_exercised=<tool:reason; tool:reason>` (verifier-only; metadata, not a finding) — emitted exactly once per verifier run.
- The exact "no defects" sentinel for the subagent identity:
  - `code-reviewer: no defects found`
  - `tdd-validator: no defects found`
  - `verifier: no defects found` (verifier still emits its `exercised=` metadata line)
  - `code+tdd: no defects found` (plan S only)

**Per-line malformed handling:** drop invalid lines, keep valid ones. The "no defects" sentinel is a valid result — do not respawn on it.

The `incomplete: <M> lower-severity lines truncated` line is **metadata, not a result**: keep it for Phase 4 telemetry, but do **not** count it toward "valid result" when deciding whether to respawn. If the only surviving line in a subagent's output is `incomplete: ...`, treat the slice as having produced no findings (every shape was malformed) and apply the respawn rule below.

Re-spawn the subagent only if zero result-bearing lines remain — that is, no defect line, no COVERAGE-GAP, no [CONCERN], no `OPEN-QUESTION`, no handoff block, no verifier `exercised=` metadata line, and no "no defects" sentinel. If a re-spawn still produces zero result-bearing lines, drop the slice and note in Phase 4.

### 3.4 OPEN-QUESTION routing (cross-slice escalation)

A subagent emits `OPEN-QUESTION` when it identifies a potential defect or contract concern whose classification genuinely depends on context not present in its slice (a function defined in another package, a contract enforced by another module, a spec clause not provided in the packet). It is the honest alternative to either inventing a classification or silently dropping the concern.

Orchestrator handling:
1. If the question can be resolved by reading a small set of named files already in the review packet but not assigned to that subagent, the orchestrator may resolve it directly (read those files, classify the underlying concern as a normal finding) — do **not** respawn the subagent for this; instead, record `OPEN-QUESTION resolved by orchestrator` in `## Review notes`.
2. If the question requires opening a new slice (a package the plan did not cover, a spec not in scope), the orchestrator may either spawn a targeted follow-up subagent within remaining budget, or accept the question as unresolved.
3. Unresolved OPEN-QUESTION entries are listed verbatim in `## Open questions` of the final report (see 4.6) and force `scope: partial` (see 4.5).

OPEN-QUESTION never appears in the action list and never affects severity directly. It documents *uncertainty the review could not eliminate* — which is itself information the user needs to trust the verdict.

---

## Phase 4 — Aggregation & Verdict (orchestrator, synchronous)

### 4.1 Collect

Gather every finding from every subagent plus Phase 2 concerns. Include handoff findings if a later slice did not supersede them. Collect `OPEN-QUESTION` entries separately into an `open_questions` set (route per 3.4: resolved by orchestrator → re-classify into normal findings; unresolved → list verbatim in `## Open questions`). Read the verifier's `exercised=` metadata line and record the `exercised` and `not_exercised` channel sets — used in 4.6 to compute the `not exercised:` line.

### 4.2 Deduplicate

Dedup key is per-shape (matching the identity rules in 3.1.1):

| Shape | Dedup key |
|---|---|
| Defect (BLOCKING / SHOULD-FIX / NICE-TO-HAVE) | `(<file:line>, <defect-class-or-short-hash>)` — same key as supersede in 3.1.1 |
| CRITICAL FOLLOW-UP | `(<file:line>, <defect-class-or-short-hash>)` — same key as supersede in 3.1.1 |
| COVERAGE-GAP | `(<ref>, <normalized summary>)` — ref alone too coarse; normalize summary by lowercasing + collapsing whitespace |
| [CONCERN] | `(<ref-or-design>, <short problem hash>)` |

Two findings are duplicates iff their per-shape keys match. Keep the more specific entry (more precise file:line, narrower ref, longer summary). When merging across shapes is impossible — for example, a [CONCERN] and a defect that name the same site — keep both; severity already differs.

### 4.3 Severity (binary rules)

**Severity translation (subagent text → final emoji):** `BLOCKING → 🔴`, `SHOULD-FIX → 🟡`, `NICE-TO-HAVE → 🔵`. Apply this translation when assembling the final report.

| Rule | Severity |
|---|---|
| Test where a non-conformant target can pass | 🔴 BLOCKING |
| Test where a conformant target can fail | 🔴 BLOCKING |
| Security defect with user-visible impact, when in altered flow OR on a touched public surface OR directly exploitable independent of the change | 🔴 BLOCKING |
| Security defect with user-visible impact, in unchanged file outside the altered flow and not directly exploitable | CRITICAL FOLLOW-UP |
| Correctness defect that produces wrong runtime behavior | 🔴 BLOCKING |
| Spec clause violated, spec is `explicit` | 🔴 BLOCKING |
| Spec clause violated, spec is `inferred` | 🟡 SHOULD-FIX |
| Race condition or concurrency defect | 🔴 BLOCKING |
| `COVERAGE-GAP` on a clause of an `explicit` spec | 🔴 BLOCKING |
| `COVERAGE-GAP` on a critical modified path (security, auth, financial, data-loss, data migration) | 🔴 BLOCKING |
| `COVERAGE-GAP` on changed public behavior without an `explicit` spec | 🟡 SHOULD-FIX |
| `COVERAGE-GAP` on a changed path that is internal / non-critical | 🟡 SHOULD-FIX |
| `COVERAGE-GAP` outside the reviewed change | follow-up |
| Design defect that does not produce wrong behavior but raises future cost | 🟡 SHOULD-FIX |
| Maintainability or clarity defect | 🟡 SHOULD-FIX |
| Cosmetic, idiomatic, naming | 🔵 NICE-TO-HAVE |
| Phase 2 concern without confirmed runtime/spec impact | 🟡 SHOULD-FIX |
| Defect (any class) on a file/region wholly outside the change and not made worse by the change | follow-up (record orchestrator note in `## Review notes`) |

If a finding straddles two rows, pick the higher severity. `CRITICAL FOLLOW-UP` and `follow-up` are not part of the action list — see Phase 4.6 for placement.

### 4.4 Sort and cap

Sort by severity (🔴 → 🟡 → 🔵), then by file path.

The 15-item action-list cap is **presentation only** and must never demote severity:

- Every 🔴 BLOCKING finding stays in the action list, even if the count exceeds 15. The cap may only push 🟡 / 🔵 entries into the "Follow-ups (not blocking)" section.
- If the 🔴 count alone exceeds 15, list all of them — exceeding the cap — and note `action list exceeds cap: <N> blocking findings` directly under the action list. Do not silently truncate or reclassify.

### 4.5 Verdict and scope (binary rules)

**Verdict:**

| Findings present | Verdict |
|---|---|
| any 🔴 | BLOCKED |
| only 🟡 / 🔵 (with or without CRITICAL FOLLOW-UP / follow-up entries) | APPROVED-WITH-FIXES |
| none in action list, but ≥ 1 CRITICAL FOLLOW-UP entry | APPROVED-WITH-FIXES |
| none in action list and no CRITICAL FOLLOW-UP | APPROVED |

**Scope:** orthogonal to the verdict. Compute as follows:

| Condition (any one is sufficient) | Scope |
|---|---|
| `## Review notes` lists `not reviewed: <package>` (XL chain cap) | partial |
| any subagent was dropped after re-spawn produced zero result-bearing lines | partial |
| any subagent output was over cap (preserved-severity exceeded the line budget) | partial |
| any unresolved `OPEN-QUESTION` is listed in `## Open questions` | partial |
| total budget exceeded — partial report emitted with `incomplete` marker | partial |
| none of the above | full |

The `scope:` line lives in the report header and is required regardless of verdict. `partial` carries one short reason in parentheses (the most material cause); list the rest in `## Review notes`. A `partial` scope means the verdict applies only to what was actually reviewed; the user should not infer global approval from `APPROVED` if scope is `partial`.

`CRITICAL FOLLOW-UP` never blocks but is severe enough to keep the verdict out of plain `APPROVED` — the pre-existing security risk must be tracked, not dismissed. Plain `follow-up` entries (out-of-scope coverage gaps, unrelated low-severity defects) do not affect the verdict.

### 4.6 Emit final report

**Evidence production for the action list:** every entry requiring an `evidence:` line (every 🔴 unconditionally; 🟡 / 🔵 optionally) is composed by the orchestrator, not by subagents. For each such entry, re-read the cited `file:line` in the review packet (already loaded in Phase 1.1) and compose ≤ 30 words describing impact, execution path, or why the behavior breaks — based only on content visible at that location and adjacent context. Never speculate beyond the read content. For `COVERAGE-GAP` entries without a concrete file site, derive evidence from the spec clause text (when the spec is `explicit`) or from the changed public-behavior site referenced in the gap summary. If the cited content is insufficient to compose a defensible evidence line, omit the `evidence:` field for 🟡 / 🔵 entries; for 🔴 entries, downgrade to 🟡 rather than fabricate.

Use this exact format:

```
# Review — <target>

verdict: <BLOCKED | APPROVED-WITH-FIXES | APPROVED>
scope: <full | partial (<one-phrase reason — pick the most material; list rest in Review notes>)>
plan: <S|M|L|XL>
subagents: <list>
specs: <list or "none">
findings: <action-list total> (🔴 <n>, 🟡 <n>, 🔵 <n>) | critical follow-ups: <n> | follow-ups: <n> | open questions: <n>
not exercised: <comma-separated channels the skill did not run. Default channels: typecheck, lint, test execution, runtime behavior. Subtract any channel the verifier (Phase 3, plans L/XL) reported as `exercised=`. Append the verifier's `not_exercised=` reasons in parentheses for each remaining channel when available. If every default channel was exercised, emit `not exercised: none`.>

## Action list

1. [🔴|🟡|🔵] <file:line> — <defect> — fix: <one-line fix>
   evidence: <≤30 words on impact / execution path / why the behavior breaks. Required for every 🔴 entry; optional for 🟡 / 🔵. Cite the read content; never speculate.>
   (or, for a coverage gap without a concrete file site:)
1. [🔴|🟡] COVERAGE-GAP <SPEC-REF §X or "API: <symbol>"> — <summary> — fix: <one-line fix>
   evidence: <≤30 words; required for 🔴>
2. ...

## Critical follow-ups

- <file:line> — <defect> — fix: <one-line fix>
- ...

## Follow-ups (not blocking)

- <file:line> — <defect> — fix: <one-line fix>
- [CONCERN] <problem> — violates <SPEC-REF §X | design> — fix: <one-line fix>
- COVERAGE-GAP <SPEC-REF §X | "API: <symbol>"> — <summary> — fix: <one-line fix>
- ...

## Open questions

<optional section, omit if empty. One bullet per unresolved OPEN-QUESTION (see 3.4). Format:>
- <file:line or symbol> — <classification depends on …> — needs: <slice / file / contract / spec ref>
- ...

## Review notes

<optional section, omit if empty. One bullet per orchestrator-level note: dropped slices, over-cap subagent outputs, fallbacks, partial / incomplete runs, defects reclassified out-of-scope, packages skipped due to plan caps. Examples:>
- subagent <name>: dropped after re-spawn produced zero result-bearing lines
- subagent <name>: output over cap — 47 lines (preserved-severity: 35)
- 3 defect(s) reclassified to follow-ups: out of scope of the change
- not reviewed: <package> (XL chain cap — packages_touched=<N>, cap=4)

## Subagent summary

<one line per subagent that ran, e.g.:
code-reviewer: <findings count>
tdd-validator: <findings count>
verifier: <findings count> | exercised: <comma-list> | not exercised: <tool:reason; tool:reason>
or, in plan S:
code+tdd: <findings count>
or, when delegation was unavailable:
fallback-main-agent: <findings count>>
```

Sections:

- **Action list** — all 🔴 BLOCKING findings (never truncated) plus as many 🟡 / 🔵 findings as fit within a total of 15 entries. Every entry here determines the verdict. COVERAGE-GAP entries without a concrete `file:line` follow their own format (see template above).
- **Critical follow-ups** — `CRITICAL FOLLOW-UP` entries (security defects in unchanged files outside the altered flow). They do not block, but are severe enough to keep the verdict out of plain `APPROVED`.
- **Follow-ups (not blocking)** — 🟡 / 🔵 overflow beyond the 15-item presentation cap, plus all `follow-up`-classified entries (out-of-scope coverage gaps, unrelated low-severity defects). Severity does not change; these are just deferred from the main list.

The action list is copy-paste ready. Hand it to an implementing agent.

---

## Re-review

After fixes are applied, re-run `/reviewer <same target>`. The skill is idempotent: it produces a fresh verdict against the new state. No memory between runs.

## Failure modes

| Failure | Action |
|---|---|
| target not resolvable | ask user, stop |
| spec reference cannot be resolved | ask user, stop |
| no spec directory exists | proceed without spec conformance, note in report |
| stack not detected | proceed without stack-idiom checks, note in report |
| subagent times out | re-spawn once, then drop with note |
| total budget exceeded | stop, emit partial report with explicit "incomplete" marker |
