from quietsql.core.models import ChartKind, ChartSpec, QueryResult

NUMERIC_PREFIXES = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "UHUGEINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "REAL",
)
TEMPORAL_PREFIXES = ("DATE", "TIMESTAMP", "TIME")


def is_numeric(data_type: str) -> bool:
    return data_type.upper().startswith(NUMERIC_PREFIXES)


def is_temporal(data_type: str) -> bool:
    return data_type.upper().startswith(TEMPORAL_PREFIXES)


def choose_chart(result: QueryResult) -> ChartSpec:
    if not result.rows:
        return ChartSpec(ChartKind.TABLE, None, None)
    numeric = [c for c, t in result.columns if is_numeric(t)]
    other = [(c, t) for c, t in result.columns if not is_numeric(t)]
    if len(result.columns) == 1 and len(numeric) == 1 and len(result.rows) == 1:
        return ChartSpec(ChartKind.METRIC, None, numeric[0])
    if len(numeric) == 1 and len(other) == 1:
        x, x_type = other[0]
        kind = ChartKind.LINE if is_temporal(x_type) else ChartKind.BAR
        return ChartSpec(kind, x, numeric[0])
    return ChartSpec(ChartKind.TABLE, None, None)
