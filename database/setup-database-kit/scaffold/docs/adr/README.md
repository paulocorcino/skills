# adr/ — architecture decision records

One decision per file, immutable once accepted (like migrations: to change a decision,
write a new ADR that supersedes the old one). Name: `NNNN-<kebab-case-title>.md`
(e.g. `0001-uuid-primary-keys.md`).

Write an ADR only when the decision is hard to reverse **and** surprising without
context **and** has a real trade-off. Everything else belongs in `dbkit/model/database.md`
(domain) or in code review.

## Template

```markdown
# NNNN — <decision, stated as a fact>

- Status: accepted | superseded by NNNN
- Date: YYYY-MM-DD

## Context
<2–5 lines: the forces that made this a decision, not a default>.

## Decision
<what was decided, imperative and specific>.

## Alternatives rejected
- **<alternative>** — <why it lost, one line>.

## Consequences
<what becomes easier, what becomes harder, what to watch>.
```
