import os
from pathlib import Path

import pytest

from quietsql.adapters.llm.llamacpp import LlamaCppTextToSql
from quietsql.core.errors import Cancelled

MODEL = Path(os.path.expanduser("~/.cache/quietsql/models/XiYanSQL-QwenCoder-3B-2504.Q4_K_M.gguf"))


class FakeStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.consumed = 0
        self.closes = 0

    def __iter__(self):
        for c in self.chunks:
            self.consumed += 1
            yield {"choices": [{"text": c}]}

    def close(self):
        self.closes += 1


class FakeLlama:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []
        self.stream = FakeStream(chunks)

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        return self.stream


def test_generate_streams_and_extracts(monkeypatch):
    provider = LlamaCppTextToSql.__new__(LlamaCppTextToSql)
    provider.llm = FakeLlama([" count(*)", " FROM sales", ";"])
    provider.max_tokens = 120
    provider._prefill_ms = 0.0
    seen = []
    out = provider.generate("ddl", "q", [], on_token=seen.append)
    assert out == "SELECT count(*) FROM sales"
    assert seen == ["SELECT", " count(*)", " FROM sales", ";"]
    prompt, kw = provider.llm.calls[0]
    assert prompt.endswith("assistant\nSELECT")
    assert kw["max_tokens"] == 120
    assert kw["temperature"] == 0.0


def test_generate_stops_consuming_when_the_callback_cancels():
    provider = LlamaCppTextToSql.__new__(LlamaCppTextToSql)
    provider.llm = FakeLlama([" a", " b", " c"])
    provider.max_tokens = 120
    provider._prefill_ms = 0.0
    seen = []

    def cb(tok):
        seen.append(tok)
        if len(seen) == 2:
            raise Cancelled("stop")

    with pytest.raises(Cancelled) as exc:
        provider.generate("ddl", "q", [], on_token=cb)
    assert str(exc.value) == "stop"
    assert seen == ["SELECT", " a"]
    assert provider.llm.stream.consumed == 1
    assert provider.llm.stream.closes == 1


def test_generate_closes_the_stream_once_on_success():
    provider = LlamaCppTextToSql.__new__(LlamaCppTextToSql)
    provider.llm = FakeLlama([" 1", ";"])
    provider.max_tokens = 120
    provider._prefill_ms = 0.0
    provider.generate("ddl", "q", [])
    assert provider.llm.stream.closes == 1


@pytest.mark.slow
@pytest.mark.skipif(not MODEL.exists(), reason="run quietsql download-models first")
def test_real_model_writes_valid_sql():
    provider = LlamaCppTextToSql(MODEL)
    ddl = "create table sales (\n  id bigint primary key,\n  amount double -- 1.5..980.0\n);"
    sql = provider.generate(ddl, "total amount of all sales", [])
    assert sql.lower().startswith("select") and "sum" in sql.lower() and "sales" in sql.lower()
