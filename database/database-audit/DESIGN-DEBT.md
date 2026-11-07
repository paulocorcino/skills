# Design debt

Step 5 of [`SKILL.md`](SKILL.md). Once every costly statement is traced and every statement-level finding classified, **follow the cost upward**: go from the statements to the **access patterns** they share, and from each pattern to the model decision or contract that explains it. A statement card fixes one query. A design-debt card names the decision that keeps producing costly queries, and routes it to whoever owns that decision.

The branch is strongest on the live branch. With only the static branch, every weight below is structural, so every design-debt card is speculative.

## 1. The co-access map

Widen step 2's set of costly statements until it covers at least 80% of the window's CPU and of its reads. Parse each normalized statement with the kit's `sqlglot` in the engine's dialect, and extract the tables it reads, the tables it writes, and every join edge with its join columns. Weight each table and each edge by the CPU, the reads, and the executions of the statements that touch it, and give each table its three **amplifications** (`SKILL.md`): read, write, and space. A statement nested in a routine counts once nested tracking is on (`COST-SOURCES.md`); until then, parse the routine's body from the carved DDL and mark those weights structural. Write the map to `.scratch/audit/coaccess.json`.

Done when every statement in the 80% set is parsed, or listed as unparsed with the parser's error, and every table it touches has its weights and its three amplifications.

## 2. Operation fan-out

Count the statements each business operation issues: a request, a screen, a job step. The counts come from query tags, the ORM's query log, or a test that counts statements per call. For each hot operation, record its statement count and the tables it touches. Where no source exists, record the gap; query tags (`SKILL.md` step 3) close it next time.

Done when every hot operation has its count, or the gap is recorded.

## 3. Structural signals

Read these from the catalog or the carved DDL. When the adoption's `discover` output exists, reuse it.

- **one-to-one pairs**: a foreign key from primary key to primary key, or a unique foreign key
- **column overlap**: two tables sharing column names and types beyond their keys and audit columns
- **sparse groups**: nullable columns that are null together, gated by a type or status column
- **key–value shapes**: an entity id, an attribute name, and a value column
- **document columns in predicates**: a JSON or XML field filtered or joined on
- **one concept, two names**: tables whose rows mean the same thing (the glossary settles it when one exists)
- **lists in a column**: a text column holding delimited ids or values, often under a plural name
- **numbered columns**: columns sharing a base name with a numeric suffix (`tag1`, `tag2`, `tag3`)
- **self-references**: a foreign key from a table to itself (a `parent_id`)
- **type-and-id pairs**: a `*_type` column beside a `*_id` column with no foreign key behind the id

## 4. Match the patterns

A pattern matches on every signal its row names, measured. A row that names no structural signal (—) matches on its workload signal alone. A row that names both and finds only one has a lead: record it Low and speculative.

| Pattern | Structural signal | Workload signal | Route |
|---|---|---|---|
| **One concept split in two** | a one-to-one pair | the pair joined in most executions that read either table, on costly paths | `database-modeling`: Identity, Relations |
| **Two concepts in one table** | a wide row with sparse groups | the groups read by different operations; one group updated far more often than the rest | `database-modeling`: Optionality |
| **A duplicated entity** | column overlap; one concept under two names | joins or copies between the two (triggers, sync jobs, dual writes) | `database-modeling`: Boundary |
| **A scattered aggregate** | one concept spread across many tables | high fan-out for one operation, or a join of five or more tables to assemble one concept | `database-modeling`: Boundary; or a contract change |
| **A missing derivation** | — | the same aggregate recomputed on every read, with many executions | `database-modeling`: Derivation |
| **Entity–Attribute–Value**, or columns hiding in a document | key–value shapes; document columns in predicates | filters, joins, or sorts on the hidden attributes | `database-modeling`: Optionality |
| **Jaywalking**: a list in one column | lists in a column | pattern matches or split functions over the list (`LIKE '%,x,%'`, `FIND_IN_SET`, `string_to_array`, `STRING_SPLIT`) | `database-modeling`: Optionality, Relations (an intersection table) |
| **Multicolumn Attributes**: one attribute spread over numbered columns | numbered columns | the same predicate repeated across them (`tag1 = ? OR tag2 = ? …`) | `database-modeling`: Optionality (a child table) |
| **Naive Trees**: a hierarchy kept only as a parent reference | a self-reference | a costly recursive query, or one query per level in a loop | `database-modeling`: Relations (path, nested sets, or closure table, chosen by the queries the tree serves) |
| **Polymorphic Associations**: one reference to many tables | a type-and-id pair | orphans counted by the census; joins that branch on the type | `database-modeling`: Relations (a key per target, or a common parent) |
| **A contract that pulls the world** | — | an operation whose cost grows with the age or size of its data (whole histories, whole aggregates), refetched often | contract change |
| **Contention designed in** | a row many operations update (a counter, a balance, a sequence kept by hand) | lock waits or deadlocks on that table | `database-modeling`: Consistency & propagation |

## The write side

Co-access counts reads. Before a card proposes merging two tables, weigh the **write amplification** the merge would cause. A frequently updated part is sometimes kept apart on purpose, so its rows stay narrow: fewer pages and log bytes written per update, cheaper in-place updates, less lock contention. That is a design, not a debt.

Compare the pair's write rates per row, from the engine's table statistics. Then search the project's decision records and model docs for the reason the split exists. A documented reason, or write rates an order of magnitude apart, rejects the merge. Record the rejection with its numbers rather than dropping it: a recorded rejection is how the next audit knows the pattern was weighed.

## The transition

A design-debt change is a **database refactoring**: the database already serves consumers, so the change runs as expand, a **transition period**, then contract. Expand adds the new shape beside the old one. During the transition both stay correct (kept in step by a trigger, a dual write the application owns, or a view standing in for the old shape) while each consumer moves over, and the old shape has a removal date. Contract removes it once no consumer reads it. The consumers come from the code the audit swept and, beyond it, from the database's other readers and writers (the modeling Boundary theme): an unknown consumer stretches the transition, so the card says so. Before the expand lands, a **regression test** freezes what the old shape answers today (the characterization the adoption marks as owed), so the contract step proves nothing changed. When the kit exists, the migrations follow `db-schema/migrations/README.md`.

## The card

A design-debt card extends the step 6 card. It replaces *Numbers* with the pattern's signals, and adds the amplification, migration price, and transition lines:

```markdown
### D1 — <the decision, in the domain's words>
- **Severity / evidence:** <severity> / <kind>
- **Pattern:** <name> — structural: <signal>; workload: <signal, with its share of CPU or reads>
- **Where:** <tables, the operations that pay, the statements that carry it>
- **Problem:** <what the design makes every caller pay, in plain words>
- **Amplification:** <read, write, and space amplification of the tables involved; the decision record searched, and what it said>
- **Proposed change:** <the model or contract change, not yet applied>
- **Migration price:** <tables rewritten, rows backfilled, consumers and contracts that change>
- **Transition:** <expand; what keeps both shapes correct; each consumer and its move; the removal date or what sets it; the regression test owed before expand>
- **Expected benefit:** <measured on a copy, or "unproven until measured">
- **Route:** <modeling theme · contract change · ADR>
```

A Low card may stay a **lead**: its heading, its pattern with both signals, and its route. Every card from Medium up carries every line above. A design-debt card is High only when every signal its row names is measured and its statements carry at least 20% of CPU or reads. A card on a structural signal alone is never High.

Done when every pattern in the table has been checked against the map. Each match is a card, or a rejection recorded with its reason.
