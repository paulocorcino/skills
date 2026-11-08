# Evidence

The disclosed branch of the **evidence pass** in [`SKILL.md`](SKILL.md), reached when the database is reachable — an adoption ran, so the ledger holds the connection recipe and `probe.json` the account's permissions. It says how to question the live data before a question reaches the user. Without a reachable database, the pass runs on the code and the docs alone.

## Facts and decisions

The data shows what **is**, defects included — never what **should be**. A status with zero rows may still be legal; 37 rows with `end < start` are more likely a bug than a rule. So evidence settles a question of fact, and arms a question of decision:

- **A fact with conclusive evidence** leaves the round, announced as established with its source — "the code writes only these four values, `OrderService.cs:88`; the data holds exactly those four".
- **A decision** stays in the round, carrying its evidence into the trade-off — "the code accepts any date; 37 rows end before they start. Is the rule end ≥ start, with those 37 rows to clean?"

What a table or column *stores* is a fact; what the domain term *means* is a decision. Evidence that a table mixes three populations turns "what is an employee?" into "the table holds three populations (counts); does *employee* cover all three?"

## The loop

Each hypothesis runs one loop, and each step can refute the one before it:

1. **Code** — where the value is written and read; the writer is the strongest explanation of what a column holds.
2. **Count** — the whole table, aggregates only: how many rows follow the hypothesis, how many deviate.
3. **Sample** — a few rows chosen to explain the count, above all the deviants.
4. **Code again** — when the sample contradicts the code, the contradiction is the finding.

A sample forms a hypothesis; a count over the whole table states its extent. A conclusion enters the round with its number, never as "from what I saw". An adoption census sizes a symptom — "395,116 broken references" — and the loop explains its cause: a column holding years where the code expects ids is not a broken reference.

A formula is validated the same way: recompute it over every row and count the rows whose stored value diverges, then sample the divergent ones. For a **[protected]** rule this is the characterization [`PROTECTED.md`](PROTECTED.md) reconciles — memo, code, stored result; validating the examples file stays with the named person and oracle it requires.

## Choosing the sample

The question chooses the rows. Seek the row that would **refute** the hypothesis — a sample that only confirms teaches little.

| Choice | Reveals |
|---|---|
| **One row per state** | which columns each state fills — an active and a dismissed employee side by side |
| **Newest against oldest** | whether a column's meaning changed over time — a column repurposed from a given year on; every column whose meaning is a gap gets this split |
| **One full cycle** | an entity followed through every table its keys reach, from birth to its terminal state — how the relations really chain; prefer a cycle from the current era |
| **The deviants** | where the hypothesis breaks — sample the rows the count found off-pattern |
| **By origin** | separate write paths — screen, import, initial load, manual script — told apart by an audit column or an id range |

Validate the ordering column before ordering by it: a creation date that is mostly null, zero, or decades in the future picks garbage as "the newest". The primary key's growth is the fallback for recency.

**Sentinels** — `''`, `0`, `'0000-00-00'`, a date far in the future, a `teste` row — are counted apart from real values in every aggregate; counted as filled, they make the evidence lie. Test rows found in production are a finding of their own, with their count.

## Rules for every query

- **Read-only**, under the adoption's read-only standing rule: the project's extractor connection (`db-schema/tools/extract_<dialect>.py`), the account `probe.json` classified. A database the adoption never reached is not queried.
- **Bounded**: a row limit on every sample, at most one row per stratum and twenty per question; a statement timeout on every query; on a production database with a read replica, the replica.
- **Personal columns show their shape, never their value** — documents, names, contacts, bank data, salary, health: length, pattern (`###.###.###-##`, `x@x.x`), null rate, distinct count — per era too, so a repurposed column shows in its shape. A column of unknown content is treated as personal until its shape says otherwise. Real values only with the user's authorization, recorded once in the ledger.
- **Nothing sampled is written to a file.** The glossary, the model, and the ADRs receive conclusions and numbers.
- **Delegated by role**: the main agent chooses the strata and states the hypothesis; a sub-agent on the smallest capable model runs the queries and returns the numbers. The interpretation stays with the main agent.

## Done

The pass is done for a question when it has an evidence line: **found** — the source and the number (`file:line`, *N rows*) — or **searched** — where it looked and found nothing. A question with no evidence line is not ready for a round.
