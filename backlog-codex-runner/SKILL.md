---
name: backlog-codex-runner
description: Execute sequential repository backlog items by launching Codex CLI from the console with gpt-5.5 medium reasoning. Use when the user asks to run, continue, or automate docs/backlog items through a Codex CLI prompt such as "executar o backlog 024", "run next backlog", or "execute the backlog sequence"; do not use staged-plan for this workflow.
---

# Backlog Codex Runner

Run one backlog item at a time through Codex CLI, using either non-interactive `codex exec`, a gated AFK sequence, or a plan-first interactive Codex CLI session when the user wants to approve a full plan before implementation.

## Workflow

1. Read the requested backlog item from `docs/backlog`.
2. If the user asks for the next item, select the first numerically sorted `docs/backlog/*.md` file whose `Labels:` line does not contain `delivered` and whose body does not contain `Status: delivered`.
3. Launch Codex CLI with:
   - model: `gpt-5.5`
   - reasoning: `medium`
   - repository root as working directory
   - plan-first interactive mode when the user wants to approve the plan before implementation
   - non-interactive `codex exec` only when the user explicitly wants unattended execution
4. The launched Codex prompt must ask the executor to:
   - execute the backlog item;
   - make a short implementation plan first;
   - inspect relevant files before editing;
   - keep all repository documentation and code comments in English;
   - preserve AppUsage and legacy `runningprocess` boundaries;
   - run the narrowest relevant validations;
   - mark the backlog item delivered after delivery evidence exists, including checked acceptance criteria and a Delivery review section;
   - update `docs/backlog/README.md` so the sequence reflects the delivered item;
   - avoid touching unrelated dirty working-tree files;
   - report files changed, validations run, and skipped validations.
5. After the Codex CLI run finishes, inspect `git status --short`, identify the next backlog item, and report it to the user.

## AFK Sequence

When the user asks to run every open `Type: AFK` backlog item, execute them in numeric filename order with one separate Codex CLI run per file:

1. Select only files under `docs/backlog` that have `Type: AFK` and are not delivered.
2. For each file, run a separate `codex exec` invocation with `gpt-5.5` and medium reasoning.
3. Require the executor to produce a concise plan before editing.
4. Require the executor to mark the backlog file as delivered with evidence before committing.
5. Require one focused commit for the completed backlog item.
6. After each run, verify that `HEAD` changed and the backlog item is marked delivered.
7. Stop immediately if Codex exits non-zero, no commit was created, or the backlog item remains open.
8. Continue to the next file only after those checks pass.

For plan-first interactive AFK execution, use one interactive Codex CLI session per backlog item. The prompt must tell Codex to use the native planning flow first, wait for the user's approval or edits, then implement, validate, mark the backlog delivered, and commit. The runner waits for that session to close before checking the commit and moving to the next item.

Temporary prompt files are removed after the Codex session exits. Use `--keep-prompt` only when debugging the exact prompt sent to a session.

## Script

Prefer the bundled Python script because it works on Windows even when PowerShell script execution is restricted.

To open a visible interactive Codex CLI window for the next item:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --next --new-console
```

For all open `Type: AFK` items with native plan-first interaction:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --all-afk --plan-first-interactive
```

To run each item in a separate visible console window and wait before advancing:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --all-afk --plan-first-interactive --new-console
```

To run an interactive Codex CLI in the current terminal:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --item 024 --interactive
```

For unattended execution with `codex exec`:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --item 024
```

For the full open `Type: AFK` sequence:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --all-afk
```

To preview which files would run:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --all-afk --dry-run
```

For the next open item:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --next
```

To launch the next item in VS Code after the run:

```powershell
python .agents\skills\backlog-codex-runner\scripts\run_backlog_codex.py --next --open-next
```

The PowerShell script is also available when local execution policy allows `.ps1` files:

```powershell
.agents\skills\backlog-codex-runner\scripts\run-backlog-codex.ps1 -Item 024
```

For the next open item:

```powershell
.agents\skills\backlog-codex-runner\scripts\run-backlog-codex.ps1 -Next
```

## Manual Command Shape

If the script is unavailable, create a temporary prompt file and run:

```powershell
codex -C . -m gpt-5.5 -c 'model_reasoning_effort="medium"' -s danger-full-access -a on-request "Read and follow the backlog execution prompt in <PROMPT_FILE_PATH>."
```

Pipe a prompt that includes the backlog file path, backlog file contents, and this task line:

```text
Task: executar o backlog <BACKLOG_ID_OR_PATH>.
First produce a concise plan, then implement the backlog item end to end.
```

Do not use the `staged-plan` skill for this workflow unless the user explicitly changes direction.
