---
name: ui-design
description: Grill the user through the product's UI/UX, one decision at a time — sweep every design theme, answer what the context already answers, surface the gaps only a human can close, and route each decision into the design system doc. Use when the user wants to define the product's look and feel, choose the delivery target (responsive web, PWA, admin portal, landing), settle navigation or CRUD form patterns, or asks for screens while gaps remain.
---

Interview me relentlessly about the product's UI/UX until every theme below is resolved or explicitly out of scope. Fire a tracer through the themes in order: where `CONTEXT.md`, an ADR, `docs/ui/mock/design.md`, `dbkit/model/database.md` (and its `dbkit/model/domains/` shards, when present), or the codebase already answers, decide it yourself, record it, and announce it as established. Where nothing answers, you have found a **gap** — a decision only I can make. Put gaps to me one per turn, each with your recommended answer — the boring mainstream choice that fits this product; an exotic option only when the context genuinely demands it — and its trade-off, and wait before the next.

The machinery stays hidden. I experience a short conversation about my product: one gap at a time, only what the context can't answer, the theme list invisible. But when my answer opens a branch — I linger on form behavior, I push on navigation — that appetite is a signal: expand that theme into its finer decisions, each with a recommendation, until the branch is closed.

Evidence lives in `docs/ui/mock/` — create the folder if it is missing, and before asking anything about visual language, invite me to drop material there: a `design.md`, HTML mockups, screenshots (suggest Google Stitch when I have nothing yet — its HTML exports are exactly the evidence this tracer eats). Then read everything in it and mine it: palette, density, shape language, typography, tone.

An HTML mock is the richest evidence — dissect it from the console: parse markup, styles, and scripts to reconstruct each page's business purpose, its components, states, navigation, and interaction dynamics, and register each as an established decision. When the mock set is large, fan out subagents to survey it and keep only the conclusions. If you later touch a mock — extend it, wire it, restyle it — every behavior it already had survives: verify from the source (and headless, via `webapp-testing`, when it runs).

When I paste a screenshot mid-interview, treat it as the answer to the current gap and extract the decisions it embodies. An existing `docs/ui/mock/design.md` is a head start, not a constraint — validate it against my answers and extend it; a missing one you build from the answers as they land.

## The themes

Walk them in dependency order — audience before delivery target, delivery target before stack, stack before shell.

- **Product & audience** — what the business does (from `CONTEXT.md` / model docs); who the primary users are; where they use it (desk-bound back office, field mobile, both); what one session accomplishes
- **Delivery target** — responsive web app (mobile + desktop), mobile-first PWA, corporate admin portal, MPA / landing pages / hotsite, native shell; installability and offline expectations
- **Stack & framework** — fit the target and whatever the repo already uses. Defaults, not mandates: Tailwind + shadcn/ui for a React web app; PrimeVue or Vuetify if the stack is Vue; DaisyUI when Tailwind-only with no component framework; Konsta, Framework7, or Onsen only when a native-feel mobile shell is the target
- **Visual language** — brand personality, information density, shape and radius language, typography roles, color roles (functional, not decorative) → tokens
- **App shell & navigation** — sidebar, drawer (hamburger), or bottom navigation, chosen by target; menu driven by permissions (RBAC) so users never see what they cannot do; active state tracking
- **Forms & CRUD** — creation vs. edition duality (what is immutable after create); asymmetric validation (what create requires that edit relaxes, and vice versa); the surface per entity weight — inline editing for flat high-frequency rows, drawer/side panel for medium forms that keep list context, modal for short confirmations, full page for heavy entities; dirty form guard on navigation; reset and cleanup lifecycle. When `dbkit/model/database.md` exists, most of this theme — and much of Identity & access — is already decided there: mine it per [model-mining.md](model-mining.md) before asking
- **Feedback & states** — loading (skeleton vs spinner), empty states that teach, error recovery, success confirmation; optimistic vs pessimistic updates; toast vs inline per severity
- **Identity & access** — authentication surface; user management screens; roles as the single source feeding both menu visibility and action availability
- **Responsiveness** — breakpoints; what collapses, stacks, or disappears at each

Deliberately outside the tracer: component implementation, copywriting, performance budgets, accessibility audits — build work follows the design system; it enters through `/to-issues` or `/to-tickets` tickets.

When my answer is vague, sharpen it against a concrete screen ("show me the busiest screen a user sees on Monday morning"); when I claim a pattern preference, stress it with a scenario before accepting it.

## Routing

Route each resolved decision the moment it lands:

- a visual token (color, type role, radius, spacing) → the frontmatter of `docs/ui/mock/design.md`
- a pattern or behavior rule (navigation model, CRUD surface, feedback dynamics, RBAC menu rule) → its section in `docs/ui/mock/design.md` — create the section if absent
- hard to reverse **and** surprising without context **and** a real trade-off → an ADR in `docs/adr/` (delivery target and framework choice usually qualify; drawer-vs-modal does not). Reference `docs/ui/mock/design.md` from the ADR, and note the companion skills the executor should invoke — check which actually exist in the current environment (e.g. `frontend-design`, `theme-factory`, `webapp-testing`) rather than assuming

The design is ready when every theme is routed or out of scope and I confirm shared understanding. Until then, screens wait. On confirmation, offer `/to-issues` or `/to-tickets` — the populated `docs/ui/mock/design.md` is the spec it slices.
