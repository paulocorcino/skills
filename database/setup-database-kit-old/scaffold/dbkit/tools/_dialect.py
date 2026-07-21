"""Single source of the project's canonical dialect: the `dialect` in dbkit/.sqlfluff.

The scaffold is **dialect-agnostic** — there is no built-in default. Tools that must
parse or lint SQL read the canonical dialect here and fail loudly when it is not
configured, so no dialect is ever assumed silently.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_SQLFLUFF = Path(__file__).resolve().parents[1] / ".sqlfluff"
_DIALECT_RE = re.compile(r"^\s*dialect\s*=\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


@lru_cache(maxsize=1)
def canonical_dialect() -> str:
    """Read the canonical dialect from dbkit/.sqlfluff, or exit with an actionable error."""
    if not _SQLFLUFF.exists():
        raise SystemExit(
            "Canonical dialect not configured: dbkit/.sqlfluff is missing. Create it with a "
            "`dialect = <mysql|postgres|tsql|sqlite|...>` line (see dbkit/README.md)."
        )
    match = _DIALECT_RE.search(_SQLFLUFF.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("dbkit/.sqlfluff has no `dialect = ...` line — set the canonical dialect there.")
    return match.group(1)
