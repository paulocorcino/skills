---
name: reviewer
description: Use when the user asks for a code review on a defined target — file, package, branch, or PR. Performs a four-phase rigorous review with TDD-expert lens, spec conformance (ADR/RFC/PRD/design-doc when present), security (OWASP Top 10), performance, maintainability, and stack-specific best practices. Outputs a verdict (BLOCKED | APPROVED-WITH-FIXES | APPROVED) and an action list ready to hand to an implementing agent. Triggered by `/reviewer` or explicit "review" / "code review" / "validate this delivery" requests on a defined target.
---

# reviewer

A four-phase code review pipeline. Read-only. Outputs a prioritized action list with an explicit verdict.

Project-agnostic: works on any repository in any language. Spec conformance (ADR/RFC/PRD) is checked when specs exist; skipped otherwise without aborting.

Default execution preference: use subagents/delegated agents when the environment supports them. If the active agent runtime has no subagent/delegation feature, run the same reviewer passes sequentially in the main agent and report `subagents: fallback-main-agent` in the final report.

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
| Final report emitted | `[reviewer] done — verdict: <BLOCKED\|APPROVED-WITH-FIXES\|APPROVED>` |

Markers are independent of the final report block — they precede it. Do not omit markers to save tokens.

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

1. Never modify a file. Never write, edit, or delete. The skill is strictly read-only.
2. Never push to remote.
3. Never invent a finding. Every finding cites a file:line and is backed by content actually read.
4. Subagent final output is capped: ≤ 30 lines. Handoff output is capped: ≤ 40 lines. If output is longer, truncate.
5. Final action list is capped at 15 items. Remainder goes to a "follow-ups" appendix.
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

**Discovery order** — try in sequence; stop at first directory that exists with files matching:

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
  - If a discovered directory exists: list candidate specs newest-first by file mtime and/or highest numbered ADR/RFC/PRD first. Pick up to 3 files whose filename, title, or first paragraph references target paths, packages, domain terms, PR title/body, or commit messages. Proceed autonomously with the strongest matches. If there is no credible match, proceed with `specs: none (no relevant spec inferred)`.
  - If no discovered directory exists: skip spec conformance entirely. Note in the context brief: `specs: none (no spec directory found)`.

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
| `packages_touched > 1` AND `files_changed > 50` | XL | one `(code, tdd)` chain per package, capped at 4 package chains | run | 12-18K per slice |
| `files_changed > 50` OR `specs_in_scope >= 3` | L | `code` chain and `tdd` chain; split by layer/file cluster | run | 18-30K per slice |
| `files_changed > 5` | M | 2 parallel: `code`, `tdd` | run | 12-18K each |
| else | S | 1 combined: `code+tdd` merged | skip | 8-12K |

### 1.7 Emit context brief

Format (plain text, no decoration, ≤ 500 tokens):

```
target: <resolved>
files: <count> changed, <added>+/<removed>-
stacks: <comma-separated>
specs:
  - <REF>: <title> (<path>)
  - ...
  (or "none" if skipped)
review_packet: diff hunks + file list + specs/excerpts prepared
intent: <one paragraph>
plan: <S|M|L|XL>
subagents: <list>
phase2: <run|skip>
budget_per_subagent: <range>K tokens
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

Use the available subagent/delegation feature for the current runtime (for example Claude Code Task/subagents, Codex `spawn_agent`, or another equivalent agent tool). Prefer spawning all independent subagents listed in the plan in parallel. If no subagent feature exists, execute the same prompts sequentially in the main agent and mark `subagents: fallback-main-agent`.

For each subagent:

```
subagent_type: general-purpose
description: <reviewer subagent name>
prompt: <full prompt from subagents/<name>.md>
       + appended context brief from Phase 1
       + appended Phase 2 findings
       + appended review packet: explicit file list, diff hunks, untracked file content, and specs/excerpts
       + appended scope rule
       + appended budget reminder ("≤ 30 final lines; ≤ <range>K working budget")
```

### 3.1.1 Large-scope handoff

A **chain** is a sequence of subagent slices linked by handoffs: every slice except the last emits a handoff instead of a final report; the last slice emits findings. Plans L and XL use chains; plans S and M do not.

For large targets, split work into sequential slices before asking any one reviewer to read too much:

1. Slice by package first, then feature area, then file cluster.
2. Each slice produces either findings or a handoff.
3. A handoff is not a summary for the user; it is context for the next reviewer.
4. The next reviewer must read the handoff before reading more files and must not reread files already marked complete unless needed to verify a specific cross-file defect.

Handoff format (≤ 40 lines):

```
handoff_from: <subagent/slice>
files_completed:
  - <path>: <purpose read, key facts, no reread unless ...>
findings_so_far:
  - <severity> <file:line> — <defect> — fix: <fix>
supersedes_findings:
  - <file:line>     # finding from a prior handoff that is cancelled by deeper reread
open_threads:
  - <question or cross-file concern> — next read: <files>
next_slice:
  - <files/directories>
```

Finding identity is `<file:line>`. Phase 4.1 removes any finding whose `<file:line>` appears in a later handoff's `supersedes_findings` list.

### 3.2 Subagent files

| Subagent | Prompt file | Mandatory in plans |
|---|---|---|
| code-reviewer | `subagents/code-reviewer.md` | M, L, XL |
| tdd-validator | `subagents/tdd-validator.md` | M, L, XL |
| code+tdd combined | merge both prompt files into one prompt | S only |

### 3.3 Validation

When subagents return:

- If final output exceeds 30 lines, truncate to 30.
- If handoff output exceeds 40 lines, truncate to 40.
- Valid finding shapes are:
  - `BLOCKING|SHOULD-FIX|NICE-TO-HAVE <file:line> — <defect> — fix: <fix>`
  - `COVERAGE-GAP <ref> — <summary> — fix: <fix>`
  - Phase 2 `[CONCERN] <problem> — violates <REF> — fix: <fix>`
  - Handoff block beginning with `handoff_from:` and ending with `next_slice:`
- Per-line malformed handling: drop invalid lines, keep valid ones. Re-spawn the subagent only if zero valid lines remain. If a re-spawn still produces zero valid lines, drop the slice and note in Phase 4.

---

## Phase 4 — Aggregation & Verdict (orchestrator, synchronous)

### 4.1 Collect

Gather every finding from every subagent plus Phase 2 concerns. Include handoff findings if a later slice did not supersede them.

### 4.2 Deduplicate

Two findings are duplicates if they share `(file, line, defect class)`. Keep the more specific one.

### 4.3 Severity (binary rules)

**Severity translation (subagent text → final emoji):** `BLOCKING → 🔴`, `SHOULD-FIX → 🟡`, `NICE-TO-HAVE → 🔵`. Apply this translation when assembling the final report.

| Rule | Severity |
|---|---|
| Test where a non-conformant target can pass | 🔴 BLOCKING |
| Test where a conformant target can fail | 🔴 BLOCKING |
| Security defect with user-visible impact, when in altered flow OR on a touched public surface OR directly exploitable independent of the change | 🔴 BLOCKING |
| Security defect with user-visible impact, in unchanged file outside the altered flow and not directly exploitable | CRITICAL FOLLOW-UP |
| Correctness defect that produces wrong runtime behavior | 🔴 BLOCKING |
| Spec clause violated (when specs are in scope) | 🔴 BLOCKING |
| Race condition or concurrency defect | 🔴 BLOCKING |
| `COVERAGE-GAP` on a spec clause, changed public behavior, or critical modified path | 🔴 BLOCKING |
| `COVERAGE-GAP` outside the reviewed change | follow-up |
| Design defect that does not produce wrong behavior but raises future cost | 🟡 SHOULD-FIX |
| Maintainability or clarity defect | 🟡 SHOULD-FIX |
| Cosmetic, idiomatic, naming | 🔵 NICE-TO-HAVE |
| Phase 2 concern without confirmed runtime/spec impact | 🟡 SHOULD-FIX |

If a finding straddles two rows, pick the higher severity. `CRITICAL FOLLOW-UP` and `follow-up` are not part of the action list — see Phase 4.6 for placement.

### 4.4 Sort and cap

Sort by severity (🔴 → 🟡 → 🔵), then by file path. Cap at 15. Move overflow to follow-ups.

### 4.5 Verdict (binary rules)

| Findings present | Verdict |
|---|---|
| any 🔴 | BLOCKED |
| only 🟡 / 🔵 | APPROVED-WITH-FIXES |
| none | APPROVED |

### 4.6 Emit final report

Use this exact format:

```
# Review — <target>

verdict: <BLOCKED | APPROVED-WITH-FIXES | APPROVED>
plan: <S|M|L|XL>
subagents: <list>
specs: <list or "none">
findings: <total> (🔴 <n>, 🟡 <n>, 🔵 <n>)

## Action list

1. [🔴|🟡|🔵] <file:line> — <defect> — fix: <one-line fix>
2. ...

## Critical follow-ups

- <file:line> — <defect> — fix: <one-line fix>
- ...

## Follow-ups (not blocking)

- <file:line> — <defect> — fix: <one-line fix>
- ...

## Subagent summary

code-reviewer: <findings count>
tdd-validator: <findings count>
```

Sections:

- **Action list** — all 🔴 BLOCKING and 🟡 SHOULD-FIX and 🔵 NICE-TO-HAVE findings, capped at 15. These determine the verdict.
- **Critical follow-ups** — `CRITICAL FOLLOW-UP` entries (security defects in unchanged files outside the altered flow). They do not block but must be tracked.
- **Follow-ups (not blocking)** — overflow from the action list cap, plus all `follow-up`-classified entries (out-of-scope coverage gaps, unrelated low-severity defects).

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
