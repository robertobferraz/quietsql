from tests.fakes import (
    FakeCatalog,
    FakeDetector,
    FakeHistory,
    FakeRunner,
    FakeTextToSql,
    FakeTranslator,
    sample_schema,
)

from quietsql.app.ask_question import AskQuestion
from quietsql.core.errors import QueryFailed, SqlRejected
from quietsql.core.models import ChartKind, Language, QueryResult, QueryStatus

DDL = "create table sales(id bigint, customer_id bigint, sold_at date, amount double);"
ONE_ROW = QueryResult((("n", "BIGINT"),), ((3,),), 1, False)
EMPTY = QueryResult((("n", "BIGINT"),), (), 0, False)
BARS = QueryResult((("city", "VARCHAR"), ("n", "BIGINT")), (("Recife", 2),), 1, False)


def build(outputs, results, language=Language.EN, pruned=False, reject=None, detector=None):
    catalog = FakeCatalog(sample_schema(), DDL, ("sales", "customers", "amount"), pruned=pruned)
    llm = FakeTextToSql(outputs)
    runner = FakeRunner(results, reject=reject)
    history = FakeHistory()
    translator = FakeTranslator(
        {"quantas vendas": "how many sales", "quantas XQ1 por XQ2": "how many XQ1 per XQ2"}
    )
    detector = detector or FakeDetector(language)
    ask = AskQuestion(detector, translator, catalog, llm, runner, history)
    return ask, llm, runner, history, catalog, translator


def test_english_question_runs_once_and_records_history():
    ask, llm, runner, history, _, translator = build(["SELECT count(*) AS n FROM sales"], [ONE_ROW])
    tokens = []
    answer = ask("s1", "how many sales", on_token=tokens.append)
    assert answer.status is QueryStatus.OK
    assert answer.result is ONE_ROW
    assert answer.chart.kind is ChartKind.METRIC
    assert answer.question.translated_text == "how many sales"
    assert translator.protected_seen == []
    assert tokens == ["SELECT", "count(*)", "AS", "n", "FROM", "sales"]
    assert history.list("s1")[0].sql == "SELECT count(*) AS n FROM sales"
    assert history.list("s1")[0].status is QueryStatus.OK


def test_portuguese_question_is_translated_with_identifiers_protected():
    ask, llm, *_, translator = build(["SELECT 1"], [ONE_ROW], language=Language.PT)
    answer = ask("s1", "quantas vendas")
    assert answer.question.language is Language.PT
    assert answer.question.translated_text == "how many sales"
    assert llm.calls[0].question == "how many sales"
    assert translator.protected_seen == [("sales", "customers", "amount")]


def test_detection_and_translation_see_the_masked_question_and_mask_once():
    detector = FakeDetector(Language.PT)
    ask, llm, *_, translator = build(["SELECT 1"], [ONE_ROW], detector=detector)
    answer = ask("s1", "quantas sales por customers")
    assert detector.seen == ["quantas XQ1 por XQ2"]
    assert translator.texts_seen == ["quantas XQ1 por XQ2"]
    assert answer.question.translated_text == "how many sales per customers"
    assert llm.calls[0].question == "how many sales per customers"


def test_duckdb_error_retries_twice_with_error_in_previous():
    ask, llm, runner, history, *_ = build(
        ["SELECT bad FROM sales", "SELECT worse FROM sales", "SELECT count(*) AS n FROM sales"],
        [QueryFailed("no such column bad"), QueryFailed("no such column worse"), ONE_ROW],
    )
    answer = ask("s1", "how many sales")
    assert answer.status is QueryStatus.OK
    assert answer.sql.attempt == 3
    assert [c.previous[-1].error if c.previous else None for c in llm.calls] == [
        None,
        "no such column bad",
        "no such column worse",
    ]


def test_gives_up_after_two_error_retries():
    ask, *_, history, _, _ = build(
        ["SELECT a", "SELECT b", "SELECT c"],
        [QueryFailed("e1"), QueryFailed("e2"), QueryFailed("e3")],
    )
    answer = ask("s1", "q")
    assert answer.status is QueryStatus.ERROR
    assert answer.error == "e3"
    assert answer.result is None
    assert answer.sql.text == "SELECT c"
    assert history.list("s1")[0].status is QueryStatus.ERROR


def test_empty_result_retries_once_with_hint():
    ask, llm, *_ = build(["SELECT 1", "SELECT 2"], [EMPTY, BARS])
    answer = ask("s1", "q")
    assert answer.status is QueryStatus.OK
    assert answer.chart.kind is ChartKind.BAR
    assert "0 rows" in llm.calls[1].previous[0].error


def test_empty_twice_returns_empty_status():
    ask, *_ = build(["SELECT 1", "SELECT 2"], [EMPTY, EMPTY])
    answer = ask("s1", "q")
    assert answer.status is QueryStatus.EMPTY
    assert answer.result is EMPTY


def test_missing_table_on_pruned_schema_retries_with_full_schema():
    ask, llm, runner, history, catalog, _ = build(
        ["SELECT * FROM products", "SELECT 1"],
        [QueryFailed("Table with name products does not exist"), ONE_ROW],
        pruned=True,
    )
    ask("s1", "q")
    assert catalog.render_calls == ["q", None]


def test_rejected_sql_counts_as_error_and_reports_rejected():
    ask, *_ = build(
        ["DROP TABLE sales", "DELETE FROM sales", "UPDATE sales SET id=1"],
        [],
        reject=SqlRejected("only read statements are allowed"),
    )
    answer = ask("s1", "q")
    assert answer.status is QueryStatus.REJECTED
    assert answer.error == "only read statements are allowed"


def test_new_attempt_sends_newline_token_first():
    ask, *_ = build(["SELECT a", "SELECT b"], [QueryFailed("x"), ONE_ROW])
    tokens = []
    ask("s1", "q", on_token=tokens.append)
    assert tokens == ["SELECT", "a", "\n", "SELECT", "b"]


def test_timings_are_filled():
    ask, *_ = build(["SELECT 1"], [ONE_ROW])
    answer = ask("s1", "q")
    d = answer.timings.as_dict()
    assert d["prefill_ms"] == 12.0
    assert all(v >= 0 for v in d.values())
