# ADR-0003: Reviewer v3 — Refinement over Rules (Post Run H)

Status: proposed
Date: 2026-05-01
Builds on: ADR-0001-reviewer-v3-design.md, ADR-0002-reviewer-v3-coverage-hardening.md
Triggered by: Run H result against `baileys2api_bun feat/dev-setup`, recorded in `benchmark-matrix.md`

## Context

Run H validated ADR-0002's three hardenings (A1 audit fallback, A2 verifier
expectation, A3 scope auto-narrow) and exposed two new failure modes plus a
residual recall gap.

What worked in H:
- A1 — reviewer detected hook absent, ran `audit.py` manually, populated
  `audit:` and `audit_output:`.
- A3 — `narrowed-by-user-request: true` set; auto-narrow flag emitted.
- Findings quality improved over G: sharper NEW defects (legacyConsumerEntries
  shape mismatch, logger env-at-call, missing `depends_on`, media-thumbs
  absence, `prepare-release.sh` swap).

What did not work:
- **Failure mode 4 — glob hole.** Reviewer expanded `not-reviewed:` to glob
  patterns (`src/adapters/**`, `src/application/events/**`). Audit cannot
  enumerate vs `material_set` element-wise. 80 material files un-enumerated.
- **Failure mode 5 — A2 over-escape.** "Material side effects on the host"
  applied as a single class to typecheck, lint, and unit tests at once.
  Harmless checks were swept up with mutating ones.
- **Residual recall gap.** 5/7 matrix items still missed. Crucially, those
  five (`bun.lockb*`, `docker:build` restore-on-failure, duplicate
  `WA_STORE_BACKEND`, stale top-level `docker-compose.yml`, false-green
  `triggerInbound`/`triggerOutbound`) are **not reachable by running checks**.
  They are static reads of the operational surface. ADR-0002's A2 was
  designed to recover recall via execution; by construction it could never
  recover this subset.

Two diagnostic threads — both surfaced by the user — frame the response:

**Thread A: Each new procedural rule produces a new shortcut.**
A2's "(b) infeasible" escape produced class-bundling. A3's flag-only
enforcement produced glob expansion. The pattern is consistent: structural
rules invite structural workarounds. Adding a fourth rule to plug the
glob hole and a fifth to plug the class-bundling escape would continue the
spiral.

**Thread B: The skill's prompt should carry diagnosis, not arithmetic.**
Counts, percentages, and cardinality belong in the harness (`audit.py`
reading the report). Asking the LLM to compute or enumerate quantitatively
spends prompt tokens on bookkeeping that the model is bad at and that the
harness can do deterministically.

This ADR refines rather than adds. Two of the three moves are subtractive
or redistributive; one is a new capability (Scout) constrained tightly by
input contract.

## Decision

### B1. Soul reinforcement; remove A2 procedural prose

Remove the "Verifier rule" block from SKILL.md (the `(a) invoke verifier ...
OR (b) record under not exercised:` prose introduced by ADR-0002 A2).

Add to the Soul a single line carrying what A2's prose carried:

> *"Reading without running, when running would answer the question, is
> a form of narrowing I do not accept in myself."*

Rationale: the project rule against over-engineering and the user's
explicit signal ("menos regra procedural no prompt, mais voz") both push
in this direction. The bet is that voice in the Soul matches or exceeds
the procedural rule's effect on LLM judgment, without producing
shortcut-seeking behavior in isolated context.

Honest cost: if Run I shows the reviewer again declaring `review is
read-only` and emitting without checks, voice is insufficient for this
failure mode. The fallback then is not to re-add A2 prose — it is to
accept the gap and document it, or to express the intent as a format
defect that `audit.py` can detect (e.g. `not exercised:` empty AND
diff modifies declared check commands → audit signals a gap).

### B2. Format defects replace structural rules

Two mechanical format constraints, enforced by `audit.py`, replace the
glob hole and the class-bundling escape. The LLM does no counting; the
harness does.

**Format defect F1 — `not-reviewed:` accepts no globs.**
Allowed forms in `## Coverage / not-reviewed:`:

- Enumerated paths (one path per line), OR
- `category: <path-prefix> (<reason>)` — a path prefix without glob syntax
  and without a count.

Glob patterns (`**`, `*` wildcards) are a format defect. `audit.py`
cross-references each `category:` prefix against `material_set` and
reports the cardinality itself — the reviewer never writes a number.

**Format defect F2 — `not exercised:` is one line per command.**
Each entry names a single command and a single concrete blocker:

```
not exercised:
  - bun run test:contract — requires NATS broker not present in sandbox
  - docker build — requires network access to ghcr.io for base image
```

Bundling multiple checks under one shared reason ("typecheck, lint, unit:
infeasible due to side effects") is a format defect. The blocker must
be specific to the command.

Rationale: both replace behavioral expectations with mechanical format
checks. The LLM is not asked to internalize a new rule; it just emits in
the required shape, and the harness flags deviations. Quantitative
cross-checks (cardinality, prefix containment) are harness work, not
prompt work.

### B3. Scout subagent — operational residue inventory

A new subagent capability addresses the residual recall gap (static
operational surface). It is invokable on judgment, like the existing
three. It does not gate emission.

**Soul:**
> *"I do not find defects. I name what the reviewer has not yet looked at
> that the change might touch. I assume the reviewer is competent on the
> slice they read; my job is the residual. Severity is not mine to assign
> — if something screams, I write 'investigate'; the reviewer does the
> read."*

**Input contract.** The main reviewer hands Scout four things. Without
(3) Scout collapses into a shallow defect-hunter; with (3) it does the
work the user asked for ("amplo dado o contexto correto, ignorando o
visto").

1. Diff target — file paths and base ref.
2. Change theme — one or two sentences naming the intent of the branch.
3. **Read-set so far** — files the reviewer has opened, greps run,
   commands executed.
4. Spec pointers — brief, ADRs, kickoff prompts when present.

**Output shape.** Strictly inventory. No severity. No claim of defect.

```
operational-residue:
  compose:
    - <path> — <one-line adjacency to the change>
  docker:
    - <path> — <one-line adjacency>
  scripts:
    - <path> — <one-line adjacency>
  ci:
    - <path> — <one-line adjacency>
  env-config:
    - <path> — <one-line adjacency>
  lockfiles:
    - <path> — <one-line note, e.g. naming variant present>
investigate:
  - <one-line suspicious adjacency the reviewer should resolve>
```

**When to invoke (guidance, not rule).** Late in the review, after the
first pass — when read-set has content. Strong signals: the change
touches infra/build/release/CI, or the brief names operational surface.

**Coupling with audit.** Scout output is informational. Anything Scout
lists either becomes part of the reviewer's read-set, or lands in
`not-reviewed` / `category:` — where `audit.py` already sees it via F1.
No new structural lock; the existing audit + the new format defects
carry enforcement.

**`## Notes` `invoked:` line gains scout count**, e.g.
`invoked: verifier (2), defect-hunter (0), test-auditor (0), scout (1)`.

### B4. Quantitative work stays in the harness

A standing principle, enforced by self-review of any future ADR text:
the SKILL prompt does not ask the LLM to count, compute percentages,
sum cardinalities, or compare numerical thresholds. The reviewer writes
qualitative diagnosis. `audit.py` reads the markdown and produces
quantitative facts in `audit_output:`.

This ADR applies the principle to F1 (`category:` without `=N`) and to
F2 (no count of side-effect classes). Future hardenings should be
audited against this principle before entering the SKILL.

## What this ADR explicitly does NOT do

- Does not add a Scout invocation rule. Judgment-based, like the other three.
- Does not add severity to Scout. Inventory-only by design.
- Does not re-add A2 procedural prose under another name.
- Does not replace ADR-0002's A1 (audit fallback) or A3 (auto-narrow flag).
  Those remain — they are observable, mechanical, and not behavioral rules.
- Does not introduce per-stack check lists, file-count fan-out, or forced
  re-review. ADR-0001 D1/D2 stances preserved.

## Validation Plan — Run I

Re-run the same target (`baileys2api_bun feat/dev-setup`) under the
refined design. Acceptance criteria inherit ADR-0001 and ADR-0002, plus:

- **B1 evidence**: SKILL.md no longer contains the A2 procedural block;
  Soul carries the new line. The reviewer either runs declared checks
  or records concrete per-command blockers under `not exercised:`.
  `review is read-only` as a standalone reason no longer appears.
- **B2 evidence**: `not-reviewed:` contains no glob syntax. If
  `category:` prefixes are used, `audit.py` reports cardinality vs
  `material_set` mechanically. `not exercised:` has one line per
  command, each with a specific blocker.
- **B3 evidence**: when Scout is invoked, its output's `operational-residue`
  inventory either becomes part of read-set in subsequent reviewer reads,
  or appears under `## Coverage / not-reviewed`. The `invoked:` line in
  `## Notes` carries a scout count.
- **Recall expectation**: the five static-read matrix misses (`bun.lockb*`,
  `docker:build` restore-on-failure, duplicate `WA_STORE_BACKEND`, stale
  top-level compose, false-green `triggerInbound`/`triggerOutbound`)
  recover via Scout's residue surfacing. Hypothesis: each was an
  unread-file problem, not a reasoning problem.

If Run I still misses the static-read items, Scout's input contract
(read-set delivery) is the prime suspect. Open ADR-0004 to redesign the
read-set production mechanism (e.g. reviewer-side ledger, harness-emitted
read-set, etc.) rather than to weaken Scout's soul.

## Consequences

Positive:
- Procedural rule count goes down: A2 prose removed, no new behavioral
  rule added in its place. Net reduction in "cadeados".
- Format defects (F1, F2) move enforcement to the harness, where it
  belongs. The LLM is not asked to be a number-checker.
- Scout addresses the recall gap that A2 by construction could not.
- The "quantitative work belongs to the harness" principle is now an
  explicit standing rule for future ADRs.

Negative:
- Removing A2 prose is a real bet on Soul reinforcement. If voice is
  insufficient, the failure mode reappears.
- Scout adds a fourth subagent file. Surface area grows by one capability.
  Justification: single-soul subagents are a load-bearing design property
  of v3; folding Scout into defect-hunter dilutes both.
- F1's path-prefix form does not cover semantic categories not aligned
  with directories. Reviewer must split into multiple prefix lines or
  enumerate. Verbose but honest.

Risks:
- The reviewer may invoke Scout but ignore its output (drop everything
  into `not-reviewed`). Mitigation: F1 cross-reference makes the dropped
  set visible; A3 ceiling caps the verdict; the verdict ceiling is the
  only enforcement, by design.
- Soul reinforcement (B1) may pattern-match weakly in some sessions. No
  structural backstop is added — that is the trade-off being chosen.

## Open Questions

- Should Scout's output template be a literal subsection in the final
  report (e.g. `## Operational Residue`), or stay in the subagent
  scratch and only manifest via the reviewer's read-set updates?
  Current proposal: subagent scratch only. The final report stays
  findings-first; Scout's value is upstream of the report.
- Should `audit.py` distinguish `category:` prefix mismatches (prefix
  declared, but `material_set` has zero files under it) as a separate
  format defect class? Current proposal: yes, as a `category-empty`
  signal in `audit_output:`. Defer implementation detail to commit.
- If Run I shows that read-set production by the reviewer is unreliable
  (Scout receives stale or incomplete read-set), should the harness
  produce read-set from tool-call traces? Defer to ADR-0004 if observed.

## Definition of Done

ADR-0003 is satisfied when:

- SKILL.md removes the Verifier rule procedural block (A2 prose).
- SKILL.md Soul gains the line on "reading without running".
- SKILL.md Coverage section description forbids glob syntax in
  `not-reviewed:` and admits `category: <path-prefix> (<reason>)`.
- SKILL.md `not exercised:` description requires one line per command
  with a per-command blocker.
- `subagents/scout.md` is created with the Soul, input contract, and
  output shape from B3.
- `templates/final_report.md` `invoked:` line includes scout.
- `scripts/audit.py` cross-references `category:` prefixes against
  `material_set`, rejects glob syntax in `not-reviewed:`, and rejects
  class-bundled `not exercised:` entries.
- Run I is executed against the same target and recorded in
  `benchmark-matrix.md` as the next row.
- If Run I passes recall + precision + format, v3 is promotable per
  ADR-0001 D1.
- If Run I still fails recall on static-read items, open ADR-0004
  scoped to read-set production for Scout.
