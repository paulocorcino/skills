# Missing tools protocol

Quality Gate detects which analysis tools are available on your system and gracefully degrades when tools are not found. This document explains how the detection works and how regressions from missing tools are handled.

## Tool detection

Each language pack declares its required and optional tools in `languages/<lang>/tools.json`. The file follows this schema:

```json
{
  "tools": [
    {
      "name": "ruff",
      "purpose": "lint / format checking",
      "detect_command": "ruff --version",
      "install_command": "pip install ruff",
      "docs_url": "https://docs.astral.sh/ruff"
    }
  ]
}
```

When `quality-gate run` executes, each language pack:

1. **Detects availability** by running `detect_command` for each tool. Tools that return exit 0 are added to `tools_used`; tools that fail are added to `tools_missing`.
2. **Continues execution** even if some tools are missing. There is no hard failure if a tool is absent — the metric that tool would provide is simply skipped or nulled.
3. **Records the state** in the output JSON: `"tools_used": [...], "tools_missing": [...]`.

## Exit codes and gaps

After all language packs complete, Quality Gate checks:

- **Exit 0 (PASSED)** — all ratchet checks passed; no missing tools or missing tools are known to be missing.
- **Exit 1 (FAILED)** — one or more ratchet rules were violated (regression detected).
- **Exit 2 (PASSED_WITH_GAPS)** — ratchet checks passed, but one or more tools are missing. Metrics from those tools are incomplete. This is a soft warning: the gate passed, but coverage is partial.
- **Exit 3 (NO_BASELINE)** — branch intent is declared but no baseline could be located at the target ref. See the message for the list of refs consulted.
- **Exit 4 (TOOL_MISSING_REGRESSION)** — a tool present in the baseline is now missing. See below.
- **Exit 5 (NO_INTENT)** — the branch has no `branch.json` declaring its mode. Run `establish --mode {extend|replace}` before `run`. See [branch-modes.md](branch-modes.md).

## Tool missing regression (exit 4)

A critical invariant guards against silent tool loss:

**If a tool was present in the baseline but is now missing, the gate FAILS with exit code 4 (TOOL_MISSING_REGRESSION).**

This prevents the gate from silently passing with fewer checks than the baseline had. For example:

- Baseline captured with `ruff`, `pytest`, `bandit` all installed → recorded in `baseline.tools_used`
- Feature branch runs with `ruff` missing → current `tools_used` is missing `ruff`
- Gate detects the asymmetry and exits 4 (TOOL_MISSING_REGRESSION)

This rule ensures you cannot accidentally reduce quality-gate rigor by uninstalling an analysis tool.

## Installing missing tools

If Quality Gate reports missing tools, consult the `tools.json` manifest for install commands. For example, if `ruff` is missing:

```bash
pip install ruff
```

Each tool's `tools.json` entry includes the canonical `install_command`. Prefer that over ad-hoc installations.

## Tools with fallback chains

Some language packs support tool fallbacks. For example, BunJS prefers `biome` for linting but will use `oxlint` if `biome` is not installed.

The preference order is documented in the language pack's `tools.json`. Quality Gate will use the first available tool in the chain and record its name in `tools_used`.

## FAQ

**Q: Can I ignore missing tools and pass the gate?**
A: If the baseline had the tool, no — exit 4 enforces tool parity. If the baseline did not have the tool, yes — missing tools do not prevent PASSED or PASSED_WITH_GAPS.

**Q: Why not auto-install tools?**
A: Quality Gate is diagnostic-only and intentionally does not modify the system. Installing tools is a deployment concern, not a diagnosis concern. Use your CI system or local shell to manage tool installation.

**Q: What if a tool fails at runtime (crashes, exits non-zero)?**
A: The language pack logs the error and treats it as broken. The tool is added to `tools_broken` (distinct from `tools_missing`), the underlying error is printed to stderr, and the report renders a **Broken Tools** section. The metric the tool would have produced is reported as `—`. Check the stderr output (or the `.quality-gate/tmp/` JSON for the project) to see the exact cause.

## jscpd in large monorepos

`jscpd` does an O(n²)-ish token comparison across the codebase. On large monorepos it can:

1. **Time out.** The BunJS pack invokes jscpd with a 300s budget and `--silent --noTips --ignore "node_modules/**,dist/**,build/**,.next/**,coverage/**,.quality-gate/**"`. If you still hit `TimeoutExpired`, the target repo needs tuning.
2. **Run out of memory** (visible as `exit=-9` / SIGKILL in the warning).

Tuning is **target-side**, not skill-side. Add a `.jscpd.json` (or a `jscpd` section in `package.json`) at the repo root:

```json
{
  "min-tokens": 100,
  "min-lines": 10,
  "gitignore": true,
  "ignore": ["**/tests/**", "**/fixtures/**", "**/*.test.ts", "**/*.spec.ts"],
  "store": "leveldb",
  "absolute": false
}
```

Notes:
- `min-tokens` / `min-lines` higher → fewer comparisons → much faster. Start at 100/10 and tune.
- `gitignore: true` makes jscpd respect `.gitignore` (only available via config file, not CLI flag).
- `store: "leveldb"` swaps the in-memory index for an on-disk one — required for very large repos.
- Excluding tests is reasonable: duplication in test scaffolding is rarely actionable and inflates the percentage.

If duplication is fundamentally not useful for the target, disable jscpd by adding `"duplication"` to a project-level skip list in `.quality-gate/config.json` (see [monorepo.md](monorepo.md)) — or simply uninstall jscpd; it will show up as missing, not broken, with the install hint in the report.

**Q: How do I see which tools were present at baseline?**
A: Inspect `.quality-gate/baseline.json` — each project's `tools_versions` object lists the tools that were available when the baseline was captured.
