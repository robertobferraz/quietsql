from quietsql.adapters.duckdb.pruning import select_tables
from quietsql.core.models import ColumnInfo, ForeignKey, Schema, TableInfo


def table(name, *cols):
    return TableInfo(name, 10, tuple(ColumnInfo(c, "VARCHAR", ex) for c, ex in cols))


SCHEMA = Schema(
    (
        table("sales", ("id", ()), ("customer_id", ()), ("amount", ())),
        table("customers", ("id", ()), ("city", ("Recife", "Olinda"))),
        table("products", ("id", ()), ("title", ())),
        table("audit_log", ("id", ()), ("message", ())),
    ),
    (ForeignKey("sales", "customer_id", "customers", "id"),),
)


def test_selects_named_table_and_fk_neighbours():
    assert select_tables(SCHEMA, "total sales amount", 10_000) == ("sales", "customers")


def test_matches_singular_and_example_values():
    assert select_tables(SCHEMA, "which product sells most in Recife", 10_000) == (
        "products",
        "customers",
        "sales",
    )


def test_nothing_matches_returns_none():
    assert select_tables(SCHEMA, "hello there", 10_000) is None


def test_budget_drops_lowest_scores_but_keeps_top():
    chosen = select_tables(SCHEMA, "sales customers products", 20)
    assert chosen == ("sales",)
