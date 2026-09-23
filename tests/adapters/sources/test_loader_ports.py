import pytest

from quietsql.adapters.sources.loader import FileSourceLoader
from quietsql.ports import SourceLoader


@pytest.mark.parametrize(
    ("adapter", "protocol"),
    [(FileSourceLoader, SourceLoader)],
)
def test_adapter_conforms_to_its_port(conforms_to_port, adapter, protocol):
    conforms_to_port(adapter, protocol)
