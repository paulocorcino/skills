---
name: database-sync
description: Sync the dbkit repo with changes that happened in the adopted live database — run reconcile, then import each fact (new/changed objects carved, dropped objects retired, model docs updated) or flag it for a human decision. Use when the user wants to sync the repo with the database, absorb/import schema drift, or asks whether the DB changed.
---

Bring the repo back in line with the adopted live database. One direction only:
this skill moves facts **DB → repo** and never writes to the database (repo → DB
is `dbkit/migrations/`, out of scope here). It requires a completed adoption —
`dbkit/tools/extract_<dialect>.py` plus its committed inventory baseline — and
the `.env` connection; if either is missing, route to the `database-adoption`
skill instead.

## 1. Tool version check (precondition, seconds)

Sync tool versions per `database-adoption` step 4 (compare `__version__` of the
repo copy against the reference in that skill's `scripts/`; equal versions with
different content = a forgotten bump — diff, decide direction, bump, then
proceed).

## 2. Detect

Run `python dbkit/tools/verify.py --live` from the repo root. Green with no
warnings → report "repo and database in sync" and stop. Otherwise collect the
reconcile findings and act on each, in this order.

## 3. Act per finding — direction decisions, applied

| Finding | Action |
|---|---|
| `APPLIED` | Nothing per-object — the baseline refresh in step 4 absorbs it. |
| `NEW` | `extract_<dialect>.py carve --objects <name>` → model docs entry: evidence-based block if material (materiality rule in `dbkit/model/README.md`), one-liner otherwise; either way record the gap — *purpose unconfirmed, arrived outside the repo N.NN* — because a table that "appeared" has an intent only its author knows. |
| `DRIFT` | First check it is not the **regression of an intended repo change** (a pending migration touching the object): if it is, stop and put it to me. Otherwise re-carve the object and update its model block; if the change removed a constraint/trigger that backed a numbered rule, the rule's fate is a decision, not a deletion — put it to me. |
| `DROPPED` | Confirm no pending migration explains it, then delete the carved file and its model docs entry. If the object backed a numbered rule or is referenced by other model blocks, flag those in the report. Deletions are git-tracked — list every removed path explicitly. |
| `MISSING` | Extraction hole — carve it now and note how it was missed. |
| `UNDEPLOYED` (warning) | Leave it: that is repo → DB work in flight. Report it so no one forgets the migration. |

## 4. Close the loop

After all findings are handled: re-run `extract_<dialect>.py inventory` **once**
(this deliberately moves the baseline to the state just absorbed), then
`python dbkit/tools/erdgen.py`, then offline `python dbkit/tools/verify.py` —
never finish red (golden rule).

## 5. Report

End with: objects imported / updated / retired (paths), model docs touched, gaps
opened (unconfirmed purposes, orphaned rules), findings left pending a human
decision, and the UNDEPLOYED list. If anything was skipped, say so — a silent
skip is how drift becomes divergence.
