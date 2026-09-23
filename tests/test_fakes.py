from tests.fakes import (
    FakeCatalog,
    FakeDetector,
    FakeHistory,
    FakeRunner,
    FakeTextToSql,
    FakeTranslator,
    sample_schema,
)

from quietsql.core.errors import QueryFailed
from quietsql.core.models import Attempt, Language, QueryResult, QueryStatus, Question


def test_fake_text_to_sql_streams_tokens_and_records_calls():
    llm = FakeTextToSql(["select 1", "select 2"])
    seen = []
    out = llm.generate("ddl", "q", [], on_token=seen.append)
    assert out == "select 1"
    assert seen == ["select", "1"]
    assert llm.calls[0].previous == []
    llm.generate("ddl", "q", [Attempt("select 1", "boom")])
    assert llm.calls[1].previous[0].error == "boom"


def test_fake_runner_raises_when_given_exception():
    runner = FakeRunner([QueryFailed("no such column")])
    try:
        runner.run("s", "select x", 10)
    except QueryFailed as e:
        assert "no such column" in str(e)
        return
    raise AssertionError


def test_fake_history_appends_and_lists_newest_first():
    h = FakeHistory()
    q = Question("a", Language.EN, "a")
    h.append("s", q, "select 1", QueryStatus.OK, {})
    h.append("s", q, "select 2", QueryStatus.OK, {})
    assert [e.sql for e in h.list("s")] == ["select 2", "select 1"]


def test_fake_catalog_and_translator():
    cat = FakeCatalog(sample_schema(), "create table sales(...)", ("sales", "customers"))
    assert cat.render(cat.schema("s"), "any").ddl.startswith("create table")
    assert FakeDetector(Language.PT).detect("oi") is Language.PT
    assert FakeTranslator({"quantas vendas": "how many sales"}).translate("quantas vendas", ()) == (
        "how many sales"
    )
    r = QueryResult((("n", "BIGINT"),), ((1,),), 1, False)
    assert FakeRunner([r]).run("s", "select 1", 10) is r
