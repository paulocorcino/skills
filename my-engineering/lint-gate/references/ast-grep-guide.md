# ast-grep guide

The template of the repo's own `docs/ast-grep.md` (or the repo's folder for docs), written by step 5 when ast-grep is approved, for navigation or for gate rules. With no gate rule yet, the section "The gate's rules" stays out until the first one. The agent of the repo reads it through one pointer line in the agent doc's tools section (`agent-docs.md` § The tools section).

Before filling it, read the docs of the pinned version that ast-grep writes for agents: `https://ast-grep.github.io/llms.txt` (an index; fetch the one `.md` page needed) and the agent skill it publishes (`ast-grep/agent-skill`: `ast-grep` for rules, `outline` for navigation). The guide holds what those docs do not: this repo's commands, rules and exception form, and the traps measured here. It points at them for the rest. Fill each `<...>`; write it in the language of the repo's docs; run every command in it once on this repo, and drop a line whose command does not run here (`outline` is alpha: check it at the pin).

As of 2026-11-08: ast-grep 0.51.1.

```markdown
# ast-grep

ast-grep reads code as a syntax tree. `<sg>` runs it at the version the repo pins. It sees syntax only: no types, no imports, nothing across files. A match is a candidate; the compiler and the linters decide what it means.

## Look before you read

Before reading a whole source file, outline it, then read only the range you need:

    <sg> outline <file>                    # items and their members, with line numbers
    <sg> outline <dir> --items exports     # the public surface of a folder (Rust, TypeScript; in Go it lists every function)
    <sg> outline <file> --items imports    # what a file depends on

## Search by shape

Search with ast-grep when the question is about the shape of code: every call of a function with a literal argument, every `catch` with an empty body, every `impl` of a trait. Search with grep when it is about text: a name, a message, a comment, a file.

    <sg> run -p '<pattern>' -l <language> <paths>
    <sg> run -p '<pattern>' -l <language> <paths> --json=stream   # one match per line, to count

The pattern is code of the language: `$X` matches one node, `$$$ARGS` any number of them. `-l` takes <the languages of this repo: rust, ts, python, go>.

A pattern that matches nothing is not proof the code is absent:

- A path is part of the pattern: `Command::new($P)` does not match `std::process::Command::new(...)`. Write the path as a metavariable (`$C::new($P)`) and read the matches.
- <Rust:> a pattern does not match inside a macro's arguments (`assert_eq!(x.unwrap(), 1)`). Search those with grep.
- <Go:> a call to a package function is parsed as a type conversion when it stands alone: `os.Exit($C)` matches nothing. Wrap it in a function and select the call: `-p 'func _() { os.Exit($C) }' --selector call_expression`. A method call (`$X.Close()`) matches as written.
- `--debug-query=pattern` prints how ast-grep parsed the pattern; test it on a snippet you know contains the code.

## Rewrite

One shape changed at many sites:

    <sg> run -p '<old>' -r '<new>' -l <language> <paths>      # prints the diff, changes nothing
    <sg> run -p '<old>' -r '<new>' -l <language> <paths> -U   # applies it

Read the diff before `-U`. The rewrite drops the line breaks of the code it replaces: run `<format command>` after it. A rewrite goes in a commit of its own, with the command in its message, and the gate passes after it.

## The gate's rules

The rules are in `<rule dir>`, one per file, and their tests in `<test dir>`. `<gate command>` runs `<sg> scan` and `<sg> test`.

- A rule's message says what to do at the site: do it.
- A new rule copies the form of one here, with `valid` cases (each false positive found) and `invalid` cases (each form of the failure), and `<sg> test --skip-snapshot-tests` passes. For rule syntax, the `ast-grep` agent skill or the llms.txt page of the rule you need.
- An exception is `// ast-grep-ignore: <rule-id> -- <why>` on the line above, the reason saying why the rule is wrong there. Every ignore names its rule; the gate fails on one that suppresses nothing. A comment that only mentions the directive starts with another word: one whose first word is `ast-grep-ignore`, in any comment form, is a directive.
```
