# Database skills

Ask a coding agent for a schema and you get `CREATE TABLE` in seconds: names that look right, a few foreign keys, and `FLOAT` for money. What you do not get is the conversation that a good data modeler has first:

- What does one row mean?
- Which states can an order move through?
- Who else writes to this table?
- What happens to the history when a customer asks to be forgotten?

With an old (legacy) database, it is worse. Nobody knows what half of the hundreds of tables are for, the rules are hidden in triggers and spreadsheets, and the agent guesses.

These five skills give the agent a method instead of a guess:

- the desired schema is written in plain SQL;
- the domain is documented as source files, next to the SQL;
- validation is automatic: one command, `verify.py`, must pass after every schema change.

| Skill | Use it when | What you get |
|---|---|---|
| **[database-setup](./database-setup/SKILL.md)** | The repo has no schema rules yet | The `db-schema/` kit, a place for the model documents, agent docs, a first ADR and a CI check, all proved to pass |
| **[database-modeling](./database-modeling/SKILL.md)** | You need to design a schema, or make a modeling decision | A detailed interview, round by round, that leaves nothing to guess and writes every answer in the right place |
| **[database-adoption](./database-adoption/SKILL.md)** | You have a database that nobody fully understands | The live schema copied into the repo (read-only), and the application code searched for the rules that the catalog cannot show |
| **[database-sync](./database-sync/SKILL.md)** | Someone changed the live database directly | The changes brought back into the repo. Every change that needs a person's decision waits for that decision |
| **[database-audit](./database-audit/SKILL.md)** | The database costs too much, or may have errors | A ranked report of where the engine spends the most and what is broken. Every finding comes with numbers |

## How they work together

```
                         ┌──> database-modeling ──> DDL, tickets, ADRs
database-setup ──────────┤        ^
  (installs the kit)     └──> database-adoption ──> database-sync  (each time the live DB changes)
                            (existing database)

database-audit: any time, on any database
```

- **New project (greenfield):** `database-setup`, then `database-modeling`. The first decision of the interview is which SQL dialect to use.
- **Existing database (brownfield):** `database-setup`, then `database-adoption`. Adoption sends its open questions to `database-modeling`. After that, `database-sync` keeps the repo in line with the database.
- **An ORM already owns the schema** (Prisma, Drizzle, Django, EF Core, Rails, …): setup offers **mirror mode**. The ORM keeps writing the DDL, and `db-schema/` becomes a documented, validated copy of it.

---

## database-setup: install the method and prove it works

It copies a versioned template into your repo:
- `db-schema/` with its tools (`verify`, `lint`, `erdgen`, `buildsql`, `doccheck`);
- `docs/db-model/` for the domain;
- agent docs that send any schema task to the right folder;
- an ADR format;
- a GitHub Actions workflow.

Then it proves that `verify.py` passes on the empty kit.

Some things are left out on purpose. It does not choose a dialect, write the model or start a glossary. Each of these is a decision for a person, and the next skill helps with it.

## database-modeling: the interview a schema needs

It goes through eleven themes, in the order in which they depend on each other:
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

It treats them as a tree of decisions, and it asks all the questions that are ready, in one round. Each question has a number, a recommended answer and its trade-off.

- **It finds the facts. You make the decisions.** Before each round it searches the code, the schema and (when it can reach it) the data. So every question shows its evidence: what it found and where, or where it looked and found nothing. If the evidence already answers a question, the skill does not ask it.
- **A rule is written together with the object that enforces it,** with its name (`uq_application_name_folded`, `ck_application_dates`), so it can be tested and split into tickets. A rule with no object to enforce it is a reason, and it goes into an ADR.
- **Protected rules** (a tax formula, a royalty, stock that must never be negative) get a calculation memo, examples checked by a named person, and guards.
- **A status becomes a state machine,** with the allowed transitions and the final states.
- **A theme is closed explicitly:** the skill reads the answers back, saves each one in its place, and checks them against every concept. So one decided enum does not quietly decide the others.

The skill writes DDL only after you confirm that the model is ready. Try it: *"Let's model the database for the booking system."*

## database-adoption: bring an old database into the repo

- **Read-only, and it checks this.** The first check reads the real permissions of the database account. If the login can write, the skill stops until you accept the risk and give a reason.
- **Numbers, never values.** Queries on the live database return counts and shapes only. Real data values never go into any file or message.
- **Coverage is computed, not claimed.** `reconcile` compares the live catalog, the saved baseline and the files in the repo. The adoption is done only when every object is in the repo, or is listed as an exception with its reason.
- **It searches the applications.** It follows every table into the code, and every column that looks like money back to the calculation that writes it. It points out home-made queues, dirty reads that decide a write, and permission checks that the server does not enforce. It also asks you where else a rule is calculated: a spreadsheet, another system, a manual step.
- **Any database engine, by porting step by step.** The skill comes with one reference extractor, for SQL Server, on purpose. For your engine, it builds a port the same way test-driven code is built: your live database is the test, and `reconcile` says red or green. It ports the connection and the read-only check first, then goes through every type of object the engine supports, and repeats until `reconcile` is green. A port that was only written is a draft. A port that reconciled your database is a tool, and it stays in your repo.
- **Every finding is a candidate, with its size.** If the code suggests a relation, the interview receives it as "N rows break it". Adding a foreign key when no rows break it is a very different decision from adding it when thousands of rows do.

Try it: *"Adopt our production SQL Server database into this repo."*

## database-sync: absorb changes on purpose

It moves facts in one direction only, from the live database to the repo. It never writes to the database.
- **Each finding gets an action:** drifted, dropped, new, stale or blocked.
- **Protected objects wait for a person.** A change that touches a protected object waits for the person who approves that rule.
- **The baseline stays the same** until no finding is waiting for a decision. Otherwise, a change that nobody approved would quietly become the new normal.

Try it: *"Did the database change since the adoption?"*

## database-audit: follow the cost

It starts from what the engine already records about its own costs (Query Store, `pg_stat_statements` and similar tools). It takes the most expensive statements and follows each one to the code that runs it: a routine, an ORM call, or a loop that repeats a query. If the engine has no reference tool, the skill first builds its own measurement tool from that engine's cost data, on your database.

- **Every finding says what kind of evidence it has:** measured, structural or speculative. A speculative performance finding is never High.
- **Waste is shown as ratios.** Rows read for each row returned, bytes written for each row changed, space used for each byte of live data, before and after.
- **It goes from single statements up to design problems.** It names known patterns such as jaywalking, polymorphic associations, naive trees and EAV, and the change each one needs.
- **One top recommendation,** then one card per finding with its numbers, location, risk and next step. It changes nothing in the database. A suggested performance fix is tested on a copy before it becomes a ticket.

Start it by name: `/database-audit`.

## The skill's tools and your copy

The tools that come with these skills (the template, the extractor, the measurement tool) never change during a run. Your repo gets its own copy, and that copy can change freely to fit your engine and your database. When a change proves useful in a run, it becomes a candidate. Only a maintainer, outside any run, can add it to the skill. So your repo gets a tool that fits it, and the next repo gets the improvements that worked.

---

## Install

Each skill is a folder with a `SKILL.md` file. This is the Agent Skills format, which Claude Code, Codex, Cursor and many other agents can load. Install with the [skills CLI](https://github.com/vercel-labs/skills) (Node 22.20 or newer). Run it from your project:

```sh
npx skills add paulocorcino/skills --skill database-setup --skill database-modeling --skill database-adoption --skill database-sync --skill database-audit
```

It asks which agents to install to. `-g` installs for all your projects, and `-a claude-code` chooses one agent. The five skills work as a set: `database-sync` uses the extractor that comes with `database-adoption`. You can also copy the folders by hand:

```sh
git clone https://github.com/paulocorcino/skills.git
cp -r skills/skills/database/database-* ~/.claude/skills/
```

`database-setup` and `database-audit` run only when you call them by name (`/database-setup`, `/database-audit`). The other skills also start when your request matches them.

Requirements: Python 3.11 or newer, and `git`. The tools for the live database come as references for SQL Server (`extract_tsql.py`, `measure_tsql.py`). For any other engine, adoption and audit build the tool during the run, and it stays in your repo.

## Feedback

These skills come from real adoptions and audits, and each one has changed after runs where it did not do well. If a skill gives your agent the wrong direction, please open an issue with the transcript. That is the most useful thing you can send.
