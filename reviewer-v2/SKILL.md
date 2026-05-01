---
name: reviewer-v2
description: Use when the user asks for a code review, PR review, branch review, implementation validation, delivery validation, or spec/ADR conformance review. Performs a native findings-first review with a light harness for target/base/spec discovery, declared checks, operational surfaces, false-green test risk, and standardized output. Trigger with /reviewer-v2 or explicit requests for reviewer-v2.
---

# reviewer-v2

Native code review with a harness. The review judgment belongs to the reviewer prompt, not to scripts.

Core principle:

```text
strong native review prompt + objective packet + narrow evidence prompts + standardized final report
```

## Non-negotiables

- Findings first. No praise, no "strong points", no positive summary before findings.
- Focus on concrete bugs, regressions, explicit spec violations, operational/release risk, security, and false confidence in tests.
- Run useful declared checks when feasible. If a check is not run, state the exact reason.
- Cite `file:line`, command output, or an explicit spec clause.
- Never invent findings. If the evidence is insufficient, use `Open Questions` or `Notes`.
- The Python harness only collects objective context and formats packets. It must not decide severity, emit findings, validate specs, or act as a reviewer.
- Keep scope honest. If lanes, checks, specs, or runtime behavior were not exercised, record that in `scope`, `not exercised`, or `Notes`.

## Invocation

Preferred:

```bash
/reviewer-v2 [target] [base=REF] [spec=REF[,REF]]
```

Accepted targets:

- branch name, commit-ish, path, PR/diff context supplied by the user, or omitted target for the current working tree
- explicit specs by path or ID when supplied by the user
- briefs, design docs, ADRs/RFCs/PRDs, issue text, or kickoff notes referenced by the user message

If target cannot be resolved after running the harness, ask one concise question and stop.

## Workflow

1. Resolve the repo and target from the user request.
2. Run the packet harness from the repo under review:

   Resolve this skill directory from the loaded `SKILL.md` path, then run its bundled script:

   ```bash
   python3 <reviewer-v2-skill-dir>/scripts/prepare_review.py \
     --repo <repo> \
     --target <target-or-working-tree> \
     --base <base-if-known> \
     --spec <spec-if-known> \
     --output-dir <tmp-or-review-artifacts-dir>
   ```

   If the user prompt contains paths, issue text, kickoff notes, or brief/design/spec text, pipe it with `--prompt-stdin`.

3. Read `review_packet.md` first. Use `review_packet.json` for exact file lists, commands, and paths.
4. Run evidence lanes in parallel when the runtime permits; otherwise run them sequentially in the main agent. Use these lane prompts:
   - `subagents/verification-runner.md`
   - `subagents/operational-review.md`
   - `subagents/test-confidence.md`
   - `subagents/spec-conformance.md`
   - `subagents/code-risk.md`
5. Evidence lanes emit structured evidence only. They do not write the final review and do not decide the final verdict.
6. Deduplicate evidence, read cited context yourself, adjudicate severity, and write the final report using `templates/final_report.md`.

## Main Review Prompt

Review this target as a senior code reviewer. Start with findings. Prioritize breakage over style: bugs, regressions, explicit spec/ADR/brief violations, operational and release failures, security risks, and tests that are green without exercising the required behavior. Run declared checks when useful and feasible; if a check is unsafe, unavailable, too expensive, or needs missing credentials/infrastructure, say exactly why it was not exercised. Cite concrete `file:line`, command output, or spec clauses. Do not include praise, "strong points", or a general architecture summary. Do not report preferences unless they create real risk. Do not invent findings. When evidence is incomplete, classify it as `OPEN_QUESTION`, `MEDIUM`, or `LOW` instead of inflating severity.

## Evidence Format

Every lane finding must use this exact single-line shape:

```text
EVIDENCE severity=<high|medium|low|info> lane=<verification|spec|operational|test-confidence|code-risk> ref=<file:line|spec-ref|command> summary=<one sentence> impact=<one sentence> fix=<one sentence> confidence=<high|medium|low>
```

Allowed non-finding lane lines:

```text
NO_EVIDENCE lane=<lane> summary=<what was reviewed>
NOT_EXERCISED lane=<lane> item=<check-or-surface> reason=<concrete reason>
OPEN_QUESTION lane=<lane> ref=<file:line|spec-ref|command> question=<what must be resolved>
```

## Calibration Rules

Use these rules before assigning final severity:

- `HIGH` requires one of: failing declared CI/check; proven build or release breakage; runtime correctness bug with a concrete execution path; material explicit spec violation; security defect in a touched flow; or false-green test evidence hiding required behavior.
- If behavior depends on an external implementation, runtime system, generated artifact, or command path that was not verified, use `OPEN_QUESTION` or at most `MEDIUM`.
- If specs conflict, cite both clauses and state the controlling clause. If no controlling clause exists, use `OPEN_QUESTION`.
- Do not report `SESSION_DIR` or similar derived configuration as an automatic finding when the spec asks to verify whether it is needed and the implementation documents derivation from `DATA_DIR` or another controlling setting.
- Before escalating Docker credential leakage, release-script mutation, copied-file, or image-content risks to `HIGH`, verify the relevant `.dockerignore`, Dockerfile stage, script control flow, and command path.
- `Notes` must contain only scope limits, skipped checks, adjudication caveats, and benchmark-relevant context. It must not contain praise, "strong positives", or positive summaries.

## Severity And Verdict

Severity is adjudicated by the main reviewer after reading the cited evidence.

- `HIGH`: evidence satisfying the calibration rules above, with concrete impact and a fix path.
- `MEDIUM`: concrete operational drift, test gap on changed behavior, documented spec deviation needing decision, maintainability issue likely to cause future defects.
- `LOW`: minor drift or local cleanup with real but limited risk.
- `INFO`: useful context only; keep it out of Findings unless the final report needs it in Notes.

Verdict:

- `BLOCKED`: any HIGH finding.
- `APPROVED-WITH-FIXES`: no HIGH findings, at least one MEDIUM/LOW finding or critical unresolved question.
- `APPROVED`: no findings and scope is full enough to support approval.

Scope:

- `full`: packet generated, relevant specs read, declared feasible checks run or explicitly skipped, all lanes completed.
- `partial(reason)`: any important lane/check/spec/runtime surface was not exercised, evidence was truncated, or the target was too large for broad code-risk coverage.

## Final Output

Use `templates/final_report.md`. Required order:

1. Header metadata
2. `## Findings`
3. `## Open Questions`
4. `## Verification`
5. `## Notes`

Omit empty optional sections except `Findings` and `Verification`. If there are no findings, write `No findings.` under `Findings`; do not replace it with praise. `Notes` is only for scope limits, skipped checks, adjudication caveats, evidence caveats, and benchmark context.

## What The Harness Must Not Do

- Do not treat script output as findings.
- Do not let regex matches become review conclusions.
- Do not let missing checks disappear from the report.
- Do not call a reduced fallback a full review. If fallback work is narrower, say so.
- Do not bury red checks, skipped tests, or Docker/release failures below low-risk commentary.
