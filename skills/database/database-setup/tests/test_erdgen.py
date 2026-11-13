"""erdgen.py: the DBML carries notes, links and relations drawn only from versioned sources."""
from __future__ import annotations

import shutil

from conftest import run

DBML = "docs/db-model/schema.dbml"
MMD = "docs/db-model/erd.mmd"


def generate(kit):
    r = run(kit, "erdgen.py")
    assert r.returncode == 0, r.stdout + r.stderr
    return (kit / DBML).read_text(encoding="utf-8")


def test_keys_nullability_and_comments(kit):
    dbml = generate(kit)
    assert "    id integer [pk, not null, note: 'Surrogate key.']" in dbml
    assert "    code varchar(20) [not null, note: 'Legacy customer code']" in dbml
    assert "    customer_code varchar(20)\n" in dbml          # explicit NULL stays nullable
    assert "        (branch, seq) [pk]" in dbml               # composite CLUSTERED pk


def test_relations(kit):
    dbml = generate(kit)
    assert ("Ref fk_invoice_customer: fin.invoice.customer_id > fin.customer.id "
            "[delete: cascade]") in dbml
    assert ("Ref fk_invoice_book: fin.invoice.(branch, seq) > fin.book.(branch, seq) "
            "[update: set null]") in dbml
    assert ("Ref: fin.invoice.customer_code > fin.customer.code [color: #d97706] "
            "// implied, no FK: legacy lookup, 3 orphans") in dbml
    mmd = (kit / MMD).read_text(encoding="utf-8")
    assert 'fin__customer |o..o{ fin__invoice : "implied customer_code"' in mmd


def test_table_notes_and_links(kit):
    dbml = generate(kit)
    assert "    a party that buys; one row per legal entity. · DDL comment: A person" in dbml
    assert "[model](database.md#fincustomer) · [DDL](../../db-schema/schema/tables/fin.customer.sql)" in dbml
    assert ("routines: [procedures fin.usp_bill]"
            "(../../db-schema/schema/native/tsql/procedures/fin.usp_bill.sql)") in dbml
    assert "    watched data: FIN-02" in dbml
    assert "    [protected] rule [FIN-01](calc/FIN-01.md)" in dbml
    assert "[override postgres](../../db-schema/schema/overrides/postgres/fin.book.sql)" in dbml
    assert "    excluded: archived" in dbml
    assert "    model block pending · ELIMINATION CANDIDATE" in dbml
    assert 'TableGroup Billing {\n    fin.book\n    fin.customer\n    fin.invoice\n}' in dbml


def test_deterministic_and_check(kit):
    first = generate(kit)
    assert generate(kit) == first
    assert run(kit, "erdgen.py", "--check").returncode == 0


def test_model_edit_without_regen_is_red(kit):
    generate(kit)
    md = kit / "docs/db-model/database.md"
    md.write_text(md.read_text(encoding="utf-8").replace("an issued invoice.", "a bill."),
                  encoding="utf-8")
    assert run(kit, "erdgen.py", "--check").returncode == 1
    assert run(kit, "doccheck.py").returncode == 1
    generate(kit)
    r = run(kit, "doccheck.py")
    assert r.returncode == 0, r.stdout


def test_implied_unknown_column_is_red(kit):
    md = kit / "docs/db-model/database.md"
    md.write_text(md.read_text(encoding="utf-8").replace(
        "customer_code → fin.customer.code", "customer_code → fin.customer.nope"), encoding="utf-8")
    generate(kit)
    r = run(kit, "doccheck.py")
    assert r.returncode == 1 and "unknown column(s) fin.customer.nope" in r.stdout


def test_malformed_implied_is_red(kit):
    md = kit / "docs/db-model/database.md"
    md.write_text(md.read_text(encoding="utf-8").replace(
        "customer_code → fin.customer.code", "links to customers somehow"), encoding="utf-8")
    generate(kit)
    r = run(kit, "doccheck.py")
    assert r.returncode == 1 and "malformed **Implied:**" in r.stdout


def test_without_model_or_baseline(kit):
    (kit / "docs/db-model/database.md").unlink()
    shutil.rmtree(kit / "db-schema/baseline")
    shutil.rmtree(kit / "docs/db-model/calc")
    dbml = generate(kit)
    assert "TableGroup" not in dbml and "routines:" not in dbml
    assert "Ref fk_invoice_customer:" in dbml


def test_verify_green(kit):
    generate(kit)
    r = run(kit, "verify.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_virgin_scaffold_green(tmp_path):
    import shutil as sh
    from conftest import SCAFFOLD
    sh.copytree(SCAFFOLD, tmp_path, dirs_exist_ok=True, ignore=sh.ignore_patterns("__pycache__"))
    (tmp_path / "db-schema" / ".sqlfluff").write_text("[sqlfluff]\ndialect = tsql\n", encoding="utf-8")
    r = run(tmp_path, "verify.py")
    assert r.returncode == 0, r.stdout + r.stderr


def _mini_kit(tmp_path, dialect, files):
    import shutil as sh
    from conftest import SCAFFOLD
    sh.copytree(SCAFFOLD, tmp_path, dirs_exist_ok=True, ignore=sh.ignore_patterns("__pycache__"))
    (tmp_path / "db-schema" / ".sqlfluff").write_text(
        f"[sqlfluff]\ndialect = {dialect}\n", encoding="utf-8")
    for name, sql in files.items():
        (tmp_path / "db-schema/schema/tables" / f"{name}.sql").write_text(sql, encoding="utf-8")
    return tmp_path


def test_postgres_comment_on_and_inline_reference(tmp_path):
    kit = _mini_kit(tmp_path, "postgres", {
        "customer": "CREATE TABLE customer (\n    id INT PRIMARY KEY\n);\n"
                    "COMMENT ON TABLE customer IS 'Buyer.';\n"
                    "COMMENT ON COLUMN customer.id IS 'Surrogate.';\n",
        "orders": "CREATE TABLE orders (\n    id INT PRIMARY KEY,\n"
                  "    customer_id INT NOT NULL REFERENCES customer (id) ON DELETE SET NULL\n);\n",
    })
    dbml = generate(kit)
    assert "    id int [pk, note: 'Surrogate.']" in dbml
    assert "    Buyer. · model block pending" in dbml
    assert "Ref: orders.customer_id > customer.id [delete: set null]" in dbml


def test_mysql_inline_comments(tmp_path):
    kit = _mini_kit(tmp_path, "mysql", {
        "item": "CREATE TABLE item (\n    id INT NOT NULL COMMENT 'Item key',\n"
                "    PRIMARY KEY (id)\n) COMMENT='Sellable item';\n",
    })
    dbml = generate(kit)
    assert "    id int [pk, not null, note: 'Item key']" in dbml
    assert "    Sellable item · model block pending" in dbml


def test_identifiers_needing_quotes(tmp_path):
    kit = _mini_kit(tmp_path, "tsql", {
        "lead": "CREATE TABLE lead (\n    [Data de início] NVARCHAR(255) NULL,\n"
                "    [Opt-in] NVARCHAR(255) NULL\n);\n",
    })
    dbml = generate(kit)
    assert '    "Data de início" nvarchar(255)\n' in dbml
    assert '    "Opt-in" nvarchar(255)\n' in dbml
    mmd = (kit / MMD).read_text(encoding="utf-8")
    assert "NVARCHAR(255) Data_de_início" in mmd and "NVARCHAR(255) Opt_in" in mmd


def test_undrawable_fks_become_comments(tmp_path):
    kit = _mini_kit(tmp_path, "tsql", {
        "u": "CREATE TABLE u (\n    user_id INT NOT NULL,\n"
             "    CONSTRAINT pk_u PRIMARY KEY CLUSTERED (user_id),\n"
             "    CONSTRAINT id FOREIGN KEY (user_id) REFERENCES dbo.u (user_id),\n"
             "    CONSTRAINT fk_ext FOREIGN KEY (user_id) REFERENCES dbo.elsewhere (id)\n);\n",
    })
    dbml = generate(kit)
    assert "// Ref id: u.user_id > u.user_id  -- references its own column(s)" in dbml
    assert "// Ref fk_ext: u.user_id > elsewhere.id  -- target table not in schema/tables/" in dbml
    assert "FK id references its own column(s) user_id (not drawable)" in dbml


def test_elimination_only_for_the_named_table(kit):
    dbml = generate(kit)
    customer = dbml.split("Table fin.customer {")[1].split("\n}")[0]
    assert "ELIMINATION" not in customer          # only mentioned on another table's line
    book = dbml.split("Table fin.book {")[1].split("\n}")[0]
    assert "ELIMINATION" not in book              # a line in its block about another table
