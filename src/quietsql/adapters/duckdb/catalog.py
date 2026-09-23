import threading
from collections.abc import Callable

import duckdb

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.history import USER_TABLES
from quietsql.adapters.duckdb.keys import NUMERIC_FAMILY
from quietsql.adapters.duckdb.render import approx_tokens, quote, render_ddl
from quietsql.core.models import ColumnInfo, ForeignKey, RenderedSchema, Schema, TableInfo

PII_PATTERNS = (
    "email",
    "e_mail",
    "phone",
    "telefone",
    "celular",
    "cpf",
    "cnpj",
    "password",
    "senha",
    "ssn",
    "rg",
)
MAX_EXAMPLES = 3
MAX_EXAMPLE_LEN = 40
FULL_DOMAIN_MAX = 10
FREE_TEXT_AVG_LEN = 40
KeyInference = Callable[[duckdb.DuckDBPyConnection, tuple[TableInfo, ...]], tuple[ForeignKey, ...]]
TableSelector = Callable[[Schema, str, int], tuple[str, ...] | None]


def is_pii(name: str) -> bool:
    lowered = name.lower()
    return any(
        p == lowered or lowered.startswith(p + "_") or lowered.endswith("_" + p)
        for p in PII_PATTERNS
    )


class DuckDbCatalog:
    def __init__(
        self,
        pool: ConnectionPool,
        budget_tokens: int = 1000,
        infer_keys: KeyInference = lambda con, tables: (),
        select: TableSelector = lambda schema, question, budget: None,
    ) -> None:
        self.pool = pool
        self.budget_tokens = budget_tokens
        self.infer_keys = infer_keys
        self.select = select
        self._lock = threading.Lock()
        self._cache: dict[str, Schema] = {}
        self._generations: dict[str, int] = {}

    def schema(self, source_id: str) -> Schema:
        with self._lock:
            cached = self._cache.get(source_id)
            if cached is not None:
                return cached
            generation = self._generations.get(source_id, 0)
        extracted = self._extract(source_id)
        with self._lock:
            if self._generations.get(source_id, 0) == generation:
                self._cache[source_id] = extracted
                return extracted
            return self._cache.get(source_id, extracted)

    def invalidate(self, source_id: str) -> None:
        with self._lock:
            self._cache.pop(source_id, None)
            self._generations[source_id] = self._generations.get(source_id, 0) + 1

    def identifiers(self, source_id: str) -> tuple[str, ...]:
        schema = self.schema(source_id)
        names = {t.name for t in schema.tables} | {c.name for t in schema.tables for c in t.columns}
        return tuple(sorted(names))

    def render(self, schema: Schema, question: str | None) -> RenderedSchema:
        full = render_ddl(schema)
        names = tuple(t.name for t in schema.tables)
        if question is None or approx_tokens(full) <= self.budget_tokens:
            return RenderedSchema(full, names, False)
        chosen = self.select(schema, question, self.budget_tokens)
        if not chosen:
            return RenderedSchema(full, names, False)
        return RenderedSchema(render_ddl(schema, chosen), tuple(chosen), True)

    def _extract(self, source_id: str) -> Schema:
        con = self.pool.writable(source_id).cursor()
        try:
            table_rows = con.execute(
                f"SELECT table_name FROM duckdb_tables() WHERE {USER_TABLES} ORDER BY table_name"
            ).fetchall()
            pks, fks = self._constraints(con)
            tables = []
            for (name,) in table_rows:
                count = con.execute(f"SELECT count(*) FROM {quote(name)}").fetchone()[0]
                stats = self._summarize(con, name)
                columns = con.execute(
                    "SELECT column_name, data_type FROM duckdb_columns() "
                    "WHERE table_name = ? ORDER BY column_index",
                    [name],
                ).fetchall()
                infos = tuple(
                    ColumnInfo(
                        col,
                        dtype,
                        self._examples(
                            con, name, col, dtype, stats.get(col, {}), (name, col) in pks
                        ),
                        (name, col) in pks,
                    )
                    for col, dtype in columns
                )
                tables.append(TableInfo(name, int(count), infos))
            declared = tuple(fks)
            inferred = tuple(self.infer_keys(con, tuple(tables)))
            known = {(fk.table, fk.column) for fk in declared}
            extra = tuple(fk for fk in inferred if (fk.table, fk.column) not in known)
            return Schema(tuple(tables), declared + extra)
        finally:
            con.close()

    @staticmethod
    def _constraints(con) -> tuple[set[tuple[str, str]], list[ForeignKey]]:
        rows = con.execute(
            "SELECT table_name, constraint_type, constraint_column_names, "
            "referenced_table, referenced_column_names FROM duckdb_constraints() "
            "WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')"
        ).fetchall()
        pks: set[tuple[str, str]] = set()
        fks: list[ForeignKey] = []
        for table, kind, cols, ref_table, ref_cols in rows:
            if kind == "PRIMARY KEY":
                pks.update((table, c) for c in cols)
            elif ref_table and ref_cols:
                fks.extend(
                    ForeignKey(table, c, ref_table, r) for c, r in zip(cols, ref_cols, strict=False)
                )
        return pks, fks

    @staticmethod
    def _summarize(con, table: str) -> dict[str, dict]:
        rows = con.execute(f"SUMMARIZE {quote(table)}").fetchall()
        description = [d[0] for d in con.description]
        out = {}
        for row in rows:
            record = dict(zip(description, row, strict=True))
            out[record["column_name"]] = record
        return out

    def _examples(self, con, table, column, dtype, stats, is_pk) -> tuple[str, ...]:
        if is_pk or is_pii(column) or not stats:
            return ()
        upper = dtype.upper()
        count = int(stats.get("count") or 0)
        distinct = int(stats.get("approx_unique") or 0)
        if count == 0:
            return ()
        if upper.startswith(NUMERIC_FAMILY):
            if distinct >= count:
                return ()
            return (f"{stats['min']}..{stats['max']}",)
        if distinct <= FULL_DOMAIN_MAX:
            limit = FULL_DOMAIN_MAX
        else:
            if distinct >= 0.9 * count:
                return ()
            if upper.startswith("VARCHAR") or upper.startswith("TEXT"):
                avg_len = con.execute(
                    f"SELECT avg(length({quote(column)})) FROM {quote(table)}"
                ).fetchone()[0]
                if avg_len and avg_len > FREE_TEXT_AVG_LEN:
                    return ()
            limit = MAX_EXAMPLES
        rows = con.execute(
            f"SELECT DISTINCT {quote(column)} FROM {quote(table)} "
            f"WHERE {quote(column)} IS NOT NULL ORDER BY 1 LIMIT {limit}"
        ).fetchall()
        return tuple(str(r[0])[:MAX_EXAMPLE_LEN] for r in rows)
