---
name: database-sync
description: Sync `db-schema/` with changes made directly in the adopted live database. Use when the user wants to absorb schema drift, or asks whether the database changed.
---

Bring the repo back in line with the adopted live database. One direction only: this skill moves facts **DB → repo** and never writes to the database (repo → DB is `db-schema/migrations/`, out of scope here). It requires a completed adoption — `db-schema/tools/extract_<dialect>.py` plus the committed baseline in `db-schema/baseline/` — and the `.env` connection. A missing baseline is restored from the repo, never rebuilt by re-running `inventory`, which would absorb whatever drift exists; with no adoption at all, route to the `database-adoption` skill instead. Standing rules:

- **Protected objects.** An object implements a rule tagged **[protected]** when the model's Routines table tags it so or its file opens with the `[protected]` header. Any change reaching such an object — drifted, dropped, or stale — enters through the change sequence in `docs/db-model/calc/README.md` and waits for the rule's approver; until the sign-off, the carved file stays as the repo's last approved version.
- **Pending findings hold the baseline.** The baseline (`db-schema/baseline/inventory.<schema>.json`) moves only when no finding is pending a human decision, and every move travels in the same commit as the carved files and model docs it accompanies — the diff is how a reviewer sees what was absorbed. Refreshing it while one pends would erase that drift from the next reconcile — the change would become normal without anyone deciding it.
- **Delegation.** Where the agent can dispatch subagents and choose their model, mechanical work — carving a batch of objects, drafting the one-line model entries the materiality rule assigns, running `erdgen` / `verify` and summarizing — goes to the smallest capable model, in batches that fit one subagent's context, returning conclusions, not dumps. Judgment stays in the main session: every DRIFT and STALE direction, anything touching a protected or numbered rule, every deletion, and anything put to the user. The closing reconcile and `verify.py` prove the batches — evidence, not self-report. With a handful of findings, the work runs inline.

## 1. Tool version check

Sync tool versions per `database-adoption` step 4: compare `__version__` of the repo copy against the reference in that skill's `scripts/`. The references stay read-only — the run upgrades or bumps only the repo copy, and a repo copy ahead of the reference is reported as a harvest candidate in step 6. Done when the repo copy is at least the reference's version.

## 2. Probe

Run `extract_<dialect>.py probe` under the adoption's read-only rule: the account's permissions may have changed since the adoption. On a write-capable account it pauses; put the headline permissions to the user — an acceptance already recorded in the ledger for this login is re-applied with its recorded reason (`--accept-write-risk`), a new one only with the user's word. Either way, a write-capable account is named in the report. Done when the probe passed or the acceptance is applied.

## 3. Detect

Run `python db-schema/tools/verify.py --live` from the repo root — reconcile covers every schema with a baseline file. Green with no warnings → report "repo and database in sync" and stop. Otherwise collect every reconcile finding. Done when each finding is listed with its schema, object, and class.

## 4. Act per finding

Work the findings in the table's order — direction decisions first, mechanical imports after.

| Finding | Action |
|---|---|
| `DRIFT` | First check it is not the **regression of an intended repo change** (a pending migration touching the object): if it is, put it to the user. A protected object goes to its approver with the impact: the definition diff (carved file vs live rendering), and the rule's examples run against the live definition wherever a read-only account can run them (a function called in a `SELECT`); where it cannot — a procedure needs `EXECUTE`, which a read-only account lacks — say so, and the approver decides with the diff. Any other object: re-carve it and update its model block; when the change removed a constraint or trigger that backed a numbered rule, the rule's fate is a decision put to the user. |
| `DATA-DRIFT` | A watched table's content changed in the live database — the parameters of a protected rule (`db-schema/baseline/watched-data.json`). It goes to the rule's approver with the change sized from aggregates (row counts, the rule's examples recomputed with the current parameters where a read-only query allows); the parameter values reach the report only as the approver needs them, never as a dump. |
| `STALE` | The carved file no longer matches the live rendering while the catalog is unchanged: the file was edited in the repo, or the renderer evolved. An edit that is an intended change is a migration still to write — put it to the user; otherwise re-carve. A protected object follows the protected rule. |
| `DROPPED` | Confirm no pending migration explains it. A protected object goes to its approver; any other: delete the carved file and its model entry, flag the numbered rules and model blocks that referenced it, and list every removed path. |
| `BLOCKED` | An object the tool cannot carve faithfully (encrypted module, unsupported class): put it to the user, and record the decision in `.scratch/adoption/exceptions.json` with its reason. |
| `NEW` | `extract_<dialect>.py carve --objects <name>` → model entry: an evidence-based block if material (materiality rule in `docs/db-model/README.md`), a one-liner otherwise; either way record the gap — *purpose unconfirmed, arrived outside the repo on YYYY-MM-DD* — since an object that appeared has an intent only its author knows. A new routine carries the adoption's marks: **behavior not characterized**, and **protected candidate** where it computes money, tax, or a reported figure. |
| `MISSING` | Extraction hole — carve it now and note how it was missed. |
| `APPLIED` | Nothing per object — the baseline refresh in step 5 absorbs it. |
| `UNDEPLOYED` (warning) | Leave it: repo → DB work in flight. Report it so the migration is not forgotten. |

Done when every finding is either applied or listed as pending with the decision it awaits and from whom.

## 5. Close the loop

When no finding is pending: re-run `extract_<dialect>.py --schema <schema> inventory` **once per schema that changed** (this deliberately moves the baseline to the state just absorbed), then `python db-schema/tools/erdgen.py`, then offline `python db-schema/tools/verify.py` — finish green (golden rule). When any finding is pending: run `erdgen.py` and offline `verify.py` the same way, leave the baseline where it is, and say so in the report — the next sync, after the decisions, moves it. Either way, the closing state — carved files, model docs, and baseline — belongs in one commit; leave it staged for the user to commit, unless they asked you to.

## 6. Report

End with: objects imported / updated / retired (paths), model docs touched, gaps opened (unconfirmed purposes, orphaned rules), findings pending a human decision — protected-rule changes awaiting their approver first, each with its impact — whether the baseline moved, the UNDEPLOYED list, and any harvest candidate from step 1, and a write-capable account from step 2. Name anything skipped: a silent skip is how drift becomes divergence.
