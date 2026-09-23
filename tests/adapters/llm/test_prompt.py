from quietsql.adapters.llm.prompt import SYSTEM, build_prompt
from quietsql.core.models import Attempt


def test_prompt_is_chatml_with_prefilled_select():
    p = build_prompt("create table sales (id bigint);", "how many sales", [])
    assert p.startswith("<|im_start|>system\n" + SYSTEM)
    expected_user = (
        "<|im_start|>user\n-- schema\ncreate table sales (id bigint);\n\n"
        "-- question\nhow many sales"
    )
    assert expected_user in p
    assert p.endswith("<|im_start|>assistant\nSELECT")


def test_prompt_includes_previous_attempts_truncated():
    p = build_prompt("ddl", "q", [Attempt("SELECT bad", "x" * 500)])
    expected = (
        "-- your previous SQL\nSELECT bad\n-- duckdb error\n" + "x" * 300 + "\n-- fix the query"
    )
    assert expected in p
    assert "x" * 301 not in p


def test_schema_comes_before_question_for_prefix_caching():
    a = build_prompt("ddl", "question one", [])
    b = build_prompt("ddl", "question two", [])
    common = a[: a.index("-- question")]
    assert b.startswith(common)
