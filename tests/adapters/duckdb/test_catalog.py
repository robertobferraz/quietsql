import duckdb
import pytest

from quietsql.adapters.duckdb.catalog import DuckDbCatalog
from quietsql.adapters.duckdb.connections import ConnectionPool


@pytest.fixture
def pool(tmp_path):
    db = tmp_path / "c.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE customers(id INTEGER PRIMARY KEY, name VARCHAR, email VARCHAR, city VARCHAR)"
    )
    con.execute(
        "INSERT INTO customers SELECT i, 'Name ' || i, 'u' || i || '@x.com', "
        "CASE i % 3 WHEN 0 THEN 'Recife' WHEN 1 THEN 'Olinda' ELSE 'Caruaru' END "
        "FROM range(300) t(i)"
    )
    con.execute(
        "CREATE TABLE sales(id INTEGER, customer_id INTEGER REFERENCES customers(id), "
        "sold_at DATE, amount DOUBLE, notes VARCHAR)"
    )
    con.execute(
        "INSERT INTO sales SELECT i, i % 300, "
        "DATE '2026-03-01' + CAST(i % 30 AS INTEGER), i * 1.5, "
        "repeat('long free text about the sale ', 4) || i FROM range(1000) t(i)"
    )
    con.execute("CREATE TABLE _quietsql_history(id INTEGER)")
    con.close()
    p = ConnectionPool()
    p.register("s", str(db))
    return p


def test_schema_lists_user_tables_columns_and_declared_keys(pool):
    schema = DuckDbCatalog(pool).schema("s")
    assert [t.name for t in schema.tables] == ["customers", "sales"]
    sales = schema.tables[1]
    assert sales.row_count == 1000
    assert [c.name for c in sales.columns] == ["id", "customer_id", "sold_at", "amount", "notes"]
    assert schema.tables[0].columns[0].is_primary_key is True
    assert schema.foreign_keys[0].referenced_table == "customers"


def test_example_values_follow_the_rules(pool):
    schema = DuckDbCatalog(pool).schema("s")
    cols = {c.name: c for t in schema.tables for c in t.columns}
    assert cols["city"].examples == ("Caruaru", "Olinda", "Recife")
    assert cols["email"].examples == ()
    assert cols["amount"].examples == ("0.0..1498.5",)
    assert cols["notes"].examples == ()
    assert len(cols["sold_at"].examples) == 3
    assert cols["id"].examples == ()


def test_low_cardinality_numeric_column_still_gets_a_range(tmp_path):
    db = tmp_path / "r.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE orders(id INTEGER, rating INTEGER)")
    con.execute("INSERT INTO orders SELECT i, (i % 5) + 1 FROM range(500) t(i)")
    con.close()
    p = ConnectionPool()
    p.register("r", str(db))
    schema = DuckDbCatalog(p).schema("r")
    rating = next(c for c in schema.tables[0].columns if c.name == "rating")
    assert rating.examples == ("1..5",)


def test_identifiers_sorted_and_deduped(pool):
    ids = DuckDbCatalog(pool).identifiers("s")
    assert ids[:3] == ("amount", "city", "customer_id")
    assert "_quietsql_history" not in ids and ids.count("id") == 1


def test_render_full_when_within_budget_and_caches(pool):
    cat = DuckDbCatalog(pool, budget_tokens=1000)
    schema = cat.schema("s")
    r = cat.render(schema, "how many sales")
    assert r.pruned is False and set(r.table_names) == {"customers", "sales"}
    assert "create table sales" in r.ddl
    assert cat.schema("s") is schema
    cat.invalidate("s")
    assert cat.schema("s") is not schema


def test_render_calls_selector_when_over_budget(pool):
    calls = []

    def select(schema, question, budget):
        calls.append(question)
        return ("sales",)

    cat = DuckDbCatalog(pool, budget_tokens=5, select=select)
    r = cat.render(cat.schema("s"), "sales by day")
    assert r.pruned is True and r.table_names == ("sales",) and calls == ["sales by day"]
    assert "create table customers" not in r.ddl


def test_schema_handles_reserved_table_and_column_names(tmp_path):
    db = tmp_path / "reserved.duckdb"
    con = duckdb.connect(str(db))
    con.execute('CREATE TABLE "order"(id INTEGER, "group" VARCHAR)')
    con.execute("INSERT INTO \"order\" SELECT i, 'g' || (i % 2) FROM range(20) t(i)")
    con.close()
    p = ConnectionPool()
    p.register("o", str(db))
    schema = DuckDbCatalog(p).schema("o")
    assert [t.name for t in schema.tables] == ["order"]
    group = schema.tables[0].columns[1]
    assert group.name == "group" and group.examples == ("g0", "g1")
    assert '"order"' in DuckDbCatalog(p).render(schema, None).ddl


def test_invalidate_during_extraction_is_not_resurrected(pool):
    cat = DuckDbCatalog(pool)

    def invalidating(con, tables):
        cat.invalidate("s")
        return ()

    cat.infer_keys = invalidating
    first = cat.schema("s")
    second = cat.schema("s")
    assert second is not first


def test_unsigned_integer_column_gets_a_range(tmp_path):
    db = tmp_path / "u.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE counts(id INTEGER, hits UBIGINT)")
    con.execute("INSERT INTO counts SELECT i, CAST(i % 4 AS UBIGINT) FROM range(40) t(i)")
    con.close()
    p = ConnectionPool()
    p.register("u", str(db))
    hits = next(c for c in DuckDbCatalog(p).schema("u").tables[0].columns if c.name == "hits")
    assert hits.examples == ("0..3",)
