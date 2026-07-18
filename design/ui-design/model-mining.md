# model-mining — turning the database model into UI decisions

When `dbkit/model/database.md` (or a `dbkit/model/domains/` shard) exists, mine it before asking anything in **Forms & CRUD** or **Identity & access**. Each mapping yields an established decision, not a question:

- identity and natural keys → the immutable-after-create set
- optionality → required fields per mode (create vs. edit)
- numbered business rules → form validation, and the after-save behavior the UI must reflect: what the database enforces itself (trigger-created rows, generated keys, defaulted values, uniqueness) the UI shows happening — it never asks the user to do it, never re-validates it in parallel
- lifecycle and state transitions → which actions each state enables, and which feedback states each form needs
- master data → selects and reference pickers
- an entity's column count and relations → its CRUD surface (inline / drawer / modal / full page)
- catalog-wide conventions (timestamp basis, collation and folding) → display formatting everywhere — the UI inherits them
- user, group, and permission tables → the established RBAC facts the menu and actions surface — the UI never grows a parallel role scheme

Ask only what the model leaves open.
