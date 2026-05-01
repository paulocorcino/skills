#!/usr/bin/env python3
"""Build an objective review packet for reviewer-v2.

This script is a harness, not a reviewer. It gathers target/base/spec facts,
declared commands, operational surfaces, changed files, and bounded diff
excerpts. It must not emit findings, decide severity, or validate specs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


MANIFEST_NAMES = {
    "package.json",
    "bun.lock",
    "bun.lockb",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "deno.json",
    "deno.jsonc",
    "go.mod",
    "Cargo.toml",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "setup.py",
    "Makefile",
    "Dockerfile",
    "Dockerfile.dev",
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.dev.yml",
    "compose.yml",
    "compose.yaml",
    ".dockerignore",
    ".env.example",
    ".npmrc",
    "bunfig.toml",
    "manifest.yaml",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
}

SPEC_DIRS = [
    "docs/adr",
    "docs/adrs",
    "docs/architecture/decisions",
    "docs/decisions",
    "adr",
    "adrs",
    "decisions",
    "architecture/decisions",
    "docs/rfc",
    "docs/rfcs",
    "rfcs",
    "docs/specs",
    "specs",
    "docs/prd",
    "prd",
    "docs/design",
    "design-docs",
    "docs/briefs",
    "briefs",
    "docs/plans",
]

TEXT_SPEC_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
DIFF_LIMIT = 240_000
SPEC_EXCERPT_LIMIT = 20_000
SPEC_SCAN_LIMIT = 500_000
FILE_SIZE_LIMIT = 200_000
GENERIC_KEYWORDS = {
    "feat",
    "feature",
    "fix",
    "bugfix",
    "chore",
    "docs",
    "doc",
    "test",
    "tests",
    "src",
    "lib",
    "app",
    "dev",
    "setup",
    "stage",
    "stages",
    "report",
    "plan",
    "plans",
    "docker",
    "compose",
    "package",
    "script",
    "scripts",
}


def run_git(repo: Path, args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def git_out(repo: Path, args: list[str]) -> str:
    proc = run_git(repo, args)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def safe_read(path: Path, limit: int | None = None) -> tuple[str, str | None]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return "", f"read error: {exc}"
    if b"\x00" in data:
        return "", "binary"
    truncated = None
    if limit is not None and len(data) > limit:
        data = data[:limit]
        truncated = f"truncated to {limit} bytes"
    try:
        return data.decode("utf-8"), truncated
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        note = "decode errors replaced"
        if truncated:
            note = f"{note}; {truncated}"
        return text, note


def ensure_repo(path: Path) -> Path:
    root = git_out(path, ["rev-parse", "--show-toplevel"])
    if not root:
        raise SystemExit(f"not a git repository: {path}")
    return Path(root)


def detect_default_base(repo: Path) -> str:
    explicit = git_out(repo, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if explicit:
        return explicit.replace("origin/", "origin/", 1)
    for candidate in ["origin/main", "origin/master", "main", "master"]:
        if git_out(repo, ["rev-parse", "--verify", candidate]):
            return candidate
    head = git_out(repo, ["rev-parse", "--short", "HEAD"])
    return head or "HEAD"


def is_commitish(repo: Path, value: str) -> bool:
    if not value:
        return False
    return bool(git_out(repo, ["rev-parse", "--verify", f"{value}^{{commit}}"]))


def split_specs(values: list[str]) -> list[str]:
    refs: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                refs.append(part)
    return refs


def extract_paths_from_prompt(prompt: str) -> list[str]:
    if not prompt:
        return []
    pattern = re.compile(r"(?P<path>(?:~|/|\./|\.\./)?[A-Za-z0-9_./@:+-]+(?:\.md|\.txt|\.rst|\.adoc|\.yaml|\.yml))")
    found: list[str] = []
    for match in pattern.finditer(prompt):
        value = match.group("path").strip("`'\"),.")
        if value not in found:
            found.append(value)
    return found


def extract_adr_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(r"\bADR[- ]?(\d{4})\b", text, flags=re.IGNORECASE):
        ref = f"ADR-{match.group(1)}"
        if ref not in refs:
            refs.append(ref)
    return refs


def keyword_tokens(keywords: list[str]) -> list[str]:
    tokens: list[str] = []
    for keyword in keywords:
        for token in re.findall(r"[A-Za-z0-9_+-]{4,}", keyword.lower()):
            normalized = token.strip("_+-")
            parts = [part for part in re.split(r"[_+-]+", normalized) if part]
            if not normalized or normalized in GENERIC_KEYWORDS:
                continue
            if parts and all(part in GENERIC_KEYWORDS for part in parts):
                continue
            if normalized not in tokens:
                tokens.append(normalized)
            for part in parts:
                if len(part) >= 4 and part not in GENERIC_KEYWORDS and part not in tokens:
                    tokens.append(part)
    return tokens


def resolve_path(repo: Path, raw: str, extra_bases: list[Path] | None = None) -> Path | None:
    expanded = Path(os.path.expanduser(raw))
    candidates = []
    if expanded.is_absolute():
        candidates.append(expanded)
    else:
        for base in extra_bases or []:
            candidates.append(base / expanded)
        candidates.append(repo / expanded)
        candidates.append(Path.cwd() / expanded)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def resolve_adr(repo: Path, raw: str) -> Path | None:
    match = re.search(r"(\d{4})", raw)
    if not match:
        return None
    number = match.group(1)
    roots: list[Path] = [repo / "docs" / "adr", repo / "docs" / "adrs", repo / "adr", repo / "adrs"]
    for ancestor in repo.parents:
        roots.extend([ancestor / "docs" / "adr", ancestor / "docs" / "adrs", ancestor / "adr", ancestor / "adrs"])
    seen_roots: set[Path] = set()
    for root in roots:
        if root in seen_roots or not root.is_dir():
            continue
        seen_roots.add(root)
        for pattern in [f"{number}-*.md", f"{number}_*.md", f"ADR-{number}*.md", f"adr-{number}*.md", f"{number}.md"]:
            matches = sorted(root.glob(pattern))
            if matches:
                return matches[0].resolve()
    return None


def relevant_nested_path(raw: str, resolved: Path, repo: Path, keywords: list[str]) -> bool:
    haystack = f"{raw} {resolved}".lower()
    tokens = keyword_tokens(keywords)
    path_parts = {Path(part).name.lower() for part in resolved.parts}
    if repo not in [resolved, *resolved.parents] and path_parts & {".claude", ".codex", ".cursor", ".vscode"}:
        return False
    if repo in [resolved, *resolved.parents]:
        return True
    if any(token in haystack for token in tokens):
        return True
    doc_markers = [
        "adr",
        "adrs",
        "rfc",
        "rfcs",
        "prd",
        "prds",
        "brief",
        "briefs",
        "spec",
        "specs",
        "decision",
        "decisions",
        "design",
        "design-docs",
        "plan",
        "plans",
        "docs",
    ]
    return any(marker in path_parts for marker in doc_markers)


def relevant_text_for_keywords(text: str, keywords: list[str]) -> str:
    tokens = keyword_tokens(keywords)
    if not tokens:
        return text
    lines = text.splitlines()
    ranges: list[tuple[int, int]] = []
    heading_re = re.compile(r"^(#{1,3})\s+(.+)$")
    for index, line in enumerate(lines):
        match = heading_re.match(line)
        if not match:
            continue
        title = match.group(2).lower()
        if not any(token in title for token in tokens):
            continue
        level = len(match.group(1))
        end = len(lines)
        for later in range(index + 1, len(lines)):
            later_match = heading_re.match(lines[later])
            if later_match and len(later_match.group(1)) <= level:
                end = later
                break
        ranges.append((index, end))
    if not ranges:
        return text
    selected: list[str] = []
    for start, end in ranges:
        selected.extend(lines[start:end])
    return "\n".join(selected)


def spec_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            return clean.lstrip("#").strip() or fallback
    return fallback


def spec_excerpt(text: str, note: str | None) -> tuple[str, str | None]:
    encoded = text.encode("utf-8")
    if len(encoded) <= SPEC_EXCERPT_LIMIT:
        return text, note
    excerpt = encoded[:SPEC_EXCERPT_LIMIT].decode("utf-8", errors="replace")
    truncation = f"truncated to {SPEC_EXCERPT_LIMIT} bytes"
    if note:
        return excerpt, f"{note}; {truncation}"
    return excerpt, truncation


def discover_specs(repo: Path, explicit_refs: list[str], prompt: str, keywords: list[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[Path] = set()

    pending_explicit: list[tuple[str, int, list[Path]]] = [
        (ref, 0, []) for ref in [*explicit_refs, *extract_paths_from_prompt(prompt), *extract_adr_refs(prompt)]
    ]
    index = 0
    while index < len(pending_explicit):
        ref, depth, bases = pending_explicit[index]
        index += 1
        resolved = resolve_adr(repo, ref) if ref.upper().startswith("ADR-") else resolve_path(repo, ref, bases)
        if resolved and resolved.is_file() and resolved not in seen:
            scan_text, scan_note = safe_read(resolved, SPEC_SCAN_LIMIT)
            excerpt, note = spec_excerpt(scan_text, scan_note)
            specs.append(
                {
                    "ref": ref,
                    "path": str(resolved),
                    "provenance": "explicit",
                    "title": spec_title(scan_text, resolved.name),
                    "excerpt": excerpt,
                    "note": note,
                }
            )
            seen.add(resolved)
            if depth < 2:
                section_keywords = keywords[:2] or keywords
                relevant_text = relevant_text_for_keywords(scan_text, section_keywords) if depth == 0 else scan_text
                for nested in extract_paths_from_prompt(relevant_text):
                    nested_resolved = resolve_path(repo, nested, [resolved.parent])
                    if (
                        nested_resolved
                        and nested_resolved.is_file()
                        and nested_resolved not in seen
                        and relevant_nested_path(nested, nested_resolved, repo, keywords)
                    ):
                        pending_explicit.append((str(nested_resolved), depth + 1, [resolved.parent]))
                for adr_ref in extract_adr_refs(relevant_text):
                    adr_resolved = resolve_adr(repo, adr_ref)
                    if adr_resolved and adr_resolved.is_file() and adr_resolved not in seen:
                        pending_explicit.append((adr_ref, depth + 1, []))

    keyword_blob = " ".join(keywords).lower()
    discovered: list[Path] = []
    for rel_dir in SPEC_DIRS:
        directory = repo / rel_dir
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_SPEC_EXTS:
                discovered.append(path)

    scored: list[tuple[int, float, Path]] = []
    tokens = keyword_tokens(keywords)
    for path in discovered:
        if path.resolve() in seen:
            continue
        haystack = str(path.relative_to(repo)).lower()
        score = 0
        for token in tokens or re.findall(r"[A-Za-z0-9_+-]{4,}", keyword_blob):
            if token.lower() in haystack:
                score += 2
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0
        scored.append((score, mtime, path))

    for score, _mtime, path in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[:8]:
        scan_text, scan_note = safe_read(path, SPEC_SCAN_LIMIT)
        excerpt, note = spec_excerpt(scan_text, scan_note)
        specs.append(
            {
                "ref": str(path.relative_to(repo)),
                "path": str(path.resolve()),
                "provenance": "inferred" if score > 0 else "discovered",
                "title": spec_title(scan_text, path.name),
                "excerpt": excerpt,
                "note": note,
            }
        )
        seen.add(path.resolve())

    return specs


def target_mode(repo: Path, target: str, base: str) -> dict[str, Any]:
    normalized = (target or "").strip()
    if not normalized or normalized in {"working-tree", "worktree", "."}:
        return {
            "mode": "working-tree",
            "target": normalized or "working-tree",
            "base": base,
            "diff_args": [],
            "name_args": [],
            "log_args": ["log", "--oneline", "-8"],
        }

    path = resolve_path(repo, normalized)
    if path and repo in [path, *path.parents]:
        rel = str(path.relative_to(repo))
        return {
            "mode": "path",
            "target": rel,
            "base": base,
            "diff_args": [base, "--", rel],
            "name_args": [base, "--", rel],
            "log_args": ["log", "--oneline", "-8", "--", rel],
        }

    if is_commitish(repo, normalized):
        return {
            "mode": "commit-ish",
            "target": normalized,
            "base": base,
            "diff_args": [f"{base}...{normalized}"],
            "name_args": [f"{base}...{normalized}"],
            "log_args": ["log", "--oneline", f"{base}..{normalized}"],
        }

    return {
        "mode": "unresolved",
        "target": normalized,
        "base": base,
        "diff_args": [],
        "name_args": [],
        "log_args": ["log", "--oneline", "-8"],
    }


def collect_diff(repo: Path, mode: dict[str, Any]) -> dict[str, Any]:
    if mode["mode"] == "working-tree":
        stat = git_out(repo, ["diff", "--stat", "HEAD"])
        name_status = git_out(repo, ["diff", "--name-status", "HEAD"])
        diff = git_out(repo, ["diff", "--unified=80", "HEAD"])
        untracked = git_out(repo, ["ls-files", "--others", "--exclude-standard"])
    elif mode["mode"] == "unresolved":
        stat = ""
        name_status = ""
        diff = ""
        untracked = ""
    else:
        stat = git_out(repo, ["diff", "--stat", *mode["diff_args"]])
        name_status = git_out(repo, ["diff", "--name-status", *mode["name_args"]])
        diff = git_out(repo, ["diff", "--unified=80", *mode["diff_args"]])
        untracked = ""

    truncated = False
    if len(diff.encode("utf-8")) > DIFF_LIMIT:
        diff = diff[:DIFF_LIMIT]
        truncated = True

    changed = parse_name_status(name_status)
    if untracked:
        for line in untracked.splitlines():
            changed.append({"status": "??", "path": line.strip()})

    return {
        "stat": stat,
        "name_status": name_status,
        "changed_files": changed,
        "diff_excerpt": diff,
        "diff_truncated": truncated,
        "untracked": [line for line in untracked.splitlines() if line.strip()],
    }


def parse_name_status(text: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            files.append({"status": status, "path": parts[2], "old_path": parts[1]})
        elif len(parts) >= 2:
            files.append({"status": status, "path": parts[1]})
    return files


def list_tracked_files(repo: Path) -> list[str]:
    out = git_out(repo, ["ls-files"])
    return [line for line in out.splitlines() if line]


def find_package_roots(repo: Path, changed_files: list[dict[str, str]], tracked: list[str]) -> list[str]:
    candidates: set[Path] = {repo}
    manifest_set = {"package.json", "go.mod", "Cargo.toml", "pyproject.toml", "deno.json", "Makefile"}
    for item in changed_files:
        current = repo / item["path"]
        parents = [current if current.is_dir() else current.parent, *current.parents]
        for parent in parents:
            if parent == parent.parent:
                break
            if repo not in [parent, *parent.parents]:
                continue
            if any((parent / name).exists() for name in manifest_set):
                candidates.add(parent)
                break
    for rel in tracked:
        path = Path(rel)
        if path.name in manifest_set:
            candidates.add((repo / path).parent)
    return sorted(str(path.relative_to(repo)) if path != repo else "." for path in candidates)


def collect_manifests(repo: Path, package_roots: list[str]) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in package_roots:
        root_path = repo if root == "." else repo / root
        for name in sorted(MANIFEST_NAMES):
            path = root_path / name
            if path.exists() and path.is_file() and path.resolve() not in seen:
                text, note = safe_read(path, 80_000)
                manifests.append(
                    {
                        "path": str(path.relative_to(repo)),
                        "size": path.stat().st_size,
                        "note": note,
                        "content_excerpt": text,
                    }
                )
                seen.add(path.resolve())
    return manifests


def parse_package_scripts(repo: Path, manifests: list[dict[str, Any]]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for manifest in manifests:
        if not manifest["path"].endswith("package.json"):
            continue
        path = repo / manifest["path"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = data.get("scripts")
        if not isinstance(scripts, dict):
            continue
        root = str(Path(manifest["path"]).parent)
        if root == ".":
            root = "."
        for name, command in sorted(scripts.items()):
            commands.append(
                {
                    "kind": "package-script",
                    "root": root,
                    "name": name,
                    "command": str(command),
                    "run_hint": f"bun run {name}",
                }
            )
    return commands


def parse_make_targets(repo: Path, manifests: list[dict[str, Any]]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    target_re = re.compile(r"^([A-Za-z0-9_.:-]+):(?:\s|$)")
    for manifest in manifests:
        if Path(manifest["path"]).name != "Makefile":
            continue
        path = repo / manifest["path"]
        text, _note = safe_read(path, 80_000)
        root = str(Path(manifest["path"]).parent)
        if root == ".":
            root = "."
        for line in text.splitlines():
            match = target_re.match(line)
            if not match:
                continue
            name = match.group(1)
            commands.append(
                {
                    "kind": "make-target",
                    "root": root,
                    "name": name,
                    "command": f"make {name}",
                    "run_hint": f"make {name}",
                }
            )
    return commands


def candidate_checks(commands: list[dict[str, str]], manifests: list[dict[str, Any]]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    keywords = [
        "check",
        "typecheck",
        "tsc",
        "lint",
        "test",
        "ci",
        "contract",
        "integration",
        "e2e",
        "build",
        "docker",
        "compose",
        "release",
    ]
    for command in commands:
        blob = f"{command['name']} {command.get('command', '')}".lower()
        if any(keyword in blob for keyword in keywords):
            checks.append(command)
    manifest_paths = {item["path"] for item in manifests}
    if "Dockerfile" in manifest_paths:
        checks.append({"kind": "docker", "root": ".", "name": "docker-build", "command": "docker build .", "run_hint": "docker build ."})
    for path in sorted(manifest_paths):
        if "compose" in Path(path).name:
            checks.append(
                {
                    "kind": "docker-compose",
                    "root": ".",
                    "name": f"compose-config:{path}",
                    "command": f"docker compose -f {path} config",
                    "run_hint": f"docker compose -f {path} config",
                }
            )
    return checks


def operational_surfaces(repo: Path, tracked: list[str], changed_files: list[dict[str, str]]) -> list[dict[str, Any]]:
    changed_paths = {item["path"] for item in changed_files}
    surfaces: list[dict[str, Any]] = []
    patterns = [
        re.compile(r"(^|/)Dockerfile(\..*)?$"),
        re.compile(r"(^|/)(docker-)?compose.*\.ya?ml$"),
        re.compile(r"(^|/)docker-compose.*\.ya?ml$"),
        re.compile(r"(^|/)\.dockerignore$"),
        re.compile(r"(^|/)\.env\.example$"),
        re.compile(r"(^|/)manifest\.ya?ml$"),
        re.compile(r"(^|/)\.npmrc$"),
        re.compile(r"(^|/)bunfig\.toml$"),
        re.compile(r"(^|/)scripts/.*"),
        re.compile(r"(^|/).*(release|setup|build|deploy|prepare|restore).*\.(sh|bash|zsh|py|js|ts|mjs|cjs)$"),
        re.compile(r"(^|/)\.github/workflows/[^/]+\.ya?ml$"),
        re.compile(r"(^|/)\.circleci/config\.ya?ml$"),
        re.compile(r"(^|/)\.buildkite/[^/]+\.ya?ml$"),
        re.compile(r"(^|/)(\.gitlab-ci\.ya?ml|azure-pipelines\.ya?ml|Jenkinsfile|buildkite\.ya?ml|appveyor\.ya?ml)$"),
        re.compile(r"(^|/)package\.json$"),
        re.compile(r"(^|/)(bun\.lock|bun\.lockb|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|go\.sum)$"),
        re.compile(r"(^|/)docs/.*/.*(report|status|release).*\.md$"),
    ]
    for rel in sorted(set(tracked) | changed_paths):
        if any(pattern.search(rel) for pattern in patterns):
            path = repo / rel
            surfaces.append(
                {
                    "path": rel,
                    "changed": rel in changed_paths,
                    "exists": path.exists(),
                    "size": path.stat().st_size if path.exists() and path.is_file() else None,
                }
            )
    return surfaces


def skipped_files(repo: Path, changed_files: list[dict[str, str]]) -> list[dict[str, str]]:
    skipped: list[dict[str, str]] = []
    for item in changed_files:
        path = repo / item["path"]
        if not path.exists() or not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > FILE_SIZE_LIMIT:
            skipped.append({"path": item["path"], "reason": f"oversized ({size} bytes)"})
            continue
        sample, note = safe_read(path, 4096)
        if note in {"binary", "non-utf8"}:
            skipped.append({"path": item["path"], "reason": note})
        elif sample.startswith("// @generated") or sample.startswith("# Code generated"):
            skipped.append({"path": item["path"], "reason": "generated marker"})
    return skipped


def format_bullets(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def format_changed_files(files: list[dict[str, str]]) -> str:
    if not files:
        return "- none"
    lines = []
    for item in files:
        if "old_path" in item:
            lines.append(f"- {item['status']} {item['old_path']} -> {item['path']}")
        else:
            lines.append(f"- {item['status']} {item['path']}")
    return "\n".join(lines)


def format_specs(specs: list[dict[str, Any]]) -> str:
    if not specs:
        return "- none"
    lines = []
    for spec in specs:
        note = f" ({spec['note']})" if spec.get("note") else ""
        lines.append(f"- {spec['title']} [{spec['provenance']}] {spec['path']}{note}")
    return "\n".join(lines)


def format_commands(commands: list[dict[str, str]]) -> str:
    if not commands:
        return "- none"
    return "\n".join(f"- {cmd['kind']} {cmd['root']} {cmd['name']}: {cmd['command']}" for cmd in commands)


def format_surfaces(surfaces: list[dict[str, Any]]) -> str:
    if not surfaces:
        return "- none"
    lines = []
    for surface in surfaces:
        marker = "changed" if surface["changed"] else "present"
        exists = "exists" if surface["exists"] else "missing/deleted"
        lines.append(f"- {surface['path']} ({marker}, {exists})")
    return "\n".join(lines)


def format_skipped(skipped: list[dict[str, str]]) -> str:
    if not skipped:
        return "- none"
    return "\n".join(f"- {item['path']}: {item['reason']}" for item in skipped)


def render_template(template: str, values: dict[str, str]) -> str:
    output = template
    for key, value in values.items():
        output = output.replace("{{" + key + "}}", value)
    return output


def build_packet(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    repo = ensure_repo(Path(args.repo).resolve())
    base = args.base or detect_default_base(repo)
    prompt = sys.stdin.read() if args.prompt_stdin else ""
    mode = target_mode(repo, args.target or "working-tree", base)
    diff = collect_diff(repo, mode)
    tracked = list_tracked_files(repo)
    branch = git_out(repo, ["branch", "--show-current"]) or "(detached)"
    head = git_out(repo, ["rev-parse", "--short", "HEAD"]) or "unknown"
    status = git_out(repo, ["status", "--short"])
    commits = git_out(repo, mode["log_args"])

    keyword_inputs = [repo.name, mode["target"], branch, commits, *[item["path"] for item in diff["changed_files"]]]
    specs = discover_specs(repo, split_specs(args.spec), prompt, keyword_inputs)
    package_roots = find_package_roots(repo, diff["changed_files"], tracked)
    manifests = collect_manifests(repo, package_roots)
    commands = [*parse_package_scripts(repo, manifests), *parse_make_targets(repo, manifests)]
    checks = candidate_checks(commands, manifests)
    surfaces = operational_surfaces(repo, tracked, diff["changed_files"])
    skipped = skipped_files(repo, diff["changed_files"])

    packet = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo": str(repo),
        "target": mode["target"],
        "base": mode["base"],
        "head": head,
        "branch": branch,
        "mode": mode["mode"],
        "diff": diff,
        "specs": specs,
        "package_roots": package_roots,
        "manifests": manifests,
        "declared_commands": commands,
        "candidate_checks": checks,
        "operational_surfaces": surfaces,
        "skipped_files": skipped,
        "git_status": status,
        "commit_messages": commits,
        "prompt_paths": extract_paths_from_prompt(prompt),
    }

    return repo, packet


def write_outputs(output_dir: Path, packet: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    script_dir = Path(__file__).resolve().parents[1]
    template_path = script_dir / "templates" / "review_packet.md"
    template = template_path.read_text(encoding="utf-8")

    diff_summary = packet["diff"]["stat"] or "(no diff stat)"
    if packet["diff"]["diff_truncated"]:
        diff_summary += "\n\nNote: diff excerpt was truncated by the harness byte limit."

    values = {
        "generated_at": packet["generated_at"],
        "repo": packet["repo"],
        "target": packet["target"],
        "base": packet["base"],
        "head": packet["head"],
        "branch": packet["branch"],
        "mode": packet["mode"],
        "diff_summary": diff_summary,
        "changed_files": format_changed_files(packet["diff"]["changed_files"]),
        "specs": format_specs(packet["specs"]),
        "declared_commands": format_commands(packet["declared_commands"]),
        "candidate_checks": format_commands(packet["candidate_checks"]),
        "operational_surfaces": format_surfaces(packet["operational_surfaces"]),
        "package_roots": format_bullets(packet["package_roots"]),
        "skipped_files": format_skipped(packet["skipped_files"]),
        "git_status": packet["git_status"] or "(clean)",
        "commit_messages": packet["commit_messages"] or "(none)",
        "diff_excerpt": packet["diff"]["diff_excerpt"] or "(empty)",
    }

    md_path = output_dir / "review_packet.md"
    json_path = output_dir / "review_packet.json"
    md_path.write_text(render_template(template, values), encoding="utf-8")
    json_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return md_path, json_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare an objective reviewer-v2 packet.")
    parser.add_argument("--repo", default=".", help="Repository path.")
    parser.add_argument("--target", default="working-tree", help="Branch, commit-ish, path, or working-tree.")
    parser.add_argument("--base", default="", help="Base ref. Defaults to origin/main, origin/master, main, or master.")
    parser.add_argument("--spec", action="append", default=[], help="Spec path/ref. May be repeated or comma-separated.")
    parser.add_argument("--prompt-stdin", action="store_true", help="Read the user prompt from stdin for path/spec discovery.")
    parser.add_argument("--output-dir", default="", help="Output directory. Defaults to a temp directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    _repo, packet = build_packet(args)
    output_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix="reviewer-v2-"))
    md_path, json_path = write_outputs(output_dir, packet)
    print(f"review_packet_md={md_path}")
    print(f"review_packet_json={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
