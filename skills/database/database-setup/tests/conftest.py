"""Maintenance tests for the scaffold tools (not copied into repos)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCAFFOLD = Path(__file__).resolve().parents[1] / "scaffold"

CUSTOMER = """-- A person or company that buys from us.
CREATE TABLE fin.customer (
    -- Surrogate key.
    id INT NOT NULL,
    code VARCHAR(20) NOT NULL, -- Legacy customer code
    full_name VARCHAR(100) NOT NULL,
    CONSTRAINT pk_customer PRIMARY KEY CLUSTERED (id)
);
"""

INVOICE = """CREATE TABLE fin.invoice (
    id INT NOT NULL,
    customer_id INT NOT NULL,
    branch INT NOT NULL,
    seq INT NOT NULL,
    customer_code VARCHAR(20) NULL,
    CONSTRAINT pk_invoice PRIMARY KEY CLUSTERED (id),
    CONSTRAINT fk_invoice_customer FOREIGN KEY (customer_id) REFERENCES fin.customer (id) ON DELETE CASCADE,
    CONSTRAINT fk_invoice_book FOREIGN KEY (branch, seq) REFERENCES fin.book (branch, seq) ON UPDATE SET NULL
);
"""

BOOK = """CREATE TABLE fin.book (
    branch INT NOT NULL,
    seq INT NOT NULL,
    CONSTRAINT pk_book PRIMARY KEY CLUSTERED (branch, seq)
);
"""

OLD = """CREATE TABLE tmp_old (
    x INT NULL
);
"""

DATABASE_MD = """# Test — Domain

## Tables

### Billing

#### fin.customer
- **Concept:** a party that buys; one row per legal entity.

#### fin.invoice
- **Concept:** an issued invoice.
- **Implied:** customer_code → fin.customer.code — legacy lookup, 3 orphans

#### fin.book
- **Concept:** numbering book.
- `fin.book_draft` — scratch copy of `fin.customer` rows — **elimination candidate**.

### Leftovers

- `tmp_old` — elimination candidate.

## Routines

| Routine | Type | Rule |
|---|---|---|
| `fin.usp_bill` | procedure | FIN-01 |
"""

INVENTORY = {"objects": [
    {"schema": "fin", "name": "customer", "type": "U", "fingerprint": "a",
     "depends_on": [], "target": "db-schema/schema/tables/fin.customer.sql"},
    {"schema": "fin", "name": "invoice", "type": "U", "fingerprint": "b",
     "depends_on": ["customer"], "target": "db-schema/schema/tables/fin.invoice.sql"},
    {"schema": "fin", "name": "usp_bill", "type": "P", "fingerprint": "c",
     "depends_on": ["invoice", "customer"],
     "target": "db-schema/schema/native/tsql/procedures/fin.usp_bill.sql"},
]}


def run(kit: Path, tool: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(kit / "db-schema" / "tools" / tool), *args],
                          cwd=kit, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    shutil.copytree(SCAFFOLD, tmp_path, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    db = tmp_path / "db-schema"
    (db / ".sqlfluff").write_text("[sqlfluff]\ndialect = tsql\nmax_line_length = 120\n", encoding="utf-8")
    tables = db / "schema" / "tables"
    for name, sql in (("fin.customer", CUSTOMER), ("fin.invoice", INVOICE),
                      ("fin.book", BOOK), ("tmp_old", OLD)):
        (tables / f"{name}.sql").write_text(sql, encoding="utf-8")
    proc = db / "schema" / "native" / "tsql" / "procedures"
    proc.mkdir(parents=True)
    (proc / "fin.usp_bill.sql").write_text("CREATE PROCEDURE fin.usp_bill AS SELECT 1;\n",
                                           encoding="utf-8")
    (db / "baseline").mkdir(exist_ok=True)
    (db / "baseline" / "inventory.fin.json").write_text(json.dumps(INVENTORY), encoding="utf-8")
    (db / "baseline" / "exceptions.json").write_text(json.dumps(
        [{"name": "book", "schema": "fin", "status": "excluded", "reason": "archived"}]),
        encoding="utf-8")
    (db / "baseline" / "watched-data.json").write_text(json.dumps(
        [{"schema": "fin", "table": "customer", "rule": "FIN-02"}]), encoding="utf-8")
    model = tmp_path / "docs" / "db-model"
    (model / "database.md").write_text(DATABASE_MD, encoding="utf-8")
    (model / "calc").mkdir()
    (model / "calc" / "FIN-01.md").write_text("Totals come from `fin.invoice`.\n", encoding="utf-8")
    ovr = db / "schema" / "overrides" / "postgres"
    ovr.mkdir(parents=True)
    (ovr / "fin.book.sql").write_text("CREATE TABLE fin.book (branch INT, seq INT);\n",
                                      encoding="utf-8")
    return tmp_path
