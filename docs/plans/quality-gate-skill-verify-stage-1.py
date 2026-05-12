#!/usr/bin/env python3
"""Stage 1 verify: Core skeleton (SKILL.md, schemas, lib, cli, _template, stub runners)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _verify import V

SLUG = "quality-gate-skill"
STAGE = 1
SKILL_ROOT = "quality-gate"

# Declared file list for Stage 1 (matches the plan's Files block, plus the
# stage report and the shim that wires `quality-gate/` -> `import quality_gate`).
ALLOWED = [
    f"{SKILL_ROOT}/SKILL.md",
    f"{SKILL_ROOT}/__init__.py",
    f"{SKILL_ROOT}/__main__.py",
    f"{SKILL_ROOT}/cli.py",
    f"{SKILL_ROOT}/schema/baseline.schema.json",
    f"{SKILL_ROOT}/schema/language_metrics.schema.json",
    f"{SKILL_ROOT}/schema/config.schema.json",
    f"{SKILL_ROOT}/lib/__init__.py",
    f"{SKILL_ROOT}/lib/detect.py",
    f"{SKILL_ROOT}/lib/baseline_io.py",
    f"{SKILL_ROOT}/lib/config.py",
    f"{SKILL_ROOT}/lib/ratchet.py",
    f"{SKILL_ROOT}/lib/report.py",
    f"{SKILL_ROOT}/lib/triage.py",
    f"{SKILL_ROOT}/lib/validate_language.py",
    f"{SKILL_ROOT}/lib/security.py",
    f"{SKILL_ROOT}/lib/backlog.py",
    f"{SKILL_ROOT}/languages/__init__.py",
    f"{SKILL_ROOT}/languages/_template/run.py",
    f"{SKILL_ROOT}/languages/_template/tools.json",
    f"{SKILL_ROOT}/languages/_template/metadata.json",
    f"{SKILL_ROOT}/languages/python/run.py",
    f"{SKILL_ROOT}/languages/python/tools.json",
    f"{SKILL_ROOT}/languages/python/metadata.json",
    f"{SKILL_ROOT}/languages/go/run.py",
    f"{SKILL_ROOT}/languages/go/tools.json",
    f"{SKILL_ROOT}/languages/go/metadata.json",
    f"{SKILL_ROOT}/languages/rust/run.py",
    f"{SKILL_ROOT}/languages/rust/tools.json",
    f"{SKILL_ROOT}/languages/rust/metadata.json",
    f"{SKILL_ROOT}/languages/bunjs/run.py",
    f"{SKILL_ROOT}/languages/bunjs/tools.json",
    f"{SKILL_ROOT}/languages/bunjs/metadata.json",
    # Python-import shim (deviation; see report).
    "quality_gate.py",
    # The verify script itself was rewritten in this stage (deviation; see report).
    f"docs/plans/{SLUG}-verify-stage-{STAGE}.py",
    f"docs/plans/{SLUG}-stage-{STAGE}-report.md",
]

V.assert_only_files_touched(ALLOWED, base_sha="HEAD~1")

# Package import.
V.run_gate(
    "PYTHONPATH=/home/corcino/.claude/skills python3 -c "
    "'import quality_gate; import quality_gate.cli; "
    "import quality_gate.lib.ratchet; import quality_gate.lib.report; "
    "import quality_gate.lib.detect; import quality_gate.lib.baseline_io; "
    "import quality_gate.lib.validate_language; import quality_gate.lib.security; "
    "import quality_gate.lib.backlog; import quality_gate.lib.triage; "
    "import quality_gate.lib.config'",
    slug=SLUG, stage=STAGE, gate="import",
)

# Py compile.
V.run_gate(
    f"python3 -m py_compile $(find /home/corcino/.claude/skills/{SKILL_ROOT} -name '*.py')",
    slug=SLUG, stage=STAGE, gate="py_compile",
)

# JSON validity for schemas, tools.json, metadata.json.
V.run_gate(
    f"for f in /home/corcino/.claude/skills/{SKILL_ROOT}/schema/*.json "
    f"/home/corcino/.claude/skills/{SKILL_ROOT}/languages/*/tools.json "
    f"/home/corcino/.claude/skills/{SKILL_ROOT}/languages/*/metadata.json; do "
    f"python3 -m json.tool \"$f\" > /dev/null || exit 1; done",
    slug=SLUG, stage=STAGE, gate="json_valid",
)

# CLI surface.
V.run_gate(
    "PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help | "
    "grep -q init && PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help | grep -q run && "
    "PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help | grep -q status && "
    "PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help | grep -q update-baseline && "
    "PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help | grep -q to-backlog",
    slug=SLUG, stage=STAGE, gate="cli_surface",
)

# Invariant: no shell scripts under languages/.
V.run_gate(
    f"test \"$(find /home/corcino/.claude/skills/{SKILL_ROOT}/languages -name '*.sh' | wc -l)\" -eq 0",
    slug=SLUG, stage=STAGE, gate="no_shell_in_languages",
)

# Each stub run.py emits schema-valid output.
for lang in ("python", "go", "rust", "bunjs"):
    V.run_gate(
        f"python3 /home/corcino/.claude/skills/{SKILL_ROOT}/languages/{lang}/run.py "
        f"--root /tmp --output /tmp/qg-{lang}-out.json && "
        f"PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language "
        f"/tmp/qg-{lang}-out.json",
        slug=SLUG, stage=STAGE, gate=f"stub_run_{lang}",
    )

# Report exists.
V.assert_report_exists(f"docs/plans/{SLUG}-stage-{STAGE}-report.md")

sys.exit(V.summarize())
