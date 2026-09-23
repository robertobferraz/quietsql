import os

import duckdb
import pytest

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.sources.loader import FileSourceLoader, sanitize
from quietsql.core.errors import SourceRejected
from quietsql.core.models import SourceKind


@pytest.fixture
def loader(tmp_path):
    return FileSourceLoader(ConnectionPool(), tmp_path / "sessions"), tmp_path


def test_sanitize():
    assert sanitize("Vendas Março-2026.csv") == "vendas_mar_o_2026"
    assert sanitize("2026.parquet") == "t_2026"


def test_upload_csv_creates_table_in_session_db(loader):
    fl, tmp = loader
    csv = tmp / "Sales.csv"
    csv.write_text("id,city\n1,Recife\n2,Olinda\n")
    src = fl.load_upload("Sales.csv", str(csv))
    assert src.kind is SourceKind.UPLOAD and src.table_count == 1
    con = duckdb.connect(fl.pool.path(src.id))
    assert con.execute("SELECT count(*) FROM sales").fetchone()[0] == 2
    assert fl.list() == (src,)


def test_open_duckdb_file(loader):
    fl, tmp = loader
    db = tmp / "x.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE a(i INTEGER); CREATE TABLE b(i INTEGER)")
    con.close()
    src = fl.open_file(str(db))
    assert src.kind is SourceKind.FILE and src.table_count == 2 and src.name == "x.duckdb"


def test_folder_loads_each_file_and_reloads_on_change(loader):
    fl, tmp = loader
    folder = tmp / "exports"
    folder.mkdir()
    (folder / "a.csv").write_text("i\n1\n")
    (folder / "b.csv").write_text("i\n1\n2\n")
    (folder / "notes.txt").write_text("ignored")
    src = fl.load_folder(str(folder))
    assert src.kind is SourceKind.FOLDER and src.table_count == 2
    (folder / "a.csv").write_text("i\n1\n2\n3\n")
    os.utime(folder / "a.csv", (2_000_000_000, 2_000_000_000))
    fl.reload(src.id)
    con = duckdb.connect(fl.pool.path(src.id))
    assert con.execute("SELECT count(*) FROM a").fetchone()[0] == 3


def test_remove_deletes_session_db(loader):
    fl, tmp = loader
    csv = tmp / "s.csv"
    csv.write_text("i\n1\n")
    src = fl.load_upload("s.csv", str(csv))
    path = fl.pool.path(src.id)
    fl.remove(src.id)
    assert not os.path.exists(path) and fl.list() == ()


def test_open_file_rejects_a_data_file_and_points_at_upload(loader):
    fl, tmp = loader
    csv = tmp / "sales.csv"
    csv.write_text("i\n1\n")
    with pytest.raises(SourceRejected) as exc:
        fl.open_file(str(csv))
    assert "upload" in str(exc.value)
    assert fl.list() == () and not fl.pool.registered(str(csv))


def test_open_file_rejects_a_non_database_file_without_leaking_duckdb_errors(loader):
    fl, tmp = loader
    notes = tmp / "notes.txt"
    notes.write_text("just text, not a database")
    with pytest.raises(SourceRejected):
        fl.open_file(str(notes))
    assert not fl.pool.registered(str(notes))


def test_open_file_still_accepts_a_real_duckdb_file(loader):
    fl, tmp = loader
    db = tmp / "real.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE a(i INTEGER)")
    con.close()
    src = fl.open_file(str(db))
    assert src.kind is SourceKind.FILE and src.table_count == 1


def test_colliding_sanitized_names_are_deduplicated(loader):
    fl, tmp = loader
    folder = tmp / "exports"
    folder.mkdir()
    (folder / "a-1.csv").write_text("i\n1\n")
    (folder / "a_1.csv").write_text("i\n1\n2\n")
    src = fl.load_folder(str(folder))
    assert src.table_count == 2
    con = duckdb.connect(fl.pool.path(src.id))
    try:
        assert con.execute("SELECT count(*) FROM a_1").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM a_1_2").fetchone()[0] == 2
    finally:
        con.close()


def test_empty_stems_get_distinct_table_names(loader):
    fl, tmp = loader
    folder = tmp / "weird"
    folder.mkdir()
    (folder / "-.csv").write_text("i\n1\n")
    (folder / "_.csv").write_text("i\n1\n2\n")
    src = fl.load_folder(str(folder))
    assert src.table_count == 2
    con = duckdb.connect(fl.pool.path(src.id))
    try:
        assert con.execute('SELECT count(*) FROM "table"').fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM table_2").fetchone()[0] == 2
    finally:
        con.close()


def test_reload_keeps_the_deduplicated_table_names(loader):
    fl, tmp = loader
    folder = tmp / "exports"
    folder.mkdir()
    (folder / "a-1.csv").write_text("i\n1\n")
    (folder / "a_1.csv").write_text("i\n1\n2\n")
    src = fl.load_folder(str(folder))
    (folder / "a-1.csv").write_text("i\n1\n2\n3\n")
    os.utime(folder / "a-1.csv", (2_000_000_000, 2_000_000_000))
    reloaded = fl.reload(src.id)
    assert reloaded.table_count == 2
    con = duckdb.connect(fl.pool.path(src.id))
    try:
        assert con.execute("SELECT count(*) FROM a_1").fetchone()[0] == 3
        assert con.execute("SELECT count(*) FROM a_1_2").fetchone()[0] == 2
    finally:
        con.close()


def test_remove_keeps_the_session_file_shared_with_another_source(loader):
    fl, tmp = loader
    csv = tmp / "s.csv"
    csv.write_text("i\n1\n")
    src = fl.load_upload("s.csv", str(csv))
    path = fl.pool.path(src.id)
    fl.pool.register("other", path)
    fl.remove(src.id)
    assert os.path.exists(path)
    fl.pool.forget("other")
