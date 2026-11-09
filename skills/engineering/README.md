# Engineering skills

A coding agent writes code like a junior developer with a deadline: it takes the easiest path the tools allow. It is fast, it never gets tired, and it says "done" as soon as nothing shows an error.

These three skills give the agent what a senior developer gives a junior:

- a plan with checkpoints;
- a reviewer who must prove every claim;
- a gate that blocks shortcuts.

Each skill uses scripts for everything a script can decide. The model's judgment is used only where judgment is needed.

| Skill | Use it when | What you get |
|---|---|---|
| **[staged-plan](./staged-plan/SKILL.md)** | A change is too big for one session | A plan that new agents run one stage at a time. Each stage must pass its checks before the next one starts |
| **[reviewer](./reviewer/SKILL.md)** | A diff needs a review before it is merged | The problems first, each one with its evidence (a line, a command or a spec), and a report of what was read and what was not |
| **[lint-gate](./lint-gate/SKILL.md)** | The repo's linters let bad agent code through | Strict linters that fail on errors, the existing problems blocked from growing, and a plan to fix them |

Each skill works alone, and they also work together: **plan** the work with staged-plan, let the agent build it, **review** it with reviewer, and let lint-gate **block** bad code in every change after that.

---

## staged-plan: a big change, one stage at a time

Long agent sessions get worse over time. The context fills up, the agent forgets early decisions, and "done" slowly moves away from what you asked for.

staged-plan splits a large piece of work into 3 to 7 stages. A subagent runs each stage with a **new, empty context**. The main agent moves to the next stage only when the current one passes its checks.

- **Each stage has its checks.** A check is one claim with a concrete value ("POST /tasks with an empty title returns 422"), proved by one named test or command. If no test or command can prove a claim, the claim is too vague, and the planner asks you instead of guessing.
- **Each stage has a list of files.** If a subagent needs a file that is not on its list, it stops and reports. It does not go looking around.
- **The plan is the contract.** Anyone, a person or an agent, can open the markdown file without other context and run it correctly.
- **Each stage reads only what it needs.** A stage gets the files it needs and little more, and it returns a short report. So no stage carries the context of another stage, and no information is lost between stages.
- **It knows when a plan is not needed.** If all the work fits in one session, it tells you to do the work directly, without a plan. Stages are useful only when the work is bigger than one context window.
- **The skill only plans.** It investigates, designs, and writes the plan and its check scripts, and then it stops. To run the work, follow the plan file.

Try it: *"Plan the migration from lib-a to lib-b as a staged plan."*

## reviewer: a review you can check

Most AI reviews are confident text about code that nobody checked. This skill has one principle written into it: *"I would rather emit a narrow honest review than a wide review whose coverage I cannot defend."* In other words: a small review that is true is better than a big review that cannot be verified.

- **Problems first.** The report starts with what is wrong. There is no summary before it.
- **Every finding has evidence:** a `file:line`, the output of a command, or a clause of a spec. A `HIGH` finding needs a failing check that was reproduced, a proven execution path, or a spec that the code breaks. A problem that seems likely but is not proven becomes an `OPEN_QUESTION`, with what is needed to answer it. It never becomes a weak `HIGH`.
- **A script checks what was reviewed.** Every changed file must appear in the findings, as reviewed, or in a list of files that were excluded or not reviewed. Every check that was not run is named, with the reason. `audit.py` returns `gap` until all of this is true, and its exact output goes into the report.
- **Complexity is measured.** The skill measures the McCabe complexity of the functions the change touches, and a fixed table turns the number into a severity. Nobody guesses it.

Try it: *"Review this branch against main."*

## lint-gate: linter rules the agent cannot get around

A rule written in `AGENTS.md` is only advice. A rule that a tool checks is a **gate**: the code cannot pass until it follows the rule. lint-gate brings a repo (Rust, TypeScript, Python or Go) to a strict gate:

1. **It measures first, and only then suggests.** It writes a strict target config as a draft, runs your tools with it, and counts how many problems each rule would find. We call these problems the **debt**. It counts them per part of the code, and separates production code from test code.
2. **It asks you questions once,** with the numbers ready: the complexity limit, the file size, the line width, which optional rule sets to use, and which module may write to the `console` or start processes. Each question shows the debt at each possible value, a recommendation, and the strictest value that costs nothing today.
3. **Every rule with no problems becomes an error right away.** Rules that still have problems go into a **debt list** inside the config. A check in the gate and in CI makes sure this list never grows. New code must follow every rule anyway: the gate fails on a problem in a line that the change adds, even when the rule is still on the debt list.
4. **It writes a transition plan** to fix the rest of the debt. The plan has phases, organized in **lanes**, so two phases never change the same files at the same time. Each rule belongs to a class, and each class has a recipe to fix it. For example: an error that the code ignores must reach the code that called it; an "escape hatch" (`any`, `unwrap`, a cast) is checked once, where the data enters the program; a file or function that does too much is split by the jobs it already does. The agent that works on a phase reads only that phase and its current state. Progress, answers and issues are recorded with commands, so nobody edits the plan by hand.
5. **It updates your `AGENTS.md`** with the gate command and the fix recipes. Rule names and numbers stay out of this file, because they get old.
6. **Run it again and it shows the progress.** It measures with the plan's own commands and reports what is left, rule by rule and phase by phase: what was fixed, what got worse, which rules can become errors now, and which rule someone turned off without a reason. It ends with the next step, and offers to open one issue for each phase.
7. **In a new repo, the gate starts on the first day.** When there is no code yet, it stops and tells you what to build first: a **walking skeleton**, the smallest version of the project that runs end to end. On the skeleton, it reads your ADRs (architecture decision records). For each rule that only one module may break (for example, only the CLI module may print), that module becomes the one exception. Every rule is an error, with no debt list and no plan.

It also closes the **exits**: the shortcuts that make a gate pass without fixing anything, from a suppression with no reason to a vendored folder that no linter checks. Each exit gets a check. Every row of the target gets a decision, and a script makes sure no row is skipped.

It can also set up two optional extras:

- **[anti-slop](https://github.com/dmmulroy/anti-slop)** rules for TypeScript, chosen one by one. They catch the casts and the `unknown` types that agents use to make code compile.
- **[ast-grep](https://ast-grep.github.io/)** as a tool for the agent. In an end-to-end test (3 runs per group), an agent that had ast-grep installed but no instructions never used it. With a one-page guide and a pointer in `AGENTS.md`, it read the outline of large files instead of the whole file, and it finished the same task, with the same accuracy, at **half the cost**.

The skill's own reference files never change during a run. Your repo gets its own copy of the configs and scripts, and that copy can change to fit your repo. A change that works well in a repo can come back into the skill later, through a separate maintenance step. The target rules have a date, and they are not trusted from memory: before each run, the skill checks every tool against its registry and against the tool's own list of rules. So a new release does not leave the skill recommending last year's linters.

Try it: *"Audit this repo's linters and tighten them."*

---

## Install

Each skill is a folder with a `SKILL.md` file. This is the Agent Skills format, which Claude Code, Codex, Cursor and many other agents can load. Install with the [skills CLI](https://github.com/vercel-labs/skills) (Node 22.20 or newer). Run it from your project:

```sh
npx skills add paulocorcino/skills --skill lint-gate --skill reviewer --skill staged-plan
```

It asks which agents to install to. `-g` installs for all your projects, and `-a claude-code` chooses one agent. You can also copy the folders by hand into your agent's skills folder:

```sh
git clone https://github.com/paulocorcino/skills.git
cp -r skills/skills/engineering/lint-gate skills/skills/engineering/reviewer skills/skills/engineering/staged-plan ~/.claude/skills/
```

To use a skill in one project only, put it in `.claude/skills/` inside that repo. The agent uses a skill when your request matches the skill's description, or when you call it by name (`/lint-gate`).

The scripts need Python and `git` on your `PATH` (Python 3.11 or newer works for all three skills). reviewer's complexity script installs its own dependencies, with pinned hashes, into the skill folder, never into your repo. lint-gate runs the linters your repo already has, plus the ones you approve.

## Feedback

These skills come from daily use, and each one has changed after runs where it did not do well. If a skill gives your agent the wrong direction, please open an issue with the transcript or the report. That is the most useful thing you can send.
