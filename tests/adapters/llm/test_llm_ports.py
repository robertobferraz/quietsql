import pytest

from quietsql.adapters.llm.llamacpp import LlamaCppTextToSql
from quietsql.ports import TextToSql


@pytest.mark.parametrize(
    ("adapter", "protocol"),
    [(LlamaCppTextToSql, TextToSql)],
)
def test_adapter_conforms_to_its_port(conforms_to_port, adapter, protocol):
    conforms_to_port(adapter, protocol)
