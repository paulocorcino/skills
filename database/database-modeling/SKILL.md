---
name: database-modeling
description: Grill the user through the database model, one decision at a time. Use when the user wants to model the database, resolve a modeling decision, or asks for DDL while gaps remain.
---

Interview me relentlessly about the database model until every theme below is resolved or explicitly out of scope. Fire a tracer through the themes in order: where `CONTEXT.md`, an ADR, the `dbkit/` docs, or the schema itself already answers, decide it yourself, record it, and announce it as established. Where nothing answers, you have found a **gap** — a decision only I can make. Put gaps to me one per turn, each with your recommended answer and its trade-off, and wait before the next.

A missing `CONTEXT.md` is a starting state, not a blocker — a brownfield adoption arrives here in exactly that state. The direction simply reverses: greenfield reads the glossary to shape the schema; brownfield reads the schema — plus the model doc's recorded gaps and the excavated code — to build the glossary, one resolved term at a time.

## The themes

Walk them in dependency order — dialect before collation, identity before uniqueness, history before any table it reshapes.

- **Dialect & portability** — canonical dialect and minimum version; secondary engines now or later; collation and folding (case, accents, whitespace); timezone and date-time storage
- **Boundary** — what domain concept one row represents; whose data it is (single organization or multi-tenant); what stays outside the model
- **Identity** — key strategy; natural keys and the scope of each uniqueness rule
- **Relations** — cardinality, ownership, and what deletion means at each edge
- **Optionality** — what is mandatory, and where absence itself carries domain meaning
- **Invariants & lifecycle** — rules that must always hold; legal state transitions and the fate of data they orphan
- **Workload** — read/write balance, and the queries the model must serve cheaply; both reshape the two themes below
- **Temporality** — current state only, or history and audit; retention
- **Derivation** — stored vs derived facts, and the single source each derives from
- **Master data** — reference records, who owns them, whether they can be removed while in use

Deliberately outside the tracer: indexes, partitioning, concurrency tuning, migration and backfill — physical design and transition planning follow the DDL; they enter through `/to-issues` or `/to-tickets` tickets, or through an ADR when a scale fact reshapes a table.

When my answer is vague, sharpen it against the glossary in `CONTEXT.md`; when I claim a relationship or invariant, stress it with a concrete scenario before accepting it.

## Routing

Route each resolved decision the moment it lands:

- a domain term → the glossary in `CONTEXT.md` (meaning only, no implementation)
- a concept, invariant, relation, or rule → its owning model file — `dbkit/model/database.md`, or its `dbkit/model/domains/` shard once promoted (growth contract in `dbkit/model/README.md`) — rules carrying prefixed IDs, each one testable
- hard to reverse **and** surprising without context **and** a real trade-off → an ADR in `docs/adr/`

The model is ready when every theme is routed or out of scope and I confirm shared understanding. Until then, DDL waits. On confirmation, offer `/to-issues` or `/to-tickets` — the populated `dbkit/model/database.md` is the spec it slices.
