import threading

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.history import TABLE, USER_TABLES, DuckDbHistory
from quietsql.core.models import Language, QueryStatus, Question


def test_append_and_list_newest_first(tmp_path):
    pool = ConnectionPool()
    pool.register("s", str(tmp_path / "h.duckdb"))
    h = DuckDbHistory(pool)
    q = Question("quantas vendas", Language.PT, "how many sales")
    first = h.append("s", q, "select 1", QueryStatus.OK, {"run_ms": 3.0})
    h.append("s", q, "select 2", QueryStatus.ERROR, {})
    rows = h.list("s")
    assert [r.sql for r in rows] == ["select 2", "select 1"]
    assert rows[1].id == first.id == 1
    assert rows[1].timings == {"run_ms": 3.0}
    assert rows[0].status is QueryStatus.ERROR
    assert rows[1].translated_text == "how many sales"
    assert len(h.list("s", limit=1)) == 1


def test_timings_column_is_json(tmp_path):
    pool = ConnectionPool()
    pool.register("s", str(tmp_path / "h.duckdb"))
    h = DuckDbHistory(pool)
    h.append("s", Question("q", Language.EN, "q"), "select 1", QueryStatus.OK, {"run_ms": 1.5})
    con = pool.writable("s").cursor()
    try:
        dtype = con.execute(
            "SELECT data_type FROM duckdb_columns() "
            "WHERE table_name = ? AND column_name = 'timings'",
            [TABLE],
        ).fetchone()[0]
    finally:
        con.close()
    assert dtype == "JSON"
    assert h.list("s")[0].timings == {"run_ms": 1.5}


def test_user_table_named_history_is_untouched_and_visible(tmp_path):
    pool = ConnectionPool()
    pool.register("s", str(tmp_path / "h.duckdb"))
    con = pool.writable("s").cursor()
    con.execute("CREATE TABLE _history(kept INTEGER)")
    con.execute("INSERT INTO _history VALUES (7)")
    con.close()
    h = DuckDbHistory(pool)
    h.append("s", Question("q", Language.EN, "q"), "select 1", QueryStatus.OK, {})
    con = pool.writable("s").cursor()
    try:
        assert con.execute("SELECT kept FROM _history").fetchall() == [(7,)]
        listed = con.execute(
            f"SELECT table_name FROM duckdb_tables() WHERE {USER_TABLES}"
        ).fetchall()
        names = [r[0] for r in listed]
    finally:
        con.close()
    assert "_history" in names and TABLE not in names
    assert len(h.list("s")) == 1


def test_concurrent_appends_keep_every_row_with_a_unique_id(tmp_path):
    pool = ConnectionPool()
    pool.register("s", str(tmp_path / "h.duckdb"))
    h = DuckDbHistory(pool)
    q = Question("quantas vendas", Language.PT, "how many sales")
    per_thread = 60
    errors: list[Exception] = []
    start = threading.Barrier(3)

    def appender() -> None:
        start.wait()
        for _ in range(per_thread):
            try:
                h.append("s", q, "select 1", QueryStatus.OK, {"run_ms": 1.0})
            except Exception as exc:
                errors.append(exc)

    def lister() -> None:
        start.wait()
        for _ in range(per_thread):
            try:
                h.list("s", limit=10)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=appender) for _ in range(2)]
    threads.append(threading.Thread(target=lister))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    rows = h.list("s", limit=1000)
    assert len(rows) == 2 * per_thread
    assert len({r.id for r in rows}) == 2 * per_thread
