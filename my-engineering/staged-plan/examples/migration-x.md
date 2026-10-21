# Example — Migration X (the parts the planner writes)

What the cognitive parts of a small migration plan look like once filled. Everything else — Execution model, policy, hand-off conventions, Stage 0, the hand-off prompts, the reviewer gate — comes verbatim from `lib/scaffold.py` and is omitted here.

```
## Context
Module Y parses dates through lib A, which is unmaintained and mis-handles
offsets. Migrate Y to lib B. 7 files, 3 public callsites (grep: `parseDate(`).
Out of scope: the reporting module's own date formatting (separate backlog item).

## Swept (requirements the source did not state)
- validation: C1.2
- failure modes: C1.3 — malformed input raises `DateParseError`, as lib A did
- idempotency / retry: not in scope — parsing is pure
- authorization: not in scope — no access path changes
- concurrency / ordering: not in scope — no shared state
- data lifecycle: not in scope — nothing persisted
- external-dependency failure: not in scope — lib B is bundled, no I/O
- state transitions: not in scope — no state machine involved
- observability: existing: parse failures already logged by the caller's error boundary

## One-way doors
| Door | Literal shape | Alternative rejected |
|---|---|---|
| New dependency lib B | `lib-b@^4`, imported only inside `src/y_v2.ts` | lib C — no offset-aware parsing without a plugin |

## Stage 1 - Add B-backed implementation alongside A
**Tier:** standard   **Effort:** standard
**Tier rationale:** new file following an existing interface; light judgment on error mapping.
**Size:** ~9k tokens
**Depends on:** none
**Files:**
- `src/y_v2.ts` (new) - lib-B-backed `parseDate`, same signature as `src/y.ts`
- `src/y_v2.test.ts` (new) - proofs for C1.x
- `package.json` - add `lib-b`
**Order of operations:**
1. Write `src/y_v2.test.ts` from the checks; run it, see it fail (module missing).
2. Add `lib-b`; implement `src/y_v2.ts` until the proofs pass.
**Checks:**
- C1.1 — `parseDate("2024-03-01T10:00:00+02:00")` returns 08:00 UTC · Proof: `bun test src/y_v2.test.ts -t "parses ISO dates with offset"`
- C1.2 — `parseDate("")` throws `DateParseError` · Proof: `bun test src/y_v2.test.ts -t "rejects empty input"`
- C1.3 — `parseDate("31/02/2024")` throws `DateParseError` · Proof: `bun test src/y_v2.test.ts -t "rejects impossible dates"`
Verify script: docs/plans/migration-x-verify-stage-1.py

## Stage 2 - Port callsites
**Tier:** mechanical   **Effort:** minimal
**Tier rationale:** import swap at 3 listed callsites; no decisions.
**Size:** ~14k tokens
**Depends on:** Stage 1
**Files:** `src/caller1.ts`, `src/caller2.ts`, `src/caller3.ts`
**Checks:**
- C2.1 — none of the 3 callers imports `./y` any more · Proof: `V.assert_grep_zero(r"from ['\"]\./y['\"]", ["src/caller1.ts", "src/caller2.ts", "src/caller3.ts"])`

## Stage 3 - Remove A-backed implementation
**Tier:** mechanical   **Effort:** minimal
**Tier rationale:** deletion plus dependency removal; the grep proves completeness.
**Size:** ~3k tokens
**Depends on:** Stage 2
**Files:** `src/y.ts` (delete), `package.json` (drop `lib-a`)
**Checks:**
- C3.1 — no reference to `lib-a` remains under `src/` or in `package.json` · Proof: `V.assert_grep_zero(r"lib-a", ["src/", "package.json"])`
```
