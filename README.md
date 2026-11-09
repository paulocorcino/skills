# Skills

Agent Skills for coding agents that write production code.

A coding agent works like a junior developer with a deadline: it takes the easiest path the tools allow. These skills give the agent the method of a senior developer instead:

- a script decides everything a script can decide;
- every claim comes with its evidence;
- an important rule is checked by a tool, not only written in a document.

The skills work in Claude Code, Codex, Cursor and other agents that read the [Agent Skills](https://agentskills.io) format.

## The skills

**[Engineering](./skills/engineering/README.md)**: plan the work, review it, and keep the quality from going down.

| Skill | What it does |
|---|---|
| [staged-plan](./skills/engineering/staged-plan/SKILL.md) | Splits a change that is too big for one session into stages. A new agent runs each stage, and each stage must pass its checks before the next one starts |
| [reviewer](./skills/engineering/reviewer/SKILL.md) | Reviews a diff. Problems come first, and each one points to a line, a command or a spec |
| [lint-gate](./skills/engineering/lint-gate/SKILL.md) | Makes a repo's linters strict, stops the existing problems from growing, and plans how to fix the rest |

**[Database](./skills/database/README.md)**: manage a database the same way you manage code.

| Skill | What it does |
|---|---|
| [database-setup](./skills/database/database-setup/SKILL.md) | Installs the method: the schema in plain SQL, the domain documented next to it, and one command that validates both |
| [database-modeling](./skills/database/database-modeling/SKILL.md) | Asks you questions about the model, round by round, until nothing is left to guess |
| [database-adoption](./skills/database/database-adoption/SKILL.md) | Brings an old database into the repo. It only reads the database, and it searches the application code for the business rules |
| [database-sync](./skills/database/database-sync/SKILL.md) | Brings into the repo the changes someone made directly in the live database. Changes that need a person's decision wait for that decision |
| [database-audit](./skills/database/database-audit/SKILL.md) | Finds what costs the most in the database and what is broken. Every finding comes with numbers |

## Install

Use the [skills CLI](https://github.com/vercel-labs/skills) (Node 22.20 or newer). Run it from your project:

```sh
npx skills add paulocorcino/skills                    # choose from the list
npx skills add paulocorcino/skills --skill lint-gate  # one skill
npx skills add paulocorcino/skills --skill lint-gate -g -a claude-code   # all your projects, one agent
```

You can also clone the repo and copy a skill folder into your agent's skills folder (`~/.claude/skills/` for Claude Code). The README of each category says what its skills need to run.

## Deprecated

The [`deprecated/`](./deprecated/) folder has skills that a newer skill replaced. They are there for reference only, and `npx skills` does not show them.
