# Monorepo and multi-project configuration

Quality Gate auto-detects projects by scanning for language manifests (e.g. `pyproject.toml`, `go.mod`, `Cargo.toml`, `package.json` + `bun.lockb`). In monorepos with multiple projects, each manifest is treated as a separate project and analyzed independently.

## Autodetect heuristic

Quality Gate searches the target repo for manifests at any directory depth:

- **Python:** `pyproject.toml`, `setup.py`, `requirements.txt`
- **Go:** `go.mod`
- **Rust:** `Cargo.toml`
- **BunJS:** `package.json` with `bun.lockb` in the same or parent directory

For each manifest found, Quality Gate:

1. Determines the language from the manifest type
2. Sets the project root to the directory containing the manifest
3. Creates a unique project key (e.g. `python_myapp`, `go_backend`, `rust_core`)
4. Runs the corresponding language pack against that root

## Baseline namespacing

Each project's metrics are stored separately in the baseline:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-12T10:00:00Z",
  "commit": "abc123def456...",
  "projects": {
    "python_myapp": {
      "language": "python",
      "root": "./packages/myapp",
      "coverage": 75.5,
      "violations": {...},
      "files": {...}
    },
    "go_backend": {
      "language": "go",
      "root": "./services/backend",
      "coverage": 82.0,
      "violations": {...},
      "files": {...}
    }
  }
}
```

Per-project metrics are compared independently. A regression in one project does not prevent other projects from passing.

## Overriding autodetect with `.quality-gate/config.json`

If autodetect does not find your projects, or if you want to customize limits per project, use `.quality-gate/config.json`:

```json
{
  "projects": [
    {
      "root": "./packages/myapp",
      "language": "python",
      "soft_limit": 300,
      "hard_limit": 800
    },
    {
      "root": "./services/backend",
      "language": "go",
      "soft_limit": 500,
      "hard_limit": 1000
    }
  ]
}
```

**Schema:**
- `projects` (array, required) — list of projects to analyze
- `root` (string, required) — project directory relative to repo root
- `language` (string, required) — one of `python`, `go`, `rust`, `bunjs`
- `soft_limit` (integer, optional) — cyclomatic complexity soft limit for this project
- `hard_limit` (integer, optional) — cyclomatic complexity hard limit for this project

If a project is listed in `config.json`, it overrides autodetect. If `config.json` is absent, autodetect is used.

## Per-language flags

When working with specific projects, use `--language` and `--only` flags:

```bash
# Run only Python projects
python -m quality_gate --cwd /path/to/repo run --language python

# Run only the "backend" project
python -m quality_gate --cwd /path/to/repo run --only backend

# Run only Python projects named "backend"
python -m quality_gate --cwd /path/to/repo run --language python --only backend
```

- `--language LANG` — filter to one language (python, go, rust, bunjs)
- `--only KEY,KEY,...` — filter to specific project keys (comma-separated)

If neither flag is specified, all detected projects are analyzed.

## Example: a three-project monorepo

```
myrepo/
├── pyproject.toml              # Python project at root
├── packages/
│   └── lib-go/
│       └── go.mod              # Go project
└── services/
    └── api-rust/
        └── Cargo.toml          # Rust project
```

Autodetect finds three projects:
- `python_myrepo` at `./` (Python)
- `go_lib-go` at `./packages/lib-go` (Go)
- `rust_api-rust` at `./services/api-rust` (Rust)

Each has independent metrics in the baseline. `quality-gate run` analyzes all three in a single command, emitting a report with one table per project.

To override the `soft_limit` for just the Go project:

```json
{
  "projects": [
    {
      "root": "./packages/lib-go",
      "language": "go",
      "soft_limit": 600
    }
  ]
}
```

Now the Go project uses a 600-complexity soft limit, while Python and Rust use defaults.

## FAQ

**Q: Can I have two Python projects at different roots?**
A: Yes. Autodetect finds each `pyproject.toml` independently. Each becomes a separate project with its own metrics and baseline entry.

**Q: What if I want to analyze only one project and skip the others?**
A: Use `--only <project-key>` to filter to a single project.

**Q: How are project keys generated?**
A: `<language>_<dirname>` where `<dirname>` is the lowest-level directory name of the project root. For `/repo/packages/myapp/pyproject.toml`, the key is `python_myapp`.

**Q: Can I rename a project key?**
A: Not without rebaselining. If you rename a directory, use `.quality-gate/config.json` with an explicit `root` to maintain continuity. Or capture a new baseline after the rename.

**Q: Do all projects need the same main branch?**
A: Yes, the baseline stores one `main_branch` globally. All projects compare against the same baseline commit.
