# Reviewer 2 Rework Proposal

## Goal

Create a `reviewer2` skill to compare against the current `reviewer`.

The benchmark showed that a short native Codex review prompt extracted better judgment than the current long protocol: it ran useful checks, prioritized concrete breakage, and produced high-signal findings. The new direction is not to add more rules to the existing skill. It is to preserve native review judgment while adding deterministic preparation and standardized output.

Core principle:

> simple review prompt + deterministic scaffold + narrow evidence agents + standardized final report

## Why The Current Skill Underperformed

- The prompt is too procedural and long, which encourages protocol compliance over review judgment.
- Fallback-main-agent can still degrade into a focused pass while sounding legitimate.
- Verifier behavior is under-enforced and too shallow; it can miss red CI, skipped tests, false greens, and docker/build failures.
- Operational/release surfaces are not first-class enough: compose, Dockerfile, env, manifest, scripts, lockfiles, reports.
- Spec adjudication is too binary for real briefs that include "verify/align" clauses and documented deviations.
- Final output permits low-signal positive notes, which weakens the code-review posture.
- L/XL handoff mechanics add complexity before the skill reliably captures obvious executable failures.

## Reviewer2 Design

### 1. Keep The Main Prompt Small

The main reviewer prompt should read like a strong native code-review request:

- Findings first.
- Focus on bugs, regressions, explicit spec violations, operational risk, security, and false confidence in tests.
- Run useful declared checks when possible.
- If something is not exercised, state the exact reason.
- Cite `file:line`, command output, or spec clause.
- No praise, no "strong points", no general summary before findings.
- Standard final shape.

The prompt should tell the agent what good review behavior is, not simulate a full workflow engine in prose.

### 2. Add A Deterministic Scaffold

Add a script, likely `scripts/prepare_review.py`, for facts that should not rely on model judgment:

- Resolve target, current branch, base branch, diff stat, changed files, and changed packages.
- Discover explicit specs from prompt, kickoff docs, branch/commit messages, and local docs.
- Read stack manifests and list declared commands.
- Detect operational surfaces: `Dockerfile*`, compose files, `.env.example`, `manifest.yaml`, release scripts, lockfiles, reports.
- Produce a review packet file with stable sections:
  - target and base
  - changed files and stats
  - specs found
  - declared commands
  - operational surfaces
  - candidate checks
  - known skipped/oversized files

The scaffold should not decide severity or final findings. It only gathers evidence.

### 3. Use Narrow Evidence Agents

Subagents should populate evidence, not own the verdict.

Suggested lanes:

- `verification-runner`: run declared checks, capture pass/fail/skips, detect red CI and suspicious green runs.
- `spec-conformance`: compare implementation against explicit brief/ADR clauses, including exact syntax requirements.
- `operational-review`: review Dockerfile, compose, env, manifest, release scripts, lockfiles, build context, and status reports.
- `test-confidence`: find false greens, skipped suites, stubs, hooks that do not exercise the behavior under test, and non-existent routes.
- `code-risk`: inspect changed code for runtime bugs, regressions, security issues, and high-risk correctness defects.

Each lane should emit structured evidence, not prose-heavy review:

```text
EVIDENCE severity=<high|medium|low|info>
lane=<verification|spec|operational|test-confidence|code-risk>
ref=<file:line | spec-ref | command>
summary=<one sentence>
impact=<one sentence>
fix=<one sentence>
confidence=<high|medium|low>
```

The main agent deduplicates, adjudicates severity, and writes the final report.

### 4. Standardize Output, Not Thought

The final report should be stable and compact:

```md
# Review — <target>

verdict: <BLOCKED | APPROVED-WITH-FIXES | APPROVED>
scope: <full | partial(reason)>
base: <base>
checks: <executed summary>
not exercised: <channels with reasons>

## Findings

1. [HIGH|MEDIUM|LOW] <file:line/spec/command> — <problem>
   impact: <why it matters>
   fix: <concrete fix>

## Open Questions

## Verification

## Notes
```

Rules:

- Findings first.
- No praise section.
- No "strong points".
- No long architecture summary.
- Notes are only for scope limits, skipped checks, spec adjudication, and evidence caveats.

## What To Reuse From Reviewer v1

Keep:

- Explicit target/base/spec resolution.
- `scope: full|partial`.
- `not exercised` as a first-class output.
- Citation discipline: `file:line`, command, or spec clause.
- Spec provenance: explicit vs inferred.
- Security carve-out for severe issues in touched flows.
- Severity-to-verdict concept.
- "No invented findings" rule.
- Read-only posture, with a carve-out for declared verification commands.

Avoid or postpone:

- Heavy four-phase ceremony.
- Large handoff chains as a first v2 feature.
- Combining prompts by raw merge.
- Over-prescriptive token budgets in the main skill prompt.
- Subagents that emit final review prose.
- Treating every weak test as automatically blocking without risk adjudication.

## Benchmark Targets

Reviewer2 should be compared against reviews A, B, C, and D on `baileys2api_bun`.

Expected capabilities:

- Catch red declared CI/unit test regression.
- Catch failed or non-exercising contract tests.
- Catch skip-heavy integration tests that exit 0 but do not exercise required scenarios.
- Catch invalid contract hook route usage.
- Catch Dockerfile/release build breakage when the brief requires docker build.
- Catch stale compose files, scripts pointing to stale compose files, and duplicate env keys.
- Catch exact brief syntax drift, such as `$GH_TOKEN_PKG` vs `${GH_TOKEN_PKG}`.
- Catch Dockerfile/manifest healthcheck drift and Dockerfile.dev volume-rule violations when specified by the brief.
- Avoid `SESSION_DIR` as an automatic finding when the spec itself says to verify whether it is derived from `DATA_DIR`; classify it via spec adjudication.
- Avoid praise and positive summaries.
- Avoid "focused pass" unless scope is explicitly partial and skipped lanes are listed.

## Definition Of Done

Reviewer2 is ready for benchmark when:

- A new `reviewer2` skill exists separately from `reviewer`.
- The original `reviewer` remains available for side-by-side comparison.
- `scripts/prepare_review.py` can generate a review packet for a branch/path target without modifying tracked source files.
- The review packet includes target/base, changed files, specs, declared commands, operational surfaces, and candidate checks.
- At least three evidence lanes exist: `verification-runner`, `operational-review`, and `test-confidence`.
- Evidence lanes emit the structured `EVIDENCE ...` format.
- The main skill prompt stays concise enough to fit on a single readable screen before examples/templates.
- Final output is standardized and findings-first.
- The skill explicitly forbids praise/strong-points sections.
- The skill records unexercised checks with concrete reasons.
- A benchmark run against `baileys2api_bun` is performed and compared to A/B/C/D.
- The benchmark comparison records:
  - findings caught by reviewer2 and missed by others
  - important findings missed by reviewer2
  - false positives
  - runtime/checks executed
  - clarity and actionability of output

## Proposed File Layout

```text
reviewer2/
  SKILL.md
  scripts/
    prepare_review.py
  templates/
    review_packet.md
    final_report.md
  subagents/
    verification-runner.md
    operational-review.md
    test-confidence.md
    spec-conformance.md
    code-risk.md
```

Start minimal:

1. Build `SKILL.md`, `prepare_review.py`, and three lanes: verification, operational, test-confidence.
2. Benchmark against `baileys2api_bun`.
3. Add spec/code-risk lanes only if the first benchmark shows evidence gaps that justify them.




Old evidence reviewer

Prompt Original A and B: use o reviewer skill para avaliar a implementação ## 2 — baileys2api_bun

**Branch**: git checkout -b feat/dev-setup
**Session directory**: ~/somoschat/repositories/baileys2api_bun
/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md


################################################################################

Segue um benchmark

Revisao A antes de alteração:

Review — baileys2api_bun @ feat/dev-setup vs dev-setup brief §2
verdict: APPROVED-WITH-FIXES
scope: partial (XL change, sampled high-leverage acceptance criteria + ADR-0011/0017/0018 surfaces)
plan: L
subagents: fallback-main-agent
specs: ADR-0011 (explicit), ADR-0016 (explicit), ADR-0017 (explicit), ADR-0018 (explicit), ADR-0019 (explicit) + brief docs/briefs/dev-setup/baileys2api_bun.md (explicit)
findings: 4 (🔴 0, 🟡 3, 🔵 1) | critical follow-ups: 0 | follow-ups: 2 | open questions: 0
not exercised: typecheck, lint, test execution, runtime behavior (skill is read-only; verifier not run)

Action list
[🟡] tests/contract.test.ts:62-66 — legacy config removed from runContractSuite despite brief §4 explicitly requiring legacy: { subject: 'whatsapp.events.{client}.>' }. ADR-0018 assertion #6 (legacy consumer entry coverage) is no longer exercised, so the channel reports "12 green" but only validates 11 of the 12 mandatory assertions. Runtime legacyConsumerEntries is still active in src/main.ts:171-174, so the production wiring exists — only the harness coverage is missing. — fix: re-add legacy: { subject: 'whatsapp.events.${client}.>' } to runContractSuite(...) so assertion #6 exercises the same surface that ships in production.
evidence: Brief §4 mandates the harness to wire legacy:. Removing it leaves runtime legacy consumer entries unverified; "all 12 assertions green" acceptance is technically false.

[🟡] docker-compose.yml — legacy docker-compose.yml (1 KB) remains alongside the canonical docker-compose.dev.yml; package.json scripts docker:up, docker:down, docker:logs still target the legacy file. A dev running docker compose up (no -f) will boot the stale stack and bypass the bind mounts, NATS override, and BuildKit secrets configured in the dev compose. — fix: delete docker-compose.yml and either remove or re-point the docker:* scripts to docker-compose.dev.yml -f.
evidence: Telegram and waba briefs explicitly delete this file as "broken copy"; same risk applies here — divergent compose files cause the wrong stack to boot silently.

[🟡] docs/dev-setup-report.md §4 + Dockerfile — production Dockerfile is documented as still broken (BLOCKER-1: @somoschat/channel2api* packages 404 on npm; report §4 row 1 is BLOCKED) and Dockerfile header still says "Validation status: planned for Stage 4" rather than recording the actual outcome. Brief §4 acceptance #4 requires a documented base image and a passing docker build. — fix: either land the resolution path (publish or vendor per ADR-0017 §5) or update the Dockerfile header comment to clearly mark the canonical image as unbuildable until ADR-0017 §5 lands, so consumers do not expect it to work.
evidence: report §4 BLOCKER-1 still open; canonical docker build fails at deps stage; only Dockerfile.dev works for now.

[🔵] tests/contract.test.ts:74-86 — triggerInbound only fetches /health and the comment acknowledges this stub does not produce NATS events, weakening assertions #1–3, #7, #8, #12 against real channel behavior. — fix: track the proposed tokenProvider hook in @channel2api/contract-tests and switch to a real outbound→echo round-trip once available.
evidence: file comment lines 67-73 already document this limitation as a follow-up on the harness package.

Follow-ups (not blocking)
src/main.ts:316-345 — DEFECT-2 in report §8 ("MediaDownloader restart loop on SIGTERM, SIGKILL at 10s") was reportedly addressed by commit 8c100d3 (withShutdownGuard + shutdownState.isShuttingDown set before stop). Acceptance criterion #5 should be re-tested live and the report row updated from FAIL → PASS.
COVERAGE-GAP — brief §4 acceptance #11 ("session persistence after restart without QR rescan") was confirmed live in stage 3; no automated regression test exists. Adding a docker-compose-driven integration test would lock the volume contract.
Review notes
Source code samples were read for tests/contract.test.ts, src/main.ts (NATS/shutdown surfaces), docker-compose.dev.yml, Dockerfile, manifest.yaml, docs/PLATFORM_CONTRACTS.md, .npmrc, bunfig.toml, package.json, .gitignore, docs/dev-setup-report.md (first ~200 lines). The 487-file diff was not exhaustively read — sampled against brief acceptance criteria §4 (15 items) and ADR-0011/0017/0018 conformance surfaces.
Manifest correctly omits SESSION_DIR (commit 7df6036) — justified by brief §3 note "Verify whether the app reads SESSION_DIR or derives from DATA_DIR".
ADR-0011 §1 dotted-type tokens (message.update, media.downloaded, etc.) are conformant per the structural rule clarification (umbrella commit 2fb7ddd); historical "DEFECT-4" in the report is no longer a defect.
ADR-0017 §3 NATS drain is satisfied by NatsClient.close() calling nc.drain() internally (verified in main.ts shutdown comment at line 320).
ADR-0019 setup is complete: .npmrc and bunfig.toml both reference ${GH_TOKEN_PKG} with no literal token; BuildKit secret wiring in Dockerfile/compose.
Subagent summary
fallback-main-agent: 4 findings (3 SHOULD-FIX, 1 NICE-TO-HAVE, 2 follow-ups)

[reviewer] done — verdict: APPROVED-WITH-FIXES

The implementation broadly conforms — five binding ADRs are wired, the harness exists, manifest/env/compose/Dockerfile.dev are aligned. Three actionable fixes: (1) re-add legacy: to the contract suite so the 12th assertion is actually exercised, (2) delete the stale top-level docker-compose.yml and repoint docker:* scripts, (3) close out the canonical Dockerfile blocker via ADR-0017 §5. SIGTERM defect appears fixed in commit 8c100d3 but report row 5 should be re-validated live.

Revisao B depois dos ajustes

Review — baileys2api_bun (branch feat/dev-setup)
verdict: APPROVED-WITH-FIXES
scope: partial (focused review against brief acceptance — full L deep-dive skipped given prior internal review cycles and 5264-line diff)
plan: L (degraded to focused main-agent pass)
subagents: fallback-main-agent
specs: brief docs/briefs/dev-setup/baileys2api_bun.md (explicit), ADR-0011, ADR-0016, ADR-0017, ADR-0018, ADR-0019, ADR-0003 (all explicit via brief)
findings: 3 (🔴 0, 🟡 2, 🔵 1) | critical follow-ups: 0 | follow-ups: 2 | open questions: 1

Action list
[🟡] tests/contract.test.ts:57-62 — Brief §4 acceptance criterion explicitly mandates legacy: { subject: 'whatsapp.events.{client}.>' } be passed to runContractSuite(...); the implementation deliberately removed the field with rationale ("no live external consumers found via grep"). The decision may be sound, but it contradicts a written acceptance line — fix: either restore the legacy arg, or amend the brief / open an ADR addendum recording the deviation so the acceptance checklist matches reality.
evidence: brief line "tests/contract.test.ts calls runContractSuite(...) with product: 'baileys' and legacy: { subject: 'whatsapp.events.{client}.>' }" is unambiguous; the harness cannot truthfully be marked "passed against brief" while the field is absent.

[🟡] src/main.ts:171-175 — legacyConsumerEntries shape { stream, name, legacyPrefix } differs from the brief's documented snippet [{ subject: 'whatsapp.events.${client}.>' }]. If @channel2api/nats-transport accepts both, leave a 1-line comment pointing to the transport's typed contract; if only the new shape is supported, update the brief example to avoid future agents copy-pasting the obsolete form — fix: add inline reference to the transport type, or update brief §2b code example.
evidence: shape mismatch is a documentation hazard for the next channel migrating its prefix.

[🔵] docker-compose.dev.yml:64-67 — bind mounts hardcode /repos/baileys2api_bun/...; works only because Dockerfile.dev sets WORKDIR /repos/baileys2api_bun. A future rename of the repo directory silently breaks the dev stack — fix: derive the path via a build arg, or comment the coupling at both ends.
evidence: implicit cross-file coupling between compose mount targets and Dockerfile WORKDIR.

Open questions
production Dockerfile (single-stage workspace /app, CMD bun run src/main.ts) is not exercised by any acceptance criterion in this brief — docker-compose.dev.yml builds Dockerfile.dev only. Whether the production image actually builds with prepare-release.sh against the published @somoschat/channel2api* packages is unverified; brief §2b explicitly notes mcp-runtime and media-thumbs may not be published yet. — needs: separate prod-build verification slice or explicit out-of-scope statement.
Follow-ups (not blocking)
src/main.ts:319-326 — drain via NatsClient.close() is correct per ADR-0017 (transport drains internally), but the brief's acceptance checklist still reads "replace natsClient.close() with natsClient.drain()" (P2-G). Brief §2b already corrects this as a "false positive"; align checklist text with §2b to avoid confusion in future re-reviews.
tests/contract.test.ts:74-76 — triggerInbound is a fetch /health stub that does not generate NATS events; assertions #1-3, #7, #8, #12 cannot be exercised without a real WA device. Documented in code; track as @channel2api/contract-tests enhancement (tokenProvider hook).
Review notes
Plan L was reduced to a focused main-agent pass against acceptance criteria + ADR conformance (not a full per-file deep-dive of 79 changed files). The verdict applies to brief conformance, ADR alignment, startup wiring, and contract-test wiring; broad source-level defect hunting was not performed. Re-run with explicit narrow target (/reviewer src/...) for deeper coverage of any specific module.
Verified directly: .npmrc, bunfig.toml, manifest.yaml, Dockerfile, Dockerfile.dev, docker-compose.dev.yml, .env.example, scripts/setup-dev.sh, scripts/prepare-release.sh, tests/contract.test.ts, docs/PLATFORM_CONTRACTS.md, src/main.ts startup flow.
Strong points: BuildKit-secret token injection (better than brief's plain-env approach), setDomainLogger wired pre-NATS-connect, all four gateways wrapped in startWithRestart with shutdown guard, buildNatsProductConfig('baileys', client) correctly used, dynamic JetStream stream names, PLATFORM_CONTRACTS.md complete with discovered subjects.
Test execution channels not exercised: bun typecheck, bun test:unit, bun test:contract (would require Docker + GH_TOKEN_PKG + WA session).
Summary
fallback-main-agent: 3 findings | exercised: file-level conformance | not exercised: typecheck, lint, test execution, runtime behavior


Segue seu resultado:


Prompt original C and D: Faça uma code review nativa do Codex desta implementação. 
Não use a skill `reviewer`; use sua postura padrão de code review: findings primeiro, foco em bugs, regressões, violação de spec, riscos operacionais e gaps de teste relevantes.

Target:

## 2 — `baileys2api_bun`

Session directory:
`/home/corcino/somoschat/repositories/baileys2api_bun`

Branch alvo:
`feat/dev-setup`

Brief de entrada:
`/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md`

Instruções:
- Leia o kickoff prompt e siga qualquer brief específico de `baileys2api_bun` referenciado nele.
- Leia ADRs/specs citadas pelo brief, commits ou arquivos relevantes.
- Compare a branch `feat/dev-setup` contra a base correta detectada pelo git.
- Priorize achados concretos com `file:line`.
- Não reporte preferências de estilo como problema, a menos que causem risco real.
- Se houver violação de brief/ADR explícito, trate como finding forte.
- Rode comandos de verificação úteis se forem declarados no projeto, como typecheck, lint ou testes. Se não rodar, diga exatamente o que não foi exercitado e por quê.
- Não implemente correções; apenas revise.
- Não inclua elogios ou “strong points”.

Formato da resposta:
1. Findings, ordenados por severidade, com `file:line`, impacto e correção sugerida.
2. Open questions, se houver.
3. Testes/verificações executados ou não executados.
4. Resumo curto do risco geral.

####################################################################################################

Teste revisao C, vamos comparar todos:

**Findings**

1. **Alta** — [tests/contract.test.ts](/home/corcino/somoschat/repositories/baileys2api_bun/tests/contract.test.ts:64): o harness ADR-0018 está conectado a hooks que não estimulam o canal. `triggerInbound` só chama `/health`, e `triggerOutbound` chama `/{MASTERKEY}/sendText`, rota que não existe para o contrato atual. Impacto: `bun run test:contract` falha e não prova ADR-0011/0017. Correção: usar hooks reais contra o provider boundary/Baileys ou derivar o token e chamar uma rota existente que gere evento/job observável.

2. **Alta** — [package.json](/home/corcino/somoschat/repositories/baileys2api_bun/package.json:17): `test:integration` sobe `channel webhook-echo`, mas não sobe `nats`; a suíte passa com `4 pass / 34 skip`. Além disso, [tests/integration/inbound-text.test.ts](/home/corcino/somoschat/repositories/baileys2api_bun/tests/integration/inbound-text.test.ts:12) declara que publica evento sintético direto no NATS e não exercita o caminho WA WebSocket → canal. Impacto: a cobertura funcional exigida pelo brief é falsa. Correção: subir NATS, falhar quando pré-condições obrigatórias não existem, e testar o container vivo com stub apenas na fronteira Baileys.

3. **Alta** — [Dockerfile](/home/corcino/somoschat/repositories/baileys2api_bun/Dockerfile:30): `docker build` falha porque o `package.json` ainda contém `file:../channel2api/...` e o contexto não contém esses pacotes. O fluxo de release também está frágil: [scripts/prepare-release.sh](/home/corcino/somoschat/repositories/baileys2api_bun/scripts/prepare-release.sh:60) só faz backup de `bun.lockb`, mas o repo usa `bun.lock`; [Dockerfile](/home/corcino/somoschat/repositories/baileys2api_bun/Dockerfile:26) copia só `bun.lockb*`. Impacto: build/release não é reprodutível e o critério “docker build passa” não está atendido. Correção: suportar `bun.lock`, restaurar o lock correto e garantir que o build use deps npm já preparadas ou workspace vendorizado.

4. **Média** — [.env.example](/home/corcino/somoschat/repositories/baileys2api_bun/.env.example:14) e [manifest.yaml](/home/corcino/somoschat/repositories/baileys2api_bun/manifest.yaml:15): `SESSION_DIR` foi omitido, apesar de ADR-0016/brief exigirem esse contrato para a sessão WA. Impacto: o control plane não sabe montar/gerenciar explicitamente o diretório crítico de sessão; perda desse volume força novo QR. Correção: adicionar `SESSION_DIR` no schema/env/manifest e fazer `paths.ts` usá-lo com fallback para `{DATA_DIR}/whatsSessions`.

5. **Média** — [src/application/workers/media-downloader.ts](/home/corcino/somoschat/repositories/baileys2api_bun/src/application/workers/media-downloader.ts:111): `MediaDownloader.start()` captura erro de inicialização e não relança, embora seja passado para `startWithRestart` em [src/main.ts](/home/corcino/somoschat/repositories/baileys2api_bun/src/main.ts:183). Impacto: o restart harness perde o backoff em falhas desse worker e pode entrar em loop imediato/log storm. Correção: relançar erro após marcar `isRunning=false`, deixando `startWithRestart` controlar o retry.

6. **Média** — [tests/provider-whatsapp/unit/event-handlers-group-participant-activity.test.ts](/home/corcino/somoschat/repositories/baileys2api_bun/tests/provider-whatsapp/unit/event-handlers-group-participant-activity.test.ts:7): o fake `StateStore` não implementa `batchUpsertContacts`, mas [event-handlers.ts](/home/corcino/somoschat/repositories/baileys2api_bun/src/providers/whatsapp/baileys/adapter/event-handlers.ts:59) agora chama esse método. Impacto: suíte unitária vermelha. Correção: atualizar o fake ou testar contra uma implementação compatível da interface.

**Open Questions**

Nenhuma.

**Testes / Verificações**

- `git diff --check 4969f4e...HEAD`: passou.
- `bun run check`: passou.
- `bun test tests/core/unit tests/provider-whatsapp/unit`: falhou, 376 pass / 1 fail.
- `DOCKER_BUILDKIT=1 docker build --secret id=gh_token_pkg,env=GH_TOKEN_PKG ...`: falhou resolvendo deps `file:../channel2api/...`.
- `bun run test:contract`: falhou, 2 pass / 7 fail / 1 error.
- `bun run test:integration`: saiu 0, mas com 34 skips e só 4 testes offline passando.

**Resumo Do Risco**

Risco geral alto. A branch não atende os critérios centrais do brief: contract conformance não passa, testes funcionais não exercitam os cenários obrigatórios, e o caminho Docker/release ainda quebra.



Segue o relatório D emitido pelo claude code:

Resumo dos achados
Sev	#	Achado
HIGH	F-1	test:ci vermelho — 1 unit test falha (handleContactsUpdate usa batchUpsertContacts mas o fake só implementa upsertContact)
MED	F-2	docker-compose.yml tem WA_STORE_BACKEND duplicado com defaults conflitantes (sqlite vs json)
MED	F-3	bunfig.toml usa ${GH_TOKEN_PKG} mas o brief exige $GH_TOKEN_PKG (violação de spec ADR-0019/brief §2c)
MED	F-4	SESSION_DIR removido do manifest — diverge do brief e ADR-0016 (decisão de design documentada, mas sem amendamento formal)
MED	F-5	triggerOutbound no contract test bate em /${MASTERKEY}/sendText que não existe como rota → 404 sempre
MED	F-6	triggerInbound é stub (/health) — não produz eventos NATS
LOW	F-7	Dockerfile HEALTHCHECK --interval=30s ≠ manifest interval_seconds: 15
LOW	F-8–9	Dockerfile COPY sem --chown + mkdir -p /data no Dockerfile.dev (viola regra do kickoff)
LOW	F-10	.env.example NATS_URL aponta para DNS interno (nats://nats:4222) — falha em bun run dev no host
Typecheck (tsc): ✅ pass · Unit tests: ❌ 376 pass / 1 fail · Docker/integration/contract: não executados (requer infra viva)
# Code Review — `baileys2api_bun` · `feat/dev-setup`

**Branch**: `feat/dev-setup` (107 commits, 487 files, +42 023 / −21 227)
**Base**: `825d183` (main)
**Date**: 2026-04-30

---

## 1 — Findings

### F-1 · `test:ci` is red — unit test regression (severity: high)

[event-handlers-group-participant-activity.test.ts:75](file:///home/corcino/somoschat/repositories/baileys2api_bun/tests/provider-whatsapp/unit/event-handlers-group-participant-activity.test.ts#L75)

`handleContactsUpdate` (implemented at [src/providers/whatsapp/baileys/adapter/event-handlers.ts:42](file:///home/corcino/somoschat/repositories/baileys2api_bun/src/providers/whatsapp/baileys/adapter/event-handlers.ts#L42)) calls `stateStore.batchUpsertContacts()`. The test's `FakeStateStore` only implements `upsertContact()` — it never implements `batchUpsertContacts()`. Result: 1 of 377 unit tests fails, making `bun run test:ci` exit non-zero.

**Impact**: CI gate is broken. Any green-signal tooling relying on `test:ci` will refuse to proceed.

**Fix**: Implement `batchUpsertContacts` in `FakeStateStore` (delegate to per-item `upsertContact`), or update the test assertions to match the batch API.

---

### F-2 · `docker-compose.yml` has duplicate `WA_STORE_BACKEND` env var (severity: medium)

[docker-compose.yml:22–25](file:///home/corcino/somoschat/repositories/baileys2api_bun/docker-compose.yml#L22-L25)

```yaml
- WA_STORE_BACKEND=${WA_STORE_BACKEND:-sqlite}   # line 22
...
- WA_STORE_BACKEND=${WA_STORE_BACKEND:-json}      # line 25
```

Two entries for the same key with different defaults (`sqlite` vs `json`). Docker Compose keeps the **last** entry, so the effective default is `json` — contradicting the `.env.example` default of `sqlite`. This is also a behavioral surprise: the `sqlite` entry is a no-op.

**Impact**: Production compose brings up with `json` backend unexpectedly; may cause state persistence issues if operator expects `sqlite`.

**Fix**: Remove one of the duplicate entries; decide the canonical default and keep only that one.

---

### F-3 · `bunfig.toml` uses `${GH_TOKEN_PKG}` instead of `$GH_TOKEN_PKG` (severity: medium — brief violation)

[bunfig.toml:2](file:///home/corcino/somoschat/repositories/baileys2api_bun/bunfig.toml#L2)

The brief at [baileys2api_bun.md §2c](file:///home/corcino/somoschat/docs/briefs/dev-setup/baileys2api_bun.md#L106-L110) specifies:
```toml
"@somoschat" = { url = "https://npm.pkg.github.com", token = "$GH_TOKEN_PKG" }
```

The actual file uses:
```toml
"@somoschat" = { url = "https://npm.pkg.github.com", token = "${GH_TOKEN_PKG}" }
```

The brief explicitly states: *"The two syntaxes (`${...}` vs `$...`) are intentional — each parser has its own. Do not normalize them."* — `.npmrc` gets `${GH_TOKEN_PKG}`, `bunfig.toml` gets `$GH_TOKEN_PKG`.

**Impact**: Bun's TOML parser may or may not expand `${...}` — if it doesn't, `bun install` silently sends the literal string `${GH_TOKEN_PKG}` as auth token, causing 401 failures that are hard to diagnose. Functionally this appears to work today in dev, but is a spec violation and a latent breakage risk across Bun versions.

**Fix**: Change to `$GH_TOKEN_PKG` per the brief.

---

### F-4 · `manifest.yaml` omits `SESSION_DIR` from infrastructure list (severity: medium — brief violation, resolved by design decision)

[manifest.yaml:15–22](file:///home/corcino/somoschat/repositories/baileys2api_bun/manifest.yaml#L15-L22)

The brief at [baileys2api_bun.md §3](file:///home/corcino/somoschat/docs/briefs/dev-setup/baileys2api_bun.md#L150-L158) lists `SESSION_DIR` as an infrastructure variable. The implementation deliberately removed it (commit `7df6036` — *"drop unused SESSION_DIR"*), since the runtime code derives the session path from `DATA_DIR` internally.

ADR-0016 [§ baileys2api_bun](file:///home/corcino/somoschat/docs/adr/0016-channel-credential-contract.md#L80-L86) also defines `SESSION_DIR` as an infrastructure variable.

This is a **documented design divergence** from both the brief and ADR-0016. The implementation is arguably cleaner (no unused env var), but it creates a gap: the control plane reads `manifest.yaml` to construct the `docker run` command — if it ever injects `SESSION_DIR`, the channel ignores it silently.

**Impact**: Low runtime risk (unused var is benign), but violates the manifest contract that the control plane trusts.

**Fix**: Either add `SESSION_DIR` to the manifest (and optionally read it in the app as an override), or update ADR-0016's baileys section to remove `SESSION_DIR`. The decision should be explicit.

---

### F-5 · Contract test `triggerOutbound` hits a non-existent route (severity: medium)

[tests/contract.test.ts:81–89](file:///home/corcino/somoschat/repositories/baileys2api_bun/tests/contract.test.ts#L81-L89)

```typescript
triggerOutbound: async (baseUrl: string) => {
    await fetch(`${baseUrl}/${MASTERKEY}/sendText`, { ... });
},
```

There is **no** `/{masterKey}/sendText` route in `server.ts`. Messaging routes use the `/{instance}/sendMessage` pattern with `?token=` query auth. The outbound route is `/{masterKey}/reloadServer` style, but `sendText` does not exist at all in the router.

This means `triggerOutbound` always receives a 404. The contract harness may tolerate this (the hook comment says "will return 4xx/5xx if the WA session is not connected"), but the intent is to actually dispatch an outbound message — it can't.

**Impact**: ADR-0018 assertions that depend on observing outbound traffic will never see real outbound events. The harness may pass vacuously for those assertions.

**Fix**: Use a valid route, e.g. `/${MASTERKEY}/sendText` → `/{instance}/sendMessage?token=<derived>` with the derived HMAC token.

---

### F-6 · Contract test `triggerInbound` only hits `/health` — no NATS event produced (severity: medium)

[tests/contract.test.ts:74–76](file:///home/corcino/somoschat/repositories/baileys2api_bun/tests/contract.test.ts#L74-L76)

```typescript
triggerInbound: async (baseUrl: string) => {
    await fetch(`${baseUrl}/health`);
},
```

The comment acknowledges this is a stub. `/health` produces no NATS events. ADR-0018 assertions #1–3, #7, #8, #12 require observing actual NATS events emitted by the channel.

**Impact**: The contract suite may pass vacuously for event-shape assertions. True conformance is not being tested.

**Fix**: This is inherent to Baileys (no inbound HTTP webhook). The follow-up (documented in the comment) to add a `tokenProvider` config hook to the harness is the right path. For now, log this as a gap.

---

### F-7 · Dockerfile HEALTHCHECK interval (30s) differs from manifest spec (15s) (severity: low)

[Dockerfile:68](file:///home/corcino/somoschat/repositories/baileys2api_bun/Dockerfile#L68) vs [manifest.yaml:41](file:///home/corcino/somoschat/repositories/baileys2api_bun/manifest.yaml#L41)

Dockerfile: `--interval=30s`
manifest.yaml: `interval_seconds: 15`
Brief: `interval_seconds: 15`

The manifest and brief agree on 15s. The Dockerfile uses 30s.

**Impact**: Docker's built-in health check will report unhealthy 2× slower than the control plane expects. Minor in dev; could delay container replacement in orchestrated environments.

**Fix**: Change Dockerfile HEALTHCHECK to `--interval=15s`.

---

### F-8 · Dockerfile COPY without `--chown` for application source (severity: low)

[Dockerfile:49–50](file:///home/corcino/somoschat/repositories/baileys2api_bun/Dockerfile#L49-L50)

```dockerfile
COPY --from=deps /app/node_modules ./node_modules   # no --chown
COPY . .                                             # no --chown
```

Then at line 54: `RUN addgroup ... && chown -R channel:channel /app`. This works, but the recursive `chown` on the entire `/app` tree is expensive for large `node_modules` — it touches every file inode. The ADR-0016 Dockerfile template uses `COPY --from=deps --chown=channel:channel`.

**Impact**: Increased image build time; no runtime bug.

**Fix**: Use `COPY --chown=channel:channel` for both COPY commands and remove the `chown -R` from the RUN step.

---

### F-9 · `Dockerfile.dev` uses `mkdir -p /data` — brief says "do NOT create with RUN mkdir" (severity: low — brief violation)

[Dockerfile.dev:75](file:///home/corcino/somoschat/repositories/baileys2api_bun/Dockerfile.dev#L74-L76)

```dockerfile
RUN addgroup -S channel && adduser -S -G channel -u 1001 channel \
    && mkdir -p /data \
    && chown -R channel:channel /repos /data
```

The kickoff prompt's Dockerfile Rule §2c states: *"Do NOT create it with RUN mkdir in the Dockerfile — Docker creates volume mount points automatically; baking them in hides missing-volume bugs."*

**Impact**: If the volume is not mounted, the container silently writes to the ephemeral `/data` inside the container layer — data loss on container recreation, with no visible error.

**Fix**: Remove `mkdir -p /data` and the `chown` of `/data`.

---

### F-10 · `.env.example` `NATS_URL` uses `nats://nats:4222` — unreachable from host (severity: low)

[.env.example:17](file:///home/corcino/somoschat/repositories/baileys2api_bun/.env.example#L17)

```
NATS_URL=nats://nats:4222
```

When running `bun run dev` on the host (not in a container), `nats://nats:4222` resolves to nothing. The `docker-compose.dev.yml` overrides this at the container level (`NATS_URL: ${NATS_URL_OVERRIDE:-nats://nats:4222}`), so containerized runs work fine.

The ADR-0016 template says `NATS_URL=nats://nats:4222`. However, the `.env.example` is also used for `bun run dev` on the host. This is an ergonomic issue: a dev running `bun --watch src/main.ts` locally will fail to connect to NATS unless they manually change the URL to `nats://localhost:4222`.

**Impact**: Dev friction; no production risk.

**Fix**: Change to `nats://localhost:4222` and document the override pattern (compose overrides to internal DNS).

---

### F-11 · `@channel2api/media-thumbs` not listed as dependency (severity: info)

Brief §2b states: *"baileys2api_bun consumes all four packages from @channel2api [...] @channel2api/media-thumbs ✅ required."*

The `package.json` does not include `@channel2api/media-thumbs`. No source code imports it either. The `prepare-release.sh` lists it (forward-compatibility) but it is not consumed.

**Impact**: None today — the code doesn't use it. The brief says "required" but it isn't actually needed yet.

**Fix**: No action needed unless media-thumbs integration is actually required. This is a brief imprecision, not a code bug.

---

### F-12 · MASTERKEY still exposed in URL paths — ADR-0016 violation (severity: info — out of scope per brief §5)

[server.ts:71–185](file:///home/corcino/somoschat/repositories/baileys2api_bun/src/adapters/inbound/http/server.ts#L71-L185)

Dozens of routes use `/{masterKey}/` and `/{instance}/{masterKey}/` patterns. ADR-0016 §Credential Exposure Prohibition says:
> *"MASTERKEY and all provider credentials must not appear in URL paths."*

This is explicitly listed as **out of scope** (brief §5, P3-B), so this is informational only. Tracked as a future brief.

---

## 2 — Open Questions

| # | Question |
|---|---------|
| Q1 | `SESSION_DIR` was removed from manifest and .env.example by design (commit `7df6036`). Does this divergence from ADR-0016's baileys section need a formal ADR amendment, or is the manifest the source of truth and the ADR should be updated? |
| Q2 | The `triggerOutbound` in `contract.test.ts` will always 404. Is the contract harness designed to tolerate 404 in these hooks, or is this masking assertion failures? Need to verify against the harness implementation. |
| Q3 | The Dockerfile is "planned for Stage 4 validation" per its header comment, but `docker build` has apparently never been validated in this branch. Was a Docker build attempted and did it succeed? |

---

## 3 — Tests / Verifications Executed

| Check | Result |
|-------|--------|
| `bun run check` (TypeScript) | ✅ **Pass** — 0 errors |
| `bun run test:ci` (unit tests + TS baseline) | ❌ **Fail** — 376 pass, **1 fail** (`handleContactsUpdate` fake state store mismatch) |
| `bun run test:contract` | ⏭ **Not executed** — requires running Docker stack (live container + NATS). Not safe to start infrastructure in review. |
| `bun run test:integration` | ⏭ **Not executed** — same reason (requires `docker compose up`). |
| `docker build` | ⏭ **Not executed** — requires `GH_TOKEN_PKG` and `prepare-release.sh` pre-step. Would need live token. |
| `docker compose -f docker-compose.dev.yml up` | ⏭ **Not executed** — same reason. |
| `.env` git tracking check (`git ls-files .env`) | ✅ **Clean** — `.env` is not tracked. |
| Brief spec compliance (manual) | ⚠ Partial — see findings F-3, F-4, F-9. |

---

## 4 — Risk Summary

**Overall risk: medium.**

The branch contains a very large amount of work (107 commits, 42K lines added) with extensive refactoring and new test coverage. The architecture is solid — NATS subjects conform to ADR-0011, `startWithRestart` wrapping is correct, `setDomainLogger` is wired, shutdown handlers are thorough.

The **key risks** are:

1. **CI is red** (F-1): the unit test suite has 1 regression. Must be fixed before merge.
2. **Contract test stimulus is non-functional** (F-5, F-6): `triggerOutbound` hits a 404 route and `triggerInbound` is a no-op. The 12-assertion contract suite likely passes vacuously for event-related assertions. True ADR-0018 conformance is unverified.
3. **`docker-compose.yml` duplicate env var** (F-2): silent behavioral bug with wrong default.
4. **`bunfig.toml` syntax** (F-3): brief spec violation that may break across Bun versions.
5. **`Dockerfile.dev` `mkdir`** (F-9): violates the Dockerfile rule from the kickoff and masks missing-volume bugs.

None of these are data-loss or security-critical in the current dev context. The highest-priority fix is F-1 (red tests), followed by F-2 (runtime behavior), then F-5 (contract test validity).




Prompt Original F (Reviwer-v2): use o reviewer skill para avaliar a implementação ## 2 — baileys2api_bun

**Branch**: git checkout -b feat/dev-setup
**Session directory**: ~/somoschat/repositories/baileys2api_bun
/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md


################################################################################

Review — baileys2api_bun feat/dev-setup
target: branch feat/dev-setup @ 3f8e099
base: main
spec: docs/briefs/dev-setup/kickoff-prompts.md §2 and the linked brief docs/briefs/dev-setup/baileys2api_bun.md (ADR-0011/0016/0017/0018/0019)
scope: partial(no docker build executed; no live container started; no bun test run by reviewer — file/spec inspection plus implementer's own report)
verdict: BLOCKED
Findings
HIGH — Production Dockerfile cannot install: lockfile is excluded from build context AND not matched by COPY glob
Dockerfile:26 does:


COPY package.json bun.lockb* bunfig.toml .npmrc ./
followed by Dockerfile:30-32 bun install --frozen-lockfile --production.

Two compounding defects:

The repo only has bun.lock (Bun 1.x text format) — there is no bun.lockb. The glob bun.lockb* does not match bun.lock. Verified: ls bun.lockb → not found; bun.lock exists (68 KB, tracked).
.dockerignore:7-8 explicitly excludes both bun.lockb and bun.lock, so even if the COPY glob were corrected, the file would not be in the build context.
Result: bun install --frozen-lockfile runs without a lockfile and fails (or silently degrades, depending on Bun version). This is independent of the agent's reported BLOCKER-1 (npm 404 on private packages); refreshing GH_TOKEN_PKG or publishing packages will not unblock criterion #1.

Impact: brief acceptance criterion #1 (docker build completes without error) cannot pass for production. Self-reported as BLOCKED but root cause was misattributed.
Fix: copy package.json bun.lock* bun.lockb* bunfig.toml .npmrc ./ and remove bun.lock / bun.lockb from .dockerignore (or replace the dev-time exclusion with a !bun.lock re-include rule).

HIGH — Spec requires bun test AND bun test:contract to pass; current state is 2/9 conformance assertions passing
Kickoff §5: "Both bun test (functional) and bun test:contract (conformance) must pass before the work is considered complete."

Implementer's own report (docs/dev-setup-report.md:578-592) shows the final harness run: 2 pass / 7 fail across the ADR-0011/0017/0018 contract assertions. Failures span subjects (#1–3), productId (#7), restart loop (#8), SIGTERM drain (#9), LOG_FORMAT (#10), setDomainLogger (#11), and envelope shape (#12). The implementer self-classifies as PARTIAL-HARNESS-CAPPED and files upstream issues against @channel2api/contract-tests, but the brief is unambiguous that the tests must pass — there is no carve-out.

Impact: the conformance gate that ADR-0018 was created to enforce is failing. The kickoff prompt explicitly forbids replacing the harness with mocks, but several failures (LOG_FORMAT, PORT mismatch) are config drift on this side, not harness bugs.
Fix: at minimum, fix the in-repo config items called out in the report's own "Remaining Blockers" table (set LOG_FORMAT=json, align PORT between .env and harness, fix legacyConsumerEntries shape) and re-run before declaring done. Upstream-only items should be tracked with explicit deferrals approved by Paulo.

HIGH — Acceptance criterion #5 (SIGTERM clean shutdown) is FAIL
docs/dev-setup-report.md:30: "MediaDownloader restart loop causes SIGKILL at 10s (DEFECT-2). Fix deferred." The report later notes container-side drain timing of 703–930ms, but assertion #9 still fails in harness. Contradictory data — either the runtime drain is fine and the harness probe is mis-targeted (PORT=8001 vs 32001), or DEFECT-2 is real. Either way, the criterion is not green.

Fix: reproduce inside the dev compose, decide whether DEFECT-2 is real, fix or align .env PORT before closing the criterion.

MEDIUM — docker-compose.dev.yml uses bind mounts; brief mandates named volumes
Kickoff DOCKERFILE RULE step 2.b: "Declare it as a named volume in docker-compose.dev.yml (both under services.<name>.volumes and the top-level volumes: key)."

docker-compose.dev.yml:60-67 uses host bind mounts (./data:/repos/...) and has no top-level volumes: block. The implementer's rationale ("host filesystem is the single source of truth for dev sessions") is reasonable, but the spec is explicit. Either get an explicit waiver from Paulo and document it as a deviation, or convert to named volumes.

MEDIUM — .dockerignore excludes public/ but public/swagger-ui.html is committed and likely served
.dockerignore:29 excludes public/. public/swagger-ui.html is git-tracked (verified: git ls-files public/). The Swagger UI page will not be present in the production image. Confirm whether the app serves it from disk; if so, this is a runtime regression for the docs surface.

MEDIUM — Brief item "replace natsClient.close() with natsClient.drain()" treated as no-op based on internal knowledge of @channel2api/nats-transport
src/main.ts:320-321 keeps natsClient.close() with a comment claiming it drains internally. The brief explicitly directs a code change. If the comment is correct, document it as a verified deviation in the report's deviation table; if not, apply the change. The current state is "trust the comment", which is what the brief was written to avoid.

LOW — WEBHOOK vs WEBHOOK_URL and API_URL env-name drift papered over with aliases
DEVIATION-1 / DEVIATION-2 in the report keep both names alive in .env.example instead of renaming the source-code reads. Acceptable as a transitional shim, but leave a tracked TODO with an owner.

Open Questions
Was docker build . actually executed end-to-end at any stage? The report says it failed at install due to npm 404; given the lockfile defect above, the proximate failure may be different from what was reported. Worth re-running once GH_TOKEN_PKG is refreshed and packages are published, with the lockfile fix applied, to confirm the failure mode.
Has Paulo been asked to formally approve PARTIAL-HARNESS-CAPPED as the closure state for this brief, or is this self-classification by the implementer? The brief's "must pass" wording does not contemplate that classification.
Verification
Check	Run	Result
Spec read (kickoff §2 + brief acceptance)	yes	spec items mapped to findings
docker build (production)	not run	NOT_EXERCISED reason=requires GH_TOKEN_PKG + private-package access; harness operates from review host
bun test / bun test:contract	not run	NOT_EXERCISED reason=would start dev compose stack; relied on implementer's documented final run (2/9)
Source/static inspection of Dockerfile, .dockerignore, compose, contract test, env, package.json, prepare-release.sh	yes	findings above
Lockfile presence in working tree	ls bun.lock bun.lockb	only bun.lock exists
.dockerignore lockfile rule	grep -c bun.lock .dockerignore	2 (both excluded)
Notes
Scope is partial: no container was started or built by the reviewer. The HIGH findings are file-grounded and do not require a runtime to confirm; the MEDIUM SIGTERM finding leans on the implementer's own contradictory data and would benefit from a live re-run.
The implementer's report is unusually candid about its own gaps; most findings here are escalations of items the report already lists as BLOCKED/FAIL/DEVIATION but which the closing summary frames as acceptable. The verdict here reflects the brief's literal "must pass" language, not a judgment that the work was poor.
ADR-0019 token wiring (bunfig.toml, .npmrc, BuildKit secret mount) looks correct in both Dockerfiles — no leak found in image layers.

Prompt Original G (Reviwer v1): use o reviewer skill para avaliar a implementação ## 2 — baileys2api_bun

**Branch**: git checkout -b feat/dev-setup
**Session directory**: ~/somoschat/repositories/baileys2api_bun
/home/corcino/somoschat/docs/briefs/dev-setup/kickoff-prompts.md


################################################################################

# Review — branch feat/dev-setup at ~/somoschat/repositories/baileys2api_bun

verdict: BLOCKED
scope: partial (487-file diff far exceeds brief; review tightly scoped to brief acceptance checklist + ADR-0011/0017/0018/0019 surface)
plan: L
subagents: fallback-main-agent
specs: kickoff-prompts.md §2 (explicit), briefs/dev-setup/baileys2api_bun.md (explicit), ADR-0011 / 0017 / 0018 / 0019 (explicit, named in brief)
findings: 4 (🔴 1, 🟡 3, 🔵 0) | critical follow-ups: 0 | follow-ups: 2 | open questions: 0
not exercised: typecheck, lint, test execution, runtime behavior (review was static; no `bun run check`, `bun test`, or harness re-run executed)

## Action list

1. [🔴] [tests/contract.test.ts:31-76](tests/contract.test.ts#L31-L76) — brief §4 acceptance criterion #18 ("all 12 ADR-0011/0017 assertions green") is unmet: only 2/9 assertions pass autonomously per docs/dev-setup-report.md:602-616. The implementer's "PARTIAL-HARNESS-CAPPED" label is self-issued, not an umbrella decision; assertions #1-3, #7-12 cascade from a `/health` stub `triggerInbound` that never publishes a real WA event. — fix: add a `tokenProvider` hook to `@channel2api/contract-tests` and wire it so `triggerOutbound` synthesizes a real WA send (closes #1-3, #7, #12); add a stdout-filter hook so Baileys library lines do not break the JSON-format probe (closes #10-11); OR formally amend ADR-0018 with a "partial-harness-capped" passing state and update the brief.
   evidence: harness output recorded as `2 pass / 7 fail` (post-reviewer-fixes) at docs/dev-setup-report.md:584-596; the kickoff prompt explicitly says "Both `bun test` (functional) and `bun test:contract` (conformance) must pass before the work is considered complete" (kickoff-prompts.md §2 line 543-544).

2. [🟡] [bunfig.toml:2](bunfig.toml#L2) — `token = "${GH_TOKEN_PKG}"` deviates from brief §2c, which prescribes `$GH_TOKEN_PKG` (no braces) and states "the two syntaxes (`${...}` vs `$...`) are intentional — do not normalize them". Commit 5144bb5 normalized it deliberately, yet docs/dev-setup-report.md §10.2 still describes the file as `token = "$GH_TOKEN_PKG"` — file and report disagree. — fix: revert to `token = "$GH_TOKEN_PKG"` to match brief + ADR-0019, OR add a Bun-parser test asserting `${VAR}` interpolation works and amend ADR-0019 §2 / the brief to reflect that both syntaxes are accepted.
   evidence: bunfig.toml line 2 contains `${GH_TOKEN_PKG}`; dev-setup-report §10.2 (line 296-303) and §10.5 (line 313-321) describe it as `$GH_TOKEN_PKG`.

3. [🟡] [src/main.ts:171-175](src/main.ts#L171-L175) — `legacyConsumerEntries` is built with shape `{stream, name, legacyPrefix}` (a consumer-cleanup form). Brief §2b prescribes shape `{subject: 'whatsapp.events.${client}.>'}` (a subject-bridge form, so existing consumers keep receiving). As a downstream effect, contract assertion #6 (legacy consumer probe) was disabled at [tests/contract.test.ts:58-62](tests/contract.test.ts#L58-L62) ("legacy: removed — no live external consumer") instead of being aligned at the channel. — fix: align the channel-side shape to a subject bridge so the migration window stays live, OR open an umbrella ADR to formally retire the bridge requirement before merge.
   evidence: brief §2b lines 64-70 show explicit shape `{ subject: 'whatsapp.events.${client}.>' }`; current src/main.ts:174 emits `{ stream: …, name: 'mcp-events-gateway', legacyPrefix: 'whatsapp.' }`.

4. [🟡] COVERAGE-GAP brief §4 #15 (functional integration tests) — `tests/integration/` contains group, inbound-text, interactive, outbound-media, outbound-text, but no `inbound-media.test.ts`; brief explicitly lists "inbound media (image, document)" as a required scenario, and dev-setup-report §12 also notes "Inbound stubs deferred (test.skip) pending live WA session". — fix: add `tests/integration/inbound-media.test.ts` with provider stub at the Baileys WhatsApp Web socket boundary (the only stub layer ADR-0018 / brief permits) covering image and document arrival.
   evidence: `ls tests/integration/` returns 5 files, none named inbound-media; brief §4 line 289 requires "inbound message, outbound message, inbound media, outbound media, group message, interactive elements".

## Follow-ups (not blocking)

- COVERAGE-GAP `bun test` (functional) — dev-setup-report §6 reports "372 pass / 17 fail" (Stage 3) without enumeration of the 17 failures; brief acceptance #14 says "Existing tests pass inside the container" — fix: triage and either fix or document each of the 17 failing tests in the report, with rationale per failure.
- [🔵] branch tip has 7 untracked stage-report drafts in `docs/plans/` plus modified `.gitignore` and `docs/dev-setup-report.md` — fix: commit or remove the untracked files before declaring the branch ready to merge; brief explicitly says "Explicit git add paths only — never git add -A".

## Review notes

- 487 files / 107 commits in this branch is far broader than the dev-setup brief mandates. Review was tightly scoped to the brief's 16 acceptance criteria and ADR-0011/0017/0018/0019 conformance. Out-of-scope engineering work (e.g. ~21 new `tests/provider-whatsapp/unit/*.test.ts` files, ~6 contract-tests, refactors under `tests/scripts/`) was not exhaustively reviewed. Hidden defects in those files would not surface here.
- delegation skipped: review packet was already loaded into main context, and the brief is a 16-item checklist; spawning three subagents would re-read the same files for the same purpose at higher token cost. Recorded as `fallback-main-agent`.
- spec provenance: brief baileys2api_bun.md and kickoff-prompts.md §2 are explicit (referenced by the user's invocation); ADR-0011/0017/0018/0019 are explicit (named in the brief). All BLOCKING gating in §4.3 applied accordingly.
- harness assertion #6 was *removed from the suite* rather than fixed; the action list captures this in finding 3 — flagging here so the user does not read "9 assertions" as the full ADR-0018 surface.
- dev-setup-report §10.5 lists `.npmrc`, `bunfig.toml`, `Dockerfile*` as "current (uncommitted)" but `git status` shows them clean — the report's commit-state column has drifted; not a defect, noted for accuracy when revising the report.

## Summary

code+tdd (inline): 4 findings
verifier: not run (sequential review only)
fallback-main-agent: 4 findings
[reviewer] done — verdict: BLOCKED

Bottom line: BLOCKED on one explicit acceptance criterion (bun test:contract is at 2/9 pass autonomously, brief says all 12 must be green). Three SHOULD-FIX deviations from the brief: bunfig.toml interpolation syntax, legacyConsumerEntries shape (with the harness assertion disabled to compensate), and a missing inbound-media integration test. Branch state is otherwise mature — Dockerfile.dev, manifest.yaml, PLATFORM_CONTRACTS.md, ADR-0011 subject migration, drain semantics, and setDomainLogger injection are all correct against the spec.

The right next move is upstream: harness gaps live in @channel2api/contract-tests, not this repo. Either land tokenProvider + stdout-filter hooks there (closes #1-3, #7, #10-12 in one go) or get an umbrella ADR amendment that formalizes the partial-harness-capped state.


####################################################################################################

# Cross-Run Comparison — Run G vs A/B/C/D/F

Run G is the cleanest like-for-like comparison against A: same skill (reviewer v1), same target, same brief, different commit on the branch (fixes were applied between A and G, so part of the delta is real progress, not reviewer drift).

## Verdicts

| Run | Reviewer | Verdict | Findings | Checks executed |
|---|---|---|---|---|
| A | v1 (pre-changes) | APPROVED-WITH-FIXES | 3🟡 + 1🔵 | none |
| B | v1 (post experimental changes) | APPROVED-WITH-FIXES | 2🟡 + 1🔵 | none |
| C | native Codex | effectively BLOCKED | 3 high + 3 med | typecheck, unit, contract, integration, docker build |
| D | native Claude Code | medium risk | 1 high + 4 med + 5 low | typecheck, unit |
| F | reviewer-v2 (calibrated) | BLOCKED | 6 (mixed) | static + report |
| G | v1 (current state) | BLOCKED | 1🔴 + 3🟡 | none |

## What G adds that A missed

- **Promotes harness pass-rate to 🔴 BLOCKING.** A read the same harness gap as a 🟡 (re-add `legacy:` to `runContractSuite`). G escalates correctly: brief §4 says "all 12 must pass", current state is 2/9, and the implementer's "PARTIAL-HARNESS-CAPPED" is self-classified — not an umbrella decision. Verdict moves from APPROVED-WITH-FIXES → BLOCKED on the literal spec language.
- **`bunfig.toml` `${GH_TOKEN_PKG}` syntax drift.** A missed it; D caught it; G caught it AND noticed that `dev-setup-report.md` describes the file with `$GH_TOKEN_PKG` while the file actually contains `${GH_TOKEN_PKG}` — file/report disagreement. This is a finding A did not have the precision to surface.
- **`legacyConsumerEntries` shape mismatch (deeper read than A).** A asked to "re-add `legacy:` to `runContractSuite`". G traces the root cause one level up: the channel-side shape `{stream, name, legacyPrefix}` is a consumer-cleanup form, brief prescribes `{subject: …}` (a subject-bridge form), and the harness's assertion #6 was *disabled* to paper over the mismatch instead of fixing the channel. A's "re-add legacy" would have fixed the symptom; G's fix points at the spec deviation that caused the symptom.
- **Missing `inbound-media.test.ts`.** A did not enumerate the integration test directory; G mapped `tests/integration/` against brief §4 #15 and identified the one scenario without a file.

## What G missed that other runs caught

- **Red unit test** (C, D): `bun run test:ci` failed because `FakeStateStore` lacks `batchUpsertContacts`. Static reviewers (A, B, F, G) all missed this; only the runs that executed `bun test` (C, D) saw it. **Root cause: G has the same blind spot as A — no verification channel was exercised.** Note that this defect may already be resolved in the current commit; the static review cannot tell either way.
- **Duplicate `WA_STORE_BACKEND`** (D): D parsed `docker-compose.yml` line-by-line and noticed two `WA_STORE_BACKEND=` entries with conflicting defaults (sqlite vs json). G did not look at `docker-compose.yml` at all (it was within scope — brief §2c — but G prioritized the brief acceptance checklist surface).
- **Docker lockfile mismatch** (C, F): production Dockerfile copies `bun.lockb*` while the repo only has `bun.lock`; F additionally found `.dockerignore` excluded both. G did not mention this. This is the largest miss: it is a 🔴 BLOCKING defect (brief §4 #4 "docker build completes without error") and G should have caught it from a static read.
- **`docker:build` restore-on-failure risk** (E in ADR): if `prepare-release.sh` succeeds but `docker build` fails, `restore-dev.sh` is never run and the worktree stays swapped. G did not surface this.
- **Stale top-level `docker-compose.yml` / `docker:*` scripts pointing to legacy compose** (A): A caught this. G did not. Either the defect was fixed between A and G (likely, given subsequent docker work in commit history) or G missed it. Worth a separate read to confirm.

## What this says about v1

The G/A pair confirms v1's strengths and weaknesses are stable across reviewer commits:

**Strengths** (consistent across A and G):
- Spec adjudication is precise. G's 🔴 promotion on the harness pass-rate, and its read of the `legacyConsumerEntries` shape mismatch, are exactly the kind of finding the long protocol is designed to produce: literal brief language → severity, with citation discipline.
- `scope: partial` was emitted with a concrete reason in both A and G. The skill's scope-honesty discipline survives the protocol.
- Spec provenance worked. G correctly classified all referenced specs as `explicit` and applied 🔴 gating only where the brief permits it.

**Weaknesses** (confirmed):
- **Verifier subagent never ran.** G's `subagents: fallback-main-agent` repeats A and B. This is the single largest gap and the reason C/D/F catch defects v1 cannot. The skill *has* a verifier slot in plan L, but in practice the orchestrator collapses to main-agent and skips checks every time. v3 has to make execution-of-checks unconditional, not opt-in.
- **Static-only review misses concrete file-grounded breakage.** G missing the `bun.lockb` lockfile defect (a 4-line static read away) is the most damning data point: even when v1 is in the file with the brief loaded, if the orchestrator does not specifically target operational surfaces, they go unread.
- **Long protocol does not increase recall.** v1's 4 findings on a 487-file diff is comparable to A's 4 findings on the same target before fixes. The protocol's elaborate phases, handoffs, and budgets do not produce more findings — they produce more *paperwork around* findings.

## Implication for v3

G strengthens the v3 thesis stated earlier in this document:

1. The native review prompt finds high-quality defects (v1 G's 🔴 + the legacyConsumerEntries shape read are real wins) — keep this.
2. The procedural ceremony does not pay (G ran as fallback-main-agent and produced ~4 findings; the protocol added cost without adding signal) — drop it.
3. Verification execution is the single biggest delta (C and D caught the red unit test; A, B, F, G all missed it) — make it mandatory in v3, not a `verifier` slot the orchestrator can skip.
4. Operational-surface coverage is brittle in static reviewers (G missed the lockfile defect that F caught and C confirmed by execution) — v3 needs a deterministic operational scan in the packet, not a lane that may or may not look at the right files.

The v3 design proposed earlier — short native prompt + harness that runs declared checks before printing the packet + 3 lanes (verification, conformance, code-risk) + anti-suppression contract — addresses all four. Run G is one more datapoint in favor of that direction.