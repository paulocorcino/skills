# TypeScript target

As of 2026-11-08: oxlint 1.92.0, oxlint-tsgolint 7.0.2006, typescript 7.0.2, typescript-eslint 8. oxlint 1.90 and later need oxlint-tsgolint 7.0.2005 or later.

## `tsconfig.json`

```jsonc
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitReturns": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noPropertyAccessFromIndexSignature": true,
    "noUncheckedSideEffectImports": true,
    "allowUnreachableCode": false,
    "allowUnusedLabels": false,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "erasableSyntaxOnly": true,          // refuses enum, namespace, parameter properties
    "forceConsistentCasingInFileNames": true
  }
}
```

The gate runs `tsc --noEmit`.

## Linter

oxlint with `--type-aware` (needs the `tsgolint` binary), or ESLint with typescript-eslint `strictTypeChecked`. Keep the one the repo has.

Rules that need type information:

| Group | Rules |
|---|---|
| Promises | `no-floating-promises`, `no-misused-promises`, `await-thenable`, `return-await` (`in-try-catch`), `prefer-promise-reject-errors`, `only-throw-error`, `require-await` |
| Unsafe types | `no-explicit-any`, `no-unsafe-assignment`, `no-unsafe-member-access`, `no-unsafe-call`, `no-unsafe-argument`, `no-unsafe-return`, `no-unsafe-type-assertion`, `no-unsafe-enum-comparison`, `no-unsafe-enum-assignment`, `no-generated-empty-object-type` (a utility type that resolves to `{}`, which takes any non-null value), `no-non-null-assertion`, `no-unnecessary-type-assertion`, `no-redundant-type-constituents` |
| Truth and null | `strict-boolean-expressions`, `prefer-nullish-coalescing`, `no-unnecessary-condition` |
| Strings | `restrict-template-expressions`, `restrict-plus-operands`, `no-base-to-string` |
| Closed sets | `switch-exhaustiveness-check` (a `default` does not count as covering a union) |
| Other | `no-deprecated`, `require-array-sort-compare`, `use-unknown-in-catch-callback-variable`, `unbound-method`, `no-confusing-void-expression`, `consistent-type-imports`, `consistent-type-exports` |

Rules with no type information: the `correctness`, `suspicious` and `pedantic` categories as errors, each noise rule off with a reason in the config. Plugins: `typescript`, `unicorn`, `import`, `promise`, and the test runner's.

| Group | Rules |
|---|---|
| Logic | `eqeqeq` (`null: ignore` when `== null` is the house idiom), `no-shadow`, `no-param-reassign`, `prefer-const`, `no-var`, `no-implicit-coercion`, `curly` (`all`), `default-case-last`, `radix` |
| Control flow | `no-nested-ternary`, `no-else-return` with `allowElseIf: false` (guard clauses) |
| Size | `complexity` (max 10, `variant: "modified"`, so an exhaustive `switch` counts once), `max-depth` (max 3), `max-params` (max 4) |
| Imports | `import/no-cycle`, `import/no-duplicates`, `import/no-self-import`, `import/first`, `import/extensions`, `import/no-default-export` (one name in every file, so grep finds it) |
| Architecture | `no-restricted-imports`, `no-restricted-globals` for the layers (decision first). `no-restricted-syntax` is ESLint only: oxlint 1.92 does not have it, so a ban on a syntax form there is an ast-grep rule (`repo.md` § ast-grep) |
| Sinks | `no-eval`, `no-implied-eval`, `no-new-func`, `no-script-url`, and `no-restricted-properties` on `innerHTML`, `outerHTML`, `insertAdjacentHTML` and `document.write` (`{ "property": "innerHTML", "message": "..." }`): class Capability, the one module that sanitizes HTML carries the exception |
| Leftovers | `no-warning-comments` (a `TODO` or `FIXME` left in the code; in the `pedantic` category) |
| Suppressions | `ban-ts-comment` with a description required; a disable comment needs a reason; an unused disable comment fails |
| unicorn | `throw-new-error`, `error-message`, `no-array-sort` (`toSorted`), `prefer-node-protocol`, `no-useless-undefined` |
| Tests | `no-focused-tests`, `no-disabled-tests`, `expect-expect` |
| Logs | `no-console`, allowed only in the logging module |
| Performance | `oxc/no-accumulating-spread` (class Waste: a spread of the accumulator inside `reduce` or a loop copies it each pass; in the `perf` category, which stays off) |

Conventions (SKILL.md § Rule classes), each on or off by the answer of step 3: `unicorn/prefer-node-protocol`, `unicorn/no-useless-undefined`, `unicorn/explicit-length-check`, `unicorn/no-hex-escape`, `unicorn/escape-case`, `unicorn/prefer-string-replace-all`, `unicorn/prefer-query-selector`, `unicorn/no-negated-condition`, `unicorn/prefer-at`, `unicorn/prefer-dom-node-dataset`, `typescript/no-unnecessary-boolean-literal-compare`; the `style` category stays off. These fail the test, so they are not conventions: `curly` and `unicorn/no-array-callback-reference` are Surface, a form a reader misreads (a line added under a brace-less `if` runs every time; `map(parseInt)` passes the index as the radix); `unicorn/prefer-add-event-listener` is Dropped value (`onclick =` drops the handler set before it); `unicorn/prefer-string-starts-ends-with` is Waste (a regex test pays for the regex engine).

## Optional family: anti-slop

[anti-slop](https://github.com/dmmulroy/anti-slop) is a set of oxlint JS plugin rules aimed at the escape hatches agents take in TypeScript: widen a value to `unknown`, then assert it back. It is vendored, not installed: the repo copies the plugin (`tools/oxlint/anti-slop/` by default), owns it, and records the upstream commit it came from (this table: commit `13909c9`, measured on 328 files, a TypeScript UI and its JavaScript tests). Three facts shape its use:

- oxlint JS plugins are alpha (oxlint 1.92 docs). The plugin imports `@oxlint/plugins`, pinned at exactly the oxlint version, so a bump moves both.
- Its rules read the syntax tree and the aliases of one file, with no type checker: they approximate more than the type-aware rules, and miss what crosses an import.
- Its author states it is a taste. Each rule is taken one at a time, by its class and its count, never the whole set.
- Measuring it fetches outside code into the scratch folder: step 1 asks the user for the yes, so step 2 measures it and step 3 asks with the counts.

| Rule | Class | Target |
|---|---|---|
| `no-chained-type-assertions`, `no-widen-then-assert` | Escape hatch | on with the type-aware rules: they name the double cast that `no-unsafe-type-assertion` flags only at its second step |
| `no-unknown-returns`, `no-unknown-type-aliases`, `no-unsafe-dictionary-type`, `no-object-parameters`, `no-reflect-get`, `no-reflect-apply` | Escape hatch | on: the boundary parser that returns a named type carries the exception |
| `no-known-value-widening` | Escape hatch | on: an explicit open type on a binding drops what inference knew (`satisfies` keeps it) |
| `no-unknown-parameters` | Escape hatch | on, with the catch parameter named `cause` (its one allowed name): `use-unknown-in-catch-callback-variable` makes that parameter `unknown` |
| `no-runtime-typeof` | Escape hatch | on, with `allowInTypeGuards: true`, after the fix by kind (below); the one decision is whether a schema library replaces the hand-written predicates |
| `require-safety-comment-for-type-assertion` | Escape hatch | on: the reason of an exception (gate property 4) asked of every non-`const` assertion, the safe ones included |
| `no-module-mocking` | Decision first | which seam a test replaces in place of a module |
| the `anti-slop-effect` rules | Decision first | `n/a` unless the repo depends on Effect; then a question on the Effect architecture they impose |
| `no-array-filter-map`, `no-reduce-accumulator-copy` | Shape | on: an extra pass or a copy per element |
| `require-readable-spacing` | — | out: blank lines belong to the formatter (one tool per property) |
| `no-shape-in-symbol-names` | — | out: a naming taste with no failure behind it |
| `no-conditional-empty-object-spread` | — | out: under `exactOptionalPropertyTypes` a conditional spread is the way to leave a field out |

A `typeof` site is fixed by what it does, and each kind has its own recipe (measured: 166 production sites of 197, 31 in tests):

- **A value whose type is already known**, probed for a function or a value (`typeof opts.onLink === "function"` on an optional callback, a nullable member): the checker's own narrowing, `opts.onLink?.(state)` or `if (!win.relaunch) return`. A check the types rule out is Fail fast; the fix is mechanical.
- **A validator of outside data** (a reply, a message, stored state): a type predicate `(v: unknown): v is Reply` in the module at the boundary. `allowInTypeGuards` lets its `typeof` through, and `no-unknown-parameters` allows the predicate's subject.
- **A check at the site of use with a fallback** (`typeof reply.message === "string" ? reply.message : ""`): the value is parsed at the boundary into a named type, and the fallback that hid a malformed reply goes.
- **A test** that inspects a value's runtime type: an override that turns the rule off for test files, with its reason.

The marker of `require-safety-comment-for-type-assertion` is configurable (default `SAFETY`): it is the same word as Rust's `// SAFETY:` on an `unsafe` block, so one word marks an unchecked invariant across stacks.

The upstream commit goes in the plan's Measured section; the research of `references/maintenance.md` reads the commits since it, and the repo takes a newer one as its own change, re-measured.

## Tools

| Check | Command |
|---|---|
| Types | `tsc --noEmit` |
| Lint | `oxlint --deny-warnings` (plus `--type-aware` over the files tsconfig checks), or `eslint --max-warnings 0` |
| Format | oxfmt, Prettier or Biome with `--check`; line ends fixed in `.gitattributes` |
| Dead code (unused files, exports, dependencies) | `knip --reporter json`, counted by `tally.py knip` (it needs a `package.json`; a repo without one has `n/a`) |
| Mutation on the diff | Stryker in incremental mode |

## Measure

- **tsconfig**: one flag at a time. Tally a run with the current flags, then a run with the current flags plus one target flag; `tally.py diff` gives that flag's sites. Flags go on the command line: `tsc --noEmit --pretty false -p tsconfig.json --noUncheckedIndexedAccess`.
- **oxlint**: a draft config file, `oxlint -c <scratch>/oxlintrc.json --ignore-pattern '<each ignorePatterns entry>' --format json <paths>`. A `-D <rule>` on the command line drops the rule's options from the config (measured: `eqeqeq` loses `null: ignore`), so options go in the draft file. A draft outside the repo resolves `ignorePatterns` from its own folder, so the repo's ignores no longer match: pass each one as `--ignore-pattern` (measured: a vendored folder added 163,000 sites to 13,000 real ones).
- **`debt.py oxlint`** prints a rule with sites as `"off"`: a target rule with options (`no-restricted-properties`, `max-params`) loses them there, so the plan carries the options for the phase that turns it on.
- **A new plugin** brings its rules of every category already on, `correctness` included. `debt.py oxlint` counts them; a hand list of the new categories misses them.
- **Type-aware oxlint**: `npx -y -p oxlint@<v> -p oxlint-tsgolint@<v> oxlint --type-aware ...`. With the tools installed in a scratch folder, oxlint looks for `tsgolint` in the repo, not beside itself: set `OXLINT_TSGOLINT_PATH` to the scratch binary. tsgolint ignores `ignorePatterns` and can run out of memory on a vendored bundle: pass the source paths explicitly, the ones tsconfig checks.
- **ESLint**: `eslint -c <scratch>/eslint.config.js -f json <paths>`. ESLint fails on an unknown rule name by itself, and its JSON lists `usedDeprecatedRules` with their replacements: that list is its drift check.
- **A JS plugin** (anti-slop) in a scratch folder needs `@oxlint/plugins` installed where the plugin's files resolve it, and `"type": "module"` in the nearest `package.json`: copy the plugin into the scratch folder that holds `node_modules`. oxlint without the plugin fails the config and prints no JSON.
- Suppressions to count: `eslint-disable`, `oxlint-disable`, `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`, `as any`, `as unknown as`, `!` non-null assertions.

## Exceptions

`// oxlint-disable-next-line <rule> -- <why>` or `// eslint-disable-next-line <rule> -- <why>`, with unused disables reported as errors. `// @ts-expect-error <why>`: it fails once the error is gone, where `@ts-ignore` stays forever.

## Do not turn on

| Rule | Why |
|---|---|
| `explicit-function-return-type` | with `strict` the inferred type is already checked |
| `no-return-await` | wrong inside `try`; `return-await` covers it |
| `arrow-body-style: always` | more lines, same behavior |
| `sonarjs/no-duplicate-string` | it merges two different things because their text is the same |
| `max-lines-per-function` | complexity finds the real problem with fewer false alarms |
| import path aliases, import sorting | style; a formatter sorts imports if wanted |
