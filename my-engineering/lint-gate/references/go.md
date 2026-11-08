# Go target

As of 2026-11-07: golangci-lint 2.15.0 (`version: "2"` config). `golangci-lint linters` lists the names of the pinned version, and `golangci-lint config verify` refuses an unknown one. `default: all` takes in every new linter at each upgrade, so the version is pinned and a bump is its own commit, re-measured.

## `.golangci.yml`

```yaml
version: "2"
linters:
  default: all
  disable:
    - exhaustruct      # forces every field in every literal; zero values are a Go idiom
    - varnamelen       # short names in short scopes are idiomatic
    - wsl              # blank-line style only
    - wsl_v5
    - nlreturn
    - godot            # comment punctuation
    - lll              # the formatter owns line length
    - funlen           # complexity finds the real problem with fewer false alarms
    - cyclop           # one complexity measure: gocognit
    - gocyclo
    - maintidx
    - dupl             # jscpd measures clones across the repo (repo.md)
    - mnd              # every literal becomes a constant with no better name
    - ireturn          # returning an interface is sometimes the design
    - testpackage      # black-box test packages are a choice
    - depguard         # decision first: on with the rules of the layers
    - paralleltest     # decision first: whether tests run in parallel
    - tparallel
    - tagliatelle      # an external wire format picks its own casing
  settings:
    gocognit:
      min-complexity: 10
    nestif:
      min-complexity: 4
    errcheck:
      check-type-assertions: true
      check-blank: true
    govet:
      enable-all: true
      disable: [fieldalignment]   # byte order of struct fields: noise outside hot paths
    exhaustive:
      default-signifies-exhaustive: false
    nolintlint:
      require-explanation: true
      require-specific: true
      allow-unused: false
    revive:
      enable-default-rules: true  # a `rules` list alone replaces the defaults
      rules:
        - name: argument-limit
          arguments: [5]
    forbidigo:
      forbid:                     # a `forbid` list replaces the default pattern, so keep it
        - pattern: ^(fmt\.Print(|f|ln)|print|println)$
        - pattern: ^os\.Exit$
          msg: exit skips every defer; return from main
        # decision first: one package owns spawns, and a test waits on a condition
        # - pattern: ^exec\.Command$
        # - pattern: ^time\.Sleep$
  exclusions:
    rules:
      - path: _test\.go
        linters: [err113, wrapcheck]
formatters:
  enable: [gofumpt, goimports]
issues:
  max-issues-per-linter: 0
  max-same-issues: 0
```

No `exclusions.presets`: each preset hides a class of findings (unchecked errors of `fmt.Fprint`, comment rules) without a reason at the site.

## Tools

| Check | Command |
|---|---|
| Format | `golangci-lint fmt --diff` |
| Lint | `golangci-lint run` |
| Module file tidy | `go mod tidy -diff` |
| Vulnerable dependency | `govulncheck ./...` |
| Unreachable code | `deadcode ./...` (golang.org/x/tools) |
| Leftovers | `godox` (on with `default: all`) |
| Tests | `go test -race -count=1 -shuffle=on ./...` |
| Coverage of the diff | `go test -coverprofile` and a diff-coverage tool |
| Mutation | `gremlins` on the changed packages |
| Go floor and tool pins | the `go` and `toolchain` lines of `go.mod`; tools by version (a `tool` directive in `go.mod`, or a binary checked by checksum in CI) |

## Measure

```
golangci-lint run --config <scratch>/.golangci.yml --output.json.path=<scratch>/gl.json ./...
python tally.py golangci gl.json --scope-depth 2
```

- `max-issues-per-linter: 0` and `max-same-issues: 0` must be in the draft: the defaults (50 per linter, 3 of the same text) cut the count, and the run still looks complete.
- `tally.py` counts staticcheck and gosec per check id (`staticcheck:SA1019`, `gosec:G104`) and revive and gocritic per rule (`revive:argument-limit`), so one linter can be split across phases.
- A `typecheck` finding means the package did not compile and was not linted: `tally.py` warns.
- Test sites: the scope column, or `tally.py diff` of a run with `--tests=false` against the full run.
- Suppressions to count: `//nolint`, `_ =` on a call that returns an error, `//go:build ignore`.
- `--new-from-merge-base=<branch>` reports only the sites on changed lines. It holds the line during a transition; it is not the end state, which reports every site.

## Exceptions

`//nolint:<linter> // <why>`. `nolintlint` with the settings above fails a bare `//nolint`, one with no reason, and one that suppresses nothing.

## Do not turn on

| Linter | Why |
|---|---|
| `exhaustruct` | every field in every literal, against zero values |
| `funlen`, `lll` | length is not the defect; complexity and the formatter cover it |
| `cyclop`, `gocyclo`, `maintidx` with `gocognit` | three scores of one property; one measure per language |
| `mnd` | named constants with no better name than the number |
