# Consistency & propagation

The disclosed branch of the **Consistency & propagation** theme in [`SKILL.md`](SKILL.md), reached when Boundary found another system reading or writing this database or a business process that changes state under more than one owner, or when Workload found contention. Rounds, routing, and the named-object rule work exactly as in `SKILL.md`; this file says what the theme asks and what each answer lands in the model.

Two leading words carry the theme:

- The **consistency boundary** is the set of rows one local transaction can change atomically: one database, one owner. Inside it an invariant is a constraint, trigger, or routine — enforced *now*. Across it no constraint can see, so the invariant becomes *eventual*: true after a process completes, carried by a table that records the process.
- A **dual write** is one business change written to two places with no shared transaction — commit the row, then publish the event; or call the other service, then commit. A crash between the two halves leaves one written and one lost, and no retry can tell which. Every pattern below exists to remove a dual write; one that removes none has no place in this model.

## First move: classify every invariant

Walk every rule the Invariants & lifecycle theme produced, plus every Boundary edge to another system, and mark each **local** or **cross-boundary**. A local rule keeps its constraint. A cross-boundary rule obeys the same named-object rule, but its object is the carrier — the outbox table, the inbox key, the saga state — and its test proves the carrier, never an impossible constraint. The classification is the frontier: each cross-boundary rule opens exactly one of the questions below, chosen by direction, never by the catalogue.

| Question the boundary raises | Pattern |
|---|---|
| This database owns a change another system must learn of | Transactional outbox; CDC as its transport or for replicas this system owns |
| This system calls another system's API and records the result | Intent first: commit the pending row, call with its id as idempotency key, reconcile what stays pending |
| Messages arrive here, and the transport redelivers | Idempotent consumer (inbox) |
| One business process changes state under several owners | Saga |
| Two writers race for the same row | Optimistic version |
| Many writers compete for one quantity in the same instant | Contested quantity |

## Transactional outbox — the change leaves

**Answers** the producer-side dual write. The event row is inserted in the *same* transaction as the state change, so both commit or neither does; a relay publishes committed rows afterwards. Delivery becomes at-least-once — which is why every consumer needs the inbox below.

**Lands in the model:** an `outbox` table — `message_id` (unique, the identity every consumer deduplicates on), `aggregate_type` + `aggregate_id` (the entity whose change it records), `event_type`, `event_version`, `payload`, `occurred_at`, `published_at`. `published_at` is a nullable column whose absence carries meaning — *pending* — so it is argued in Optionality, never defaulted silently. Where order matters, a per-aggregate sequence with `uq_outbox_aggregate_seq`. The rule that ties change to event names its writer: the routine or trigger that writes both (`usp_order_place`, `trg_order_outbox`); when the application writes both, the rule names the outbox table and the atomicity test that proves it.

**Opens these questions:**

- Which state changes are events? Each event type is a domain term — `OrderPlaced` lands in the glossary like any noun.
- Payload: *event-carried state* (consumers need no call back) or *notification + id* (consumers re-read, so they need a read contract)?
- Ordering scope: per aggregate, or none? Global ordering is rarely real and always expensive.
- Retention of published rows — a Temporality decision. The outbox is a delivery queue, the audit trail is a record: two jobs, two retention rules, two tables.

**Trap:** the payload is a public contract. Once consumers read it, its shape is versioned (`event_version`) independently of the source tables, so a refactor of the tables leaves the payload intact. Personal data inside a payload outlives any erasure the source honours — Temporality's erasure line covers it.

## Change Data Capture — the log is the transport

**Answers** propagation read from the database's own commit log (PostgreSQL logical replication, SQL Server CDC or Change Tracking, MySQL row-format binlog) instead of application code. Two legitimate uses: tailing the **outbox** table, the strongest relay, since it reads only committed rows in commit order; and replicating this system's **own** tables to stores it also owns (search index, cache, analytics). In brownfield it is often the only option — the legacy writer cannot be changed to write an outbox.

**Lands in the model:**

- A primary key on every captured table — the change stream keys on it. An adoption census row *no declared primary key* is a CDC blocker, sized.
- Delete semantics made explicit: a hard delete emits a key-only tombstone unless the full before-image is captured (`REPLICA IDENTITY FULL` and kin). If consumers must know *what* was deleted, choose here between before-image capture and soft delete — and soft delete reshapes every uniqueness rule in Identity (`uq_… WHERE deleted_at IS NULL`).
- A capture list, table by table, with the columns that must never leave (personal data, secrets) named.

**Opens these questions:** which tables are captured, and who consumes each stream; raw tables or outbox only; whether consumers need before-images; the engine prerequisites the canonical dialect demands (a Dialect & portability fact — look it up, never ask).

**Trap:** CDC on raw tables publishes the internal model. Every column rename becomes a breaking change for a consumer the team may not know exists. Default to outbox-tailing for anything that crosses a context; reserve raw-table capture for replicas inside the same owner.

## Idempotent consumer — the message arrives

**Answers** at-least-once delivery. Brokers redeliver, relays republish after a crash, webhooks retry — every consumer sees duplicates, and out-of-order arrival unless the transport guarantees otherwise. Effectively-once processing is at-least-once delivery plus an idempotent effect, and the database is where idempotency is cheapest to make airtight.

**Lands in the model**, one of three mechanisms per message stream — one mechanism per stream, never two:

- **Inbox** — a `processed_message` table: `consumer` + `message_id` under `uq_processed_message_consumer_id`, `processed_at`. The insert runs in the same transaction as the effect, so the unique violation *is* the deduplication.
- **Natural idempotency** — the effect is an upsert on a business key the message carries: `uq_payment_provider_ref`.
- **Version gate** — the entity stores `source_version`; an update applies only when the incoming version is higher, and the rule names the routine that holds that conditional update. The only one of the three that also absorbs out-of-order arrival.

**Opens these questions:** what identifies a message — the producer's `message_id` or the external provider's id, never the broker offset or a hash of the payload; deduplication scope (per consumer, per handler); inbox retention, at least the longest redelivery window the transport allows; whether order matters per entity. Inbound API commands carry the same shape: an `Idempotency-Key` table that also stores the response to replay.

**Trap:** the dedupe check living outside the effect's transaction — check-then-act races two deliveries through. Keying on the payload collapses two legitimately identical events into one.

## Saga — the process spans owners

**Answers** a business transaction that crosses consistency boundaries, where a distributed commit is unavailable or rejected. It becomes a sequence of local transactions, each with a **compensation** — a new business fact that semantically undoes the step (a refund, a release), never a delete. Consistency is eventual and isolation is gone: other readers *see* the intermediate states.

**Lands in the model:**

- **Intermediate states become domain states.** `pending_payment`, `cancelling`, `compensated` are closed-domain values in Invariants & lifecycle, glossary terms, with legal transitions — the *semantic lock* that tells every other reader the row is mid-process.
- **Orchestration** — a `saga` table owned by one context: `saga_id`, `saga_type`, `state` (closed domain, `ck_saga_state`), `current_step`, `correlation_id`, `expires_at` for the timeout, `last_error`; a `saga_step` history when Temporality asks for it. **Choreography** keeps no central table — the state is scattered across participants' statuses, and "where is this order?" has no single row to answer it. Past two or three steps, prefer orchestration; the choice earns an ADR.
- Each step consumes through the inbox and emits through the outbox — the patterns compose, they never compete.

**Opens these questions, step by step:** the compensation of each step; the **pivot** — the step after which compensation ends and only forward retry remains; what other readers may do with a row in each intermediate state; the timeout and what fires when it expires; which context owns the saga state.

**Trap:** missing isolation shows up as anomalies — a lost update when a user edits a row mid-saga, a decision made on a state later compensated. Answer each with a named countermeasure: the semantic lock state, a commutative update (increment, never overwrite), or the optimistic version below.

## Optimistic version — two writers, one row

**Answers** the lost update: two operators editing the same record, a saga step racing a user. A `row_version` column (or the engine's native type) checked on every update turns the silent overwrite into a detectable conflict. Per table, the decision is whether a lost update matters — when it does, the rule names the column and the conditional update.

## Contested quantity — many writers, one quantity

**Answers** a quantity many writers decrement in the same instant — stock in a flash sale, seats for an event, slots in a calendar, a budget drawn by concurrent requests. The invariant (never below zero, never sold twice) is the easy half; the representation decides whether the system survives the peak.

**The guarantee lives in a constraint; locking hints and isolation levels tune throughput.** The invariant is enforced by a named unique or check constraint, so it holds under every isolation level, every hint, and every writer — application, job, or manual script. A design where swapping a hint or an isolation level could oversell has its guarantee in the wrong place.

**Lands in the model** — the representation is the decision, chosen from Workload's contention facts (peak concurrent writers, quantity size):

| Representation | Fits | Cost |
|---|---|---|
| **Counter** — one row, a conditional decrement under `ck_<qty>_non_negative` | low simultaneous contention | every writer queues on one row |
| **Row per unit** — one row per sellable unit, claimed by a skip-locked read, guarded by a unique constraint on the active claim | high contention, small quantity | row count grows with the quantity |
| **Bounded pool** — unit rows only up to a cap sized to peak demand, refilled from the counter or ledger that remains the source of truth | high contention, large quantity | a replenishment routine, serialised so concurrent claims queue behind one refill instead of all refilling at once |

**A single-writer engine** (SQLite) serializes every write already: the counter with a conditional decrement is the representation, and the contention moves to the write lock — short write transactions opened with `BEGIN IMMEDIATE`, a busy timeout, WAL mode so readers never wait on the writer.

**Opens these questions:** the peak — how many writers in the same second, against what quantity; when the claim happens (on intent, at checkout, on payment) and how long it holds; how an expired claim returns to the pool; for a bounded pool, the cap and the refill trigger.

**Rules the routines carry:**

- **A read that feeds a decision reads committed data.** Dirty reads (`READ UNCOMMITTED`, `NOLOCK`) can return rows later rolled back, return a row twice, or miss rows entirely — tolerable for a display that may be slightly wrong, never for "is there stock? then claim it". Snapshot reads (MVCC, or the engine's read-committed-snapshot mode) give readers committed data without blocking writers.
- **A skip-locked claim locks what it reads.** The canonical dialect's skip-locked read — `FOR UPDATE SKIP LOCKED` where the engine has it, update-lock plus read-past plus row-lock hints where it does not — must take the row lock in the same statement; a read-past without a lock lets two sessions pick the same row, and escalation to page or table locks silently disables the skip. Look the mechanism up for the canonical dialect; record it in the routine's rule.
- **Fixed lock order.** A routine touching several tables touches them in one stated order (the unit before the claim, say); a fixed order removes the circular wait behind deadlocks.

**Trap:** the skip-locked read alone is not the guarantee. A session whose snapshot predates another's commit can still reach a just-claimed unit; the unique constraint on the active claim is what refuses it, and the routine retries the next unit or answers *sold out*.

## Brownfield signals

The adoption's excavation and census already hold this theme's evidence. A trigger copying rows into a `*_log` or `*_queue` table, a `processed` / `sent` flag column, a job polling `WHERE status = 'pending'` — each is a home-made outbox or inbox. Name it as a candidate, bring its census numbers (stuck rows, duplicate deliveries) into the trade-off, and let the user decide whether to formalise it or replace it. The adoption's answer to *who else reads or writes this database* is this theme's Boundary input: every external consumer there gets a direction and a pattern here, or a stated reason it needs none.

## Closing the theme

Closed when every invariant is marked local or cross-boundary; every cross-boundary one names its carrier object; every other system Boundary found has a direction and a pattern, or a written reason it needs none; every event type and every saga state is a glossary term; every contested quantity has its representation chosen against stated peak facts and its guarantee in a named constraint; and the outbox-vs-CDC, orchestration-vs-choreography, and contested-quantity representation choices each sit in an ADR.
