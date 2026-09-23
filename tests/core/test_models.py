from datetime import datetime

from quietsql.core.errors import QueryFailed, QueryTimeout, QuietsqlError, SqlRejected
from quietsql.core.models import (
    ChartKind,
    ChartSpec,
    ColumnInfo,
    Language,
    QueryResult,
    Question,
    Source,
    SourceKind,
    StageTimings,
    TableInfo,
)


def test_question_is_immutable():
    q = Question(text="quantas vendas", language=Language.PT, translated_text="how many sales")
    try:
        q.text = "x"
    except AttributeError:
        return
    raise AssertionError("Question must be frozen")


def test_stage_timings_as_dict_has_every_stage():
    t = StageTimings()
    t.generate_ms = 2900.0
    assert t.as_dict() == {
        "detect_ms": 0.0,
        "translate_ms": 0.0,
        "prefill_ms": 0.0,
        "generate_ms": 2900.0,
        "transpile_ms": 0.0,
        "run_ms": 0.0,
    }


def test_enums_are_strings():
    assert Language.PT == "pt"
    assert SourceKind.FOLDER == "folder"
    assert ChartKind.METRIC == "metric"


def test_table_info_holds_columns():
    t = TableInfo(name="sales", row_count=3, columns=(ColumnInfo("id", "BIGINT"),))
    assert t.columns[0].examples == ()
    assert t.columns[0].is_primary_key is False


def test_query_result_and_chart_spec():
    r = QueryResult(columns=(("n", "BIGINT"),), rows=((1,),), total_rows=1, truncated=False)
    c = ChartSpec(kind=ChartKind.METRIC, x=None, y="n")
    assert r.rows[0][0] == 1 and c.y == "n"


def test_source_fields():
    s = Source(
        "abc", "sales.duckdb", SourceKind.FILE, "/tmp/sales.duckdb", 3, datetime(2026, 9, 18)
    )
    assert s.kind is SourceKind.FILE


def test_error_hierarchy():
    assert issubclass(SqlRejected, QuietsqlError)
    assert issubclass(QueryTimeout, QueryFailed)
    assert str(SqlRejected("only SELECT allowed")) == "only SELECT allowed"
