# Protected rules

The disclosed branch of **protected rule** in [`SKILL.md`](SKILL.md), reached the first time one surfaces — declared by the user, or proposed by you and confirmed. Rounds, routing, and the named-object rule work exactly as in `SKILL.md`; this file says what a protected rule owes beyond its enforcing object, so that the next agent touching it knows a regression is expensive and a human signs every change.

Four leading words carry it:

- The **oracle** is a source of the correct result independent of the code: the regulator's published example, the official spreadsheet, the accountant's worked calculation. Code checked against itself proves only that it agrees with itself — existing code included.
- A **worked example** is one concrete case — every input, the expected result to the last cent or decimal place — validated by a named person against the oracle.
- **Effective dating**: a legal formula and its parameters change with the law; each version holds from a start date to an end date, and a past period is always computed with the version in force then.
- **Four-eyes**: every change to a protected rule is approved by a human before it lands.

## The folder contract

On the first protected rule, create `docs/db-model/calc/README.md` from [`CALC-README.md`](CALC-README.md), verbatim. It is the repository's own source of truth for protected rules — the memo template, the examples-file format, the change protocol, the guards — and it is what a later agent reads when it touches the code without running this skill. Write every memo and examples file to its format; when the format needs to change, change the README.

## Per protected rule

- **The memo** `docs/db-model/calc/<RULE-ID>-<slug>.md`, every section filled. Two sections fail silently and earn the most legwork. *Precision*: the rounding **point** — per line, per item, per period, or on the total — is where silent cents are born; when the user's description admits two readings, write a case on which they differ by a cent and let the oracle decide. *Source*: cite only an article you have verified; an unverified one stays a named gap in the memo.
- **The examples file** `docs/db-model/calc/<RULE-ID>.examples.yaml`. Draft candidate cases — computed in exact decimal arithmetic, `validated_by: null` — so the user has something concrete to check against the oracle; the validation itself is the user's. The memo describes the cases in one line each and points at the file; the cases live in the file alone.
- **The implementation** — where the rule is computed, a database routine or application code, is the user's decision, with its trade-off (a routine sits beside the data and is reachable by every writer; application code is easier to test and version) and an ADR. Exactly one implementation per rule: every other consumer — reports, screens, the filing query — reads the stored result. The rule names its implementing objects either way; database objects go in the Routines table, application objects in the memo's Implementation section.
- **The tag** — the rule reads **[protected]** in the model file and links its memo; every implementing object carries the same tag where it is listed, and opens with the README's header comment in its DDL or source file — the pointer an agent meets at the exact point of change.
- **The guard** — one line in the project's agent instructions file, written once for all protected rules. That file is the one the project already uses (`AGENTS.md`, `CLAUDE.md`, or another its tooling reads) — name it to the user; when the project has none, propose creating `AGENTS.md` and create it only with the user's authorization:

  > Protected rules are tagged **[protected]** in `docs/db-model/` and in a header comment on their code. Their specs in `docs/db-model/calc/` are canonical over any implementation: read `docs/db-model/calc/README.md` and follow its change sequence before touching a protected rule's code, parameters, or examples.

  Then record the README's **Guards** — form lint, review gate, mutation testing — as owed in the memo's change protocol; they are sliced into tickets with the DDL. Whether the `CODEOWNERS` entry lands is the user's call.

## What lands in the model

- **Exact numerics** — the Dialect & portability decision applied to every column the formula reads or writes.
- **Parameter tables with effective dating** — rates, reference prices, thresholds as rows with `valid_from` / `valid_to`, each table listed in `db-schema/baseline/watched-data.json` (`[{"schema", "table", "rule"}]`) so reconcile reports a `DATA-DRIFT` when its rows change outside the repo; versions never overlapping (`ex_<param>_no_overlap`, or a trigger where the dialect lacks exclusion constraints). A changed rate is a new row; a version's value never changes — closing its open `valid_to` is the one edit an existing row receives.
- **One rounding routine** — mode and point live in one named routine (`fn_<rule>_round`, or its application-code equivalent) every computation calls: one place to read, one place to change, one place the form lint allows rounding.
- **A reproducible result** — the computed result stored with the inputs it used and the rule version applied (`<rule>_calculation`: inputs, `rule_version`, result, `computed_at`), so an audit years later replays it to the same cent. A correction is a new calculation row superseding the old one — Temporality's history, never an overwrite.
- **A protected query** — a view or routine feeding an official filing is a protected rule like any formula: its memo states the filter, the grouping, and the period boundaries, and its examples are small fixtures with the expected rows.

## Brownfield: characterize before touching

When the rule already lives in code — a legacy routine, an application service — that code is a **golden master** before it is a refactoring target: an oracle of *change*, never of *correctness*. The adoption marked it *behavior not characterized*; characterize it by **approval testing** — run it over representative real inputs, with the user's permission, since inputs and results may be financially sensitive, and freeze its outputs — then compare every output with the memo. Each divergence is a finding put to the user: a legacy bug the business has been living with, or a memo that missed a nuance. Only once the user settles every divergence do the worked examples freeze; until then the golden master guards the refactor and the memo guards the truth. Mutation testing over the legacy routine shows how much of it the frozen outputs actually cover.

## Closing

Closed when `docs/db-model/calc/README.md` exists; every protected rule is tagged in the model file with its objects tagged in the Routines table; its memo has every section filled — Implementation naming the single location — and every unverified source named as a gap; every case in its examples file carries `validated_by` and `validated_on` against a named oracle; its parameters carry effective dating; its result is reproducible; the guard line sits in the agent instructions file; and the README's guards are recorded as owed.
