# Go target

As of 2026-11-07: golangci-lint 2.15.0 (`version: "2"` config). `golangci-lint linters` lists the names of the pinned version, and `golangci-lint config verify` refuses an unknown one. `default: all` takes in every new linter at each upgrade, so the version is pinned and a bump is its own commit, re-measured.

## `.golangci.yml`

```yaml
version: "2"
linters:
  default: all
  disable:
    # `default: all` turns deprecated linters on too: their names stay here
    - exhaustruct      # deprecated; and it forces every field in every literal, against zero values
    - exhaustruct_v5   # its successor, the same rule
    - varnamelen       # short names in short scopes are idiomatic
    - wsl              # deprecated; blank-line style only
    - wsl_v5
    - gomodguard       # deprecated; depguard holds the imports
    - gomodguard_v2
    - nlreturn
    - godot            # comment punctuation
    - lll              # gofmt owns layout and does not wrap lines; the line-width knob is not asked for Go
    - funlen           # complexity finds the real problem with fewer false alarms
    - cyclop           # one complexity measure: gocognit
    - gocyclo
    - maintidx
    - dupl             # jscpd measures clones across the repo (repo.md)
    - mnd              # every literal becomes a constant with no better name
    - ireturn          # returning an interface is sometimes the design
    - testpackage      # black-box test packages are a choice
    - depguard         # decision first: on with the rules of the layers (below)
    - paralleltest     # decision first: whether tests run in parallel
    - tparallel
    - tagliatelle      # an external wire format picks its own casing
  settings:
    gocognit:
      min-complexity: 10
    nestif:
      min-complexity: 4           # nestif scores nested blocks; the depth knob (3) is revive's max-control-nesting
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
        - name: max-control-nesting
          arguments: [3]
    gosec:
      config:                     # the widest mode each rule accepts; a tool that writes files with these modes is not a finding
        G301: "0755"
        G302: "0755"
        G306: "0644"
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
# conventions (SKILL.md § Rule classes), each on or off by the answer of step 3:
# whitespace, usestdlibvars, intrange, copyloopvar, canonicalheader, decorder, grouper,
# funcorder, inamedparam, tagalign, embeddedstructfieldcheck, and the gocritic checks
# tagged `style`. Waste: perfsprint, prealloc, mirror. Surface, not conventions:
# nonamedreturns, nakedret, errname (a name or a scope a reader can misread).
issues:
  max-issues-per-linter: 0
  max-same-issues: 0
  uniq-by-line: false             # the default keeps one issue per line and hides the rest
```

`depguard`, once its decision is taken: `list-mode: strict` with an `allow` list denies every import outside it (`lax` with a `deny` list lets an unlisted import through, measured):

```yaml
    depguard:
      rules:
        main:
          list-mode: strict
          files: [$all]
          allow: [$gostd, <module path>]   # plus each dependency the decision admits
```

No `exclusions.presets`: each preset hides a class of findings (unchecked errors of `fmt.Fprint`, comment rules) without a reason at the site.

## Tools

| Check | Command |
|---|---|
| Format | `golangci-lint fmt --diff` |
| Lint | `golangci-lint run` |
| Module file tidy | `go mod tidy -diff` |
| Vulnerable dependency | `govulncheck ./...`: its result depends on the Go toolchain that runs it as much as on the code (measured: 15 standard-library findings at one patch release, all fixed by a later one), so the toolchain is pinned |
| Unreachable code | `deadcode ./...` (golang.org/x/tools); it exits 0 when it reports, so the gate fails on any output: `test -z "$(deadcode ./...)"` |
| Leftovers | `godox` (on with `default: all`) |
| Tests | `go test -race -count=1 -shuffle=on ./...` |
| Coverage of the diff | `go test -coverprofile` and a diff-coverage tool |
| Mutation | `gremlins` on the changed packages |
| Go floor and tool pins | the `go` and `toolchain` lines of `go.mod`, or the exact toolchain in CI (`go-version`, `GOTOOLCHAIN`); tools by version, in a tools module run as `go tool -modfile=tools/go.mod <tool>` so the product's `go.mod` stays as it is. Two tools whose dependencies conflict (golangci-lint and actionlint, measured) take a module each |

## Measure

```
golangci-lint run --config <scratch>/.golangci.yml --output.json.path=<scratch>/gl.json ./...
python tally.py golangci gl.json --scope-depth 2
```

- `max-issues-per-linter: 0`, `max-same-issues: 0` and `uniq-by-line: false` must be in the draft: the defaults (50 per linter, 3 of the same text, one issue per line) cut the count, and the run still looks complete (measured: 459 sites with `uniq-by-line` at its default, 543 without).
- A draft outside the repo sets `run.relative-path-mode: wd`, or the paths come out relative to the draft's folder and `--scope-depth` groups them wrongly.
- A 0 is evidence when the run read every file: `go list -f '{{len .GoFiles}} {{len .TestGoFiles}} {{len .XTestGoFiles}}' ./...` summed against `git ls-files '*.go' | wc -l`.
- The debt list: `debt.py golangci --sites <tally.json>... [--noise noise.json] --by-id gosec,gocritic` prints the `disable` block, and `debt.py shrink` reads its list items. A linter in `disable` is off whole, so its checks with no site go unenforced: `--by-id` keeps gosec and gocritic on and lists only their check ids with sites (`settings.gosec.excludes`, `settings.gocritic.disabled-checks`). revive and govet have no list form `--by-id` writes: each stays in `disable` while any of its checks has sites (govet's `shadow`, say), which turns its other checks off for that window; the plan's first slice for it removes those sites. A linter off whole cannot flip per scope; it flips once, in the slice that removes its last site.
- Measuring a linter of the debt list: `--enable-only <linter>` runs it with the config's settings and exclusions; `-E <linter>` does not turn on a linter that `disable` names.
- A count can depend on which linters run beside it (measured: gosec G703 at 6 with the whole debt list, 5 alone): confirm a 0 with the full set.
- The nesting curve: `tally.py curve golangci <run at min-complexity 1> --rule nestif`. nestif reports a block from `min-complexity` on, so the curve's count over L is what a run at L + 1 reports.
- `tally.py` counts staticcheck and gosec per check id (`staticcheck:SA1019`, `gosec:G104`) and revive and gocritic per rule (`revive:argument-limit`), so one linter can be split across phases.
- A `typecheck` finding means the package did not compile and was not linted: `tally.py` warns.
- The test column is a floor for the linters the config excludes in `_test.go` (`err113`, `wrapcheck`): their test sites are not counted.
- `go tool -modfile=...` builds the tool for the host OS: a CI matrix over platforms runs the lint on a runner per OS, or a prebuilt binary with `GOOS` set.
- Test sites: by file name (`_test.go`). A `tally.py diff` of a run with `--tests=false` against the full run misplaces a production site that only shows when the tests are loaded (measured: three `gosec:G602` sites in `main.go`).
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
