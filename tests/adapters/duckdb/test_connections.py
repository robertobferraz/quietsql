import threading

import duckdb
import pytest

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.core.errors import QueryFailed, QuietsqlError


def make_db(path, value):
    con = duckdb.connect(str(path))
    con.execute(f"CREATE TABLE t AS SELECT {value} AS v")
    con.close()
    return str(path)


def test_unknown_source_raises_domain_error():
    pool = ConnectionPool()
    for call in (pool.path, pool.writable, pool.read_only):
        with pytest.raises(QueryFailed, match="nope"):
            call("nope")
    assert issubclass(QueryFailed, QuietsqlError)


def test_path_is_resolved_and_writable_is_cached(tmp_path):
    db = make_db(tmp_path / "a.duckdb", 1)
    pool = ConnectionPool()
    pool.register("s", db)
    assert pool.path("s") == str((tmp_path / "a.duckdb").resolve())
    assert pool.writable("s") is pool.writable("s")


def test_read_only_shares_the_cached_connection(tmp_path):
    pool = ConnectionPool()
    pool.register("s", make_db(tmp_path / "a.duckdb", 1))
    reader = pool.read_only("s")
    assert reader.execute("SELECT v FROM t").fetchone()[0] == 1
    reader.close()
    assert pool.writable("s").execute("SELECT v FROM t").fetchone()[0] == 1


def test_two_sources_on_one_file_share_one_connection(tmp_path):
    db = make_db(tmp_path / "a.duckdb", 1)
    pool = ConnectionPool()
    pool.register("one", db)
    pool.register("two", str(tmp_path / "." / "a.duckdb"))
    assert pool.writable("one") is pool.writable("two")
    pool.forget("one")
    assert pool.writable("two").execute("SELECT v FROM t").fetchone()[0] == 1


def test_register_to_a_new_path_drops_the_old_connection(tmp_path):
    pool = ConnectionPool()
    pool.register("s", make_db(tmp_path / "a.duckdb", 1))
    old = pool.writable("s")
    pool.register("s", make_db(tmp_path / "b.duckdb", 2))
    assert pool.writable("s") is not old
    assert pool.writable("s").execute("SELECT v FROM t").fetchone()[0] == 2
    with pytest.raises(duckdb.Error):
        old.execute("SELECT v FROM t")


def test_forget_closes_the_file(tmp_path):
    pool = ConnectionPool()
    pool.register("s", make_db(tmp_path / "a.duckdb", 1))
    con = pool.writable("s")
    pool.forget("s")
    with pytest.raises(duckdb.Error):
        con.execute("SELECT v FROM t")
    with pytest.raises(QueryFailed):
        pool.path("s")


def test_concurrent_writable_never_opens_two_connections(tmp_path):
    pool = ConnectionPool()
    pool.register("s", make_db(tmp_path / "a.duckdb", 1))
    start = threading.Barrier(8)
    seen = []

    def grab():
        start.wait()
        seen.append(pool.writable("s"))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == 8 and len({id(c) for c in seen}) == 1
