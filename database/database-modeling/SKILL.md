---
name: database-modeling
description: Grill the user through the database model in dependency-ordered rounds — sweep every modeling theme, surface the gaps only a human can close, and route each answer to its source of truth. Use when the user wants to model the database, resolve a modeling decision, or asks for DDL while gaps remain.
---

Interview the user relentlessly about the database model until shared understanding is reached for all *the themes* listed below. Map each theme as a *design tree*, where each decision branches out into the decisions that depend on it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask *now* without guessing at answers you haven't heard yet. A settled decision is not always a heard one: where `CONTEXT.md`, an ADR, the `dbkit/` docs, or the schema itself already answers, decide it yourself, record it, and announce it as established — it never enters a round. Ask the whole remaining frontier in one round: number each question and give your recommended answer **with its trade-off**. Then wait for the user's answers before the next round.

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a *later* round, not this one.

Finding *facts* is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The *decisions* are the user's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

A missing `CONTEXT.md` is a starting state, not a blocker — a brownfield adoption arrives here in exactly that state. The direction simply reverses: greenfield reads the glossary to shape the schema; brownfield reads the schema — plus the model doc's recorded gaps and the excavated code — to build the glossary, one resolved term at a time. When an adoption ran, its **DB-to-Domain discovery** sets the walking order — cross-domain hub entities first (every later answer references them), then cluster by cluster, core tables before the rest — and each unnamed cluster is itself a Boundary gap: naming a domain area is a decision only the user can make. A gap the adoption sized with a census number carries that number inside the trade-off you put to them — "declaring this relation costs cleaning N orphans" is a different decision at N = 0. As domain terms and decisions surface, actively sharpen the language and update `CONTEXT.md` and ADRs inline (`/domain-modeling`).

## The themes

Walk them in dependency order — dialect before collation, identity before uniqueness, history before any table it reshapes.

- **Dialect & portability** — canonical dialect and minimum version; secondary engines now or later; collation and folding (case, accents, whitespace); timezone and date-time storage
- **Boundary** — what domain concept one row represents; whose data it is (single organization or multi-tenant); what stays outside the model
- **Identity** — key strategy; natural keys and the scope of each uniqueness rule — including satellite names (aliases, codes, synonyms) that share a namespace with the name they orbit
- **Relations** — cardinality, ownership, and what deletion means at each edge
- **Optionality** — what is mandatory *and* what is deliberately nullable, each with its reason; where absence itself carries domain meaning
- **Invariants & lifecycle** — rules that must always hold; every closed domain and its allowed values; legal state transitions and the fate of data they orphan
- **Workload** — read/write balance, and the queries the model must serve cheaply; both reshape the two themes below
- **Temporality** — current state only, or history and audit; retention
- **Derivation** — stored vs derived facts, the single source each derives from, and the mapping itself written out, not referred to
- **Master data** — reference records, who owns them, whether they can be removed while in use; one mechanism per hole, never two

Deliberately outside the tree: indexes, partitioning, concurrency tuning, migration and backfill — physical design and transition planning follow the DDL; they enter through `/to-prd` or `/to-spec` → `/to-issues` or `/to-tickets` for open tickets, or through an ADR when a scale fact reshapes a table.

When the user's answer is vague, sharpen it against the glossary in `CONTEXT.md`; when they claim a relationship or invariant, stress it with a concrete scenario before accepting it.

A theme is not closed when the user stops talking about it. Close it explicitly: read back what it produced, name where each part landed, and state whether it earned an ADR and why — Temporality, Invariants & lifecycle, and Master data usually do. Two traps live here. A theme that answered *some* of the schema silently claims the rest: one closed domain written down implies the others were considered, one uniqueness rule implies its satellites, a mandatory column implies the nullable ones were argued. Sweep the theme across every concept in the glossary before closing, not just the concept we were discussing. And a decision is only recorded when the model file says how it is represented — a term named in the vocabulary but with no rule stating the column, flag, or row that carries it is still a gap, however settled it felt in conversation.

## Routing

Route each resolved decision the moment it lands:

- a domain term → **two** writes, never one: the meaning to the glossary in `CONTEXT.md` (no implementation), and the `Term | Meaning | Table` line to the model file's Vocabulary — `Table` reads *pending* until the DDL exists. A term resolved and absent from that table is a dropped decision.
- a concept, invariant, relation, or rule → its owning model file — `dbkit/model/database.md`, or its `dbkit/model/domains/` shard once promoted (growth contract in `dbkit/model/README.md`) — rules carrying prefixed IDs, each one testable
- **a rule is written only with the object that enforces it, named** — `uq_application_name_folded`, `trg_alias_namespace`, `ck_application_dates` — even though the object does not exist yet; that name is what `/to-issues` slices and what the test in `dbkit/tests/` targets. Naming no object means it is not a rule: it is rationale, and rationale goes to an ADR. Any routine, view, or trigger a rule names also lands in the model file's Routines table, or `doccheck.py` fails once the DDL arrives.
- hard to reverse **and** surprising without context **and** a real trade-off → an ADR in `docs/adr/`. Prose like "accepted cost" or "we rejected X because" inside a numbered rule is the tell that it belongs there instead.

## Closing

Before declaring the model ready, sweep the artifact — a grill appends in conversation order, and the file must not read that way:

- rule IDs reordered and contiguous within each prefix
- every `CONTEXT.md` term present in the Vocabulary table, and every term the model represents named by some rule
- what the Boundary theme ruled *out* stated in "The business" — negative scope is what stops the next session reopening it
- every object named by a rule present in the Routines table
- decisions carrying trade-off prose moved out to ADRs, leaving the rule itself
- `python dbkit/tools/verify.py` green

The model is ready when every theme is routed or out of scope, the sweep is clean, and the user confirms shared understanding. Until then, DDL waits. On confirmation, offer `/to-prd` or `/to-spec` → `/to-issues` or `/to-tickets` — the populated `dbkit/model/database.md` is the spec it slices.
