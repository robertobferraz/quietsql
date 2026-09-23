from quietsql.adapters.llm.extract import extract_sql


def test_plain_sql_passthrough():
    assert extract_sql("SELECT count(*) FROM sales") == "SELECT count(*) FROM sales"


def test_strips_fences_and_prose():
    raw = "SELECT 1\n```\nThis query counts rows."
    assert extract_sql(raw) == "SELECT 1"
    assert extract_sql("```sql\nSELECT 2\n```") == "SELECT 2"


def test_keeps_first_statement_only():
    assert extract_sql("SELECT 1;\nSELECT 2") == "SELECT 1"


def test_duplicate_select_from_prefill_is_collapsed():
    assert extract_sql("SELECT SELECT id FROM t") == "SELECT id FROM t"
    raw = "SELECT  \n  WITH x AS (SELECT 1) SELECT * FROM x"
    assert extract_sql(raw) == "WITH x AS (SELECT 1) SELECT * FROM x"
