# Design debt

The disclosed branch of step 3 in [`SKILL.md`](SKILL.md). Once every costly statement is traced, **follow the cost upward**: go from the statements to the **access patterns** they share, and from each pattern to the model decision or contract that explains it. A statement card fixes one query. A design-debt card names the decision that keeps producing costly queries, and routes it to whoever owns that decision.

The branch is strongest on the live branch. With only the static branch, every weight below is structural, so every design-debt card is speculative.

## 1. The co-access map

Widen step 2's set of costly statements until it covers at least 80% of the window's CPU and of its reads. Parse each normalized statement with the kit's `sqlglot` in the engine's dialect, and extract the tables it reads, the tables it writes, and every join edge with its join columns. Weight each table and each edge by the CPU, the reads, and the executions of the statements that touch it. A statement nested in a routine counts once nested tracking is on (`COST-SOURCES.md`); until then, parse the routine's body from the carved DDL and mark those weights structural. Write the map to `.scratch/audit/coaccess.json`.

Done when every statement in the 80% set is parsed, or listed as unparsed with the parser's error, and every table it touches has a read weight and a write weight.

## 2. Operation fan-out

Count the statements each business operation issues: a request, a screen, a job step. The counts come from query tags, the ORM's query log, or a test that counts statements per call. For each hot operation, record its statement count and the tables it touches. Where no source exists, record the gap; query tags (step 3) close it next time.

Done when every hot operation has its count, or the gap is recorded.

## 3. Structural signals

Read these from the catalog or the carved DDL. When the adoption's `discover` output exists, reuse it.

- **one-to-one pairs**: a foreign key from primary key to primary key, or a unique foreign key
- **column overlap**: two tables sharing column names and types beyond their keys and audit columns
- **sparse groups**: nullable columns that are null together, gated by a type or status column
- **key–value shapes**: an entity id, an attribute name, and a value column
- **document columns in predicates**: a JSON or XML field filtered or joined on
- **one concept, two names**: tables whose rows mean the same thing (the glossary settles it when one exists)

## 4. Match the patterns

Each pattern needs a structural signal **and** a workload signal. One of the two alone is a lead: record it Low and speculative.

| Pattern | Structural signal | Workload signal | Route |
|---|---|---|---|
| **One concept split in two** | a one-to-one pair | the pair joined in most executions that read either table, on costly paths | `database-modeling`: Identity, Relations |
| **Two concepts in one table** | a wide row with sparse groups | the groups read by different operations; one group updated far more often than the rest | `database-modeling`: Optionality |
| **A duplicated entity** | column overlap; one concept under two names | joins or copies between the two (triggers, sync jobs, dual writes) | `database-modeling`: Boundary |
| **A scattered aggregate** | one concept spread across many tables | high fan-out for one operation, or a join of five or more tables to assemble one concept | `database-modeling`: Boundary; or a contract change |
| **A missing derivation** | — | the same aggregate recomputed on every read, with many executions | `database-modeling`: Derivation |
| **Columns hiding in a document or a key–value table** | key–value shapes; document columns in predicates | filters, joins, or sorts on the hidden attributes | `database-modeling`: Optionality |
| **A contract that pulls the world** | — | an operation whose cost grows with the age or size of its data (whole histories, whole aggregates), refetched often | contract change |
| **Contention designed in** | a row many operations update (a counter, a balance, a sequence kept by hand) | lock waits or deadlocks on that table | `database-modeling`: Consistency & propagation |

## The write side

Co-access counts reads. Before a card proposes merging two tables, weigh what the merge does to writes. A frequently updated part is sometimes kept apart on purpose, so its rows stay narrow: fewer pages rewritten per update, cheaper in-place updates, less lock contention. That is a design, not a debt.

Compare the pair's write rates per row, from the engine's table statistics. Then search the project's decision records and model docs for the reason the split exists. A documented reason, or write rates an order of magnitude apart, rejects the merge. Record the rejection with its numbers rather than dropping it: a recorded rejection is how the next audit knows the pattern was weighed.

## The card

A design-debt card extends the step 5 card. It replaces *Numbers* with the pattern's two signals, and adds two lines:

```markdown
### D1 — <the decision, in the domain's words>
- **Severity / evidence:** <severity> / <kind>
- **Pattern:** <name> — structural: <signal>; workload: <signal, with its share of CPU or reads>
- **Where:** <tables, the operations that pay, the statements that carry it>
- **Problem:** <what the design makes every caller pay, in plain words>
- **Write side:** <write rates per table; the decision record searched, and what it said>
- **Proposed change:** <the model or contract change, not yet applied>
- **Migration price:** <tables rewritten, rows backfilled, consumers and contracts that change>
- **Expected benefit:** <measured on a copy, or "unproven until measured">
- **Route:** <modeling theme · contract change · ADR>
```

A design-debt card is High only when both signals are measured and its statements carry at least 20% of CPU or reads. A card on a structural signal alone is never High.

Done when every pattern in the table has been checked against the map. Each match is a card, or a rejection recorded with its reason.
