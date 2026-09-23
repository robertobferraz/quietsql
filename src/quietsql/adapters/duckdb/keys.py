import duckdb

from quietsql.adapters.duckdb.naming import singular
from quietsql.adapters.duckdb.render import quote
from quietsql.core.models import ForeignKey, TableInfo

INT_FAMILY = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
)
NUMERIC_FAMILY = INT_FAMILY + (
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "REAL",
)


def _family(dtype: str) -> str:
    return "int" if dtype.upper().startswith(INT_FAMILY) else "text"


def _pk_candidates(con, table: TableInfo) -> list[tuple[str, str]]:
    preferred = ("id", f"{table.name}_id", f"{singular(table.name)}_id")
    found = []
    for col in table.columns:
        if col.name not in preferred:
            continue
        if col.is_primary_key:
            found.append((col.name, col.data_type))
            continue
        if table.row_count == 0:
            continue
        total, distinct, nulls = con.execute(
            f"SELECT count(*), count(DISTINCT {quote(col.name)}), "
            f"count(*) - count({quote(col.name)}) FROM {quote(table.name)}"
        ).fetchone()
        if total > 0 and distinct == total and nulls == 0:
            found.append((col.name, col.data_type))
    return found


def _referenced_table(column: str, tables: dict[str, TableInfo]) -> str | None:
    base = None
    if column.endswith("_id"):
        base = column[:-3]
    elif column.startswith("id_"):
        base = column[3:]
    elif column in tables or column + "s" in tables:
        base = column
    if base is None:
        return None
    for candidate in (base, base + "s", base + "es"):
        if candidate in tables:
            return candidate
    for name in tables:
        if name.startswith(base + "_"):
            return name
    return None


def infer_foreign_keys(
    con: duckdb.DuckDBPyConnection,
    tables: tuple[TableInfo, ...],
    sample: int = 2000,
    min_containment: float = 0.95,
) -> tuple[ForeignKey, ...]:
    by_name = {t.name: t for t in tables}
    pks: dict[str, list[tuple[str, str]]] = {}

    def candidates(name: str) -> list[tuple[str, str]]:
        if name not in pks:
            pks[name] = _pk_candidates(con, by_name[name])
        return pks[name]

    found: list[ForeignKey] = []
    for table in tables:
        for col in table.columns:
            ref = _referenced_table(col.name, by_name)
            if ref is None or ref == table.name:
                continue
            for pk_col, pk_type in candidates(ref):
                if _family(pk_type) != _family(col.data_type):
                    continue
                matched = f"WHERE fk IN (SELECT {quote(pk_col)} FROM {quote(ref)})"
                sampled = (
                    f"(SELECT {quote(col.name)} FROM {quote(table.name)} "
                    f"USING SAMPLE {sample} ROWS)"
                )
                distinct_fks = (
                    f"(SELECT DISTINCT {quote(col.name)} AS fk FROM {sampled} "
                    f"WHERE {quote(col.name)} IS NOT NULL)"
                )
                row = con.execute(
                    f"SELECT count(*) FILTER ({matched}) * 1.0 / count(*) FROM {distinct_fks}"
                ).fetchone()
                ratio = row[0] if row and row[0] is not None else 0.0
                if ratio >= min_containment:
                    found.append(ForeignKey(table.name, col.name, ref, pk_col))
                    break
    return tuple(found)
