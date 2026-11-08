# baseline/ — the live database as last absorbed (versioned, governed)

What the adopted live database looked like the last time the repo absorbed its
changes. `reconcile` diffs the live catalog against these files to report drift, so
they are **governed state**, committed like `schema/` — never local scratch. Written by
the adoption tool (`db-schema/tools/extract_<dialect>.py`); empty until an adoption runs.

| File | What it holds | Who writes it |
|---|---|---|
| `inventory.<schema>.json` | one per adopted schema: every object's catalog fingerprint, dependencies, and carve target, plus a content hash of each watched table | `extract_<dialect>.py --schema <schema> inventory` |
| `exceptions.json` | human decisions: objects `excluded` or `blocked`, each with its reason | by hand, when the user decides |
| `watched-data.json` | tables whose **data** is part of a rule tagged **[protected]** (rates, reference prices): `[{"schema", "table", "rule"}]` | by hand, with the protected rule |

## Rules

- **Moving the baseline is a decision.** Re-running `inventory` makes the live state
  the new reference: do it only when every reconcile finding has been decided; the
  move belongs in the same commit as the carved files and model docs it accompanies — the diff is how
  a reviewer sees what was absorbed.
- **A missing baseline is restored from git**, never rebuilt by re-running `inventory`:
  that would turn whatever drift exists into the reference.
- The files hold names, fingerprints, row counts, and hashes — no row values and no
  definitions; the names are already in git through the carved DDL.
- Local working state of an adoption (connection ledger, probe, census, discovery)
  stays in `.scratch/adoption/`, gitignored.
