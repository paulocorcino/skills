# Maintenance

The references are a cache of what the tools are today. They go stale three ways: a rule is renamed or removed (`drift.py diff` and `check` find it), a default or a recommendation changes (only the release notes say so), or a better tool appears for a property (nothing in the old tool's output says so). The research covers the last two; maintenance applies what a run found.

## Research

Runs when `drift.py age` says `research: required` for a reference, in a skill run (step 2) or in maintenance.

For each reference flagged:

1. **Releases in between.** For each tool of its `As of` line, read the release notes of every release from the `As of` version to the pin: breaking changes, defaults changed, rules deprecated or renamed, options removed, a new minimum version of a companion tool.
2. **Tools per property.** For each row of the reference's Tools table (for `repo.md`, each tool it names): the tool is still maintained (a release in the last 12 months, the repository not archived), it has no announced successor, and no other tool now covers the property with a measured edge. A candidate tool is recorded with its source; it enters a repo only as a `decision`, measured there (§ The gate: one tool per property).
3. **Do not turn on.** Each row still holds at the pin: the rule still exists, and its reason still applies.

Sources, in order: the tool's own output at the pin (`--rules`, `--help`, its config schema); its docs written for agents when it has them (an `llms.txt`, an agent skill it publishes); its release notes and changelog; the registry (npm, PyPI, crates.io, GitHub releases); a documentation tool the agent has (Context7 or similar), then a web search, for what the first three do not answer. Each finding names its source: a URL, or the command and version that printed it. A finding with no source stays out.

Done when every release in the range and every Tools row has a line in the harvest file, `no change` included.

## The harvest file

`<scratch>/reference-drift.md`, outside the repo and outside the skill. One table per reference flagged, with the columns `Reference`, `Line or row`, `Change`, `Source`, `Version`:

- **Line or row**: the reference's line as it is, or `new row` with the table it joins.
- **Change**: the new text, or `no change`, or `remove — <why>`.
- **Source**: a URL, or the command and version.
- **Version**: the tool version the change is true from.

The first line of the file is the `drift.py age` output it answers.

## Apply

Runs when the user asks to refresh the skill's references. It is the one time the skill's own files change.

1. Run `drift.py age` over every reference that names tools (`repo.md`, the stack references, `ast-grep-guide.md`). For each flagged one, take the harvest files the user points at, and do the research for what they do not cover.
2. For each tool whose pin moved, print the rule lists of the `As of` version and of the pin, and run `drift.py diff`. Each added rule joins a row of its class, or is listed as having none; each removed or renamed one leaves the reference or takes its successor.
3. Apply each harvest line whose source checks out at the pin. A line whose source does not reproduce is dropped, with the reason in the report.
4. Rewrite the `As of` line: today's date and the versions checked.
5. Run `drift.py check` over each target config the reference holds, saved as a draft, and `rows.py list` over the references before and after: the report names the rows added and removed, since every repo's Coverage table changes with them.
6. Commit in the skill's repository when the user has authorized commits.

Done when `drift.py age` says `research: not required` for every reference, `drift.py check` passes on every target config, and every harvest line is applied or dropped with its reason.
