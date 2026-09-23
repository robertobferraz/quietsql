import duckdb
import pytest

from quietsql.adapters.duckdb.catalog import DuckDbCatalog
from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.runner import DuckDbRunner
from quietsql.core.errors import QueryFailed, QueryTimeout, SqlRejected


@pytest.fixture
def pool(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE sales(id INTEGER, city VARCHAR, amount DOUBLE)")
    con.execute("INSERT INTO sales SELECT i, 'c' || (i % 3), i * 1.5 FROM range(100) t(i)")
    con.close()
    p = ConnectionPool()
    p.register("s", str(db))
    return p


def test_validate_transpiles_postgres_to_duckdb():
    out = DuckDbRunner(ConnectionPool()).validate("SELECT amount::float8 FROM sales;")
    assert "CAST(amount AS DOUBLE)" in out
    assert "float8" not in out and not out.endswith(";")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sales",
        "UPDATE sales SET id = 1",
        "DROP TABLE sales",
        "INSERT INTO sales VALUES (1)",
        "CREATE TABLE x AS SELECT 1",
        "COPY sales TO 'x.csv'",
        "ATTACH 'other.duckdb'",
    ],
)
def test_validate_rejects_non_read(sql):
    with pytest.raises(SqlRejected):
        DuckDbRunner(ConnectionPool()).validate(sql)


def test_validate_rejects_two_statements():
    with pytest.raises(SqlRejected, match="one statement"):
        DuckDbRunner(ConnectionPool()).validate("SELECT 1; SELECT 2")


def test_validate_accepts_with_describe_summarize():
    r = DuckDbRunner(ConnectionPool())
    assert r.validate("WITH t AS (SELECT 1 AS a) SELECT * FROM t")
    assert r.validate("DESCRIBE sales")
    assert r.validate("SUMMARIZE sales")


def test_run_returns_rows_and_types(pool):
    res = DuckDbRunner(pool).run(
        "s", "SELECT city, count(*) AS n FROM sales GROUP BY 1 ORDER BY 1", 10
    )
    assert res.columns == (("city", "VARCHAR"), ("n", "BIGINT"))
    assert res.rows == (("c0", 34), ("c1", 33), ("c2", 33))
    assert res.total_rows == 3 and res.truncated is False


def test_run_truncates_and_counts_total(pool):
    res = DuckDbRunner(pool).run("s", "SELECT id FROM sales ORDER BY id", 10)
    assert len(res.rows) == 10 and res.total_rows == 100 and res.truncated is True


def test_run_wraps_duckdb_error(pool):
    with pytest.raises(QueryFailed, match="nope"):
        DuckDbRunner(pool).run("s", "SELECT nope FROM sales", 10)


def test_run_times_out(pool):
    slow = "SELECT count(*) FROM range(200000000) a, range(200) b"
    with pytest.raises(QueryTimeout):
        DuckDbRunner(pool, timeout_s=0.2).run("s", slow, 10)


def test_run_cannot_write_even_if_validate_is_bypassed(pool):
    with pytest.raises(QueryFailed):
        DuckDbRunner(pool).run("s", "DELETE FROM sales", 10)
    con = duckdb.connect(pool.path("s"), read_only=True)
    assert con.execute("SELECT count(*) FROM sales").fetchone()[0] == 100


def test_run_cannot_write_via_cached_writable_cursor(pool, tmp_path):
    writable = pool.writable("s")
    with pytest.raises(QueryFailed):
        DuckDbRunner(pool).run("s", "DELETE FROM sales", 10)
    assert writable.execute("SELECT count(*) FROM sales").fetchone()[0] == 100

    export_path = tmp_path / "export.csv"
    with pytest.raises(QueryFailed):
        DuckDbRunner(pool).run("s", f"COPY sales TO '{export_path}' (HEADER)", 10)
    assert not export_path.exists()


def test_run_strips_the_trailing_semicolon_before_counting(pool):
    res = DuckDbRunner(pool).run("s", "SELECT id FROM sales ORDER BY id;", 10)
    assert len(res.rows) == 10 and res.total_rows == 100 and res.truncated is True


def test_run_and_catalog_share_one_connection_per_file(pool):
    pool.register("twin", pool.path("s"))
    res = DuckDbRunner(pool).run("s", "SELECT count(*) AS n FROM sales", 10)
    assert res.rows == ((100,),)
    schema = DuckDbCatalog(pool).schema("twin")
    assert [t.name for t in schema.tables] == ["sales"]
    assert DuckDbRunner(pool).run("twin", "SELECT count(*) AS n FROM sales", 10).rows == ((100,),)
