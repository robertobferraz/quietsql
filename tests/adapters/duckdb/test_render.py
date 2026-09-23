from quietsql.adapters.duckdb.render import approx_tokens, quote, render_ddl
from quietsql.core.models import ColumnInfo, ForeignKey, Schema, TableInfo


def test_render_ddl_normalized_with_keys_and_examples():
    schema = Schema(
        (
            TableInfo(
                "sales",
                10,
                (
                    ColumnInfo("id", "BIGINT", is_primary_key=True),
                    ColumnInfo("customer_id", "BIGINT"),
                    ColumnInfo("amount", "DOUBLE", ("1.5..980.0",)),
                    ColumnInfo("status", "VARCHAR", ("paid", "open")),
                ),
            ),
            TableInfo("customers", 3, (ColumnInfo("id", "BIGINT", is_primary_key=True),)),
        ),
        (ForeignKey("sales", "customer_id", "customers", "id"),),
    )
    assert render_ddl(schema) == (
        "create table sales (\n"
        "  id bigint primary key,\n"
        "  customer_id bigint references customers(id),\n"
        "  amount double, -- 1.5..980.0\n"
        "  status varchar -- paid, open\n"
        ");\n"
        "create table customers (\n"
        "  id bigint primary key\n"
        ");"
    )


def test_render_ddl_subset_keeps_order():
    schema = Schema(
        (
            TableInfo("a", 1, (ColumnInfo("x", "INTEGER"),)),
            TableInfo("b", 1, (ColumnInfo("y", "INTEGER"),)),
        )
    )
    assert render_ddl(schema, tables=["b"]) == "create table b (\n  y integer\n);"


def test_render_quotes_identifiers_that_need_it():
    schema = Schema((TableInfo("my table", 1, (ColumnInfo("Total Amount", "DOUBLE"),)),))
    assert render_ddl(schema) == 'create table "my table" (\n  "Total Amount" double\n);'


def test_approx_tokens():
    assert approx_tokens("") == 1 and approx_tokens("x" * 400) == 101


def test_quote_protects_reserved_words():
    assert quote("order") == '"order"'
    assert quote("group") == '"group"'
    assert quote("select") == '"select"'
    assert quote("end") == '"end"'
    assert quote("binary") == '"binary"'
    assert quote("customers") == "customers"
    assert quote("customer_id") == "customer_id"


def test_render_ddl_quotes_reserved_table_and_column():
    schema = Schema((TableInfo("order", 1, (ColumnInfo("group", "VARCHAR"),)),))
    assert render_ddl(schema) == 'create table "order" (\n  "group" varchar\n);'
