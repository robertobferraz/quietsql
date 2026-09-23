import pytest
from tests.fakes import FakeCatalog, FakeHistory, FakeLoader, sample_schema

from quietsql.app.history import ListHistory
from quietsql.app.sources import SourceService
from quietsql.core.errors import SourceRejected
from quietsql.core.models import Language, QueryStatus, Question


def test_upload_registers_and_invalidates_catalog():
    catalog = FakeCatalog(sample_schema(), "ddl", ())
    svc = SourceService(FakeLoader(), catalog)
    s = svc.upload("sales.csv", "/tmp/sales.csv")
    assert s.name == "sales.csv"
    assert catalog.invalidated == [s.id]
    assert svc.list() == (s,)
    assert svc.tables(s.id).tables[0].name == "sales"


def test_too_many_tables_is_rejected_and_removed():
    loader = FakeLoader()
    svc = SourceService(loader, FakeCatalog(sample_schema(), "ddl", ()), max_tables=2)
    with pytest.raises(SourceRejected):
        svc.open_folder("/exports")
    assert loader.list() == ()


def test_list_history_delegates():
    h = FakeHistory()
    h.append("s", Question("q", Language.EN, "q"), "select 1", QueryStatus.OK, {})
    assert ListHistory(h)("s")[0].sql == "select 1"


def test_reload_refreshes_the_source_and_invalidates_catalog():
    loader = FakeLoader()
    catalog = FakeCatalog(sample_schema(), "ddl", ())
    svc = SourceService(loader, catalog)
    s = svc.open_folder("/exports")
    catalog.invalidated.clear()
    again = svc.reload(s.id)
    assert again.id == s.id
    assert loader.reloaded == [s.id]
    assert catalog.invalidated == [s.id]
