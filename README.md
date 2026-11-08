# Skills

Agent Skills for coding agents that write production code. Coding agents work the way a junior on a deadline does: whatever path the tooling lets through. These skills give the agent a senior's method instead: scripts decide what a script can decide, every claim carries its evidence, and the rule that matters is checked by a tool, not written in a doc.

They load in Claude Code, Codex, Cursor and the other agents that read the [Agent Skills](https://agentskills.io) format.

## The skills

**[Engineering](./skills/engineering/README.md)**: plan, review, and hold the line.

| Skill | What it does |
|---|---|
| [staged-plan](./skills/engineering/staged-plan/SKILL.md) | Splits a change too big for one session into stages that fresh agents run green to green |
| [reviewer](./skills/engineering/reviewer/SKILL.md) | Reviews a diff findings first, each finding backed by a line, a command or a spec clause |
| [lint-gate](./skills/engineering/lint-gate/SKILL.md) | Tightens a repo's linters to a hard gate, freezes the debt so it only shrinks, and plans the rest |

**[Database](./skills/database/README.md)**: a database governed as code.

| Skill | What it does |
|---|---|
| [database-setup](./skills/database/database-setup/SKILL.md) | Installs the method: the schema in plain SQL, the domain documented beside it, one command to validate |
| [database-modeling](./skills/database/database-modeling/SKILL.md) | Interviews you through the model, round by round, until nothing is silently assumed |
| [database-adoption](./skills/database/database-adoption/SKILL.md) | Brings a legacy database under governance, read-only, with the application code excavated for its rules |
| [database-sync](./skills/database/database-sync/SKILL.md) | Absorbs changes made directly in the live database, holding the ones that need a human decision |
| [database-audit](./skills/database/database-audit/SKILL.md) | Finds where the database spends and what is broken, every finding backed by numbers |

## Install

With the [skills CLI](https://github.com/vercel-labs/skills) (Node 22.20+), from your project:

```sh
npx skills add paulocorcino/skills                    # pick from the list
npx skills add paulocorcino/skills --skill lint-gate  # one skill
npx skills add paulocorcino/skills --skill lint-gate -g -a claude-code   # every project, one agent
```

Or clone the repo and copy a skill folder into your agent's skills folder (`~/.claude/skills/` for Claude Code). Each category README says what its skills need to run.

## Deprecated

[`deprecated/`](./deprecated/) holds skills that a newer one replaced. They stay for reference and are hidden from `npx skills`.
