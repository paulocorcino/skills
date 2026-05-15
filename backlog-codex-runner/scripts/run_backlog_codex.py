#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run_text(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()


def repo_root():
    try:
        root = run_text(["git", "rev-parse", "--show-toplevel"], None)
    except subprocess.CalledProcessError as exc:
        raise SystemExit("This script must run inside a git repository.") from exc
    return Path(root).resolve()


def backlog_files(root):
    backlog_dir = root / "docs" / "backlog"
    return sorted(path for path in backlog_dir.glob("*.md") if path.name[:3].isdigit() and path.name[3:4] == "-")


def is_delivered(path):
    content = path.read_text(encoding="utf-8")
    labels_delivered = any(line.startswith("Labels:") and "delivered" in line for line in content.splitlines())
    status_delivered = any(line.startswith("Status: delivered") for line in content.splitlines())
    return labels_delivered or status_delivered


def is_afk(path):
    content = path.read_text(encoding="utf-8")
    return any(line.strip() == "Type: AFK" for line in content.splitlines())


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
        prefix = normalized.zfill(3) + "-"
        for path in files:
            if path.name.startswith(prefix):
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


def codex_executable():
    resolved = shutil.which("codex")
    if resolved:
        return resolved
    if os.name == "nt":
        try:
            found = subprocess.check_output(["where.exe", "codex"], text=True, stderr=subprocess.DEVNULL).splitlines()
        except subprocess.CalledProcessError:
            found = []
        if found:
            return found[0]
    return "codex"


def make_prompt(root, backlog_path):
    relative = backlog_path.relative_to(root).as_posix()
    skill_path = (root / ".agents" / "skills" / "backlog-codex-runner" / "SKILL.md").resolve()
    status = git_status(root)
    content = backlog_path.read_text(encoding="utf-8")
    return f"""Task: executar o backlog {relative}.

You are running from Codex CLI as the implementation executor for this repository.
This runner skill is repository-local at `{skill_path}`. Do not try to read `C:\\Users\\paulo.corcino\\.codex\\skills\\.system\\backlog-codex-runner\\SKILL.md`; that global system-skill path does not exist for this project.

Required execution model:
1. Read AGENTS.md/repository instructions and the backlog item below.
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


def codex_exec(root, prompt):
    command = [
        codex_executable(),
        "exec",
        "-C",
        str(root),
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="medium"',
        "-s",
        "danger-full-access",
        "-a",
        "never",
        "-",
    ]
    return subprocess.run(command, cwd=root, input=prompt, text=True, check=False)


def make_interactive_prompt(prompt_path, plan_first):
    if plan_first:
        return (
            "Read and follow the backlog execution prompt in this file: "
            f"{prompt_path}. Use the native Codex planning flow first: produce a complete plan, "
            "wait for my approval or edits, and only then implement, validate, mark the backlog delivered, "
            "and commit. If Codex Plan Mode is available in this CLI session, enter/use it before making edits."
        )

    return (
        "Read and follow the backlog execution prompt in this file: "
        f"{prompt_path}. Start by summarizing your plan, then execute it. "
        "If you need clarification, ask me in this interactive Codex CLI session."
    )


def interactive_command(root, prompt_text):
    return [
        codex_executable(),
        "-C",
        str(root),
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="medium"',
        "-s",
        "danger-full-access",
        "-a",
        "on-request",
        prompt_text,
    ]


def run_one_exec(root, backlog_path, require_commit):
    before_head = git_head(root)
    prompt = make_prompt(root, backlog_path)
    print()
    print(f"=== Running {backlog_path.relative_to(root).as_posix()} ===")
    completed = codex_exec(root, prompt)
    after_head = git_head(root)

    if completed.returncode != 0:
        print(f"Stopping: Codex CLI exited with code {completed.returncode}.")
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


def run_one_interactive(root, backlog_path, require_commit, plan_first, new_console, debug=False, keep_prompt=False):
    before_head = git_head(root)
    prompt = make_prompt(root, backlog_path)
    prompt_path = write_prompt_file(root, backlog_path, prompt)
    interactive_prompt = make_interactive_prompt(prompt_path, plan_first)

    print()
    print(f"=== Running interactive {backlog_path.relative_to(root).as_posix()} ===")
    print(f"Prompt file: {prompt_path}")

    try:
        if new_console:
            completed = launch_interactive_console(root, interactive_prompt, wait=True, debug=debug)
        else:
            completed = subprocess.run(interactive_command(root, interactive_prompt), cwd=root, check=False)
    finally:
        remove_prompt_file(prompt_path, keep_prompt)

    after_head = git_head(root)
    has_new_commit = before_head != after_head
    delivered = is_delivered(backlog_path)

    if completed.returncode != 0 and not (has_new_commit and delivered):
        print(f"Stopping: interactive Codex CLI exited with code {completed.returncode}.")
        return completed.returncode

    if completed.returncode != 0:
        print(f"Interactive Codex CLI exited with code {completed.returncode}, but delivery gates passed; continuing.")

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


def run_afk_sequence(root, dry_run, require_commit, plan_first_interactive=False, new_console=False, debug=False, keep_prompt=False):
    items = open_afk_backlog_files(root)
    if dry_run:
        if not items:
            print("No open Type: AFK backlog item found.")
            return 0
        mode = "plan-first-interactive" if plan_first_interactive else "codex-exec"
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

    for path in items:
        if plan_first_interactive:
            code = run_one_interactive(root, path, require_commit, plan_first=True, new_console=new_console, debug=debug, keep_prompt=keep_prompt)
        else:
            code = run_one_exec(root, path, require_commit)
        if code != 0:
            return code

    print()
    print("All open Type: AFK backlog items were processed.")
    return 0


def write_prompt_file(root, backlog_path, prompt):
    prompt_dir = root / ".agents" / "tmp" / "backlog-codex-runner"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f"{backlog_path.name.removesuffix('.md')}-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def launch_interactive_console(root, interactive_prompt, wait=False, debug=False):
    codex_command = interactive_command(root, interactive_prompt)
    if os.name == "nt":
        quoted = " ".join(quote_powershell_arg(part) for part in codex_command)
        command = (
            f"Set-Location -LiteralPath {quote_powershell_arg(str(root))}; "
            f"& {quoted}; "
            "$codexExit = $LASTEXITCODE"
        )
        if wait:
            command += (
                "; Write-Host ''; "
                "Read-Host 'Codex finished. Press Enter to return to the backlog runner'; "
                "exit $codexExit"
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
            return subprocess.CompletedProcess(codex_command, return_code)
        return subprocess.CompletedProcess(codex_command, 0)

    if wait:
        return subprocess.run(codex_command, cwd=root, check=False)

    subprocess.Popen(codex_command, cwd=root)
    return subprocess.CompletedProcess(codex_command, 0)


def quote_powershell_arg(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description="Run one docs/backlog item through Codex CLI.")
    parser.add_argument("--item", help="Backlog number, path, or filename fragment.")
    parser.add_argument("--next", action="store_true", help="Run the first undelivered backlog item.")
    parser.add_argument("--all-afk", action="store_true", help="Run all open Type: AFK backlog items in numeric order.")
    parser.add_argument("--plan-first-interactive", action="store_true", help="For each selected item, use interactive Codex CLI planning before implementation.")
    parser.add_argument("--no-require-commit", action="store_true", help="Do not stop when a run finishes without a new commit.")
    parser.add_argument("--open-next", action="store_true", help="Open the next undelivered backlog item in VS Code.")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive Codex CLI instead of codex exec.")
    parser.add_argument("--new-console", action="store_true", help="Open interactive Codex CLI in a new visible console window.")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated prompt without invoking Codex.")
    parser.add_argument("--debug-launch", action="store_true", help="Print the generated console launch command before opening Codex.")
    parser.add_argument("--keep-prompt", action="store_true", help="Keep temporary prompt files after Codex exits for debugging.")
    args = parser.parse_args()

    root = repo_root()
    require_commit = not args.no_require_commit

    if args.all_afk:
        return run_afk_sequence(root, args.dry_run, require_commit, args.plan_first_interactive, args.new_console, args.debug_launch, args.keep_prompt)

    backlog_path = resolve_item(root, args.item, args.next)
    prompt = make_prompt(root, backlog_path)

    if args.dry_run:
        print(prompt)
        return 0

    if args.interactive or args.new_console:
        prompt_path = write_prompt_file(root, backlog_path, prompt)
        interactive_prompt = make_interactive_prompt(prompt_path, args.plan_first_interactive)
        if args.new_console:
            launch_interactive_console(root, interactive_prompt, debug=args.debug_launch)
            print(f"Opened interactive Codex CLI for: {backlog_path.relative_to(root).as_posix()}")
            print(f"Prompt file: {prompt_path}")
            return 0

        try:
            return subprocess.run(interactive_command(root, interactive_prompt), cwd=root, check=False).returncode
        finally:
            remove_prompt_file(prompt_path, args.keep_prompt)

    completed = codex_exec(root, prompt)

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
