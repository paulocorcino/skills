# ADR-0001: Reviewer v2 Benchmark And Design Direction

Status: proposed
Date: 2026-04-30

## Context

The original `reviewer` skill was benchmarked against multiple reviews of the same target:

- Target: `baileys2api_bun`
- Branch: `feat/dev-setup`
- Main spec input: `/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md`
- Relevant brief: `docs/briefs/dev-setup/baileys2api_bun.md`
- Relevant ADRs cited across runs: ADR-0011, ADR-0016, ADR-0017, ADR-0018, ADR-0019, ADR-0003

The goal was not only to find defects in that branch, but to evaluate which review style extracts the most useful signal from the agent.

The main observation: a short native Codex review prompt produced stronger practical findings than the long `reviewer` protocol. The new `reviewer-v2` direction keeps native review judgment, but adds a deterministic scaffold, narrow evidence lanes, and a standardized final report.

## Decision

Create and benchmark `reviewer-v2` separately from `reviewer`.

Design direction:

- Keep the main prompt short and findings-first.
- Use `prepare_review.py` only for objective packet generation.
- Use narrow evidence lanes for verification, operational review, test confidence, spec conformance, and code risk.
- Keep the final report standardized.
- Preserve `scope`, `not exercised`, cited evidence, and explicit spec adjudication.
- Avoid praise, "strong points", and broad positive summaries.

## Benchmark Summary

| Run | Reviewer Style | Verdict | Main Strength | Main Weakness |
|---|---|---:|---|---|
| A | reviewer v1 before changes | APPROVED-WITH-FIXES | Good spec/brief reading and actionable operational findings | Did not execute checks; missed red tests and executable failures |
| B | reviewer v1 after experimental changes | APPROVED-WITH-FIXES | Standardized output shape remained usable | Degraded Plan L to focused pass; softened findings; missed important operational risks |
| C | native Codex review | High risk / effectively blocked | Best practical defect discovery via executed checks | Less standardized output; missed some spec/operational drift |
| D | Claude Code native review | Medium risk | Good spec syntax and operational drift detection | Did not execute docker/contract/integration; repeated SESSION_DIR ambiguity |
| E | reviewer-v2 | BLOCKED | Best standardized high-signal output; strong verification and false-green detection | Too sensitive; some speculative or over-severe findings |
| F | reviewer-v2 calibrated | BLOCKED | Better precision on `SESSION_DIR`, `drain()`, and speculative credential findings | Lost recall on false-green hooks and Docker/release risks; still leaked positive notes |

## Benchmark A - Reviewer v1 Before Changes

Main findings:

- `tests/contract.test.ts` removed `legacy` from `runContractSuite`, violating brief/ADR-0018 acceptance expectations.
- Stale top-level `docker-compose.yml` remained alongside canonical `docker-compose.dev.yml`.
- `package.json` docker scripts still pointed to legacy compose commands.
- Production `Dockerfile` was still documented as blocked/unvalidated.
- `triggerInbound` only hit `/health`, so contract assertions did not exercise real channel behavior.
- Follow-up noted session persistence lacked automated regression coverage.

Assessment:

- A was useful and pragmatic.
- It correctly caught stale compose/script drift that later reviews sometimes missed.
- It was weaker than C/E because it did not run executable checks.

## Benchmark B - Reviewer v1 After Experimental Changes

Main findings:

- `legacy` removal was reported, but softened as "restore or amend the brief".
- `legacyConsumerEntries` shape mismatch was reported as documentation hazard.
- Hardcoded compose mount path was reported as low severity.
- Dockerfile/prod build uncertainty was moved to open question.
- Report included "Strong points", reducing review density.

Assessment:

- B was worse than A.
- It violated the intended reviewer protocol by reducing Plan L into a focused main-agent pass.
- It missed the stale `docker-compose.yml`/script problem.
- It converted concrete build risk into open question.
- This run showed that adding rules without protecting native review judgment can degrade quality.

## Benchmark C - Native Codex Review

Main findings:

- `bun run test:contract` failed because contract hooks did not stimulate the channel.
- `test:integration` exited successfully while most tests were skipped.
- Production Docker/release path was broken or fragile:
  - `package.json` still had `file:../channel2api/...` deps.
  - `Dockerfile` copied `bun.lockb*` while the repo used `bun.lock`.
  - `prepare-release.sh` backed up `bun.lockb`, not `bun.lock`.
- `SESSION_DIR` was reported as missing from env/manifest.
- `MediaDownloader.start()` swallowed startup failure and hid it from `startWithRestart`.
- Unit test fake missed `batchUpsertContacts`, making the suite fail.

Assessment:

- C produced the strongest practical defect discovery before v2.
- It ran useful checks and prioritized runtime/build/test breakage.
- It overreached on `SESSION_DIR`: the brief also said to verify whether the app derives session path from `DATA_DIR`, and repository docs showed that removal was intentional.
- It missed A's stale top-level compose/script drift.

## Benchmark D - Claude Code Native Review

Main findings:

- `test:ci` was red due to the `batchUpsertContacts` fake mismatch.
- `docker-compose.yml` had duplicate `WA_STORE_BACKEND` entries with conflicting defaults.
- `bunfig.toml` used `${GH_TOKEN_PKG}` where the brief required `$GH_TOKEN_PKG`.
- `SESSION_DIR` was omitted from manifest despite brief/ADR-0016, but noted as a documented design divergence.
- `triggerOutbound` used a non-existent `/sendText` route.
- `triggerInbound` only hit `/health`.
- Dockerfile healthcheck interval drifted from manifest.
- Dockerfile/Dockerfile.dev violated some Dockerfile rules from kickoff.
- `.env.example` used container DNS `nats://nats:4222`, which is awkward for host `bun run dev`.

Assessment:

- D added valuable spec exactness and operational drift detection.
- It was useful for `bunfig.toml`, duplicate compose env, and Dockerfile/manifest drift.
- It did not run docker/integration/contract checks.
- It still treated `SESSION_DIR` as a finding/open question rather than cleanly adjudicating the conflicting spec clauses.

## Benchmark E - Reviewer v2

Main findings:

- `bun run test:unit` failed.
- `triggerInbound` was a `/health` stub and could not synthesize WA inbound events.
- `triggerOutbound` posted to `/sendText`, but the real route is `/:instanceId/sendMessage?token=<HMAC>`.
- `Dockerfile` copied `bun.lockb*` while only `bun.lock` existed.
- `Dockerfile` final stage used `COPY . .`, raising concern about registry auth files entering the runtime image.
- `package.json` `docker:build` used `prepare-release.sh && docker build && restore-dev.sh`; failed builds skip restore and leave the worktree swapped.
- `docker-compose.dev.yml` forwarded `GH_TOKEN_PKG` at runtime.
- `natsClient.close()` vs literal brief requirement for `drain()` was flagged.
- `DATA_DIR`/manifest/dev-compose mount drift was flagged.
- Duplicate `WA_STORE_BACKEND` in `docker-compose.yml` was caught.
- Integration tests were identified as weak or mislabeled:
  - inbound test publishes synthetic NATS events rather than exercising WA -> Baileys -> NATS;
  - outbound HTTP contract only asserted `status` property, not success.
- Several additional operational/code-risk items were flagged.

Assessment:

- E is the best direction so far.
- It combines the power of native review with standardized output.
- It caught most high-value findings from C and D.
- It also became too sensitive:
  - Some findings should be downgraded to `OPEN_QUESTION`.
  - Some operational risks were speculative.
  - `Notes` still included "Strong positives", violating the no-praise rule.

## Benchmark F - Reviewer v2 Calibrated

Main findings:

- `bun run test:unit` was red with two failing tests.
- `tests/contract.test.ts` omitted the `legacy` argument required by brief acceptance.
- `bunfig.toml` used `${GH_TOKEN_PKG}` despite the brief requiring `$GH_TOKEN_PKG`.
- Working tree had uncommitted/untracked report files and unpushed branch state.
- `SESSION_DIR` was correctly moved to open question rather than automatic finding.
- `natsClient.close()` was treated as passing based on the explicit brief note that it delegates to drain semantics.

Important misses:

- It did not raise `triggerInbound` `/health` and `triggerOutbound` `/sendText` as findings, even though these were high-confidence false-green risks in C/D/E.
- It missed Docker/release lockfile mismatch and `docker:build` restore-on-failure risk from E/C.
- It missed duplicate `WA_STORE_BACKEND` in `docker-compose.yml`.
- It missed A's stale top-level compose/script drift.
- It still included positive notes such as "well-instrumented" and "BuildKit-secret pattern is correct", which violates the no-praise rule.

Assessment:

- F improved precision by avoiding several overreaches from E.
- F regressed recall too far: calibration suppressed high-confidence operational and test-confidence findings.
- The next reviewer-v2 iteration must preserve F's adjudication discipline without losing E's coverage.

## Cross-Benchmark Findings

High-confidence defects repeatedly supported:

- Red declared tests are blocking evidence.
- Contract hooks provide false confidence:
  - `/health` cannot produce inbound NATS events.
  - `/sendText` is not the real outbound route.
- Docker/release path is fragile:
  - lockfile mismatch;
  - file workspace deps vs production build;
  - release script restore path can be skipped on failure.
- Operational drift matters:
  - stale compose files;
  - scripts pointing to wrong compose;
  - duplicate env keys;
  - manifest/compose/env mismatch.
- Exact spec syntax matters when the brief explicitly calls it out:
  - `$GH_TOKEN_PKG` vs `${GH_TOKEN_PKG}` is not style if the spec says parser syntax differs.
- Calibration must not suppress recurring high-confidence findings:
  - false-green contract hooks;
  - Docker/release lockfile mismatch;
  - restore-on-failure script risk;
  - duplicate compose env/default drift.

Recurring false-positive or adjudication risks:

- `SESSION_DIR` should not be an automatic finding. The brief required verification, and the implementation documented derivation from `DATA_DIR`.
- `natsClient.close()` vs `drain()` needs adjudication against the transport implementation before being high severity.
- Docker mountpoint creation rules can conflict with runtime ownership concerns; do not report both directions without resolving the controlling spec.
- Runtime credential leakage via `.npmrc`/`bunfig.toml` needs proof of actual copied files and token availability before high severity.
- Working-tree dirtiness is useful benchmark context, but should usually be `LOW` unless it changes the reviewed diff or invalidates executed checks.

## Reviewer v2 Calibration Rules

Reviewer-v2 should add these adjudication rules:

- `HIGH` requires one of:
  - failing declared CI/check;
  - proven build/release breakage;
  - runtime correctness bug with execution path;
  - material explicit spec violation;
  - security defect in touched flow;
  - false-green test hiding required behavior.
- If behavior depends on unverified external implementation, classify as `OPEN_QUESTION` or `MEDIUM`, not `HIGH`.
- If two specs conflict, cite both and state the controlling clause. If no controlling clause exists, use `OPEN_QUESTION`.
- If a finding depends on a file being copied into an image or a command mutating state, verify the relevant `.dockerignore`, script, or command path before final severity.
- `Notes` must never include positives. Only include scope limits, skipped checks, adjudication caveats, and benchmark-relevant context.
- Calibration should reduce speculative severity, not remove recurring proven findings. If a lane emits high-confidence false-green or release evidence, the main reviewer must either include it or explicitly explain why it was rejected.

## Consequences

Positive:

- Reviewer-v2 can preserve native review strength while producing repeatable output.
- Evidence lanes make coverage explicit.
- The final report is easier to compare across benchmark runs.

Negative:

- More moving parts than a single native prompt.
- Evidence lanes can overproduce medium/low operational findings.
- The main reviewer must still adjudicate aggressively to avoid false positives.

## Definition Of Done For Reviewer v2 Benchmark

Reviewer-v2 is benchmark-ready when:

- It reproduces the high-confidence findings from C/D/E while preserving F's better adjudication of `SESSION_DIR` and `drain()`.
- It catches A's stale compose/script drift.
- It does not repeat B's focused-pass degradation.
- It avoids automatic `SESSION_DIR` false positives.
- It blocks praise/strong-positive notes.
- It distinguishes proven findings from open questions.
- It records executed and skipped checks with concrete reasons.
- A comparison matrix is maintained for A/B/C/D/E and future runs.
