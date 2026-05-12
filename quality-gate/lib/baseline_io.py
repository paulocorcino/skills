"""Read/write .quality-gate/baseline.json.

Read: prefer `git show <main>:.quality-gate/baseline.json`. Fall back to the
working tree only when the current branch equals `main_branch` (or when git is
unavailable / the file is not in main yet).

Write: only allowed when `--update-baseline` is set AND the current branch is
the configured main branch (or `--force` is set). Write is atomic: write to a
temp file in the same directory then rename.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

BASELINE_RELPATH = ".quality-gate/baseline.json"


class BaselineError(Exception):
    pass


def _git(cmd: list[str], cwd: str | os.PathLike) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def current_branch(cwd: str | os.PathLike) -> Optional[str]:
    rc, out, _ = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out.strip() if rc == 0 else None


def read_baseline(repo_root: str | os.PathLike, main_branch: str = "main") -> Optional[dict]:
    """Return parsed baseline dict, or None when no baseline exists."""
    repo = Path(repo_root)
    # Try git show first.
    rc, out, _ = _git(["git", "show", f"{main_branch}:{BASELINE_RELPATH}"], repo)
    if rc == 0 and out.strip():
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise BaselineError(f"baseline in {main_branch} is not valid JSON: {exc}") from exc

    # Fall back to working tree when on main.
    branch = current_branch(repo)
    wt_path = repo / BASELINE_RELPATH
    if wt_path.is_file() and (branch == main_branch or branch is None):
        try:
            return json.loads(wt_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BaselineError(f"working-tree baseline is not valid JSON: {exc}") from exc

    return None


def write_baseline(
    repo_root: str | os.PathLike,
    data: dict,
    *,
    main_branch: str = "main",
    force: bool = False,
) -> Path:
    """Atomically write baseline to disk. Returns the written path.

    Refuses unless the current branch is `main_branch` or `force=True`.
    Caller is responsible for actually staging/committing the file.
    """
    repo = Path(repo_root)
    branch = current_branch(repo)
    if not force and branch is not None and branch != main_branch:
        raise BaselineError(
            f"refusing to write baseline from branch {branch!r}; "
            f"main_branch is {main_branch!r} (use --force to override)"
        )

    target = repo / BASELINE_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix="baseline-", suffix=".json.tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target
