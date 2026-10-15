"""Single source of the project's canonical dialect: the `dialect` in db-schema/.sqlfluff.

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
    """Read the canonical dialect from db-schema/.sqlfluff, or exit with an actionable error."""
    if not _SQLFLUFF.exists():
        raise SystemExit(
            "Canonical dialect not configured: db-schema/.sqlfluff is missing. Create it with a "
            "`dialect = <mysql|postgres|tsql|sqlite|...>` line (see db-schema/README.md)."
        )
    match = _DIALECT_RE.search(_SQLFLUFF.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("db-schema/.sqlfluff has no `dialect = ...` line — set the canonical dialect there.")
    return match.group(1)


# The schema a bare object name lives in, per dialect. Objects outside it are
# named "<schema>.<name>" — in their file name and in the tools' output — so two
# schemas never collide (db-schema/schema/README.md). Dialects absent here have
# no default schema: any schema-qualified name keeps its prefix.
DEFAULT_SCHEMAS = {"tsql": "dbo", "postgres": "public", "redshift": "public",
                   "duckdb": "main", "snowflake": "public"}


def default_schema() -> str | None:
    return DEFAULT_SCHEMAS.get(canonical_dialect())


def qualified(schema: str | None, name: str) -> str:
    """An object's qualified name: bare in the default schema, <schema>.<name>
    elsewhere — the same string as its file stem."""
    default = default_schema()
    if not schema or (default and schema.lower() == default):
        return name
    return f"{schema}.{name}"
