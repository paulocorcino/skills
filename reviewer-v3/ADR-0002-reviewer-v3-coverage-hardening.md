# ADR-0002: Reviewer v3 — Coverage Expectation Hardening (Post Run G)

Status: proposed
Date: 2026-05-01
Builds on: ADR-0001-reviewer-v3-design.md (Stop-hook variant)
Triggered by: Run G result against `baileys2api_bun feat/dev-setup`

## Context

Run G was the first end-to-end exercise of reviewer-v3 against the
`baileys2api_bun feat/dev-setup` benchmark target defined in
`reviewer-v2/ADR-0001-reviewer-v2-benchmark.md`. Result against ADR-0001's
acceptance criteria:

| Dimension | Aceite | Run G | Result |
|---|---|---|---|
| Recall — red `bun run test:unit` | catch | not run | ❌ |
| Recall — false-green `triggerInbound`/`triggerOutbound` | catch | missed | ❌ |
| Recall — `bun.lockb*` vs `bun.lock` | catch | missed | ❌ |
| Recall — `docker:build` restore-on-failure | catch | missed | ❌ |
| Recall — duplicate `WA_STORE_BACKEND` | catch | missed | ❌ |
| Recall — stale top-level compose/script drift | catch | missed | ❌ |
| Recall — `$GH_TOKEN_PKG` vs `${GH_TOKEN_PKG}` | catch | LOW | ✓ |
| Precision — `SESSION_DIR` | OPEN_QUESTION | INFO + Open Question | ✓ |
| Precision — credential leakage speculation | avoid | avoided | ✓ |
| Format — Notes praise-free | required | clean | ✓ |
| Format — `audit:` field present and consistent | required | absent | ❌ |
| Format — `not exercised:` line present | required | present | ✓ |

Recall ≈ 14% (1/7). The pattern matches Run B (v1 after experimental tweaks):
"softened concrete build risk, missed stale compose/script drift, did not
execute checks". This is precisely the regression v3 was designed to avoid.

Three concrete failure modes drove the result. Each maps to a soft spot in
ADR-0001 that this ADR hardens.

### Failure mode 1 — Audit did not fire
Run G's closing note: *"The Stop-hook for the reviewer-v3 audit safety net
was not installed during this session (permission to write
~/.claude/settings.json was offered but I did not wait for confirmation
before producing this report). The audit will not fire automatically; if you
want the coverage cross-check, install the hook and re-run."*

The Stop-hook design (D6 in ADR-0001 modified variant) made the audit
opt-in per session. When the hook is missing, audit silently does not
fire. The LLM noticed and proceeded anyway. There is no fallback path.

### Failure mode 2 — Verifier was not invoked
The reviewer chose explicitly not to run any check: *"review is read-only
against an already-staged branch"*. The verifier subagent — whose soul is
"turn suspicion into executable facts" — never entered the picture. Without
a stronger nudge, "subagents-as-capabilities" degenerated into "subagents
never used".

Every recall miss in Run G except `$GH_TOKEN_PKG` would have been caught
by simply running `bun run test:unit`, `bun run test:contract`, and
inspecting docker/compose/script artifacts that the brief explicitly
named. The verifier soul was the right design; it just was not activated.

### Failure mode 3 — Scope auto-narrowed
The reviewer wrote `scope: partial(mandate is the dev-setup brief acceptance
checklist; not a full audit of the 487-file / +42k-line branch diff)` and
moved 487 files to `not-reviewed (out of scope)`. This is technically valid
under D5/F: any `not-reviewed` entry with a reason satisfies the rule.
But "out of scope" is exactly the focused-pass degradation that turned
Run B into a regression against Run A. The Coverage rule has no teeth
against a reviewer who decides the scope is smaller than the user implied.

## Decision

Three adjustments to ADR-0001. None add procedure. Each makes an existing
expectation observable in the output, so silent omission becomes a format
defect instead of a judgment call.

### A1. Audit fallback when Stop hook is not active

The Stop-hook design stays as the **preferred path**. But it is no longer
the only path. Hardening:

- The SKILL prompt instructs the main reviewer to **detect whether the
  Stop hook is active** before emitting the report. Detection is a single
  read of `.claude/settings.json` (or the equivalent settings location)
  for a hook entry that references `stop_audit.py`.
- If the hook is **not active**: the main reviewer must run
  `scripts/fact_pack.py` followed by `scripts/audit.py` manually, with
  the draft Coverage block as `audit.py`'s `--coverage` input, before
  the final report leaves its hands. The literal audit output goes into
  the required `audit_output:` trailer.
- The required `audit:` field stays in the template. Its value comes from
  the hook (when active) or from the manual invocation (when not).
  Emitting the report without `audit:` populated remains a format defect.
- The SKILL prompt explicitly forbids the pattern Run G used: emitting the
  report with `audit: not run (hook not installed)`. Either the hook
  fires, or the LLM runs the script. There is no third option.

This restores the project-self-contained property the original ADR-0001
D6 had, while keeping the Stop-hook ergonomics the modified D6 brought.

### A2. Verifier expectation when checks would answer the request

Subagents stay LLM-invokable on judgment. The change is to one specific
case where omission was clearly wrong in Run G.

The SKILL adds this rule (no threshold, single trigger condition,
single allowed escape):

> **When the diff modifies declared check commands (test scripts, build
> scripts, CI config, dockerfiles, compose files) OR when the user's
> request implies validation against acceptance criteria, you must either:**
>
> **(a) invoke the `verifier` subagent (or run the relevant declared
> checks yourself) and include their output in `## Verification`, OR**
>
> **(b) record under `not exercised:` the concrete reason running was
> infeasible — missing credentials, prohibited side effect, undeclared
> command, sandboxed environment without network, etc.**
>
> **"Out of scope" and "review is read-only" are not sufficient reasons.
> If the checks would directly answer the request and you have access
> to run them, run them.**

This is the smallest possible nudge that turns Run G's failure into a
visible omission. The LLM still decides *which* checks. It just can no
longer silently decide *no* checks when checks would answer the question.

### A3. Scope auto-narrowing detection

The audit script gains one extra check.

If the LLM's `## Coverage` declares `not-reviewed` covering more than
**40% of `material_set`** OR more than **30 files**, audit signals
`scope-auto-narrowed` and surfaces a provocation:

> *"You declared <N>/<M> material files as not-reviewed with reason
> '<reason>'. If the user explicitly requested a narrowed scope (e.g.
> 'check only the brief acceptance criteria'), confirm by adding
> `narrowed-by-user-request: true` to your Coverage block. Otherwise,
> consider widening coverage or splitting `not-reviewed` reasons by
> file group."*

The provocation is informational; it does not block emission. But the
LLM must add the `narrowed-by-user-request: true` flag (when applicable)
or split the `not-reviewed` reasons into more specific groups. The flag
documents the decision; the splitting forces the LLM to be honest about
what was actually skipped (oversized vs out-of-expertise vs
narrowed-by-request).

Audit output trailer gains a corresponding line:

```
scope-auto-narrowed: yes (487/494 files; reason: out of scope)
       — narrowed-by-user-request: true|false|unspecified
```

When `narrowed-by-user-request: false` or `unspecified` and the
auto-narrow threshold is hit, the verdict is forced to
`APPROVED-WITH-FIXES` at strongest, never plain `APPROVED`. (Verdict
ceiling, not floor — the reviewer can still issue BLOCKED if findings
warrant.)

## What this ADR explicitly does NOT do

To stay aligned with the project rule against over-engineering, this ADR
deliberately rejects:

- Adding a list of mandatory checks per stack (would be target-specific).
- Auto-spawning subagents at file-count thresholds (was abolished in
  ADR-0001 D2; not reintroducing).
- Forcing re-review when the LLM already declined once (still a
  provocation, never a force; ADR-0001 stance preserved).
- Adding more `## Notes` rules. The structural placeholder from D8
  is doing its job (Run G's Notes were clean).
- Replacing `severity_signal` advisory with hard subagent verdicts
  (ADR-0001 D7 single-locus calibration preserved).

The hardening is targeted at the three observed failure modes only.

## Validation Plan — Run H

Re-run the same target under the hardened design. Acceptance criteria
inherit ADR-0001 plus:

- **A1 evidence**: the report's `audit:` field is populated either by
  hook output or by manual `fact_pack.py` + `audit.py` invocation. Never `not run`.
- **A2 evidence**: at least the declared `bun run test:unit` and
  `bun run test:contract` are exercised (verifier or main), OR the
  `not exercised:` line names the concrete blocker for each.
- **A3 evidence**: if the reviewer narrows scope, the Coverage block
  contains `narrowed-by-user-request: true` and the audit trailer
  acknowledges it; otherwise coverage is broad or auto-narrow detection
  fires.

Recall expectations from ADR-0001 are unchanged. The hypothesis is that
A1+A2 alone recover most of the missed recall, because each missed item
in Run G was reachable via an executed check or via reading an operational
file the brief named.

If Run H still misses items not reachable by checks (e.g. stale
`docker-compose.yml` drift, which is a static read), that points at a
fourth failure mode this ADR did not address — surface it for ADR-0003.

## Consequences

Positive:

- Audit is no longer opt-in per session.
- "Don't run any checks" is no longer a silent option.
- Auto-narrowing is observable and bounded.
- All three changes are in the SKILL prompt + audit script — no harness
  expansion, no new subagents, no per-stack rules.

Negative:

- A1 adds one filesystem read (settings.json) and possibly one bash call
  per session. Negligible.
- A2 may push the LLM toward false positives if checks fail for
  environmental reasons unrelated to the diff. Mitigation: the rule
  permits documenting under `not exercised:` with a concrete blocker.
- A3 thresholds (40% / 30 files) are guesses. May need tuning after
  Run H if false-trigger rate is high.

Risks:

- The LLM may game A2 by writing dismissive `not exercised:` reasons
  ("would take too long", "not requested"). This is the same failure
  mode as Coverage `not-reviewed` abuse and has no purely structural
  remedy — relies on the soul of the verifier in the SKILL prompt.
- Manual audit invocation in A1 depends on the LLM remembering to do it
  when the hook is absent. If Run H shows this still fails, the next
  iteration may need a hard requirement that the SKILL refuses to
  proceed without a populated `audit:` field — but that is a step
  toward the "too rigid" end the user explicitly wants to avoid.

## Open Questions

- Should the audit script (A3) refuse to emit `pass` when
  `scope-auto-narrowed: yes` and `narrowed-by-user-request:
  unspecified`? Current proposal: no, it emits with the trailer; the
  verdict ceiling is the only enforcement. Revisit after Run H.
- Should A2 list specific check classes that *count* (typecheck, lint,
  unit, contract, integration, build) versus those that don't (e.g. e2e
  in environments without infra)? Current proposal: no canonical list
  — keep the rule generic, let the LLM judge. Revisit if Run H shows
  the LLM running cosmetic checks (e.g. format-check) and skipping the
  ones that would catch defects.
- Whether to add a per-subagent invocation count to `## Notes`
  (`invoked: verifier (3 commands), defect-hunter (0)`) for cost and
  behavior tracking. Current proposal: yes, deferred to implementation,
  not a separate ADR.

## Definition of Done

ADR-0002 is satisfied when:

- SKILL.md contains the A1, A2, A3 rules verbatim.
- `audit.py` implements the auto-narrow detection and emits the
  `scope-auto-narrowed:` trailer.
- Final report template's `audit:` field is enforced as a format defect
  on absence (already in ADR-0001 D8 default; reaffirmed here).
- Run H is executed against the same target and recorded in the
  benchmark matrix as the next row, with explicit comparison against
  ADR-0001 + ADR-0002 acceptance.
- If Run H passes recall + precision + format, v3 is promotable per
  ADR-0001 D1.
- If Run H still fails recall on items reachable by static reading
  (not by checks), open ADR-0003 to address the static-coverage gap
  separately.
