import pytest

from quietsql.adapters.duckdb.catalog import DuckDbCatalog
from quietsql.adapters.duckdb.history import DuckDbHistory
from quietsql.adapters.duckdb.runner import DuckDbRunner
from quietsql.ports import Catalog, HistoryStore, QueryRunner


@pytest.mark.parametrize(
    ("adapter", "protocol"),
    [(DuckDbRunner, QueryRunner), (DuckDbCatalog, Catalog), (DuckDbHistory, HistoryStore)],
)
def test_adapter_conforms_to_its_port(conforms_to_port, adapter, protocol):
    conforms_to_port(adapter, protocol)
