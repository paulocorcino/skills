#!/usr/bin/env python3
"""End-to-end verify for the quality-gate skill (after final stage)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _verify import V

SLUG = "quality-gate-skill"
SKILL_ROOT = "quality-gate"

# Package + all submodules import.
V.run_gate(
    "PYTHONPATH=/home/corcino/.claude/skills python3 -c "
    "'import quality_gate, quality_gate.cli, quality_gate.lib.ratchet, "
    "quality_gate.lib.report, quality_gate.lib.detect, quality_gate.lib.baseline_io, "
    "quality_gate.lib.validate_language, quality_gate.lib.security, "
    "quality_gate.lib.backlog, quality_gate.lib.triage, quality_gate.lib.config'",
    slug=SLUG, stage="e2e", gate="import_all",
)

# Compile all Python files.
V.run_gate(
    f"python3 -m py_compile $(find /home/corcino/.claude/skills/{SKILL_ROOT} -name '*.py')",
    slug=SLUG, stage="e2e", gate="py_compile",
)

# Every JSON file valid.
V.run_gate(
    f"for f in $(find /home/corcino/.claude/skills/{SKILL_ROOT} -name '*.json'); do "
    f"python3 -m json.tool \"$f\" > /dev/null || exit 1; done",
    slug=SLUG, stage="e2e", gate="json_valid_all",
)

# CLI surface includes all five subcommands.
V.run_gate(
    "out=$(PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate --help); "
    "for s in init run status update-baseline to-backlog; do "
    "echo \"$out\" | grep -q \"$s\" || exit 1; done",
    slug=SLUG, stage="e2e", gate="cli_subcommands",
)

# Each language pack's sample-output.json validates against language_metrics schema.
for lang in ("python", "go", "rust", "bunjs"):
    V.run_gate(
        f"PYTHONPATH=/home/corcino/.claude/skills python3 -m quality_gate.lib.validate_language "
        f"/home/corcino/.claude/skills/{SKILL_ROOT}/languages/{lang}/sample-output.json",
        slug=SLUG, stage="e2e", gate=f"sample_output_{lang}",
    )

# No shell scripts under languages/.
V.run_gate(
    f"test \"$(find /home/corcino/.claude/skills/{SKILL_ROOT}/languages -name '*.sh' | wc -l)\" -eq 0",
    slug=SLUG, stage="e2e", gate="no_shell_in_languages",
)

# SKILL.md references resolve.
V.run_gate(
    "python3 -c \"import re,os,sys; "
    f"p='/home/corcino/.claude/skills/{SKILL_ROOT}/SKILL.md'; "
    "t=open(p).read(); base=os.path.dirname(p); "
    "missing=[l for l in re.findall(r'\\(references/[^)]+\\)', t) "
    "if not os.path.exists(os.path.join(base, l[1:-1]))]; "
    "sys.exit(1 if missing else 0)\"",
    slug=SLUG, stage="e2e", gate="skill_md_links",
)

# Ratchet module exposes compare().
V.run_gate(
    "PYTHONPATH=/home/corcino/.claude/skills python3 -c "
    "'from quality_gate.lib import ratchet; assert hasattr(ratchet, \"compare\")'",
    slug=SLUG, stage="e2e", gate="ratchet_api",
)

sys.exit(V.summarize())
