# Database skills

Ask a coding agent for a schema and you get `CREATE TABLE` in seconds: plausible names, a few foreign keys, `FLOAT` for the money. What you don't get is the conversation a good data modeler would force first: what one row means, which states an order can move through, who else writes to this table, and what happens to the history when a customer asks to be forgotten.

Ask it to work on a legacy database and it's worse. Nobody knows what half of the hundreds of tables are for, the rules live in triggers and spreadsheets, and the agent guesses.

These five skills give the agent a method instead of a guess. Desired state is declared in plain SQL, the domain is documented as source next to it, and validation is mechanical: one command, `verify.py`, has to be green after every schema change.

| Skill | When you reach for it | What you get |
|---|---|---|
| **[database-setup](./database-setup/SKILL.md)** | A repo with no schema governance yet | The `db-schema/` kit, the model-docs home, agent docs, an ADR seed and a CI backstop, proved green |
| **[database-modeling](./database-modeling/SKILL.md)** | A schema to design, or a modeling decision to settle | A relentless interview, round by round, that leaves no theme silently assumed and writes every answer where it belongs |
| **[database-adoption](./database-adoption/SKILL.md)** | An existing database nobody fully understands | The live schema carved into the repo, read-only, with the application code excavated for the rules the catalog can't show |
| **[database-sync](./database-sync/SKILL.md)** | Someone changed the live database directly | The drift brought back into the repo, with every change that needs a human decision held until it gets one |
| **[database-audit](./database-audit/SKILL.md)** | A database that costs too much, or might be wrong | A ranked report of where the engine spends and what is broken, every finding backed by numbers |

## How they fit together

```
                         ┌──> database-modeling ──> DDL, tickets, ADRs
database-setup ──────────┤        ^
  (installs the kit)     └──> database-adoption ──> database-sync  (whenever the live DB drifts)
                            (brownfield)

database-audit: any time, on any database
```

- **Greenfield:** `database-setup`, then `database-modeling`. The grill's first decision is the canonical SQL dialect.
- **Brownfield:** `database-setup`, then `database-adoption`. It hands its open gaps to `database-modeling`, then `database-sync` keeps the repo honest afterwards.
- **An ORM that already owns the schema** (Prisma, Drizzle, Django, EF Core, Rails, …): setup offers *mirror mode*, where the ORM keeps writing the DDL and `db-schema/` becomes its documented, validated mirror.

---

## database-setup: the method, installed and green

It copies a versioned scaffold into your repo:
- `db-schema/` with its tools (`verify`, `lint`, `erdgen`, `buildsql`, `doccheck`);
- `docs/db-model/` for the domain;
- agent docs that route any schema task to the right folder;
- an ADR format;
- a GitHub Actions workflow.

Then it proves `verify.py` passes on the empty kit.

What it leaves out is deliberate. It doesn't pick a dialect, write the model or start a glossary, because each of those is a decision that belongs to a human, through the next skill.

## database-modeling: the interview a schema deserves

It walks eleven themes in dependency order:
- dialect and portability;
- boundary;
- identity;
- relations;
- optionality;
- invariants and lifecycle;
- workload;
- temporality;
- derivation;
- master data;
- consistency and propagation.

It works them as a tree of decisions and asks every question that is ready, in one round. Each question comes numbered, with a recommended answer and its trade-off.

- **Facts are its job, decisions are yours.** Before each round it searches the code, the schema and (when reachable) the data, so every question carries an evidence line: what it found and where, or where it looked and found nothing. A question the evidence settles never reaches you.
- **A rule is written with the object that enforces it**, named (`uq_application_name_folded`, `ck_application_dates`), so it can be tested and sliced into tickets. A rule with no enforcing object is rationale, and goes to an ADR.
- **Protected rules** (a tax formula, a royalty, stock that must never go negative) get a calculation memo, examples validated by a named person, and guards.
- **Statuses become state machines**, with legal transitions and terminal states.
- **A theme closes explicitly**: read back, routed, and swept across every concept, so one settled enum doesn't silently claim the rest.

DDL waits until you confirm the model is ready. Try it with: *"Let's model the database for the booking system."*

## database-adoption: a legacy database, brought under governance

- **Read-only, and it checks.** The probe reads the account's real permissions and pauses on a write-capable login until you accept the risk with a reason.
- **Numbers, never values.** Live queries return counts and shapes. Sampled values stay out of every file and message.
- **Coverage is computed, not claimed.** `reconcile` compares the live catalog, the committed baseline and the carved files, and the adoption is done only when every object is carved or listed as an exception with its reason.
- **It excavates the applications.** It traces every table into the code, and every money-like column back to the arithmetic that writes it. It flags home-made queues, dirty reads deciding a write and authorization checks with no server-side guard, and asks you where else a rule is computed: a spreadsheet, another system, a manual step.
- **Any engine, by reconcile-driven porting.** The skill ships one reference extractor, SQL Server, on purpose: for your engine it builds the port the way test-driven code is built, with your live database as the test and `reconcile` as red or green. It ports the connection and the read-only probe first, then sweeps every object class the engine supports, and carves and reconciles until the reconcile is green. A port that has only been written is a draft; one that reconciled your database is a tool, and it lives in your repo.
- **Every finding is a candidate, sized.** A relation the code implies arrives at the grill as "violated by N rows", because declaring a foreign key over zero orphans and over thousands of them are different decisions.

Try it with: *"Adopt our production SQL Server database into this repo."*

## database-sync: drift, absorbed on purpose

It moves facts one way, from the live database to the repo, and never writes to the database.
- **Each finding gets its action:** drifted, dropped, new, stale or blocked.
- **Protected objects wait for a person.** A change that reaches one waits for that rule's approver.
- **The baseline holds.** It moves only when no finding is pending a human decision. Otherwise a change nobody approved would quietly become the new normal.

Try it with: *"Did the database change since the adoption?"*

## database-audit: follow the cost

It starts from what the engine already records about its own spending (Query Store, `pg_stat_statements` and kin), takes the costliest statements and traces each one to the code that issues it. That can be a routine, an ORM call, or a loop repeating a query. On an engine with no reference tool, it first builds its own measurement tool from that engine's cost sources, against your database.

- **Every finding names its evidence:** measured, structural or speculative. A speculative performance finding is never High.
- **Amplification as ratios.** Rows read per row returned, bytes written per row changed, space per byte of live data, before and after.
- **It climbs from statements to design debt.** Jaywalking, polymorphic associations, naive trees and EAV get named as patterns, with the transition each needs.
- **One top recommendation**, then a card per finding with its numbers, location, risk and route. It changes nothing in the database; a proposed performance fix is proven on a copy before it becomes a ticket.

Start it by name: `/database-audit`.

## Germline and soma

The tools these skills ship (the scaffold, the extractor, the measurement tool) are the **germline**: no run ever changes them. The copy in your repo is the **soma**: it mutates freely to fit your engine and your database. A mutation that proved itself in a run comes back as a harvest candidate, and only a maintainer, outside any run, selects it into the germline. Your repo gets a tool shaped for it, and the next repo gets the improvements that survived.

---

## Install

Each skill is a folder with a `SKILL.md`, the format coding agents load as Agent Skills. Copy the ones you want into your agent's skills folder. For Claude Code:

```sh
git clone https://github.com/paulocorcino/skills.git
cp -r skills/database/database-* ~/.claude/skills/
```

`database-setup` and `database-audit` run only when you call them by name (`/database-setup`, `/database-audit`); the others also start when your request matches them.

Requirements: Python 3.11+ and `git`. The live-database tools come as references for SQL Server (`extract_tsql.py`, `measure_tsql.py`); for any other engine, adoption and audit build the tool for it as part of the run, and it stays in your repo.

## Feedback

These skills come out of real adoptions and audits, and each one has changed after a run where it fell short. If one misleads your agent, an issue with the transcript is the most useful thing you can send.
