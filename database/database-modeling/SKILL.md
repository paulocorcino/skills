---
name: database-modeling
description: Grill the user through the database model in dependency-ordered rounds — sweep every modeling theme, surface the gaps only a human can close, and route each answer to its source of truth. Use when the user wants to model the database, resolve a modeling decision, or asks for DDL while gaps remain.
---

Interview the user relentlessly about the database model until shared understanding is reached for all *the themes* listed below. Map each theme as a *design tree*, where each decision branches out into the decisions that depend on it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask *now* without guessing at answers you haven't heard yet. A settled decision is not always a heard one: where the glossary, an ADR, the `docs/db-model/` docs, or the schema itself already answers, decide it yourself, record it, and announce it as established — it never enters a round. Ask the whole remaining frontier in one round: number each question and give your recommended answer **with its trade-off**. Then wait for the user's answers before the next round.

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a *later* round, not this one.

Finding *facts* is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — on the smallest capable model, where the agent can choose one — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The *decisions* are the user's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

**The glossary** is the project's ubiquitous-language file, whatever its name. Resolve it once, before the first round: the file `AGENTS.md` / `CLAUDE.md` names; else `CONTEXT-MAP.md` and the per-context `CONTEXT.md` files it points to; else a root `CONTEXT.md`; else `GLOSSARY.md`. Every write goes to that file. Two candidates both alive is a decision for the user — the answer lands in the project's agent instructions file, so the next session resolves it without asking. Several contexts mean several glossaries, and every table has exactly one owning context: the one whose glossary defines what its row represents.

A missing glossary is a starting state, not a blocker — a brownfield adoption arrives here in exactly that state. The direction simply reverses: greenfield reads the glossary to shape the schema; brownfield reads the schema — plus the model doc's recorded gaps and the excavated code — to build the glossary, one resolved term at a time. When an adoption ran, its **DB-to-Domain discovery** sets the walking order — cross-domain hub entities first (every later answer references them), then cluster by cluster, core tables before the rest — and each unnamed cluster is itself a Boundary gap: naming a domain area is a decision only the user can make. A gap the adoption sized with a census number carries that number inside the trade-off you put to them — "declaring this relation costs cleaning N orphans" is a different decision at N = 0. As domain terms and decisions surface, actively sharpen the language and update the glossary and ADRs inline (`/domain-modeling` — its format applies to whichever file the glossary resolved to; with none, it creates `CONTEXT.md`).

## The themes

Walk them in dependency order — dialect before collation, identity before uniqueness, history before any table it reshapes.

- **Dialect & portability** — canonical dialect and minimum version; secondary engines now or later; collation and folding (case, accents, whitespace); timezone and date-time storage; exact numerics — money, quantities, their unit and rounding rule; an engine without an exact decimal type (SQLite) stores them as integers in the smallest unit
- **Boundary** — what domain concept one row represents; which context owns each table — another context reaches it through a contract, never as a co-owner; whose data it is (single organization or multi-tenant — when multi-tenant, the tenant key inside every uniqueness rule and every cross-table reference, by composite key, plus the isolation mechanism when clients reach the database directly); every other system that reads or writes this database, and in which direction; what stays outside the model
- **Identity** — key strategy; natural keys and the scope of each uniqueness rule — including satellite names (aliases, codes, synonyms) that share a namespace with the name they orbit
- **Relations** — cardinality, ownership, and what deletion means at each edge; every edge a declared foreign key can enforce — a polymorphic reference (type + id) stays a gap until split into separate keys or tables
- **Optionality** — what is mandatory *and* what is deliberately nullable, each with its reason; where absence itself carries domain meaning; every attribute that is filtered, joined, or constrained is a column, never a field inside a document (JSON)
- **Invariants & lifecycle** — rules that must always hold; every closed domain opened value by value — each value a glossary term, and the mechanism that holds the set (check constraint, lookup table, or native enum); legal state transitions and the fate of data they orphan
- **Workload** — read/write balance, and the queries the model must serve cheaply; *contention* — the rows many writers hit in the same instant, and the representation that spreads them (see Consistency & propagation); all three reshape the themes below
- **Temporality** — current state only, or history and audit; retention, and erasure of personal data across history and every copy that left the database
- **Derivation** — stored vs derived facts, the single source each derives from, and the mapping itself written out, not referred to; for each stored derivation, the query that earns it and how stale it may be
- **Master data** — reference records, who owns them, whether they can be removed while in use; one mechanism per hole, never two
- **Consistency & propagation** — the *consistency boundary*: which invariants one local transaction enforces and which span owners; how each state change another system must learn of leaves, and each message this database absorbs arrives, without a *dual write*; concurrent writers to one row or one contested quantity. When Boundary found no other system and no multi-owner process, and Workload found no contention, the theme closes in one stated line. Otherwise read [`CONSISTENCY.md`](CONSISTENCY.md) before its first round.

Deliberately outside the tree: indexes, partitioning, the choice of locking hints and isolation levels, migration and backfill — every invariant holds under any of them, because a constraint enforces it — physical design and transition planning follow the DDL; they enter through `/to-prd` or `/to-spec` → `/to-issues` or `/to-tickets` for open tickets, or through an ADR when a scale fact reshapes a table.

A **protected rule** is one whose error costs money, a fine, or legal exposure — a royalty or tax formula, a calculation where a cent or a decimal place changes the outcome, an invariant whose breach is a business incident (selling stock that does not exist), a query that feeds an official filing. The user declares it ("this rule is protected"); propose the marking yourself whenever a rule touches money, tax, a legal source, or more decimal places than display needs — the marking itself stays the user's decision. A protected rule carries more than its enforcing object: read [`PROTECTED.md`](PROTECTED.md) the first time one surfaces.

When the user's answer is vague, sharpen it against the glossary; when they claim a relationship or invariant, stress it with a concrete scenario before accepting it.

A theme is not closed when the user stops talking about it. Close it explicitly: read back what it produced, name where each part landed, and state whether it earned an ADR and why — Temporality, Invariants & lifecycle, Master data, and Consistency & propagation usually do. Two traps live here. A theme that answered *some* of the schema silently claims the rest: one closed domain written down implies the others were considered, one uniqueness rule implies its satellites, a mandatory column implies the nullable ones were argued. Sweep the theme across every concept in the glossary before closing, not just the concept we were discussing. And a decision is only recorded when the model file says how it is represented — a term named in the vocabulary but with no rule stating the column, flag, or row that carries it is still a gap, however settled it felt in conversation.

## Routing

Route each resolved decision the moment it lands:

- a domain term → **two** writes, never one: the meaning to the glossary (no implementation), and the `Term | Meaning | Table` line to the model file's Vocabulary — `Table` reads *pending* until the DDL exists. A term resolved and absent from that table is a dropped decision.
- a concept, invariant, relation, or rule → its owning model file — `docs/db-model/database.md`, or its `docs/db-model/domains/` shard once promoted (growth contract in `docs/db-model/README.md`) — rules carrying prefixed IDs, each one testable
- **a rule is written only with the object that enforces it, named** — `uq_application_name_folded`, `trg_alias_namespace`, `ck_application_dates` — even though the object does not exist yet; that name is what `/to-issues` slices and what the test in `db-schema/tests/` targets. Naming no object means it is not a rule: it is rationale, and rationale goes to an ADR. Any routine, view, or trigger a rule names also lands in the model file's Routines table, or `doccheck.py` fails once the DDL arrives.
- a protected rule → its rule tagged **[protected]** in the model file, plus the calculation memo, examples file, and guards laid out in [`PROTECTED.md`](PROTECTED.md)
- hard to reverse **and** surprising without context **and** a real trade-off → an ADR in `docs/adr/`. Prose like "accepted cost" or "we rejected X because" inside a numbered rule is the tell that it belongs there instead.

## Closing

Before declaring the model ready, sweep the artifact — a grill appends in conversation order, and the file must not read that way. The sweep reorders and completes what was decided; a decision it uncovers goes back to the user as one more round.

- rule IDs reordered and contiguous within each prefix
- every glossary term present in the Vocabulary table, every closed-domain value among them, and every term the model represents named by some rule
- every table assigned to exactly one owning context, and every invariant marked local or cross-boundary — each cross-boundary one carried by its named outbox, inbox, or saga object
- what the Boundary theme ruled *out* stated in "The business" — negative scope is what stops the next session reopening it
- every object named by a rule present in the Routines table
- every **[protected]** rule closed as [`PROTECTED.md`](PROTECTED.md) defines — above all, every case in its examples file validated by a named person against a named oracle
- decisions carrying trade-off prose moved out to ADRs, leaving the rule itself
- `python db-schema/tools/verify.py` green

The model is ready when every theme is routed or out of scope, the sweep is clean, and the user confirms shared understanding. Until then, DDL waits. On confirmation, offer `/to-prd` or `/to-spec` → `/to-issues` or `/to-tickets` — the populated `docs/db-model/database.md` is the spec it slices.
