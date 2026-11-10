# Agent docs

What the gate tells the agent through the repo's agent doc. The doc is loaded in every session, so each line earns its place: it carries what the agent cannot find by looking, and leaves the rest to the gate.

## Which file

One canonical doc: `AGENTS.md` when the repo has it, or the agent doc it already uses. Every other agent doc (`CLAUDE.md`, an editor's rules file) points at it (`@AGENTS.md`, or one line naming it) instead of repeating it. A repo with none gets `AGENTS.md` and the pointers its agents read.

## What goes in

- **The gate command**, and when a change is done: the one command, and what a pass looks like.
- **The fast loop**: the per-edit hook and that its output is read, or, with no hook, the command that runs the fast linters on the changed files.
- **What to do when a rule fails**, by class: the recipes, in the words of this repo (its owning modules, its boundaries).
- **The exception form** of each stack, and that its reason names why the rule is wrong here.
- **What stays unchanged unless the task asks**: linter configs, baselines, ratchet constants. A count only goes down.
- **The behaviors of the decisions** the developer took (the module that owns spawns, where output is printed).
- **A pointer to each guide the run installed** (`ast-grep-guide.md`): one line whose words name the cases that reach it, so the agent opens the guide at the moment it needs it. A guide for work beyond the gate (reading, searching, rewriting code) gets its pointer outside the lint gate block, in the doc's section for tools (§ The tools section): under a lint heading, an agent that is reading code, not linting it, passes it by.

## What stays out

Rule names, thresholds and tool versions. They live in the configs and the CI pins, and a copy in the doc goes stale with the next bump. An agent cannot measure a score while it writes, so a number in the doc is a guess; the failing rule and the tool's own near-limit warning are the target. A tool's install line stays out unless finding it takes more than one lookup.

## When it changes

The doc states only checks that are on. Step 5 writes the block for the gate as step 5 leaves it, and turns each `advice` line that a rule now on checks into the behavior and the check. A line still `advice` stays as it is until its phase: each phase of the plan rewrites the lines of the rules it turns on, in the commit that turns them on.

## The block

Written in the language of the repo's docs; the `<...>` filled from this repo, the lines of a class with no rule on yet left out:

```markdown
## Lint gate

- Before you call a change done, run `<gate command | the CI steps, in order, until the gate command exists>`; it passes when <what a pass prints>.
- While you edit, <the hook runs the formatter and the fix command of each convention on, then the fast linters on each file you change: read its output and fix it before you go on | run `<fast command> <files>` on the files you changed>.
- When a rule fails, fix the cause:
  - an error, a `Result` or a Promise that nobody reads goes to its caller or to the log;
  - a fallback that hides a failure goes away, and the failure reaches `<the boundary that handles it>`;
  - `any`, a cast, `!` or `unwrap` becomes a value narrowed once, where it enters (`<boundary modules>`);
  - <output | a process spawn | exit> goes through `<owning module>`;
  - a function that is too complex is a god function, and a file that is too long a god file: split each by the responsibilities it already carries, one function or module per responsibility, or rewrite the function with guard clauses or a table of cases;
  - a duplicated block that is one rule becomes one function named for the rule; two rules that only look alike stay two, with the ignore marker and its reason.
- An exception is the last resort: `<exception form>`, with a reason that says why the rule is wrong at that line.
- Linter configs, baselines and ratchet constants change only when the task is about them, and a count only goes down.
- <With a debt list:> the lines you add meet every rule, the rules still on the debt list too: the gate fails on a debt rule's site on a new line.
```

## The tools section

When the repo has ast-grep installed, for navigation or for gate rules, its pointer goes in the doc's section for tools, or in a new one before the map of where things live:

```markdown
## Tools

- Before reading a whole source file, to find code by its shape (a call with a given argument, an empty block, an implementation), or to rewrite one shape at many sites, use ast-grep: `<path of the ast-grep guide>`.
```

This is the placement the guide was measured with (`repo.md` § ast-grep).
