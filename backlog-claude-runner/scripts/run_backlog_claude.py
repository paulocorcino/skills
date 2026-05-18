#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import json
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_EXEC_MODEL = "claude-sonnet-4-6"
DEFAULT_EXEC_EFFORT = "low"
DEFAULT_CACHE_LIMIT = 2_000_000  # 2M tokens for Opus
DEFAULT_CACHE_THRESHOLD = 80  # percentage
DEFAULT_CACHE_CHECK_INTERVAL = 300  # 5 minutes


def run_text(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


def repo_root():
    try:
        root = run_text(["git", "rev-parse", "--show-toplevel"], None)
    except subprocess.CalledProcessError as exc:
        raise SystemExit("This script must run inside a git repository.") from exc
    return Path(root).resolve()


def _backlog_dir(root):
    for candidate in (root / "docs" / "backlog", root / "docs" / "backlogs"):
        if candidate.is_dir():
            return candidate
    return root / "docs" / "backlog"  # default for error messages


def backlog_files(root):
    backlog_dir = _backlog_dir(root)

    def has_numeric_prefix(name):
        dash = name.find("-")
        return dash > 0 and name[:dash].isdigit()

    def sort_key(path):
        dash = path.name.find("-")
        return (int(path.name[:dash]), path.name)

    return sorted(
        (path for path in backlog_dir.glob("*.md") if has_numeric_prefix(path.name)),
        key=sort_key,
    )


def _field_value(line, field):
    stripped = line.lstrip("-*> \t").replace("**", "").replace("__", "")
    prefix = f"{field}:"
    if not stripped.lower().startswith(prefix.lower()):
        return None
    return stripped[len(prefix):].strip()


def is_delivered(path):
    import re
    if not path.exists():
        return (path.parent / "closed" / path.name).exists()
    for line in path.read_text(encoding="utf-8").splitlines():
        flat = line.replace("**", "").replace("__", "").lower()
        if re.search(r"status\s*:\s*delivered\b", flat):
            return True
        if re.search(r"labels\s*:[^\n]*\bdelivered\b", flat):
            return True
        if re.search(r"type\s*:[^\n]*\bdelivered\b", flat):
            return True
    return False


def is_afk(path):
    import re
    for line in path.read_text(encoding="utf-8").splitlines():
        value = _field_value(line, "Type")
        if value is None:
            continue
        first_token = re.split(r"[\s\-—–|,;]", value.strip(), maxsplit=1)[0]
        if first_token.upper() == "AFK":
            return True
    return False


def open_afk_backlog_files(root):
    return [path for path in backlog_files(root) if is_afk(path) and not is_delivered(path)]


def resolve_item(root, item, use_next):
    files = backlog_files(root)
    if use_next:
        for path in files:
            if not is_delivered(path):
                return path
        raise SystemExit("No undelivered backlog item found under docs/backlog.")

    if not item:
        raise SystemExit("Provide --item <NNN|path> or use --next.")

    candidate = Path(item)
    if candidate.exists():
        return candidate.resolve()

    normalized = item.strip()
    if normalized.isdigit():
        target = int(normalized)
        for path in files:
            dash = path.name.find("-")
            if dash > 0 and path.name[:dash].isdigit() and int(path.name[:dash]) == target:
                return path

    for path in files:
        if normalized.lower() in path.name.lower():
            return path

    raise SystemExit(f"Could not resolve backlog item '{item}'.")


def next_after(root, current):
    seen_current = False
    for path in backlog_files(root):
        if seen_current and not is_delivered(path):
            return path
        if path.name == current.name:
            seen_current = True
    return None


def git_status(root):
    result = subprocess.run(["git", "status", "--short"], cwd=root, text=True, capture_output=True, check=False)
    return result.stdout.strip()


def git_head(root):
    return run_text(["git", "rev-parse", "HEAD"], root)


def claude_executable():
    resolved = shutil.which("claude")
    if resolved:
        return resolved
    if os.name == "nt":
        try:
            found = subprocess.check_output(["where.exe", "claude"], text=True, stderr=subprocess.DEVNULL).splitlines()
        except subprocess.CalledProcessError:
            found = []
        if found:
            return found[0]
    return "claude"


def make_prompt(root, backlog_path):
    relative = backlog_path.relative_to(root).as_posix()
    skill_path = (root / ".agents" / "skills" / "backlog-claude-runner" / "SKILL.md").resolve()
    status = git_status(root)
    content = backlog_path.read_text(encoding="utf-8")
    return f"""Task: executar o backlog {relative}.

You are running from Claude Code CLI as the implementation executor for this repository.
This runner skill is repository-local at `{skill_path}`.

Required execution model:
1. Read CLAUDE.md/AGENTS.md/repository instructions and the backlog item below.
2. Produce a concise plan first.
3. Implement the backlog item end to end, staying within the requested backlog scope.
4. Inspect relevant files before editing.
5. Keep repository documentation and code comments in English.
6. Preserve the distinction between legacy runningprocess and AppUsage.
7. Treat process, user, browser, URL, window title, command line, and document data as sensitive.
8. Do not revert unrelated working-tree changes. Work with existing changes only when they belong to this backlog item.
9. Run the narrowest relevant validations.
10. Before committing, mark the backlog item as completed: change its labels/status to delivered, tick completed acceptance criteria, add or update a Delivery review section with concrete evidence, validations run, and any skipped or unavailable validation.
11. Update docs/backlog/README.md so the sequence reflects that this backlog item is delivered.
12. Commit the completed backlog item after validations pass. Use one focused commit for this backlog item, including code, tests, backlog status updates, and related documentation for this backlog item.
13. Final response must list files changed, important decisions, validations run, validations skipped or unavailable, and the commit SHA.

Initial git status:
```
{status}
```

Backlog item path: {relative}

Backlog item contents:
```
{content}
```
"""


def claude_exec(root, prompt, model):
    command = [
        claude_executable(),
        "-p",
        "--model",
        model,
        "--dangerously-skip-permissions",
        prompt,
    ]
    return subprocess.run(command, cwd=root, text=True, check=False)


def make_interactive_prompt(prompt_path, plan_first):
    if plan_first:
        return (
            "Read and follow the backlog execution prompt in this file: "
            f"{prompt_path}. Enter Plan Mode first: produce a complete plan, "
            "wait for my approval or edits, and only then implement, validate, mark the backlog delivered, "
            "and commit. Use ExitPlanMode to surface the plan for approval before making edits."
        )

    return (
        "Read and follow the backlog execution prompt in this file: "
        f"{prompt_path}. Start by summarizing your plan, then execute it. "
        "If you need clarification, ask me in this interactive Claude CLI session."
    )


def interactive_command(root, prompt_text, model, effort=None, remote_control=False):
    cmd = [
        claude_executable(),
        "--model",
        model,
        "--dangerously-skip-permissions",
    ]
    if remote_control:
        cmd.append("--remote-control")
    if effort:
        cmd += ["--effort", effort]
    cmd.append(prompt_text)
    return cmd


def run_one_exec(root, backlog_path, require_commit, model):
    before_head = git_head(root)
    prompt = make_prompt(root, backlog_path)
    print()
    print(f"=== Running {backlog_path.relative_to(root).as_posix()} ===")
    completed = claude_exec(root, prompt, model)
    after_head = git_head(root)

    if completed.returncode != 0:
        print(f"Stopping: Claude CLI exited with code {completed.returncode}.")
        return completed.returncode

    if require_commit and before_head == after_head:
        print("Stopping: backlog execution finished but no new commit was created.")
        return 2

    if not is_delivered(backlog_path):
        print("Stopping: backlog execution finished but the backlog item is still not marked delivered.")
        return 3

    print(f"Delivered: {backlog_path.relative_to(root).as_posix()}")
    if before_head != after_head:
        subject = run_text(["git", "log", "-1", "--pretty=%h %s"], root)
        print(f"Commit: {subject}")
    return 0


def remove_prompt_file(prompt_path, keep_prompt):
    if keep_prompt:
        return
    try:
        prompt_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Warning: could not remove temporary prompt file {prompt_path}: {exc}")


def run_one_interactive(root, backlog_path, require_commit, plan_first, new_console, model, debug=False, keep_prompt=False, remote_control=False):
    before_head = git_head(root)
    prompt = make_prompt(root, backlog_path)
    prompt_path = write_prompt_file(root, backlog_path, prompt)
    interactive_prompt = make_interactive_prompt(prompt_path, plan_first)

    print()
    print(f"=== Running interactive {backlog_path.relative_to(root).as_posix()} ===")
    print(f"Prompt file: {prompt_path}")

    try:
        if new_console:
            completed = launch_interactive_console(root, interactive_prompt, model, wait=True, debug=debug, remote_control=remote_control)
        else:
            completed = subprocess.run(interactive_command(root, interactive_prompt, model, remote_control=remote_control), cwd=root, check=False)
    finally:
        remove_prompt_file(prompt_path, keep_prompt)

    after_head = git_head(root)
    has_new_commit = before_head != after_head
    delivered = is_delivered(backlog_path)

    if completed.returncode != 0 and not (has_new_commit and delivered):
        print(f"Stopping: interactive Claude CLI exited with code {completed.returncode}.")
        return completed.returncode

    if completed.returncode != 0:
        print(f"Interactive Claude CLI exited with code {completed.returncode}, but delivery gates passed; continuing.")

    if require_commit and not has_new_commit:
        print("Stopping: interactive backlog execution finished but no new commit was created.")
        return 2

    if not delivered:
        print("Stopping: interactive backlog execution finished but the backlog item is still not marked delivered.")
        return 3

    print(f"Delivered: {backlog_path.relative_to(root).as_posix()}")
    if has_new_commit:
        subject = run_text(["git", "log", "-1", "--pretty=%h %s"], root)
        print(f"Commit: {subject}")
    return 0


def plan_file_path(root, backlog_path):
    # Plans land under <repo>/docs/plans/ — the canonical location the
    # staged-plan skill scaffolds against. Previously this used
    # `.agents/tmp/backlog-claude-runner/`, which forced the staged-plan skill
    # to bypass its deterministic scaffold (the scaffold's location guard
    # rejected paths outside docs/plans/), producing structurally divergent
    # plans across invocations. With the scaffold now path-agnostic-within-repo
    # AND this dir matching the scaffold default, the two skills compose
    # cleanly: every plan goes through the deterministic scaffold path.
    plan_dir = root / "docs" / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    return plan_dir / f"{backlog_path.name.removesuffix('.md')}-plan.md"


def make_staged_plan_prompt(root, backlog_path, plan_path):
    relative = backlog_path.relative_to(root).as_posix()
    content = backlog_path.read_text(encoding="utf-8")
    return f"""Task: Generate a staged implementation plan for backlog item {relative}.

Invoke the `staged-plan` skill to design a multi-stage plan for the backlog item below.

Hard constraints:
- Do NOT enter plan mode. Do NOT implement, edit, validate, or commit anything.
- The skill is a PLANNING skill — produce the plan only and stop.
- Non-interactive context: the environment variable `STAGED_PLAN_NONINTERACTIVE=1` is set. Follow the skill's "Non-interactive" branch of the Pre-scaffold approval gate: emit the `<<PRE_SCAFFOLD_SUMMARY>>...<<END>>` block to stdout, then run `scaffold.py` (do NOT call `AskUserQuestion` — there is no human to answer).
- Run `scaffold.py` with `--output {plan_path}` so the deterministic boilerplate is rendered. Do NOT hand-write the plan markdown; hand-rolled plans diverge in structure across invocations and bypass the pre-execution placeholder gate. Then `Edit` to replace each `<FILL>` placeholder.
- After writing the plan to disk, your final line of output must be exactly:
  PLAN_WRITTEN: {plan_path}

============================================================
MANDATORY: APPEND THE FOLLOWING BLOCK VERBATIM AT THE VERY END OF THE PLAN FILE
============================================================
This block is NOT optional. It is NOT a suggestion. It MUST be the LAST section
of the generated plan markdown, copied EXACTLY as written below, including the
heading, every bullet, every backtick, every newline, and the final token.
The executor of this plan has NO prior context and will rely on this block to
close out delivery. If this block is missing, the plan is invalid.

--- BEGIN APPENDED BLOCK (copy literally to end of plan) ---

## Delivery & Exit Instructions (mandatory, do not skip, not delegate to subagents, execute main agent only, last message execution to finish)

*** DONT SKIP OR DELEGATE THESE INSTRUCTIONS FOR SUBAGENTS ***

Backlog item: `{relative}`

Before committing, the following are mandatory:

1. Update `{relative}`: change the Status/Labels line to indicate `delivered`,
   tick (`[x]`) the Acceptance Criteria items that were fulfilled, and add
   (or update) a `## Delivery review` section at the end of the file
   containing: files changed (list), validations run with their result,
   validations skipped or unavailable with the reason, and any relevant
   decisions.
2. Update `docs/backlog/README.md` to reflect that this item was delivered.
3. Create exactly one focused commit including code, tests, backlog updates,
   and related documentation — short message in the repository's style.

Final response must list: files changed, validations run, validations
skipped, and the commit SHA.

When (and only when) every mandatory step above is done and the commit is
created, end your final message with this token on its own line:

BACKLOG_RUNNER_DONE_EXIT

--- END APPENDED BLOCK ---
============================================================

Backlog item path: {relative}

Backlog item contents:
```
{content}
```
"""


def make_execute_plan_prompt(root, backlog_path, plan_path):
    relative = backlog_path.relative_to(root).as_posix()
    status = git_status(root)
    return f"""Task: executar o backlog {relative} seguindo o plano em {plan_path}.

You are running in a fresh Claude Code CLI session with no prior context.
Read the plan file at {plan_path} and execute it stage by stage.

Required execution model:
1. Read CLAUDE.md/AGENTS.md/repository instructions and the plan file.
2. Implement each stage in order, staying within the requested backlog scope.
3. Inspect relevant files before editing.
4. Keep repository documentation and code comments in English.
5. Run the narrowest relevant validations after each stage.
6. Do not revert unrelated working-tree changes.
7. Before committing, mark the backlog item {relative} as completed: change its labels/status to delivered, tick completed acceptance criteria, add or update a Delivery review section with concrete evidence, validations run, and any skipped or unavailable validation.
8. Update docs/backlog/README.md so the sequence reflects that this backlog item is delivered.
9. Commit the completed backlog item in one focused commit (code, tests, backlog status updates, and related documentation for this backlog item).
10. Final response must list files changed, important decisions, validations run, validations skipped or unavailable, and the commit SHA.

Initial git status:
```
{status}
```

Backlog item path: {relative}
Plan file path: {plan_path}
"""


def run_one_via_staged_plan(root, backlog_path, require_commit, model, new_console, debug=False, keep_prompt=False, auto_continue=False, exec_model=DEFAULT_EXEC_MODEL, exec_effort=DEFAULT_EXEC_EFFORT, remote_control=False):
    relative = backlog_path.relative_to(root).as_posix()
    plan_path = plan_file_path(root, backlog_path)

    print()
    print(f"=== Planning {relative} ===")
    print(f"Plan target: {plan_path}")

    plan_prompt = make_staged_plan_prompt(root, backlog_path, plan_path)
    plan_cmd = [
        claude_executable(),
        "-p",
        "--model",
        model,
        "--dangerously-skip-permissions",
        plan_prompt,
    ]
    # Signal non-interactive mode to the staged-plan skill: AskUserQuestion
    # would hang in `claude -p`, and there is no plan-mode tool here. The
    # skill detects this env var, emits a <<PRE_SCAFFOLD_SUMMARY>> block to
    # stdout for audit, and proceeds straight to scaffold + fill without
    # prompting. See staged-plan/SKILL.md § Pre-scaffold approval gate.
    plan_env = os.environ.copy()
    plan_env["STAGED_PLAN_NONINTERACTIVE"] = "1"
    set_runner_phase("planning", root)
    completed = subprocess.run(plan_cmd, cwd=root, text=True, check=False, env=plan_env)
    if completed.returncode != 0:
        print(f"Stopping: planning session exited with code {completed.returncode}.")
        return completed.returncode

    if not plan_path.exists():
        print(f"Stopping: planning session finished but plan file was not created at {plan_path}.")
        return 4

    print(f"Plan written: {plan_path}")
    if not auto_continue:
        print()
        print("Review or edit the plan now. Press Enter to execute it, or Ctrl-C to abort.")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            print("Aborted before execution.")
            return 130

    before_head = git_head(root)
    interactive_prompt = (
        f"Execute {plan_path}"
    )

    print()
    print(f"=== Executing {relative} (model={exec_model}, effort={exec_effort}) ===")
    set_runner_phase("executing", root)
    pid_file = Path(tempfile.mkstemp(prefix="backlog-claude-runner-", suffix=".pid")[1])
    env = os.environ.copy()
    env["BACKLOG_RUNNER_PID_FILE"] = str(pid_file)
    try:
        if new_console:
            completed = launch_interactive_console(root, interactive_prompt, exec_model, wait=True, debug=debug, effort=exec_effort, env=env, pid_file=pid_file, remote_control=remote_control)
        else:
            cmd = interactive_command(root, interactive_prompt, exec_model, effort=exec_effort, remote_control=remote_control)
            proc = subprocess.Popen(cmd, cwd=root, env=env)
            pid_file.write_text(str(proc.pid))
            return_code = proc.wait()
            completed = subprocess.CompletedProcess(cmd, return_code)
    finally:
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    after_head = git_head(root)
    has_new_commit = before_head != after_head
    delivered = is_delivered(backlog_path)

    hook_killed = completed.returncode in (143, -15)
    if completed.returncode != 0 and not hook_killed:
        print(f"Stopping: execution session exited with code {completed.returncode} (not the hook's SIGTERM).")
        return completed.returncode
    if hook_killed:
        print("Auto-exit token detected; Claude session was terminated by Stop hook.")

    if require_commit and not has_new_commit:
        print(f"Stopping: no new commit created (HEAD still {before_head[:8]}). The executor likely emitted the DONE_EXIT token without actually running `git commit`.")
        return 2

    if not delivered:
        print(f"Stopping: {relative} is still not marked `delivered`. The executor likely skipped the backlog bookkeeping step.")
        return 3

    clear_runner_phase()
    print(f"Delivered: {relative}")
    if has_new_commit:
        subject = run_text(["git", "log", "-1", "--pretty=%h %s"], root)
        print(f"Commit: {subject}")
    return 0


def run_afk_sequence(root, dry_run, require_commit, model, plan_first_interactive=False, new_console=False, debug=False, keep_prompt=False, via_staged_plan=False, auto_continue=False, exec_model=DEFAULT_EXEC_MODEL, exec_effort=DEFAULT_EXEC_EFFORT, cache_threshold=None, cache_check_interval=DEFAULT_CACHE_CHECK_INTERVAL, remote_control=False):
    items = open_afk_backlog_files(root)
    if dry_run:
        if not items:
            print("No open Type: AFK backlog item found.")
            return 0
        mode = "via-staged-plan" if via_staged_plan else ("plan-first-interactive" if plan_first_interactive else "claude-exec")
        print(f"Mode: {mode}")
        for path in items:
            print(path.relative_to(root).as_posix())
        return 0

    if not items:
        print("No open Type: AFK backlog item found.")
        return 0

    print("Open Type: AFK backlog sequence:")
    for path in items:
        print(f"- {path.relative_to(root).as_posix()}")

    state_file = Path.home() / ".claude" / ".backlog-cache-state"

    for i, path in enumerate(items):
        # Check cache reset timer before starting new plan (skip first item)
        if i > 0 and cache_threshold is not None:
            minutes_until, _ = get_cache_reset_time(cache_check_interval)
            if minutes_until > 0:
                print(f"\n📊 Cache still warming up: {minutes_until:.1f} minutes until reset")
                wait_for_cache_reset_by_time(minutes_until, cache_check_interval)

        if via_staged_plan:
            code = run_one_via_staged_plan(root, path, require_commit, model, new_console, debug=debug, keep_prompt=keep_prompt, auto_continue=auto_continue, exec_model=exec_model, exec_effort=exec_effort, remote_control=remote_control)
        elif plan_first_interactive:
            code = run_one_interactive(root, path, require_commit, plan_first=True, new_console=new_console, model=model, debug=debug, keep_prompt=keep_prompt, remote_control=remote_control)
        else:
            code = run_one_exec(root, path, require_commit, model)

        # Record execution time for next cache reset calculation
        if code == 0:
            save_execution_time(state_file)

        if code != 0:
            if code not in (130, -2) and handle_rate_limit(root, sys.argv):
                return 0  # at job scheduled; exit cleanly
            return code

    print()
    print("All open Type: AFK backlog items were processed.")
    return 0


def write_prompt_file(root, backlog_path, prompt):
    prompt_dir = root / ".agents" / "tmp" / "backlog-claude-runner"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f"{backlog_path.name.removesuffix('.md')}-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def is_wsl():
    if os.name != "posix":
        return False
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def shell_quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def launch_wsl_console(root, claude_command, wait, debug):
    distro = os.environ.get("WSL_DISTRO_NAME", "")
    inner = " ".join(shell_quote(part) for part in claude_command)
    bash_cmd = f"cd {shell_quote(str(root))} && {inner}"
    if wait:
        bash_cmd += "; ec=$?; echo; read -p 'Claude finished. Press Enter to close...' _; exit $ec"

    wt = shutil.which("wt.exe")
    wsl_args = ["wsl.exe"]
    if distro:
        wsl_args += ["-d", distro]
    wsl_args += ["--cd", str(root), "--", "bash", "-lc", bash_cmd]
    launch = [wt, "new-tab", *wsl_args] if wt else ["cmd.exe", "/c", "start", "", *wsl_args]

    if debug:
        print("WSL launch command:")
        print(" ".join(shell_quote(p) for p in launch))

    proc = subprocess.Popen(launch)
    if wait:
        # wt.exe returns immediately after opening the tab; we cannot reliably wait on the tab itself.
        # Fall back to running synchronously in the current terminal when wait=True is required.
        proc.wait()
        if Path(wt).exists():
            print("Note: wt.exe does not block until the tab closes; running this item in the current terminal instead so the runner can wait.")
            return subprocess.run(claude_command, cwd=root, check=False)
    return subprocess.CompletedProcess(claude_command, 0)


def launch_interactive_console(root, interactive_prompt, model, wait=False, debug=False, effort=None, env=None, pid_file=None, remote_control=False):
    if pid_file is not None:
        print("Note: auto-exit Stop hook is not supported with --new-console; the new tab/window will need to be closed manually.")
    claude_command = interactive_command(root, interactive_prompt, model, effort=effort, remote_control=remote_control)
    if is_wsl():
        return launch_wsl_console(root, claude_command, wait, debug)
    if os.name == "nt":
        quoted = " ".join(quote_powershell_arg(part) for part in claude_command)
        command = (
            f"Set-Location -LiteralPath {quote_powershell_arg(str(root))}; "
            f"& {quoted}; "
            "$claudeExit = $LASTEXITCODE"
        )
        if wait:
            command += (
                "; Write-Host ''; "
                "Read-Host 'Claude finished. Press Enter to return to the backlog runner'; "
                "exit $claudeExit"
            )
        if debug:
            print("PowerShell launch command:")
            print(command)
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                *([] if wait else ["-NoExit"]),
                "-Command",
                command,
            ],
            cwd=root,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        if wait:
            return_code = proc.wait()
            return subprocess.CompletedProcess(claude_command, return_code)
        return subprocess.CompletedProcess(claude_command, 0)

    if wait:
        return subprocess.run(claude_command, cwd=root, check=False)

    subprocess.Popen(claude_command, cwd=root)
    return subprocess.CompletedProcess(claude_command, 0)


def quote_powershell_arg(value):
    return "'" + value.replace("'", "''") + "'"


def get_last_execution_time(state_file):
    """Get timestamp of last backlog execution from state file."""
    try:
        if state_file.exists():
            timestamp = float(state_file.read_text().strip())
            return timestamp
    except (ValueError, OSError):
        pass
    return None


def save_execution_time(state_file):
    """Save current time as last execution timestamp."""
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(str(time.time()))
    except OSError as e:
        print(f"Warning: could not save execution time: {e}")


def get_cache_reset_time(check_interval=DEFAULT_CACHE_CHECK_INTERVAL):
    """Get time until cache resets (5 min inactivity from last execution).
    Returns: (minutes_until_reset, last_execution_timestamp) or (0, None) if should proceed."""
    state_file = Path.home() / ".claude" / ".backlog-cache-state"
    last_exec = get_last_execution_time(state_file)

    if last_exec is None:
        return 0, None  # First run, proceed

    elapsed = time.time() - last_exec
    cache_reset_window = 300  # 5 minutes

    if elapsed >= cache_reset_window:
        return 0, last_exec  # Cache has reset, proceed

    minutes_until_reset = (cache_reset_window - elapsed) / 60
    return minutes_until_reset, last_exec


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def wait_for_cache_reset_by_time(minutes_remaining, check_interval=DEFAULT_CACHE_CHECK_INTERVAL):
    """Wait for cache reset based on inactivity timer (5 min from last execution).
    Cache resets after 5 minutes of inactivity from the last Claude execution."""
    print(f"\n⏳ Cache window will reset in {minutes_remaining:.1f} minutes (5 min inactivity)")
    print("   Monitoring...\n")

    start_time = time.time()
    checks = 0

    while True:
        checks += 1
        minutes_until, _ = get_cache_reset_time(check_interval)

        elapsed = time.time() - start_time
        if minutes_until <= 0:
            print(f"✓ [{format_duration(elapsed)}] Cache reset detected!")
            print("\n✓ Resuming backlog execution.\n")
            return

        status = f"[{format_duration(elapsed)}] Check #{checks}: Reset in {minutes_until:.1f} minutes"
        print(f"  {status}")

        time.sleep(check_interval)


RUNNER_STATE_FILE = Path.home() / ".claude" / ".backlog-runner-state"


def set_runner_phase(phase, cwd):
    try:
        RUNNER_STATE_FILE.write_text(json.dumps({"phase": phase, "cwd": str(cwd)}))
    except OSError:
        pass


def clear_runner_phase():
    try:
        RUNNER_STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def get_runner_state():
    """Returns {"phase": str, "cwd": str} or {}."""
    try:
        if RUNNER_STATE_FILE.exists():
            return json.loads(RUNNER_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def find_latest_transcript(cwd):
    """Find the most recently written Claude transcript JSONL for the given cwd.
    Returns (Path, session_id) or (None, None)."""
    projects_base = Path.home() / ".claude" / "projects"
    if not projects_base.exists():
        return None, None

    encoded = str(cwd).lstrip("/").replace("/", "-")
    candidate = projects_base / f"-{encoded}"
    search_dirs = [candidate] if candidate.exists() else list(projects_base.iterdir())

    best_path, best_mtime = None, 0
    for d in search_dirs:
        if not d.is_dir():
            continue
        for p in d.glob("*.jsonl"):
            mtime = p.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best_path = p

    if best_path and (time.time() - best_mtime) < 180:
        return best_path, best_path.stem
    return None, None


def extract_reset_time(transcript_path):
    """Scan transcript JSONL for 'resets 3:45pm' or 'resets Mon 12:00am'.
    Returns (day_str_or_None, time_str) or (None, None) if not found."""
    try:
        text = transcript_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(
            r"resets\s+(?:([A-Za-z]{3})\s+)?(\d{1,2}:\d{2}\s*[ap]m)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1), match.group(2).replace(" ", "")
    except OSError:
        pass
    return None, None


def compute_reset_datetime(day_str, time_str):
    """Convert ('Mon', '3:45pm') to an absolute future datetime."""
    m = re.match(r"(\d{1,2}):(\d{2})([ap]m)", time_str, re.IGNORECASE)
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    now = datetime.now()
    reset = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if day_str:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        target = day_map.get(day_str[:3].lower())
        if target is not None:
            days = (target - now.weekday()) % 7 or 7
            reset += timedelta(days=days)
    elif reset <= now:
        reset += timedelta(days=1)

    return reset


def schedule_retry(command, run_at_dt, cwd=None):
    """Schedule command via 'at' or a detached background Python process.
    cwd: working directory where the command must run.
    Returns (description_str, success_bool)."""
    wait_secs = max(60, int((run_at_dt - datetime.now()).total_seconds()))
    cwd_str = str(cwd) if cwd else None

    if shutil.which("at"):
        parts = []
        if cwd_str:
            parts.append(f"cd {shlex.quote(cwd_str)}")
        parts.append(" ".join(shlex.quote(str(a)) for a in command))
        cmd_str = " && ".join(parts)
        at_time = run_at_dt.strftime("%H:%M %Y-%m-%d")
        result = subprocess.run(
            ["at", at_time], input=cmd_str, text=True, capture_output=True
        )
        if result.returncode == 0:
            job_info = result.stderr.strip()
            return f"'at' job at {at_time} — {job_info}", True

    # Fallback: detached background Python process
    bg = (
        f"import time, subprocess\n"
        f"time.sleep({wait_secs})\n"
        f"subprocess.run({command!r}, cwd={cwd_str!r})\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", bg],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return f"background process PID {proc.pid} (sleeps {wait_secs}s)", True


def handle_rate_limit(root, original_argv):
    """Detect rate limit from latest transcript and schedule a retry.
    If the limit hit during execution, injects --resume-session so Claude
    resumes the interrupted interactive session. During planning, restarts clean.
    Returns True if limit was detected and retry was scheduled."""
    transcript, session_id = find_latest_transcript(root)
    if not transcript:
        return False

    day_str, time_str = extract_reset_time(transcript)
    if not time_str:
        return False

    reset_dt = compute_reset_datetime(day_str, time_str)
    if not reset_dt:
        return False

    retry_dt = reset_dt + timedelta(minutes=5)
    state = get_runner_state()
    phase = state.get("phase")
    cwd = Path(state["cwd"]) if state.get("cwd") else root

    cmd = [sys.executable] + original_argv[:]
    if phase == "executing" and session_id and "--resume-session" not in cmd:
        cmd += ["--resume-session", session_id]

    method, ok = schedule_retry(cmd, retry_dt, cwd=cwd)
    if ok:
        print(
            f"\n⏸  Rate limit · phase={phase or 'unknown'} · reset {reset_dt.strftime('%H:%M')} "
            f"→ retry {retry_dt.strftime('%H:%M')}"
        )
        print(f"   Cwd: {cwd}")
        print(f"   Method: {method}")
        if phase == "executing" and session_id:
            print(f"   Resume session: {session_id}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Run one docs/backlog item through Claude Code CLI.")
    parser.add_argument("--item", help="Backlog number, path, or filename fragment.")
    parser.add_argument("--next", action="store_true", help="Run the first undelivered backlog item.")
    parser.add_argument("--all-afk", action="store_true", help="Run all open Type: AFK backlog items in numeric order.")
    parser.add_argument("--plan-first-interactive", action="store_true", help="For each selected item, use interactive Claude CLI planning before implementation.")
    parser.add_argument("--no-require-commit", action="store_true", help="Do not stop when a run finishes without a new commit.")
    parser.add_argument("--open-next", action="store_true", help="Open the next undelivered backlog item in VS Code.")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive Claude CLI instead of claude -p.")
    parser.add_argument("--new-console", action="store_true", help="Open interactive Claude CLI in a new visible console window.")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated prompt without invoking Claude.")
    parser.add_argument("--debug-launch", action="store_true", help="Print the generated console launch command before opening Claude.")
    parser.add_argument("--keep-prompt", action="store_true", help="Keep temporary prompt files after Claude exits for debugging.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model to invoke (default: {DEFAULT_MODEL}).")
    parser.add_argument("--via-staged-plan", action="store_true", help="Two-step flow per item: non-interactive session invokes the staged-plan skill and writes a plan file, then a fresh interactive session executes that plan.")
    parser.add_argument("--auto-continue", action="store_true", help="With --via-staged-plan, skip the manual review pause between planning and execution.")
    parser.add_argument("--exec-model", default=DEFAULT_EXEC_MODEL, help=f"Model for the execution session (default: {DEFAULT_EXEC_MODEL}).")
    parser.add_argument("--exec-effort", default=DEFAULT_EXEC_EFFORT, help=f"Reasoning effort for the execution session. Valid: low/medium/high/xhigh/max (default: {DEFAULT_EXEC_EFFORT}). Pass empty string to omit.")
    parser.add_argument("--cache-threshold", type=int, default=None, help="Enable cache throttling: wait 5 minutes between plans to let Claude's cache reset. No API key needed. Default: disabled.")
    parser.add_argument("--cache-check-interval", type=int, default=DEFAULT_CACHE_CHECK_INTERVAL, help=f"Seconds between cache status checks while waiting for reset (default: {DEFAULT_CACHE_CHECK_INTERVAL}).")
    parser.add_argument("--no-remote-control", action="store_false", dest="remote_control", help="Disable Remote Control (enabled by default).")
    parser.add_argument("--resume-session", metavar="SESSION_ID", help="Resume an interrupted execution session before continuing --all-afk (injected automatically on retry).")
    parser.set_defaults(remote_control=True)
    args = parser.parse_args()
    exec_effort = args.exec_effort or None

    root = repo_root()
    require_commit = not args.no_require_commit

    if args.all_afk:
        if args.resume_session:
            print(f"\n▶ Resuming interrupted execution session {args.resume_session}...")
            resume_cmd = [
                claude_executable(),
                "--resume", args.resume_session,
                "--dangerously-skip-permissions",
                (
                    "Continue where you left off. If the backlog item work is substantially "
                    "complete, mark it delivered, update docs/backlog/README.md, and commit. "
                    "Emit BACKLOG_RUNNER_DONE_EXIT on its own line when done. "
                    "If nothing is pending, just emit BACKLOG_RUNNER_DONE_EXIT."
                ),
            ]
            if is_wsl():
                resume_result = launch_wsl_console(root, resume_cmd, wait=True, debug=False)
            else:
                resume_result = subprocess.run(resume_cmd, cwd=root, check=False)
            print(f"Resume session exited with code {resume_result.returncode}")
        return run_afk_sequence(root, args.dry_run, require_commit, args.model, args.plan_first_interactive, args.new_console, args.debug_launch, args.keep_prompt, args.via_staged_plan, args.auto_continue, args.exec_model, exec_effort, args.cache_threshold, args.cache_check_interval, args.remote_control)

    backlog_path = resolve_item(root, args.item, args.next)

    if args.via_staged_plan:
        if args.dry_run:
            print(make_staged_plan_prompt(root, backlog_path, plan_file_path(root, backlog_path)))
            return 0
        return run_one_via_staged_plan(root, backlog_path, require_commit, args.model, args.new_console, debug=args.debug_launch, keep_prompt=args.keep_prompt, auto_continue=args.auto_continue, exec_model=args.exec_model, exec_effort=exec_effort, remote_control=args.remote_control)

    prompt = make_prompt(root, backlog_path)

    if args.dry_run:
        print(prompt)
        return 0

    if args.interactive or args.new_console:
        prompt_path = write_prompt_file(root, backlog_path, prompt)
        interactive_prompt = make_interactive_prompt(prompt_path, args.plan_first_interactive)
        if args.new_console:
            launch_interactive_console(root, interactive_prompt, args.model, debug=args.debug_launch, remote_control=args.remote_control)
            print(f"Opened interactive Claude CLI for: {backlog_path.relative_to(root).as_posix()}")
            print(f"Prompt file: {prompt_path}")
            return 0

        try:
            return subprocess.run(interactive_command(root, interactive_prompt, args.model, remote_control=args.remote_control), cwd=root, check=False).returncode
        finally:
            remove_prompt_file(prompt_path, args.keep_prompt)

    completed = claude_exec(root, prompt, args.model)

    next_path = next_after(root, backlog_path)
    print()
    print(f"Backlog item executed: {backlog_path.relative_to(root).as_posix()}")
    if next_path:
        print(f"Next backlog item: {next_path.relative_to(root).as_posix()}")
        if args.open_next:
            subprocess.run(["code", "-r", str(next_path)], cwd=root, check=False)
    else:
        print("No later undelivered backlog item found.")

    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
