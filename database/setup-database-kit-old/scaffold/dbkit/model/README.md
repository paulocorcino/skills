# model/ — schema domain and diagrams

The schema's description layer: the **intent** (source, handwritten) and the
**diagrams** (generated). Do not keep DDL here — DDL lives in `schema/`.

| File | Nature | Who edits |
|---|---|---|
| `database.md` | **SOURCE** — domain, vocabulary, business rules | human/agent, by hand |
| `domains/<subdomain>.md` | **SOURCE** — a promoted subdomain (created on demand — growth contract below) | human/agent, by hand |
| `erd.mmd` | **GENERATED** — Mermaid diagram | `dbkit/tools/erdgen.py` |
| `schema.dbml` | **GENERATED** — DBML | `dbkit/tools/erdgen.py` |

> ⚠️ Never edit `erd.mmd`/`schema.dbml` by hand — they are overwritten. Run
> `python dbkit/tools/erdgen.py` after changing tables.

## `database.md` — the source of intent

Kept **alongside** the DDL: every new table has a section; every business rule has a
matching test in `dbkit/tests/`. On a fresh project, create the file from this skeleton
(fixed section order):

```markdown
# <Project> — Domain, vocabulary and business rules

> Canonical dialect: <dialect>.
> Tables: `dbkit/schema/tables/` · Diagram: `dbkit/model/erd.mmd` · Routines: `dbkit/schema/native/<dialect>/`.

## The business
<2–4 lines: what this system is, in domain terms>.

## Vocabulary (ubiquitous language)
| Term | Meaning | Table |
|---|---|---|

## Core business rules
- **<PREFIX>-<NN> — <name>**: <the rule> → `<routine or constraint that enforces it>`.

## Tables
<group by subdomain with `### <Group>` headings — mandatory from the first table; one block per table>

## Routines (N3 — `dbkit/schema/native/<dialect>/`)
<the routines table — see below>

## Conscious divergences from the original dump
<only if migrating an existing schema; otherwise omit>
```

### Per-table block

```markdown
#### <table>
- **Concept:** <what a row represents in the business>.
- **Invariants:** <what must always hold — each becomes a test in dbkit/tests/>.
- **Relations:** <cardinality and FK action with neighbors>.
```

### Materiality (adopted schemas)

On a fresh project every table earns its full block at creation. On an adopted
legacy schema, the full block is owed only where the table is **material**: it
holds rows, a routine touches it, or something references it (declared or
implied FK). Every other table keeps its one-line entry (`doccheck` requires
the mention), marked **elimination candidate** — the visibility is the point:
an owner either confirms its purpose (then it earns a block) or it becomes a
drop ticket. Reserve *model block pending* for material tables only.

### Growth contract

Rule IDs are `<PREFIX>-<NN>`: pick a short stable prefix per subdomain group
(e.g. `APP`, `MD`); rules that cut across subdomains use the catalog-wide prefix
(e.g. `CAT`). When `database.md` outgrows one comfortable read (~1,500 lines) or
sessions consistently touch a single subdomain, promote that `###` group — tables
and its rules together — to `domains/<subdomain>.md`, leaving `database.md` as the
map: business, vocabulary, cross-cutting rules, and the index of domain files.
Prefixed IDs make the move purely mechanical — nothing renumbers.

### Routines section

Map every N3 object → the business rule it implements (rules are numbered above).
Support objects under `native/<dialect>/` (`sequences/`, `synonyms/`, `types/` —
whichever the dialect has) are listed here too, by name with a one-line purpose —
`doccheck.py` fails when any native object is missing from the model docs:

```markdown
| Routine | Type | Rule it implements |
|---|---|---|
| `<name>(args)` | function/procedure/trigger/view | <PREFIX>-<NN> — <short label> |
```
