# Reviewer V2 Benchmark Matrix

This is a living comparison artifact for `reviewer-v2` benchmark runs. The ADR
records the design decision; this matrix tracks observed review performance over
time.

## Baseline Runs

| Run | Reviewer Style | Verdict | High-Confidence Findings Caught | Important Misses | False Positives / Overreach | Checks Executed |
|---|---|---:|---|---|---|---|
| A | reviewer v1 before changes | APPROVED-WITH-FIXES | Contract removed `legacy`; stale compose/script drift; weak contract hook; prod Docker uncertainty | Did not catch red declared tests or executable failures | Limited | Not executed |
| B | reviewer v1 after experimental changes | APPROVED-WITH-FIXES | `legacy` removal; fixture shape mismatch; hardcoded compose mount | Missed stale compose/script drift; softened concrete build risk | "Strong points"; concrete issues downgraded too far | Not executed |
| C | native Codex review | effectively BLOCKED | Red contract/unit checks; skipped-heavy integration; Docker/release breakage; swallowed startup failure | Missed stale compose/script drift and some spec/operational exactness | `SESSION_DIR` treated too strongly despite derivation evidence | Unit, contract, integration/build-oriented checks |
| D | Claude Code native review | Medium risk | Duplicate compose env; `$GH_TOKEN_PKG` syntax drift; outbound/inbound hook mismatch; Dockerfile/manifest drift | Did not execute docker/contract/integration checks | `SESSION_DIR` remained unresolved too prominently | Limited or not executed |
| E | reviewer-v2 initial | BLOCKED | Unit failure; false-green contract hooks; Docker lockfile mismatch; release restore risk; operational drift; weak integration tests | Overproduced some medium/low operational concerns | Some speculative findings over-severe; positive notes leaked into report | Unit and targeted verification evidence |
| F | reviewer-v2 calibrated | BLOCKED | Red unit/CI chain; missing `legacy` arg; `$GH_TOKEN_PKG` syntax drift; dirty/unpushed tree state; `SESSION_DIR` moved to open question | Missed false-green contract hooks as findings; missed Docker/release lockfile and restore risks; missed duplicate compose env; missed stale compose/script drift | Became too conservative; still includes positive notes; under-reports operational/test-confidence evidence | Typecheck, unit, compose config, fixture/baseline checks |

## Calibration Targets

Reviewer-v2 is benchmark-ready when it:

- Reproduces high-confidence findings from C/D/E.
- Catches A's stale compose/script drift.
- Avoids B's focused-pass degradation and positive-summary output.
- Does not report `SESSION_DIR` as an automatic finding when derivation from
  `DATA_DIR` is documented or required to be verified.
- Distinguishes proven findings from `OPEN_QUESTION`.
- Does not suppress high-confidence false-green or Docker/release findings while
  calibrating away speculative operational risks.
- Records executed and skipped checks with concrete reasons.

## Future Run Template

| Run | Reviewer Style | Verdict | High-Confidence Findings Caught | Important Misses | False Positives / Overreach | Checks Executed |
|---|---|---:|---|---|---|---|
| G | reviewer-v2 recall+precision calibration | TBD | TBD | TBD | TBD | TBD |

## Per-Finding Tracking Template

| Finding | Expected Classification | A | B | C | D | E | Latest reviewer-v2 | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Red declared test/check | HIGH | missed | missed | caught | caught | caught | caught | Blocking when command is declared and feasible |
| False-green contract hook | HIGH | caught | missed | caught | caught | caught | missed | Blocking when it hides required behavior |
| Docker/release breakage | HIGH/MEDIUM | partial | softened | caught | partial | caught | missed | Severity depends on proof of command path |
| Stale compose/script drift | MEDIUM | caught | missed | missed | caught | caught | missed | Operational drift with deploy/dev impact |
| Exact token syntax drift | LOW/MEDIUM | missed | missed | missed | caught | not prominent | caught | Spec-exact issue; severity depends on functional risk |
| `SESSION_DIR` omission with documented derivation | OPEN_QUESTION or no finding | n/a | n/a | overreach | overreach | overreach | open question | Not automatic when `DATA_DIR` controls it |
| Runtime credential leakage via image copy | OPEN_QUESTION/MEDIUM unless proven | n/a | n/a | n/a | n/a | overreach risk | avoided | Requires Dockerfile, `.dockerignore`, and variable-flow proof |
| Positive notes / praise leakage | none allowed | clean | leaked | clean | leaked summary | leaked | still leaked lightly | Notes must not contain positives |
