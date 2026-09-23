import duckdb

from quietsql.adapters.duckdb.catalog import DuckDbCatalog
from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.keys import infer_foreign_keys


def make(tmp_path):
    db = tmp_path / "k.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE customers AS SELECT i AS id, 'n' || i AS name FROM range(50) t(i)")
    con.execute(
        "CREATE TABLE products AS SELECT i AS product_id, 'p' || i AS title FROM range(20) t(i)"
    )
    con.execute(
        "CREATE TABLE sales AS SELECT i AS id, i % 50 AS customer_id, i % 20 AS product_id, "
        "i % 7 AS region_id, i * 2.0 AS amount FROM range(500) t(i)"
    )
    con.execute("CREATE TABLE regions AS SELECT i AS id FROM range(3) t(i)")
    con.close()
    pool = ConnectionPool()
    pool.register("s", str(db))
    return pool


def test_infers_verified_keys_only(tmp_path):
    pool = make(tmp_path)
    tables = DuckDbCatalog(pool).schema("s").tables
    con = pool.writable("s").cursor()
    fks = infer_foreign_keys(con, tables)
    pairs = {(fk.table, fk.column, fk.referenced_table, fk.referenced_column) for fk in fks}
    assert ("sales", "customer_id", "customers", "id") in pairs
    assert ("sales", "product_id", "products", "product_id") in pairs
    assert not any(fk.column == "region_id" for fk in fks)


def test_catalog_uses_inferred_keys(tmp_path):
    pool = make(tmp_path)
    schema = DuckDbCatalog(pool, infer_keys=infer_foreign_keys).schema("s")
    assert any(fk.referenced_table == "customers" for fk in schema.foreign_keys)


def test_rejects_name_matching_non_contained_column(tmp_path):
    db = tmp_path / "reject.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE customers AS SELECT i AS id FROM range(10) t(i)")
    con.execute(
        "CREATE TABLE orders AS SELECT i AS id, i + 1000 AS customer_id FROM range(10) t(i)"
    )
    con.close()
    pool = ConnectionPool()
    pool.register("r", str(db))
    tables = DuckDbCatalog(pool).schema("r").tables
    con = pool.writable("r").cursor()
    fks = infer_foreign_keys(con, tables)
    assert not any(fk.column == "customer_id" for fk in fks)


def containment_pool(tmp_path, name, misses):
    db = tmp_path / f"{name}.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE customers AS SELECT i AS id FROM range(100) t(i)")
    con.execute(
        "CREATE TABLE orders AS SELECT i AS id, "
        f"CASE WHEN i < {misses} THEN i + 1000 ELSE i END AS customer_id FROM range(100) t(i)"
    )
    con.close()
    pool = ConnectionPool()
    pool.register(name, str(db))
    return pool


def inferred_columns(pool, source_id):
    tables = DuckDbCatalog(pool).schema(source_id).tables
    con = pool.writable(source_id).cursor()
    return {fk.column for fk in infer_foreign_keys(con, tables)}


def test_rejects_containment_just_below_the_threshold(tmp_path):
    pool = containment_pool(tmp_path, "low", 10)
    assert "customer_id" not in inferred_columns(pool, "low")


def test_accepts_containment_just_above_the_threshold(tmp_path):
    pool = containment_pool(tmp_path, "high", 3)
    assert "customer_id" in inferred_columns(pool, "high")


def test_threshold_is_the_policy_not_the_absence_of_matches(tmp_path):
    pool = containment_pool(tmp_path, "tuned", 10)
    tables = DuckDbCatalog(pool).schema("tuned").tables
    con = pool.writable("tuned").cursor()
    fks = infer_foreign_keys(con, tables, min_containment=0.85)
    assert any(fk.column == "customer_id" for fk in fks)


class Recording:
    def __init__(self, con):
        self.con = con
        self.statements = []

    def execute(self, sql, *args):
        self.statements.append(sql)
        return self.con.execute(sql, *args)


def test_primary_key_candidates_are_built_only_for_referenced_tables(tmp_path):
    db = tmp_path / "lazy.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE customers AS SELECT i AS id FROM range(10) t(i)")
    con.execute("CREATE TABLE unrelated AS SELECT i AS id FROM range(10) t(i)")
    con.execute("CREATE TABLE orders AS SELECT i AS id, i % 10 AS customer_id FROM range(10) t(i)")
    con.close()
    pool = ConnectionPool()
    pool.register("l", str(db))
    tables = DuckDbCatalog(pool).schema("l").tables
    recording = Recording(pool.writable("l").cursor())
    fks = infer_foreign_keys(recording, tables)
    assert any(fk.referenced_table == "customers" for fk in fks)
    assert not any("unrelated" in sql for sql in recording.statements)
