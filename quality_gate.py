"""Import shim: expose `quality-gate/` (hyphenated, Claude-skill convention)
as the Python-importable package `quality_gate` (underscore).

The skill folder is named `quality-gate/` so Claude Code discovers `SKILL.md`
under the standard skill-folder convention. Python disallows hyphens in module
names, so this shim wires the hyphenated directory in as the `quality_gate`
package at import time.

`import quality_gate` -> loads `quality-gate/__init__.py` with submodule search
in `quality-gate/`, so `import quality_gate.cli`, `quality_gate.lib.ratchet`,
etc. all resolve normally.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_PKG_DIR = pathlib.Path(__file__).resolve().with_name("quality-gate")
_INIT = _PKG_DIR / "__init__.py"

if not _INIT.is_file():
    raise ImportError(f"quality-gate package directory not found at {_PKG_DIR}")

_spec = importlib.util.spec_from_file_location(
    "quality_gate", _INIT, submodule_search_locations=[str(_PKG_DIR)]
)
if _spec is None or _spec.loader is None:
    raise ImportError("failed to build spec for quality_gate package")

_module = importlib.util.module_from_spec(_spec)
sys.modules["quality_gate"] = _module
_spec.loader.exec_module(_module)

# Mirror attributes onto this shim so `from quality_gate import X` via the
# shim path also works.
globals().update({k: v for k, v in vars(_module).items() if not k.startswith("_")})


# When invoked as `python -m quality_gate`, dispatch to the CLI. Python's `-m`
# loads this file as `__main__` (because the shim is a top-level module, not
# a package directory), so the package's own __main__.py is never executed.
if __name__ == "__main__":
    import sys as _sys
    from quality_gate.cli import main as _cli_main
    _sys.exit(_cli_main())
