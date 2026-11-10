# Rust target

As of 2026-11-07: Rust 1.99.1 (clippy 0.1.99). An unknown lint name in `Cargo.toml` is only a warning, so it hides itself: `drift.py check clippy` finds it.

## `Cargo.toml`

Every crate has `[lints] workspace = true`; a crate without it is outside the gate (count those crates in the inventory).

```toml
[workspace.lints.rust]
unsafe_code = "forbid"                # "deny" + a named #[expect] per FFI block when the repo needs unsafe
rust_2018_idioms = { level = "deny", priority = -1 }
unreachable_pub = "deny"
unused_qualifications = "deny"
let_underscore_drop = "deny"
non_ascii_idents = "deny"
missing_debug_implementations = "deny"

[workspace.lints.clippy]
all = { level = "deny", priority = -1 }
pedantic = { level = "deny", priority = -1 }
cognitive_complexity = "deny"          # restriction; the limit is in clippy.toml
# restriction lints, one at a time:
unwrap_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
print_stdout = "deny"                  # a CLI binary allows it at its root, with a reason
print_stderr = "deny"
let_underscore_must_use = "deny"
let_underscore_untyped = "deny"
unused_result_ok = "deny"
map_err_ignore = "deny"
wildcard_enum_match_arm = "deny"
string_slice = "deny"
indexing_slicing = "deny"              # in crates that parse outside data
as_conversions = "deny"
allow_attributes = "deny"              # #[expect] fails when it suppresses nothing
allow_attributes_without_reason = "deny"
undocumented_unsafe_blocks = "deny"
tests_outside_test_module = "deny"
exit = "deny"
mem_forget = "deny"
# conventions (§ Conventions): on only by the answer of step 3
clone_on_ref_ptr = "deny"             # Arc::clone(&x) for x.clone()
str_to_string = "deny"                # to_owned() for to_string() on a &str
mod_module_files = "deny"             # one style of module file
# pedantic noise, off with a reason:
must_use_candidate = "allow"           # fires on every pure fn; #[must_use] where ignoring is a bug
missing_errors_doc = "allow"           # docs on the public API of a published library only
```

`clippy::all` holds the `style` group, so `collapsible_if` and `match_like_matches_macro` are on with no extra line. `collapsible_if` joins `if a { if b {} }`; nesting depth is limited by cognitive complexity, which counts nesting.

## `clippy.toml`

```toml
cognitive-complexity-threshold = 10
too-many-arguments-threshold = 5       # more arguments travel in a named struct
allow-unwrap-in-tests = true
allow-expect-in-tests = true
allow-dbg-in-tests = true
allow-print-in-tests = true
allow-panic-in-tests = true            # for `panic`; a helper outside a #[test] fn still counts
allow-indexing-slicing-in-tests = true # for `indexing_slicing`
disallowed-methods = [
  { path = "std::process::exit", reason = "exit skips every Drop: temp files, flushes and locks stay as they are. Return from main" },
  { path = "std::env::set_var", reason = "changing the environment while another thread reads it is undefined behavior" },
  { path = "std::env::remove_var", reason = "changing the environment while another thread reads it is undefined behavior" },
  # decision first: one module owns spawns, and a test waits on a condition
  # { path = "std::process::Command::new", reason = "spawn only through crate::proc" },
  # { path = "std::thread::sleep", reason = "a test waits on a condition, not on a time" },
]
disallowed-types = []                  # only a type that is wrong everywhere in this code
```

`disallowed-methods` also applies to test code, and `clippy.toml` has no tests switch for it. When the test runner gives each test its own process (nextest does), the root of a crate whose tests change the environment carries `#![cfg_attr(test, expect(clippy::disallowed_methods, reason = "..."))]`, and each `tests/` crate root carries `#![expect(...)]`: one exception per crate, not one per call.

## Tools

| Check | Command |
|---|---|
| Format | `cargo fmt --all --check` with a `rustfmt.toml` |
| Lints, test code too | `cargo clippy --locked --workspace --all-targets --all-features -- -D warnings` |
| Docs and intra-doc links | `RUSTDOCFLAGS="-D warnings" cargo doc --locked --no-deps` |
| Advisories, licenses, sources | `cargo deny check` |
| Declared, unused dependency | `cargo machete` |
| Dead code | the compiler's `dead_code` under `-D warnings` within a crate; `unreachable_pub` so that a `pub` item no other crate uses is `pub(crate)`, and `dead_code` then sees it |
| Leftovers (a `TODO`, `FIXME` or commented-out code) | no lint: `tally.py pattern '//\s*(TODO\|FIXME\|XXX\|HACK)\b' --ext .rs --expect N` as a ratchet; clippy's `todo` covers only the macro |
| A feature that does not build alone | `cargo hack --each-feature check` |
| Public API break (published library) | `cargo semver-checks` |
| Lockfile matches `Cargo.toml` | `--locked` on every cargo command in CI |
| Too-new language feature | `rust-version` in `Cargo.toml` and a CI job on that version |
| Doctests | `cargo test --doc` (nextest does not run them) |
| Mutation on the diff | `cargo mutants --in-diff <diff>` |

## Measure

The draft lives in `<scratch>/clippy.toml`, read through `CLIPPY_CONF_DIR`. The lints go on the command line as `-W`, so the repo's `Cargo.toml` stays as it is:

```
CLIPPY_CONF_DIR=<scratch> cargo clippy --workspace --all-features --message-format=json -- \
  -W clippy::all -W clippy::pedantic -W clippy::cognitive_complexity -W clippy::unwrap_used ... \
  -W unreachable_pub -W unused_qualifications ... \
  -A clippy::must_use_candidate -A clippy::missing_errors_doc \
  > <scratch>/clippy.prod.json
# the same with --all-targets > <scratch>/clippy.all.json
python tally.py clippy clippy.prod.json --json prod.json --scope-depth 2
python tally.py clippy clippy.all.json --json all.json --scope-depth 2
python tally.py diff prod.json all.json        # the test sites
```

- A test module inside a source file is compiled only with `--all-targets`, so the production run and the diff is the clean split; a path filter misses inline `#[cfg(test)]` modules.
- `-W` on the command line loses to an `#[allow]` or `#[expect]` in the source: those sites are hidden debt. Count `#[allow(` and `#[expect(` per lint with a grep.
- Clippy sees only the `#[cfg]` branches of the host platform. A count from one OS misses the others' code; a baseline written from clippy on one OS fails on another. A baseline ratchet in a multi-OS CI needs a scorer that reads the source text, or one measuring OS that CI also uses.
- `cognitive_complexity` is in `restriction` (clippy 0.1.99), so `pedantic` does not turn it on: it is named. Its score changes between clippy versions. Pin the toolchain of the step that measures it. A repo with its own scorer keeps it (one tool per property): the two scores differ (measured: clippy put 135 functions over 10 where a source-text scorer found none).
- `tests_outside_test_module` fires on every test of an integration test crate (`tests/`): that crate is the test module. The fix is one `#![expect(clippy::tests_outside_test_module, reason = "...")]` at each `tests/` crate root; the lint then checks that unit tests live in `#[cfg(test)]`.
- A `CLIPPY_CONF_DIR` draft replaces the repo's `clippy.toml` whole: start the draft from a copy of it, or its settings (`allow-unwrap-in-tests`) are lost and the count grows.
- A crate that fails to build is not linted: `tally.py` warns.
- `cargo` writes to `CARGO_TARGET_DIR` when it is set: a global one can point into another checkout of the repo. Every measuring command sets it to the scratch folder.
- **Per crate**: under `[lints] workspace = true` every crate reads one lint table, so a group (`pedantic`) goes on for the workspace with one debt list. A crate that reaches 0 locks its gain with a crate-root `#![deny(<the lints still in the list>)]`. A crate-root `#![expect(...)]` as a per-crate debt list fails on the platform where the lint does not fire (an unfulfilled expectation under `-D warnings`), and `allow_attributes` refuses `#![allow]`.

## Exceptions

`#[expect(clippy::<lint>, reason = "<why>")]` on the item. A lint that fires on one platform only: `#[cfg_attr(<platform>, expect(clippy::<lint>, reason = "..."))]`. `allow_attributes` refuses a bare `#[allow]`, which outlives the code it excused.

## Conventions

The lints of this target that pick one of two forms with the same behavior and the same cost (SKILL.md § Rule classes, Convention): the restriction lints under `# conventions` above, `unused_qualifications` of rustc, and these of `pedantic`, which goes on as a group: `doc_markdown`, `redundant_closure_for_method_calls`, `semicolon_if_nothing_returned`, `unreadable_literal`, `uninlined_format_args`, `single_match_else`, `if_not_else`, `manual_let_else`, `map_unwrap_or`, `unnested_or_patterns`, `ignored_unit_patterns`, `manual_string_new`, `default_trait_access`, `explicit_iter_loop`, `explicit_into_iter_loop`, `items_after_statements`, `needless_continue`, `needless_raw_string_hashes`, `range_plus_one`, `inconsistent_struct_constructor`. A convention off sits in the debt block under `noise: convention (<Dn>)`. Most have a machine-applicable fix: `cargo clippy --fix` applies the `safe` sites.

A pedantic lint not named here goes by the test of the class, from `cargo clippy --explain <lint>`: `cast_possible_truncation` and `case_sensitive_file_extension_comparisons` change a result, so they are not conventions; `needless_pass_by_value` and `format_push_string` are Waste.

## Do not turn on

| Lint | Why |
|---|---|
| `clippy::expect_used` | `expect` with a message is the way to state an invariant |
| `arithmetic_side_effects`, `float_arithmetic` | they refuse `a + b`; only money or cryptography code |
| the whole `clippy::restriction` group | some of its lints contradict each other; one at a time, as above |
| `missing_docs` everywhere | it produces empty docs to pass; the public API of a published library only |
