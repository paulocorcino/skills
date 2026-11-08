# Python target

As of 2026-11-08: ruff 0.17.4, mypy 2.4.1, vulture 2.16, deptry 0.25.1, pip-audit 2.10.1, complexipy 8.3.0. `select = ["ALL"]` takes in every new rule at each ruff upgrade, so the version is pinned and a bump is its own commit, re-measured.

## Ruff (`pyproject.toml` `[tool.ruff]`, or `ruff.toml`)

```toml
line-length = 100
target-version = "py312"               # the floor of requires-python; with none, the version the deploy runs (a Dockerfile, CI)

[lint]
select = ["ALL"]
ignore = [
  "COM812", "ISC001",                  # conflict with the formatter
  "D",                                 # docstrings everywhere produce empty ones to pass; D1 on a published library's public API only
  "CPY",                               # a copyright header is a policy, not a defect
  "TRY003", "EM101", "EM102",          # message style; the exception type carries the meaning
  "PLR2004",                           # every literal becomes a constant with no better name
]

[lint.mccabe]
max-complexity = 10                    # C901

[lint.pylint]
max-args = 5                           # PLR0913; PLR0917 limits positional ones

[lint.flake8-tidy-imports]
ban-relative-imports = "all"

[lint.flake8-tidy-imports.banned-api]
"os._exit".msg = "exit skips cleanup: return from main"
# decision first: one module owns spawns, and a test waits on a condition
# "subprocess.Popen".msg = "spawn only through <pkg>.proc"
# "time.sleep".msg = "a test waits on a condition, not on a time"

[lint.per-file-ignores]
"tests/**" = ["S101"]                  # pytest asserts
```

Rules `ALL` brings that carry the agent errors: `BLE001` (blind `except`), `S110` (`except: pass`), `ANN401` (`Any`), `T20` (`print`), `ERA001` (commented-out code), `FIX002` (a `TODO` left behind), `PGH003` (bare `type: ignore`), `PGH004` (bare `noqa`), `RUF100` (a `noqa` that suppresses nothing), `FBT` (boolean flags), `ARG` (unused arguments).

Ruff's complexity (`C901`) is cyclomatic. For cognitive complexity, the measure that counts nesting, add `complexipy --max-complexity-allowed 10`.

## Type checker

Keep the one the repo has. mypy:

```ini
[mypy]
strict = true
warn_unreachable = true
disallow_any_explicit = true
disallow_any_unimported = true
enable_error_code = ignore-without-code, redundant-expr, truthy-bool, truthy-iterable, possibly-undefined, unused-awaitable, explicit-override, mutable-override, deprecated, redundant-self
```

An unknown error code fails the config: check the list against the pinned mypy. `disable_error_code` does not turn off a code that `enable_error_code` names (mypy 2.4.1, measured): a code with debt leaves `enable_error_code` until its phase (`debt.py mypy --enabled <the list>` names them).

pyright: `"typeCheckingMode": "strict"`, plus `reportUnnecessaryTypeIgnoreComment`, `reportImplicitOverride`, `reportUninitializedInstanceVariable` and `reportImportCycles` at `"error"`.

## Tools

| Check | Command |
|---|---|
| Format | `ruff format --check` |
| Lint | `ruff check` |
| Types | `mypy` or `pyright` over the package and its tests |
| Cognitive complexity | `complexipy --max-complexity-allowed 10` |
| Declared, unused or missing dependency | `deptry .` |
| Dead code (functions, classes, imports nobody uses) | `vulture <paths> --min-confidence 80`, counted by `tally.py vulture`; a false positive goes in a whitelist file, which a ratchet holds |
| Vulnerable dependency | `pip-audit` or `osv-scanner` |
| Lockfile matches the project | `uv lock --check` (or the lock tool's equivalent) in CI |
| Import layers | `import-linter` contracts (decision first) |
| Tests | pytest with `--strict-markers --strict-config`, `xfail_strict = true`, `filterwarnings = ["error"]`, no rerun plugin |
| Coverage of the diff | `diff-cover` over the coverage report |
| Mutation | `mutmut` on the changed modules |
| Python floor | a CI job on the lowest `requires-python` |

## Measure

- **The debt list**: `debt.py ruff --sites <ruff tally>` prints the `ignore` array and `debt.py mypy --sites <mypy tally>` the `disable_error_code` list, each entry under its `debt:` comment; `debt.py shrink` reads both.
- **Ruff**: `ruff check --config <scratch>/ruff.toml --output-format json --no-cache . > ruff.json`. `--config` with a file replaces the repo's settings, so the draft holds every setting, `extend-exclude` included.
- **mypy**: `mypy --config-file <scratch>/mypy.ini -O json <packages>`, run by the interpreter that has the project's dependencies (`--python-executable <venv>/python` when mypy lives elsewhere), or every import is `Any` and the count drops. **pyright**: `pyright -p <scratch>/pyrightconfig.json --outputjson`; paths in a pyright config are relative to the config file, so the draft names the repo's paths absolutely.
- **Nesting depth**: ruff's only depth rule (`PLR1702`) is a preview rule, out of a pinned gate: the knob is `n/a` for Python unless the repo runs preview, and complexity carries nesting.
- **deptry** reads only what it finds as the project's code: pass the test folders too, or their imports are not checked (measured: 12 of 34 files read).
- complexipy, deptry and pip-audit have no `tally.py` format: their counts come from their own JSON (`--output json`, `-o`, `-f json`), recorded with the command.
- Test sites: run with `tests/` excluded and with it included, then `tally.py diff`, or read the scope column with `--scope-depth`.
- Suppressions to count: `# noqa`, `# type: ignore`, `# pyright: ignore`, `# pragma: no cover`, `typing.cast(`, `Any`.

## Exceptions

`# noqa: <CODE>  # <why>` and `# type: ignore[<code>]  # <why>`. Ruff and mypy do not check the reason, so a ratchet test counts `noqa` and `type: ignore` comments without a trailing reason, and that count may only go down. `RUF100` and mypy's `warn_unused_ignores` (in `strict`) fail a suppression that suppresses nothing.

## Do not turn on

| Rule | Why |
|---|---|
| the `D` group everywhere | empty docstrings to pass |
| `PLR2004` magic values | named constants with no better name than the number |
| `disallow_any_expr` | it fails on every value a library types as `Any`; `disallow_any_explicit` covers what the code writes |
| ruff `preview` rules in the gate | they change between releases; take one in when it becomes stable |
