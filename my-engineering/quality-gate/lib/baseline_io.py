"""Read/write .quality-gate/baseline.json and .quality-gate/branch.json.

Baseline read (mode-aware):
    extend  → git show <merge-base(HEAD, anchor_ref)>:.quality-gate/baseline.json
    replace → working tree .quality-gate/baseline.json (branch's own snapshot)
    None    → on main: working tree .quality-gate/baseline.json

Baseline write:
    establish owns this. Writes are atomic (tempfile + rename).

Branch intent (branch.json):
    Read/written in the working tree. Required on any branch != main_branch.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

BASELINE_RELPATH = ".quality-gate/baseline.json"
BRANCH_RELPATH = ".quality-gate/branch.json"


class BaselineError(Exception):
    pass


class BranchIntentError(Exception):
    pass


# ── git helpers ───────────────────────────────────────────────────────────────


def _git(cmd: list[str], cwd: str | os.PathLike) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def current_branch(cwd: str | os.PathLike) -> Optional[str]:
    rc, out, _ = _git(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out.strip() if rc == 0 else None


def merge_base(cwd: str | os.PathLike, ref: str) -> Optional[str]:
    """Return merge-base SHA between HEAD and `ref`, or None on failure."""
    rc, out, _ = _git(["git", "merge-base", "HEAD", ref], cwd)
    if rc != 0:
        return None
    sha = out.strip()
    return sha or None


def _show_at(cwd: str | os.PathLike, ref_or_sha: str, relpath: str) -> Optional[str]:
    """Return file contents at a given git ref/sha, or None if not present."""
    rc, out, _ = _git(["git", "show", f"{ref_or_sha}:{relpath}"], cwd)
    if rc == 0 and out.strip():
        return out
    return None


# ── baseline I/O ──────────────────────────────────────────────────────────────


def read_baseline(
    repo_root: str | os.PathLike,
    *,
    mode: Optional[str],
    anchor_ref: str = "main",
    on_main: bool = False,
) -> tuple[Optional[dict], list[str]]:
    """Read baseline according to branch intent mode.

    Returns (data, refs_consulted). `data` is None when no baseline can be
    located. `refs_consulted` is the ordered list of refs/paths the loader
    tried — used by callers to build actionable NO_BASELINE messages.

    mode semantics:
      on_main=True  → read working-tree baseline (mode is ignored)
      mode=replace  → read working-tree baseline (branch's own committed snapshot)
      mode=extend   → read baseline at merge-base(HEAD, anchor_ref)
    """
    repo = Path(repo_root)
    refs: list[str] = []

    if on_main:
        wt = repo / BASELINE_RELPATH
        refs.append(f"working tree ({BASELINE_RELPATH})")
        if wt.is_file():
            try:
                return json.loads(wt.read_text(encoding="utf-8")), refs
            except json.JSONDecodeError as exc:
                raise BaselineError(f"working-tree baseline is not valid JSON: {exc}") from exc
        return None, refs

    if mode == "replace":
        wt = repo / BASELINE_RELPATH
        refs.append(f"working tree ({BASELINE_RELPATH})")
        if wt.is_file():
            try:
                return json.loads(wt.read_text(encoding="utf-8")), refs
            except json.JSONDecodeError as exc:
                raise BaselineError(f"working-tree baseline is not valid JSON: {exc}") from exc
        return None, refs

    if mode == "extend":
        mb = merge_base(repo, anchor_ref)
        if mb is None:
            refs.append(f"git merge-base HEAD {anchor_ref} (failed)")
            return None, refs
        refs.append(f"{mb} (merge-base with {anchor_ref}):{BASELINE_RELPATH}")
        raw = _show_at(repo, mb, BASELINE_RELPATH)
        if raw is None:
            return None, refs
        try:
            return json.loads(raw), refs
        except json.JSONDecodeError as exc:
            raise BaselineError(f"baseline at {mb} is not valid JSON: {exc}") from exc

    raise BaselineError(f"unsupported mode {mode!r}")


def _atomic_write_json(target: Path, data: dict) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.stem + "-", suffix=target.suffix + ".tmp", dir=str(target.parent)
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


def write_baseline(repo_root: str | os.PathLike, data: dict) -> Path:
    """Atomically write baseline.json. Caller decides authorization (establish)."""
    target = Path(repo_root) / BASELINE_RELPATH
    return _atomic_write_json(target, data)


def delete_baseline(repo_root: str | os.PathLike) -> bool:
    """Delete the working-tree baseline.json. Returns True if a file was removed."""
    target = Path(repo_root) / BASELINE_RELPATH
    if target.is_file():
        target.unlink()
        return True
    return False


# ── branch intent I/O ─────────────────────────────────────────────────────────


def read_branch_intent(repo_root: str | os.PathLike) -> Optional[dict]:
    """Return the parsed branch.json from the working tree, or None if absent."""
    path = Path(repo_root) / BRANCH_RELPATH
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BranchIntentError(f"branch.json is not valid JSON: {exc}") from exc


def write_branch_intent(repo_root: str | os.PathLike, data: dict) -> Path:
    target = Path(repo_root) / BRANCH_RELPATH
    return _atomic_write_json(target, data)


def delete_branch_intent(repo_root: str | os.PathLike) -> bool:
    path = Path(repo_root) / BRANCH_RELPATH
    if path.is_file():
        path.unlink()
        return True
    return False
