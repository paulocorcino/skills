# Adding a new language pack

This guide walks you through adding a new language to Quality Gate. The language must follow the canonical contract defined in `languages/_template/`.

## Contract overview

Each language pack lives in `languages/<lang>/` and consists of three files:

1. **`run.py`** — the executable that analyzes the project and outputs metrics
2. **`tools.json`** — manifest declaring which tools are required, how to detect them, and how to install them
3. **`metadata.json`** — metadata: language name, file extensions, manifest types, default complexity limits

All three files are required. The `run.py` script must produce output that validates against the canonical `schema/language_metrics.schema.json`.

## Step 1: Copy the template

```bash
cp -r quality-gate/languages/_template quality-gate/languages/your-lang
```

Review the template files to understand the contract before editing.

## Step 2: Write `metadata.json`

Populate the metadata for your language:

```json
{
  "language": "your-lang",
  "manifests": ["package.json", "your-lang.lock"],
  "extensions": [".ts", ".tsx", ".js"],
  "soft_limit": 300,
  "hard_limit": 800
}
```

- `language` — the short name (e.g. `python`, `go`, `rust`, `bunjs`)
- `manifests` — which files signal a project of this language (e.g. `go.mod` for Go)
- `extensions` — file extensions to analyze (used for file-level metrics)
- `soft_limit` — cyclomatic complexity soft threshold (warning; ratchet allows this)
- `hard_limit` — cyclomatic complexity hard threshold (failure if exceeded)

## Step 3: Write `tools.json`

Declare the tools your language pack will invoke:

```json
{
  "tools": [
    {
      "name": "linter-tool",
      "purpose": "lint / format checking",
      "detect_command": "linter-tool --version",
      "install_command": "install-command-here",
      "docs_url": "https://docs.example.com"
    },
    {
      "name": "test-runner",
      "purpose": "tests + coverage",
      "detect_command": "test-runner --version",
      "install_command": "install-command-here",
      "docs_url": "https://docs.example.com"
    }
  ]
}
```

Each tool entry must have:
- `name` — tool identifier (used in logs and tool presence tracking)
- `purpose` — human-readable description
- `detect_command` — shell command to test if the tool is installed (exit 0 = present)
- `install_command` — shell command to install the tool (for user reference)
- `docs_url` — link to official documentation

Quality Gate runs `detect_command` at startup. Tools that return exit 0 are added to `tools_used`; tools that fail are added to `tools_missing`. If a tool is in the baseline's `tools_used` but missing now, the gate fails with exit code 4.

## Step 4: Write `run.py`

Implement the analysis logic. The script must:

1. Accept `--root` (directory to analyze) and `--output` (path to write JSON) arguments
2. For each tool in `tools.json`, run detection and collect availability
3. For available tools, invoke them under `--root` and parse their JSON output
4. Normalize all metrics into the canonical schema
5. Write valid JSON to `--output`

### Canonical schema

Your output must validate against `schema/language_metrics.schema.json`:

```python
import json
import sys

def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Detect tools
    tools_used = []
    tools_missing = []
    for tool in REQUIRED_TOOLS:
        if tool_available(tool):
            tools_used.append(tool)
        else:
            tools_missing.append(tool)

    # Run analysis
    coverage = run_coverage_tool(args.root)
    violations = run_lint_tools(args.root)
    duplication = run_duplication_tool(args.root)
    files = scan_files(args.root)

    # Build output
    output = {
        "language": "your-lang",
        "root": args.root,
        "tools_used": tools_used,
        "tools_missing": tools_missing,
        "coverage": coverage,
        "violations": violations,
        "duplication": duplication,
        "files": files
    }

    # Write to --output
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
```

### Key requirements

1. **Deterministic ordering** — sort all lists alphabetically and all dictionaries by key
2. **2-decimal rounding** — percentages must have exactly 2 decimal places (e.g. `75.50`)
3. **Schema validation** — the output must validate against `language_metrics.schema.json`
4. **File metrics** — include `lines`, `bytes`, and `max_depth` for each file crossing the `soft_limit`
5. **Tool tracking** — record every tool in `tools_used` and `tools_missing` accurately

## Step 5: Create a sample output

Write `sample-output.json` as an example of valid output from your language pack. This file:

- Must validate against `schema/language_metrics.schema.json`
- Should represent a realistic small project (2–3 source files, ~100 lines of code)
- Is used for documentation and test fixtures

Example:

```json
{
  "language": "your-lang",
  "root": "/sample/project",
  "tools_used": ["linter-tool", "test-runner"],
  "tools_missing": [],
  "coverage": 85.50,
  "violations": {
    "errors": 0,
    "warnings": 2
  },
  "duplication": 0.0,
  "files": [
    {
      "path": "src/main.ts",
      "lines": 150,
      "bytes": 3200,
      "max_depth": 5
    }
  ]
}
```

## Step 6: Validate

Before submitting, validate your output and code:

```bash
# Validate metadata and tools
python3 -m json.tool quality-gate/languages/your-lang/metadata.json
python3 -m json.tool quality-gate/languages/your-lang/tools.json
python3 -m json.tool quality-gate/languages/your-lang/sample-output.json

# Validate sample output against the schema
PYTHONPATH=. python3 -m quality_gate.lib.validate_language \
  quality-gate/languages/your-lang/sample-output.json

# Test that run.py is syntactically correct
python3 -m py_compile quality-gate/languages/your-lang/run.py

# (Optionally) test run.py against a real project
python3 quality-gate/languages/your-lang/run.py --root /path/to/project --output /tmp/out.json
```

## Step 7: Update cli.py and detection

Once your language pack is ready:

1. Add your language to the `LANGUAGE_CHOICES` in `cli.py`
2. Add the manifest file to `lib/detect.py`
3. Ensure the language pack is discoverable via `import quality_gate.languages.your_lang`

## Compatibility notes

- Do NOT use shell scripts under `languages/your-lang/`. All runners must be Python.
- Do NOT import the `quality-gate` harness from within `run.py`. Your script must be standalone.
- Do NOT modify `schema/language_metrics.schema.json` to accommodate your language. If your metrics don't fit the schema, the schema itself may need revision (file an issue).
- Do NOT add new fields to the output beyond those in the schema. Stick to the contract.

## Testing your language pack

Once integrated, test end-to-end:

```bash
# Initialize a test repo with your language
cd /tmp && mkdir test-repo && cd test-repo
mkdir .quality-gate
git init
echo 'your-lang markers here' > manifest.file

# Run the quality gate on your test repo
PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --cwd . run

# Check the exit code
echo $?
```

If exit 0 or 2 (PASSED or PASSED_WITH_GAPS), your language pack is working.

## Deferred features

The following are out of scope for the initial language pack:

- Auto-installation of tools (use `--install-command` for now)
- Language-specific CI configuration
- IDE integration
- Historical metrics tracking

These can be added in future skill updates.

## FAQ

**Q: Can I make `soft_limit` and `hard_limit` dynamic (based on file count)?**
A: Not yet. Keep them as static integers in `metadata.json`. Dynamic limits belong in a future evolution.

**Q: What if my language doesn't have a standard coverage tool?**
A: Set `coverage` to `null` in your output. The ratchet rules will treat it as not applicable.

**Q: Should `run.py` do anything besides collect metrics?**
A: No. It should be pure analysis, no side effects. Do not modify the project, create temporary files, or install tools.

**Q: How do I handle errors in my tools?**
A: Log them to stderr and move the tool to `tools_missing`. The language pack must not crash. Quality Gate's harness will catch unexpected errors; your job is graceful degradation.
