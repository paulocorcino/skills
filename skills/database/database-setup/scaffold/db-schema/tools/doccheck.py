#!/usr/bin/env python
"""doccheck.py — coherence between db-schema/ and the model docs (pipeline step 5).

This is the one check that spans both roots: the DDL under `db-schema/` and the domain
prose under `docs/db-model/` (path declared in `_paths.py`).

Presence checks only (semantic quality stays a human-review concern):
  1. every schema/tables/<name>.sql is mentioned in the model docs' database.md or
     domains/*.md (heading, code span, or bold — shard-aware);
  2. every routine file under schema/native/<dialect>/ is mentioned in the
     model docs (Routines section or elsewhere);
  3. committed diagrams in sync — delegated to erdgen.py --check;
  4. every migration in migrations/ starts with a description comment.

Exit 0 = coherent. Any failure = exit 1.
"""
from __future__ import annotations

import re
import subprocess
import sys

from _paths import KIT_ROOT, MODEL_DIR, display

ROOT = KIT_ROOT
TABLES_DIR = ROOT / "schema" / "tables"
NATIVE_DIR = ROOT / "schema" / "native"
MIGRATIONS_DIR = ROOT / "migrations"


def model_text() -> str:
    chunks = []
    main = MODEL_DIR / "database.md"
    if main.exists():
        chunks.append(main.read_text(encoding="utf-8"))
    domains = MODEL_DIR / "domains"
    if domains.is_dir():
        for f in sorted(domains.glob("*.md")):
            chunks.append(f.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def mentioned(name: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])",
                     text) is not None


def main() -> int:
    problems: list[str] = []
    text = model_text()

    if not text.strip():
        if any(TABLES_DIR.glob("*.sql")):
            problems.append(f"{display(MODEL_DIR / 'database.md')} missing or empty "
                            "while schema/tables/ has tables")
    else:
        for f in sorted(TABLES_DIR.glob("*.sql")):
            if not mentioned(f.stem, text):
                problems.append(f"table not in model docs: {f.stem}")
        if NATIVE_DIR.is_dir():
            for f in sorted(NATIVE_DIR.rglob("*.sql")):
                if not mentioned(f.stem, text):
                    problems.append(f"native object not in model docs: "
                                    f"{f.relative_to(NATIVE_DIR)}")

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "erdgen.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        problems.append("erd out of sync: " + (result.stdout or result.stderr).strip())

    if MIGRATIONS_DIR.is_dir():
        for f in sorted(MIGRATIONS_DIR.rglob("*.sql")):
            first = f.read_text(encoding="utf-8").lstrip()
            if not first.startswith("--"):
                problems.append(f"migration without description comment: {f.name}")

    if problems:
        print(f"doccheck: {len(problems)} problem(s)")
        for p in problems:
            print(f"  {p}")
        return 1
    n_tables = len(list(TABLES_DIR.glob("*.sql")))
    n_native = len(list(NATIVE_DIR.rglob("*.sql"))) if NATIVE_DIR.is_dir() else 0
    print(f"doccheck: OK — {n_tables} tables and {n_native} native objects all "
          "present in model docs; diagrams in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
