# docs/db-model/calc/ — protected rules

Every rule tagged **[protected]** in `docs/db-model/` has its specification here: a rule whose error costs money, a fine, or legal exposure. Read this file before changing a protected rule's formula, parameters, code, or examples — every object that implements one, database routine or application code, opens with a header comment pointing at its memo.

**The memo and its examples file are canonical.** The implementation is a candidate that must reproduce them, wherever it lives. When code and memo disagree, the disagreement goes to the rule's approver — the code may be wrong, or the memo may have missed a nuance, and only the approver settles which. The memo changes only through the change protocol below.

The layout follows established practice, so a reader can recognise it:

- **Rules as Code** (OpenFisca, Catala) — parameters carry effective dates and a reference to the legal article; tests are input/output cases kept beside the rule.
- **Specification by Example** (FIT tables, Gherkin `Examples`) — the examples table *is* the test, never a copy of it.
- **IPE**, *Information Produced by the Entity* — a query that feeds an official filing is audited for completeness and accuracy like any formula.
- **Model risk management** (SR 11-7) — documented, validated by someone independent of the author, changed under control.

## Files

| File | Holds |
|---|---|
| `<RULE-ID>-<slug>.md` | The **calculation memo**: the living specification of one rule |
| `<RULE-ID>.examples.yaml` | Its **worked examples** — the single copy the tests read |

## The calculation memo

A memo gains a version whenever the law or the business changes the rule. A *choice* made along the way (why rounding happens per product, why this reference price) is an ADR in `docs/adr/`, linked from the memo. Sections, in order:

```markdown
# <RULE-ID> [protected] — <name>

## Source
<law / decree / regulator resolution / contract clause, down to the article; where no written source exists, the human owner of the rule, by role>

## Formula
<written out in full; every variable mapped to its column or parameter; every unit stated>

## Precision
| Value | Type and scale | Rounding |
|---|---|---|
<every input, intermediate, and result; rounding mode (half-up, half-even) and rounding point (per line, per item, per period, on the total)>

## Effective dating
| Version | Valid from | Valid to | What changed | Source |
|---|---|---|---|---|

## Implementation
<the single place the rule is computed — database routine or application module, by path — and the objects that form it; every other consumer reads the stored result; the ADR that chose the location>

## Worked examples
Cases in [`<RULE-ID>.examples.yaml`](<RULE-ID>.examples.yaml) — what each one probes, in one line each.

## Change protocol
Approver: <role>. Every proposed change first shows its impact: which cases change, and by how much.
```

## The examples file

One case per entry. Decimal values are **quoted strings** — an unquoted `0.1` is parsed as a binary float and the cent the file exists to protect is gone before the test runs.

```yaml
rule: ROY-01
cases:
  - id: E1
    probes: typical case, oil
    period: "2026-06"
    input:
      rate: "0.1000"
      volumes_m3: ["120.500", "80.250"]
      price_brl_per_m3: "2450.1234"
    output:
      amount_brl: "49186.23"
    oracle: accountant's spreadsheet, sheet 2026-06
    validated_by: null      # person or role
    validated_on: null      # YYYY-MM-DD
```

Choose cases to break the formula, never to flatter it: a typical case; zero and boundary inputs; a period crossing an effective-date change; a rounding knife-edge (a value landing on the half); the largest expected magnitude against the declared scale; an adjustment or negative case where the domain allows one.

A rule that must hold under concurrency states the concurrent load in its case (`concurrent_writers: 51`, `units: 50`), and its test runs that load as real simultaneous sessions against a real database of the canonical dialect — a sequential test passes whether or not the race is handled.

The test for a rule is parametrised over this file. A case with `validated_by` set is a hard assertion; a case without it is reported as skipped, *awaiting validation*, so the gap stays visible in every run.

## Changing a protected rule

The expected values belong to the human who validated them: a failing case means the code is wrong, and an expected value changes only with the approver's sign-off recorded in the case (`validated_by`, `validated_on`). A legal change is a new effective-dated version — of the parameters and of the memo. The previous version keeps its value; closing its open `valid_to` is the one edit it receives, so past periods keep computing with the version they were computed under.

Every change — to the code, the parameters, the memo, or the examples — runs this sequence, each step done only when its check holds:

1. **Read** the memo and every ADR it links. Done when you can state, in the memo's terms, what the change alters.
2. **Baseline** — run the rule's examples before touching anything. Done when they are green; a red baseline is itself the finding — report it and stop.
3. **Impact** — compute every case the change would move: case, old value, new value, difference. A refactor that should move nothing proves it here with an empty report. Replay a sample of stored calculations under their recorded rule version; past periods must reproduce to the cent.
4. **Approval** — a non-empty impact report goes to the approver *before* the change lands, together with the memo version it implies. Done when the approval is in the conversation, the PR, or the cases themselves.
5. **Land** — code, memo version, and examples change together, in one commit, and the examples run green again.

Moving the implementation between the database and the application is a change like any other: both implementations run against the examples and the stored calculations until both agree, and only then does the old one go.

## Guards

Owed by every protected rule, and sliced into tickets with the DDL:

- **Header comment** — every object that implements the rule, in DDL or application source, opens with `[protected] <RULE-ID> — spec: docs/db-model/calc/<RULE-ID>-<slug>.md`, the pointer met at the exact point of change.
- **Form lint** — static rules over the code and the DDL (Semgrep, SQLFluff custom rules): money and regulated quantities never in binary floating point; rounding only inside the rule's rounding routine; the rule's parameters read only through their effective-dated lookup.
- **Review gate** — a `CODEOWNERS` entry naming the approver over the memo, its examples file, and the objects the rule names.
- **Mutation testing** (Stryker, mutmut, or the stack's equivalent) over the rule's routines — when a mutant survives, the examples leave the rule unguarded and need another case.
