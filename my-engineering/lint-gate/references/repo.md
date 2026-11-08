# Repository target

As of 2026-11-08: no version pinned here; each tool runs at its latest stable release.

The checks that hold for every stack. Each row is measured like a lint rule: its count today, or `n/a — <why>`, or `decision — <question>`.

## The gate itself

| Check | Form |
|---|---|
| One local command | `just check`, `make check`, an xtask or a script runs every check below and every stack's checks, prints one row per check, and exits non-zero on any failure |
| CI mirrors it | a test reads the CI workflows and the gate's step list, and fails when a CI check has no local step or a local step names a CI step that is gone |
| No warn level | every linter runs with its deny-warnings flag (`-D warnings`, `--deny-warnings`, `--max-warnings 0`) |
| Pinned tools | every tool in CI by exact version, fetched binaries checked by checksum; a test compares the pin in CI with the pin in the docs |
| New releases of the pinned tools | a scheduled CI job: the latest stable release of each pin, and `drift.py diff` of the rule lists when it is newer; a newer release opens an issue, so drift is found without a run of this skill |
| Locked dependencies | every install and build in CI with the lockfile flag (`--locked`, `--frozen-lockfile`, `uv sync --locked`) |

## Structure and size

| Check | Tool |
|---|---|
| No new duplicated block | jscpd with `--fail-on-new-clones 0` against the base branch (it reads every stack) |
| The existing duplicated blocks only go down | the jscpd JSON report counted by `tally.py jscpd --expect N`, N the count today (strategy: count ratchet) |
| Function complexity at most 10 | the linter of each stack. A tool that scores only the code compiled for the host (clippy under `#[cfg]`, Go under build tags) misses the other platforms; a scorer that reads the source text counts every branch |
| File size at most N lines | a CI script |
| Inline test block at most N lines | a CI script |
| Direction of dependencies | the package graph, or an import rule (`no-restricted-imports`, `depguard`, `import-linter`) — decision first |
| Ratchets as tests | a test, or `tally.py pattern REGEX --ext ... --expect N`, counts a forbidden pattern and holds the count in a constant. It fails when the count is above the constant, and when it is below: the change that removes a site lowers the constant, so the gain is locked |

## Tests

| Check | Tool |
|---|---|
| No automatic retry | retries off in the runner: a flaky test fails |
| Doctests run | each stack's doctest command |
| Coverage of the diff at least N% | measured on changed lines only |
| The test catches the real error | mutation testing on the diff: the automatic form of "see the test go red" |
| No silent snapshot update | snapshot tools in CI with updates off and unreferenced snapshots rejected |
| No focused or skipped test left behind | the test lint of each stack; a ratchet on skips, each with a reason |

## Security

| Check | Tool |
|---|---|
| A secret in the code | gitleaks, in the gate and in CI |
| A vulnerable dependency | each stack's audit tool, osv-scanner for vendored code |
| Static analysis | CodeQL |
| An unsafe workflow | zizmor and actionlint; actions pinned by SHA; the smallest `permissions:` |
| Dependency updates | Dependabot or Renovate, in groups, with a cooldown before a new release is proposed (zizmor flags a Dependabot config without one) |

## Text and files

| Check | Tool |
|---|---|
| A typo in code or docs | `typos`, accepting only words spelled that way on purpose |
| Shell scripts | shellcheck and shfmt on every tracked `.sh` file, not only the `run:` steps a workflow linter reads |
| PowerShell scripts | PSScriptAnalyzer (`Invoke-ScriptAnalyzer -Recurse -EnableExit`) on every tracked `.ps1` file |
| HTML and CSS | `html-validate` and `stylelint` on the files the repo writes (vendored files out) |
| TOML, YAML, Markdown | taplo, yamllint, markdownlint |
| A broken link in the docs | lychee |
| Line ends and encoding | `.gitattributes` and editorconfig-checker |
| A generated file out of date | run the generator, then `git diff --exit-code` |
| Commit message format | commitlint, or a small CI check |
| Changelog | one fragment per pull request, checked by CI |
| Internal words in user-facing text | a check written for the project (an issue number or a decision id in an error message) |

## Flow

| Check | Form |
|---|---|
| Protected main branch | every check required; changes reach main only through a pull request |
| An agent hook | refuses `--no-verify`, a force push, and an edit nobody asked for to a baseline, a ratchet constant or a linter config |
| Shift left | a per-edit agent hook runs the fast linters and the formatter check on the changed files and hands the output back to the agent; the editor reads the same config files, so a rule set only by a CLI flag is invisible there |
| Pre-commit hook (optional) | only the fast checks over changed files; CI is the real gate |

## Measure the duplication

```
jscpd --min-tokens 30 --min-lines 5 --reporters json --output <scratch> <paths>
python tally.py jscpd <scratch>/jscpd-report.json --prefix <path>/ --scope-depth 2
python tally.py curve jscpd <scratch>/jscpd-report.json --rule jscpd:<language> --prefix <path>/ --at 30,50,75,100
```

- jscpd reads the repo's `.jscpd.json` even with flags on the command line: its ignore list holds, and each flag replaces only its own setting. `--min-tokens` alone keeps the file's `minLines`: pass both sizes.
- The `curve` is an estimate from one run at the lowest size; the count at the chosen size comes from a run at that size (measured: the curve gave 186 clones at 50 tokens, a run at 50/5 gave 225).
- jscpd 4.x names each file from the folder it scanned, and `--prefix` puts that folder back; jscpd 5.x names files from the repo root already, and `--prefix` then breaks them. Check one path of the report before tallying.
- jscpd reads code blocks in Markdown: the plan's target configs and the copied scripts would count as clones. Ignore both, with the reason.
- A site is one clone: a block copied to three places is two clones.

## Exits

The ways to turn the gate green without fixing the code. Each one is `closed by <check>` or `open`; an open exit is a row of the plan.

| Exit | Closed by |
|---|---|
| A warn level | every linter with its deny-warnings flag |
| A bypass (`--no-verify`, a force push, a merge with a red check) | the agent hook, and the protected branch with every check required |
| An unasked edit to a lint config, a debt list, an ignore list or a ratchet constant | the agent hook; `debt.py shrink` against the base branch; a ratchet test on each ignore list (`ignorePatterns`, `extend-exclude`, `per-file-ignores`, `_typos.toml`) whose size only goes down |
| A suppression with no reason, or one that suppresses nothing | each stack's own checks (`allow_attributes_without_reason`, `nolintlint`, `RUF100`, unused disable directives, `ban-ts-comment`) |
| A blanket or file-level suppression (`@ts-nocheck`, a file-level disable, a crate-root `allow`) | the blanket rule of the stack (`PGH004`, `ban-ts-comment`, `allow_attributes`), and a ratchet that counts file-level disables |
| A path no check reads (a new directory outside every glob) | the gate's tools take the repo root or `git ls-files`, not a hand list of folders; the measure checks that each run read the files the inventory lists |
| A skipped or deleted test | the skipped-test ratchet (each skip with its reason, the count only down), and mutation testing on the diff |
| A weakened test (an assertion that checks nothing) | mutation testing on the diff |
| Code the gate does not build (`#[cfg]` of another platform, a feature, a build tag) | `--all-features` and the platform matrix in CI |
| A split into helpers with no responsibility, to pass a complexity limit | open: no tool tells a responsibility from a cut; a human reads the split |
| Two rules merged into one helper to remove a clone | open: no tool tells one rule from two that look alike; a human reads the merge |
| A clone hidden by an ignore marker (`jscpd:ignore-start`) | a ratchet that counts the markers, each with its reason |
| A row of a reference that the lint gate run skipped | `rows.py check` on the plan |
| An `ast-grep-ignore` with no rule id, or on the first line of a file | the ratchet at 0 on ignores without a rule id and a reason (§ ast-grep) |
| A force push to the default branch that drops the base commit: `shrink` against an empty base passes | branch protection on the default branch (no force push); a pull request compares with its merge base |
| The skill's own artifacts in the repo (the copied scripts, the plan's code blocks) counted or linted as the repo's code | excluded from the linters and jscpd by path, with the reason, and named in the plan |
| A new `noise:` entry in a debt list: a debt rule off "for good" | `debt.py shrink` fails unless the reason cites a decision id the plan records |
| A fake reason on an exception | open: a ratchet counts the exceptions, and a human reads each new one |

## Agent docs

Every rule of the agent docs is `checked by <check>` or `advice` (step 1). For each `advice` rule a tool could check, the plan adds the check, from the cheapest rung that expresses it:

1. A setting of a rule that already exists: a pattern rule takes a list (`disallowed-methods`/`disallowed-types`, ruff `banned-api`, `forbidigo`, `no-restricted-imports`/`no-restricted-syntax`, `depguard`).
2. An ast-grep rule (§ ast-grep): a pattern over the syntax tree, the same YAML for every language, with its message and its tests. It sees syntax only: no types, no scopes, nothing across files.
3. A ratchet test that counts the pattern in the source text: for what has no syntax (a comment's wording, a file's name), or a count that only goes down.
4. A rule of its own in the linter's plugin system (an ESLint or oxlint JS plugin, a golangci-lint module plugin over `go/analysis`, a dylint library for Rust), for a rule that needs types or scopes. Ruff has no plugins: Python stops at rung 3.

A check of rung 2, 3 or 4 is code the gate trusts, so it is built like code:

- **Its message is the fix.** It names what to do at the site, in the words of the rule's class ("parse the value at its boundary and return a named type"), not only what is wrong: the agent reads the message in its edit loop and nothing else.
- **It has tests**: the code it must refuse and the code it must let through, one case per false positive found.
- **A vendored one keeps its provenance**: the upstream repository and commit beside the copy. An update stages the new upstream apart and merges it three ways (the old upstream, the local copy, the new upstream), so a local change survives.

What the doc then says about the check is in `agent-docs.md`.

## ast-grep

Two reasons to take it in, asked apart in step 3:

- **The agent's navigation**, in any repo: `outline` maps a file before it is read, and a search by shape finds what grep misreads. It installs the tool and its guide, with no gate step. Measured (a synthetic Rust repo, n=3 per arm, the tool installed in both): with the guide and its pointer the agent outlined the large file instead of reading it and cost 49% less, at the same accuracy; without them it never touched the installed tool. `outline` is alpha: its pin is checked by `drift.py age`, not by the gate.
- **Gate rules**, only when there are candidates: step 1 lists them (each `advice` rule of the agent docs that no setting of rung 1 expresses, and each pattern held today by a text ratchet that has a syntax); step 2 measures each as a draft rule. A gate step with no rule checks nothing, so the scan and the tests join the gate with the first rule.

Step 5 installs it once approved, for either reason.

- **Install**: `@ast-grep/cli` from npm, `ast-grep-cli` from PyPI or `ast-grep` from crates.io, by the package manager the repo already has, at an exact version. A repo with none of them (a Go module, say) runs it through a pinned one-shot line, `npx -y -p @ast-grep/cli@<version> ast-grep` (the package has two binaries, so `-p` and the name are needed) or `uvx --from ast-grep-cli@<version> ast-grep`, written in the guide, with no gate step until it has a rule. It is 0.x: a minor release can change a rule's matches, so a bump is its own commit, re-measured.
- **Layout**: `sgconfig.yml` at the root with `ruleDirs` and `testConfigs`; one rule per file, its `id` the file name; `languageGlobs` maps `.js` and `.mjs` to the TypeScript grammar when one rule covers both.
- **Gate**: `ast-grep test --skip-snapshot-tests` and `ast-grep scan --error=unused-suppression`; a rule at `severity: error` makes the scan exit 1. Both run in the local gate and in CI. The scan of the gate runs every rule: `--filter`, `--rule`, `--inline-rules` or `--off` turn the unused-suppression report off without a word.
- **Measure**: `ast-grep scan -c <scratch>/sgconfig.yml --json=stream <paths> > out.jsonl`, read by `tally.py astgrep`. A clean run prints nothing, so a 0 is evidence only with a probe: the same rule without its condition (the regex or the constraint) counts every site it inspected. A vendored folder the repo tracks is excluded with `--globs '!**/vendor/**'` (measured: it held most of the matches).
- **Scope by path**: `files:` and `ignores:` globs in a rule. A path condition and a syntax condition are not ORed in one rule, so "test code" (a `tests/` file or an inline `#[cfg(test)]` module) takes two rules: one with `files:`, one with `inside: {kind: mod_item, follows: {kind: attribute_item, regex: 'cfg\(test\)'}, stopBy: end}`. An `ignores:` list of debt sites is a debt list of its own; `debt.py shrink` does not read YAML, so a ratchet test holds it.
- **A rule**: its message says what to do, in the words of the rule's class; `valid` cases hold every false positive found, `invalid` cases every form of the failure. YAML: a message with `: ` in it is quoted. `inside` and `has` look at the direct parent or child by default; `stopBy: end` widens them to every ancestor or descendant (measured: a rule on the string argument of `.context()` then matched the string of another call in the same chain), so it goes in only where the rule means any depth.
- **The agent's guide**: step 5 writes `ast-grep-guide.md` into the repo, filled and checked on it, and the agent doc points at it from its tools section (`agent-docs.md` § The tools section), outside the lint gate block: the tool then serves the agent's navigation, search and rewrites too, not only the gate. ast-grep publishes its own docs for agents (`https://ast-grep.github.io/llms.txt`, one `.md` per page) and an agent skill (`ast-grep/agent-skill`): the guide is checked against them at the pinned version and points at them for rule writing, instead of copying them.
- **Exception**: `// ast-grep-ignore: <rule-id> -- <why>` on the line above, or at the end of the line; the reason after the id leaves the directive working, and the scan reports one that suppresses nothing. A comment is a directive when `ast-grep-ignore` is its first word, in any comment form: `//`, `///`, `//!`, `#`, and in backticks too. A bare one silences every rule on its line or the next, and on the first line of a file followed by a blank line it silences the whole file (measured: a module doc `` //! `ast-grep-ignore` names... `` on line 1 hid a shell spawn). A comment that talks about the directive starts with another word. A ratchet at 0 refuses every directive without a rule id and a reason (`tally.py pattern '(//[/!]?|#)\s*`?ast-grep-ignore`?(?!:\s*[\w,\s-]+?\s--\s+\S)' --ext <exts> --expect 0`), and another counts them (`tally.py pattern '(//[/!]?|#)\s*`?ast-grep-ignore' --ext <exts> --expect N`).

## Where the tools look

- A Windows checkout with `core.autocrlf` has CRLF files in the working tree: shellcheck, the formatters and yamllint report every line until the line endings are fixed (`.gitattributes`). Measure them on an LF copy until then: `git -c core.autocrlf=false archive HEAD | tar -x -C <scratch>/lf` (a plain `git archive` on Windows writes CRLF too).

A linter run over a folder reads every file in it, tracked or not. An agent's own folders (`.claude/`, `.agents/`, `.codex/`, `.cursor/` and the like) hold installed skills, hooks and, in some setups, whole worktrees of the repo: a run over them counts another copy of the code, or code the repo does not own. Measure over the tracked files (`git ls-files` feeds the paths), or put each such folder in the tool's ignore list; the folders the repo tracks as its own source stay in.

## Suppressions

Count every suppression form of every stack (each stack reference lists its forms), the duplication markers (`jscpd:ignore-start`), and every exception without a reason. They are debt the lint run cannot see: the tool honors them.
