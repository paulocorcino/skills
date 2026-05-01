# Reviewer v3 Benchmark Matrix

Living comparison artifact for reviewer-v3 runs. Mirror of
`reviewer-v2/benchmark-matrix.md` style. Each new run gets one row plus a
detailed entry below.

Target across all rows: `baileys2api_bun`, branch `feat/dev-setup`, brief
`docs/briefs/dev-setup/baileys2api_bun.md`, kickoff prompts §2 in
`docs/briefs/dev-setup/kickoff-prompts.md`. ADRs in scope: ADR-0011, 0016,
0017, 0018, 0019, 0003.

## Per-Run Summary

| Run | ADR baseline | Verdict | Recall (matrix items) | Format compliance | Notable strength | Notable weakness |
|---|---|---:|---|---|---|---|
| G | ADR-0001 (Stop-hook variant) | APPROVED-WITH-FIXES | 1/7 | audit absent | honest about hook missing | Stop hook not installed → audit silently skipped; verifier never invoked; 487/494 files marked not-reviewed |
| H | ADR-0001 + ADR-0002 | BLOCKED | ~2/7 (1 regression on `$GH_TOKEN_PKG`) | audit populated; not-exercised present; narrowed-by-user-request flag set | A1 worked: manual audit invocation; sharp NEW findings (legacyConsumerEntries shape mismatch, logger env-at-call, missing depends_on, media-thumbs absence, docker build BLOCKED) | A2 escape over-applied (typecheck/lint claimed infeasible without proof); A3 glob hole (`src/**/*` patterns defeated per-file enumeration); 80 material files un-enumerated |
| I | ADR-0001 + ADR-0002 | BLOCKED | **4/7** (lockfile glob, restore-on-failure newly caught; 1 still-regression on `$GH_TOKEN_PKG`) | audit populated; gap enumerated by file (21 specific paths); narrowed-by-user-request flag set; A3 categories show counts | **Best run yet.** Caught 2 matrix items no previous v3 run got (`bun.lockb*`/`bun.lock` mismatch in Dockerfile; docker:build && chain leaves repo in npm-aliased state on build failure). NEW deep finding F1 (SIGTERM race in `withShutdownGuard`) that no prior reviewer (v1, v2, native) discovered. Concrete A2 reason class ("sandbox lacks bun toolchain") instead of vague "infeasible". | **Audit measurement bug**: 21 files reported as `gap` are in fact reviewed (cited in findings + listed in Verification "what I read"); audit script reads only `excluded` + `not-reviewed`, can't see implicit-reviewed evidence. Verifier still not invoked even when sandbox-class reason was concrete. |

## Per-Criterion Tracking

| Criterion | Expected | A (v1) | B (v1+) | C (Codex) | D (CC native) | E (v2) | F (v2 cal.) | G (v3) | H (v3+ADR2) | I (v3+ADR2) |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| red `bun test:unit` | catch | — | — | ✓ | ✓ | ✓ | ✓ | ✗ | partial (contract harness reported as HIGH from in-repo report) | not run (sandbox lacks bun) — concrete reason class |
| false-green `triggerInbound`/`triggerOutbound` | catch | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | partial (only `triggerInbound` /health flagged) | OQ2 raises false-green risk via TDD framing on `triggerInbound`; `triggerOutbound` missed |
| `bun.lockb*` vs `bun.lock` lockfile mismatch | catch | partial | softened | ✓ | partial | ✓ | ✗ | ✗ | ✗ | **✓ (F2)** |
| `docker:build` restore-on-failure | catch | partial | softened | ✓ | partial | ✓ | ✗ | ✗ | ✗ | **✓ (F6)** |
| duplicate `WA_STORE_BACKEND` in compose | catch | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| stale top-level `docker-compose.yml` drift | MEDIUM | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `$GH_TOKEN_PKG` vs `${GH_TOKEN_PKG}` syntax | LOW/MEDIUM | ✗ | ✗ | ✗ | ✓ | weak | ✓ | ✓ | ✗ (regression) | ✗ |
| `SESSION_DIR` documented derivation | OPEN_QUESTION / no finding | n/a | n/a | overreach | overreach | overreach | OQ | OQ + INFO | not raised | F5 MEDIUM (manifest-vs-brief consistency, not over-classified) |
| credential leakage via image copy | OPEN_QUESTION/MEDIUM unless proven | n/a | n/a | n/a | n/a | overreach risk | avoided | avoided | avoided | avoided |
| `## Notes` praise-free | required | clean | leaked | clean | leaked | leaked | leaked-light | clean | clean | clean |
| `audit:` field populated | required (post-ADR-0001) | n/a | n/a | n/a | n/a | n/a | n/a | ✗ | ✓ | ✓ |
| `narrowed-by-user-request:` flag when scope shrinks | required (post-ADR-0002) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | ✓ | ✓ |
| **NEW**: SIGTERM race in `withShutdownGuard` (root-cause depth) | bonus | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **✓ (F1)** — no prior reviewer caught |
| **NEW**: `extra_hosts: "host-gateway:host-gateway"` semantic bug | bonus | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **✓ (F4)** |
| **NEW**: `tests/` excluded from container breaks acceptance #11 | bonus | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | **✓ (F7)** |

## Run G — reviewer-v3 (ADR-0001, Stop-hook variant)

**Date:** 2026-04-30
**Verdict:** APPROVED-WITH-FIXES
**Token cost:** unmeasured

**Findings emitted:**
- MEDIUM: `tests/contract.test.ts:54-58` — `legacy` field removed; brief acceptance line not honoured.
- MEDIUM: `docs/dev-setup-report.md:512` — `bun test:contract` 1/9 passing; criterion §4 not closed.
- LOW: `bunfig.toml:2` — uses `${GH_TOKEN_PKG}` instead of `$GH_TOKEN_PKG`.
- INFO: `manifest.yaml:14-21` — omits `SESSION_DIR`.
- INFO: `docker-compose.dev.yml:35-39` — parent-context build deviates from brief Dockerfile skeleton.

**Failure modes confirmed:**
1. **Stop hook opt-in failure**: hook not installed → audit silently absent; reviewer noted but proceeded.
2. **Verifier never invoked**: subagents-as-capabilities degenerated to subagents-never-used; chose "read-only" without running any declared check.
3. **Scope auto-narrowed**: 487/494 files marked `not-reviewed (out of scope)`; matched Run B focused-pass degradation pattern.

**Drove ADR-0002.**

## Run H — reviewer-v3 (ADR-0001 + ADR-0002)

**Date:** 2026-05-01
**Verdict:** BLOCKED
**Token cost:** unmeasured

**Findings emitted:**
- HIGH: brief acceptance #16 (contract harness 12/12 green) not met — final harness 2/9.
- HIGH: brief acceptance #1 (`docker build`) still BLOCKED — `prepare-release.sh` swaps to unpublished `@somoschat/*`.
- MEDIUM: `src/main.ts:171-173` — `legacyConsumerEntries` shape `{ stream, name, legacyPrefix }` does not match brief `[{ subject: 'whatsapp.events.${client}.>' }]`; consumer-cleanup form vs legacy-subscription form.
- MEDIUM: `@channel2api/media-thumbs` listed required in brief §2b but absent from `package.json`.
- MEDIUM: `docker-compose.dev.yml:51-53` drops `depends_on: nats` without retry/back-off cushion; first-boot races possible.
- MEDIUM: `src/infrastructure/observability/logger.ts:107` reads `process.env.LOG_FORMAT` at call-time, bypassing constructor/setter contract.
- LOW: `tests/contract.test.ts:74-76` — `triggerInbound /health` cannot exercise ADR-0011 subject conformance.
- LOW: untracked working-tree state on a "complete" feature branch; 30 commits ahead of `origin/feat/dev-setup` not pushed.

**ADR-0002 outcomes:**
- **A1 worked**: reviewer detected hook absent, ran `audit.py` manually, populated `audit:` and `audit_output:`.
- **A3 partially worked**: `narrowed-by-user-request: true` set; auto-narrow flag emitted in audit_output.
- **A2 over-applied**: `verifier (0)` justified via "material side effects on the host (docker, network, GH_TOKEN_PKG)"; this lumped harmless checks (`bun run check`, unit tests) with mutating ones, claiming a single broad "infeasible" reason.

**New failure modes observed:**

4. **Glob hole in `not-reviewed`**: reviewer expanded to glob patterns (`src/adapters/**`, `src/application/events/**`, etc.); audit cannot enumerate vs `material_set` element-wise. Result: 80 material files un-enumerated; audit returned `gap` but the reviewer emitted anyway because A3 only forces a flag, not enumeration.
5. **A2 escape clause too broad**: "infeasible" applied as a single class to all checks; typecheck and unit tests have no real side-effect blocker but were swept up in the same justification. Confirms the risk listed in ADR-0002 Consequences.

**Strengths over Run G:**
- Format fully compliant (audit + flags).
- Sharper findings on real defects beyond the original matrix (legacyConsumerEntries shape, logger env-at-call, depends_on omission, media-thumbs absence, prepare-release.sh swap path).
- Correct verdict (BLOCKED) driven by genuine HIGH issues, not by matrix-item recall.

**Weaknesses persisting from Run G:**
- 5 of 7 matrix recall items still missed.
- 1 matrix regression (`$GH_TOKEN_PKG` was caught in G, missed in H).
- Did not run `bun run check` even though it has no side effects.

## Run I — reviewer-v3 (ADR-0001 + ADR-0002)

**Date:** 2026-05-01
**Verdict:** BLOCKED
**Token cost:** unmeasured

**Findings emitted:**
- F1 HIGH: `src/main.ts:282-346` — SIGTERM clean-exit ≤10s fails; root-cause is race between `withShutdownGuard` flag and in-flight `startWithRestart` promise leaking `CONNECTION_DRAINING` rejection back into restart timer; container exits 137 on `MediaDownloader` restart loop. ADR-0017 §9 violation reproduced via `dev-setup-report.md:172-177`.
- F2 HIGH: `Dockerfile:26` — `COPY package.json bun.lockb* bunfig.toml .npmrc ./` does not match repo's actual `bun.lock` (Bun 1.1+ text format); `frozen-lockfile` will run with no lockfile in build context. Verified via `ls bun.lock*` and `grep "COPY.*bun" Dockerfile Dockerfile.dev`. **MATRIX RECALL item caught for the first time in v3.** Plus the upstream npm-publish blocker (BLOCKER-1).
- F3 MEDIUM: `tests/contract.test.ts:57-62` — `legacy: { subject }` removed; ADR-0011 #6 not exercised against this channel.
- F4 MEDIUM: `docker-compose.dev.yml:54-57` — `extra_hosts: "host-gateway:host-gateway"` is non-functional Docker syntax; key-side use of the special token does not produce a real address; `nats://host-gateway:4222` will fail DNS resolution inside container.
- F5 MEDIUM: `manifest.yaml:15-22` omits `SESSION_DIR` despite brief §3 listing it; brief and manifest disagree silently. Correctly framed (no over-classification on the documented `DATA_DIR`-derivation).
- F6 MEDIUM: `package.json:27` — `docker:build` `&&` chain leaves repo in npm-aliased state if `docker build` fails (`restore-dev.sh` skipped). **MATRIX RECALL item caught for the first time in v3.**
- F7 LOW: `.dockerignore:19` excludes `tests/` while brief acceptance #11 requires `docker compose run --rm channel bun test`; image lacks tests, command finds nothing. Acceptance command unreachable.
- F8 LOW: `docker-compose.dev.yml:48-49` stale comment about `NATS_URL` (claims `.env` is `nats://localhost:4222`; actual is `nats://nats:4222`).

**Strengths over Run H:**
- Caught `bun.lockb*` lockfile mismatch (F2) and `docker:build` restore-on-failure (F6) — two matrix items no v3 run got before. Recall jumped from ~2/7 to 4/7.
- F1 SIGTERM root-cause analysis is novel: no prior reviewer (v1, v2, native, or earlier v3 runs) discovered the `withShutdownGuard` race. Sharp depth on real production risk.
- A2 reason class is concrete: "sandbox lacks bun toolchain on PATH" is verifiable, not a vague "infeasible".
- A3 audit_output now enumerates `gap` files explicitly (21 paths listed) and breaks `not-reviewed` into `category: <prefix> — N files under prefix` with counts. Glob shortcut narrowed but not eliminated.

**New observation: audit measurement bug**
- The audit's `gap: <21 files>` line lists `Dockerfile`, `docker-compose.dev.yml`, `manifest.yaml`, `package.json`, `src/main.ts`, `tests/contract.test.ts`, etc. — files the LLM **did read** (listed under Verification "What I read directly") and **did cite** in F1, F2, F3, F4, F5, F6.
- These files are implicit-reviewed under Coverage format F (ADR-0001 D5: anything not in `excluded` or `not-reviewed` is reviewed). But `audit.py` only reads the `excluded` and `not-reviewed` blocks; it has no signal about implicit-reviewed unless every file is enumerated explicitly.
- Result: audit reports `gap` even when the LLM correctly did the work. False-negative on the audit's part, not a behavior problem on the LLM's part.
- **Fix path** (cirurgical, no new locks): `audit.py` should treat as reviewed any file that appears in (a) `excluded`, (b) `not-reviewed`, OR (c) any finding's `ref:<path>` citation, OR (d) the optional Verification "What I read directly" enumeration. `gap` is reported only for files material AND not present in any of those four sets.

**Weaknesses persisting:**
- Verifier still not invoked. Sandbox-lacks-bun is a legitimate reason for `bun test`, but `git`, `grep`, `ls`, etc. were used directly by the main reviewer — no parallelism, no specialist context.
- 3 of 7 matrix items still missed (`triggerOutbound`/sendText, duplicate `WA_STORE_BACKEND`, stale top-level `docker-compose.yml`, `$GH_TOKEN_PKG` syntax). The first two would require directly opening the not-reviewed `tests/integration/` and `docker-compose.yml` (top-level) files. The brief-narrowed scope made this a deliberate skip.

## Open Thinking (Pre-ADR-0003)

User signal: avoid adding more "locks" (cadeados). The pattern in v1 → v2 → v3
shows that procedural rules and structural enforcers harden behaviour but
each one increases the surface area. ADR-0002's three rules already strain
the "small main prompt" principle.

Two failure modes still unaddressed (4: glob hole; 5: A2 over-escape) point at
the same root cause: the LLM uses **abstraction shortcuts** (glob patterns,
broad-class "infeasible" claims) to satisfy structural rules without doing
the underlying work. Adding more rules invites more shortcuts.

Possible single-axis adjustments under consideration (none yet adopted):

- **Soul-level reinforcement instead of new rules.** Strengthen the SKILL's
  voice on the verifier soul ("verification limits are part of the truth")
  and the main reviewer's anti-narrowing soul ("creating a feeling of
  completeness where there was only partial coverage is my unforgivable
  failure"). Bet: voice in the prompt outperforms more structural enforcers
  at the level of LLM judgment.
- **Single new convention: `not-reviewed` accepts only enumerated files OR
  explicit `category-summary: <category>=<N>`** — no glob syntax. The format
  defect catches glob-shortcut without naming a new rule.
- **Single new check on A2: typecheck/lint must not appear in `not exercised:`
  with class `mutating-side-effects`** — narrow exception, no full taxonomy.

Decision deferred. Worth a fresh-context conversation before committing.

## Promotion Status

reviewer-v3 is **close to promotable** per ADR-0001 D1, pending one cirurgical
fix.

- Run G failed on audit firing.
- Run H passed audit firing but failed recall on 5/7 matrix items, regressed
  on 1, and revealed two new failure modes (glob hole, A2 over-escape).
- **Run I**: 4/7 matrix recall + 3 novel high-quality findings (F1 SIGTERM
  race, F4 host-gateway syntax, F7 tests-excluded-from-image); A2 reason
  class concrete; A3 enumeration of `not-reviewed` categories with counts;
  audit fired and emitted gap details. **Quality jump is real.**

The single remaining blocker is the **audit measurement bug** documented
under Run I: 21 reviewed files appear as `gap` because `audit.py` cannot
see implicit-reviewed evidence (Coverage format F intentionally omits
positive markers). This is a **measurement bug, not a behavior bug** —
the LLM did the right thing; the audit just can't observe it.

Recommended next step: implement the audit fix described under Run I
("Fix path") and re-run the same target as **Run J**. If Run J holds the
recall improvements of I AND the audit reports `pass` (or a real, smaller
gap), v3 is promotable per ADR-0001 D1.

The `Open Thinking` section above is intentionally preserved as a record of
the soul-vs-rule choice still pending if the audit fix alone is not enough
to close remaining gaps.
