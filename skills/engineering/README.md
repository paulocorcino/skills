# Engineering skills

Coding agents write code the way a junior on a deadline does: whatever path the tooling lets through. They are fast, they are tireless, and they will declare victory the moment nothing complains.

These three skills give the agent what a senior engineer would give that junior: a plan with checkpoints, a reviewer who has to prove every claim, and a gate that will not let a shortcut through. Each one leans on scripts for whatever a script can decide, and keeps the model's judgment for what only judgment can do.

| Skill | When you reach for it | What you get |
|---|---|---|
| **[staged-plan](./staged-plan/SKILL.md)** | A change too big for one session | A plan that a chain of fresh agents executes stage by stage, green to green |
| **[reviewer](./reviewer/SKILL.md)** | A diff to review before it merges | Findings first, each one backed by a line, a command or a spec clause, plus an audit of what was and was not read |
| **[lint-gate](./lint-gate/SKILL.md)** | A repo whose linters let agent code slide | Strict linters at error, the rest of the debt frozen so it only shrinks, and a plan to pay it off |

They work alone, and they fit together: **plan** the work with staged-plan, let the agent build it, **review** it with reviewer, and let lint-gate **hold** the line on every change after that.

---

## staged-plan: big changes, one honest stage at a time

Long agent sessions rot. The context fills up, early decisions get forgotten, and "done" quietly drifts from what was asked.

staged-plan cuts a large track into 3–7 stages, each executed by a subagent with a **fresh context window**. The parent only moves on when the stage is green.

- **Every stage carries its checks.** Each check is one claim with a concrete value ("POST /tasks with an empty title returns 422"), proved by one named test or command. A claim with no nameable proof is too vague to write, so the planner asks instead of guessing.
- **Every stage has a file list.** A subagent that needs a file outside its list stops and reports instead of wandering.
- **The plan is the contract.** Anyone, human or agent, can open the markdown cold and run it correctly.
- **The skill only plans.** It investigates, designs, scaffolds the plan and its verify scripts, and stops. Execution follows the plan file.

Try it with: *"Plan the migration from lib-a to lib-b as a staged plan."*

## reviewer: a review you can audit

Most AI reviews are confident prose about code nobody checked. This one has a soul written into the skill: *"I would rather emit a narrow honest review than a wide review whose coverage I cannot defend."*

- **Findings first.** The report opens on what is wrong, with no summary in front of it.
- **Every finding cites evidence:** a `file:line`, command output, or a spec clause. A `HIGH` needs a reproduced failing check, a proven execution path, or a cited spec violation. Plausible but unproven defects become `OPEN_QUESTION` with what is needed to settle them, never a soft `HIGH`.
- **Coverage is audited by a script.** Every changed file ends up in the findings, reviewed, or explicitly listed as excluded or not reviewed, and every check not run is named with its reason. `audit.py` returns `gap` until that holds, and its verbatim output goes into the report.
- **Complexity comes from measurement.** McCabe numbers for the functions the change touches, mapped to severity by a fixed table, never by feel.

Try it with: *"Review this branch against main."*

## lint-gate: a linter config the agent cannot sweet-talk

A rule written in `AGENTS.md` is advice. A rule a tool checks is a gate. lint-gate takes a repo (Rust, TypeScript, Python, Go) to a hard gate:

1. **It measures before it suggests.** It writes a strict target config as a draft, runs your tools with it, and counts the debt each rule would raise, per scope, split between production and test code.
2. **It interviews you once,** with the numbers in hand: complexity limit, file size, line width, which optional families to adopt, who owns `console` or process spawns. Each question shows the debt curve, a recommendation, and the tightest value that costs nothing today.
3. **Every rule with no violation becomes an error at once.** The rules that still have violations go into a **debt list** inside the config, and a check in the gate and in CI keeps that list from ever growing.
4. **It writes a transition plan** for the remaining debt, in phases. Each rule has a class, and each class has a fix recipe: a dropped error reaches its caller, an escape hatch (`any`, `unwrap`, a cast) is narrowed once at the boundary, and a god file or god function is split by the responsibilities it already carries.
5. **It updates your `AGENTS.md`** with the gate command and the fix recipes. Rule names and numbers stay out of it, because they go stale.

It also closes the exits: the shortcuts that turn a gate green without fixing anything, from a suppression with no reason to a vendored folder nobody lints. Each one gets a check, and every row of the target gets a verdict, enforced by a script.

Two optional extras it can set up:

- **[anti-slop](https://github.com/dmmulroy/anti-slop)** rules for TypeScript, curated one by one: the casts and `unknown` widening that agents use to make code compile.
- **[ast-grep](https://ast-grep.github.io/)** for the agent's toolbox. In an end-to-end test (n=3 per arm), an agent with ast-grep installed but untaught never touched it. With a one-page guide and a pointer in `AGENTS.md`, it outlined large files instead of reading them whole, and finished the same task, with the same accuracy, at **half the cost**.

Its references are a germline no run changes: your repo's configs and its copy of the scripts are the soma, and what proves itself there comes back through maintenance. The target is a dated cache, not a memory. Before each run the skill checks every tool against its registry and against the tool's own rule list, so a new release doesn't leave it recommending last year's linters.

Try it with: *"Audit this repo's linters and tighten them."*

---

## Install

Each skill is a folder with a `SKILL.md`, the Agent Skills format that Claude Code, Codex, Cursor and many other agents load. Install with the [skills CLI](https://github.com/vercel-labs/skills) (Node 22.20+), from your project:

```sh
npx skills add paulocorcino/skills --skill lint-gate --skill reviewer --skill staged-plan
```

It asks which agents to install to; `-g` installs for every project, `-a claude-code` picks one agent. Or copy the folders by hand into your agent's skills folder:

```sh
git clone https://github.com/paulocorcino/skills.git
cp -r skills/skills/engineering/lint-gate skills/skills/engineering/reviewer skills/skills/engineering/staged-plan ~/.claude/skills/
```

Use `.claude/skills/` inside a repo to scope a skill to that project. The agent picks a skill up when your request matches its description, or when you call it by name (`/lint-gate`).

The scripts need Python and `git` on `PATH` (Python 3.11 or newer covers all three). reviewer's complexity script installs its own hash-pinned dependencies into the skill folder, never into your repo. lint-gate runs the linters your repo already has, plus the ones you approve.

## Feedback

These skills come out of daily use, and each one has been changed by runs where it fell short. If one misleads your agent, an issue with the transcript or the report is the most useful thing you can send.
