# State machine

The disclosed branch of the **Invariants & lifecycle** theme in [`SKILL.md`](SKILL.md), reached when a concept carries a status — any closed domain whose value changes over the row's life. Rounds, routing, and the named-object rule work exactly as in `SKILL.md`; this file says what the theme asks of each status and what each answer lands in the model.

A **state machine** is the closed set of states plus the transitions between them. The set is the easy half — a check constraint, lookup table, or native enum holds it. The transitions are the half a check constraint cannot see: it reads the row as it is now, never the value it came from.

## What each state machine asks

- **States** — every value a glossary term; the initial state, and the **terminal** states no transition leaves.
- **Transitions** — every legal pair *from → to*, and what fires it: a user action, a job, an inbound message, a saga step. The list is closed like the states: a pair absent from it is refused.
- **State-dependent columns** — what each state makes mandatory or empty in the row: `shipped_at` present in `shipped`, `cancel_reason` present only in `cancelled`. One check constraint across the state and its columns (`ck_order_shipped_has_date`) holds it declaratively on every engine.
- **Frozen rows** — whether a terminal state freezes the row against further edits, and the fate of data a transition orphans.
- **The path** — whether past transitions are history; Temporality decides, and a kept history is the state-change table below.

## Enforcing the transitions

| Object | Role |
|---|---|
| **Transition table** `<entity>_transition (from_state, to_state)` | The legal pairs as data — the single source every enforcement reads, and the application can read too |
| **Trigger** `trg_<entity>_transition` | Compares the old and new state against the transition table on every update; holds under every writer — application, job, manual script. The default |
| **Routine as the only write path** `usp_<entity>_transition` | Holds only while grants deny direct updates of the state column — the rule names the grant beside the routine |
| **State-change history** `<entity>_state_change` | When Temporality keeps the path: a composite foreign key `(from_state, to_state)` to the transition table, so no illegal pair is ever recorded |

The rule names the transition table and the enforcing object together; its test in `db-schema/tests/` tries every forbidden pair and expects each refused.

## One source with the application

The application often encodes the same machine — an enum, a State pattern class per state, a workflow library. Two encodings drift apart silently, so one is the source and the other is derived from it or compared to it by a test:

- **The database is the source** — the transition table; the application reads it, or a test compares the application's list against it.
- **The application is the source** — the database holds only the state set, and no guard refuses an illegal transition from a manual script or a job. That gap is a trade-off, so it lands in an ADR.

In brownfield, the adoption's excavation records state machines living only in the application. Each opens this file's questions, carrying the census numbers into the trade-off: rows in a state the application's list does not know, rows whose columns contradict their state.

## Closing a state machine

Closed when every state and terminal state is a glossary term; every legal transition is listed with what fires it; every state-dependent column has its check constraint named; the enforcing object and its test are named; and the source — database or application — is chosen, with an ADR when it is the application.
