from quietsql.app.chart import choose_chart, is_numeric, is_temporal
from quietsql.core.models import ChartKind, QueryResult


def result(columns, rows):
    return QueryResult(tuple(columns), tuple(rows), len(rows), False)


def test_single_number_is_metric():
    c = choose_chart(result([("total", "DOUBLE")], [(10.5,)]))
    assert c.kind is ChartKind.METRIC and c.y == "total" and c.x is None


def test_category_and_number_is_bar():
    c = choose_chart(result([("city", "VARCHAR"), ("n", "BIGINT")], [("Recife", 3), ("Olinda", 1)]))
    assert c.kind is ChartKind.BAR and c.x == "city" and c.y == "n"


def test_date_and_number_is_line():
    c = choose_chart(result([("day", "DATE"), ("n", "BIGINT")], [("2026-03-01", 3)]))
    assert c.kind is ChartKind.LINE and c.x == "day"


def test_number_first_still_bar():
    c = choose_chart(result([("n", "BIGINT"), ("city", "VARCHAR")], [(3, "Recife"), (1, "Olinda")]))
    assert c.kind is ChartKind.BAR and c.x == "city" and c.y == "n"


def test_three_columns_is_table():
    c = choose_chart(result([("a", "VARCHAR"), ("b", "BIGINT"), ("c", "BIGINT")], [("x", 1, 2)]))
    assert c.kind is ChartKind.TABLE


def test_empty_result_is_table():
    assert choose_chart(result([("n", "BIGINT")], [])).kind is ChartKind.TABLE


def test_type_predicates():
    assert is_numeric("DECIMAL(18,3)") and is_numeric("HUGEINT") and not is_numeric("VARCHAR")
    assert is_temporal("TIMESTAMP WITH TIME ZONE") and not is_temporal("BIGINT")
