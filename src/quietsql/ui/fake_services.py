import time
from collections.abc import Callable, Sequence
from datetime import datetime

from quietsql.app.ask_question import AskQuestion
from quietsql.app.history import ListHistory
from quietsql.app.run_sql import RunSql
from quietsql.app.services import Services
from quietsql.app.sources import SourceService
from quietsql.core.errors import QueryFailed, SqlRejected
from quietsql.core.models import (
    Attempt,
    ColumnInfo,
    ForeignKey,
    HistoryEntry,
    Language,
    QueryResult,
    RenderedSchema,
    Schema,
    Source,
    SourceKind,
    TableInfo,
)

SALES = TableInfo(
    "sales",
    48213,
    (
        ColumnInfo("id", "BIGINT", is_primary_key=True),
        ColumnInfo("customer_id", "BIGINT"),
        ColumnInfo("sold_at", "DATE", ("2026-03-01", "2026-03-02", "2026-03-03")),
        ColumnInfo("amount", "DOUBLE", ("1.5..980.0",)),
    ),
)
CUSTOMERS = TableInfo(
    "customers",
    900,
    (
        ColumnInfo("id", "BIGINT", is_primary_key=True),
        ColumnInfo("name", "VARCHAR", ("Ana", "Bruno", "Carla")),
        ColumnInfo("city", "VARCHAR", ("Recife", "Olinda", "Caruaru")),
    ),
)
PRODUCTS = TableInfo(
    "products",
    120,
    (ColumnInfo("id", "BIGINT", is_primary_key=True), ColumnInfo("name", "VARCHAR")),
)
SHIPMENTS = TableInfo(
    "shipments",
    15400,
    (
        ColumnInfo("id", "BIGINT", is_primary_key=True),
        ColumnInfo("order_id", "BIGINT"),
        ColumnInfo("shipped_at", "DATE", ("2026-03-05", "2026-03-10", "2026-03-15")),
        ColumnInfo("carrier", "VARCHAR", ("FedEx", "UPS", "DHL")),
        ColumnInfo("tracking", "VARCHAR"),
    ),
)
RETURNS = TableInfo(
    "returns",
    2100,
    (
        ColumnInfo("id", "BIGINT", is_primary_key=True),
        ColumnInfo("shipment_id", "BIGINT"),
        ColumnInfo("returned_at", "DATE", ("2026-03-08", "2026-03-12", "2026-03-18")),
        ColumnInfo("reason", "VARCHAR", ("Defective", "Not as described", "No longer needed")),
        ColumnInfo("status", "VARCHAR", ("pending", "approved", "rejected")),
    ),
)
SCHEMA = Schema(
    (SALES, CUSTOMERS, PRODUCTS),
    (ForeignKey("sales", "customer_id", "customers", "id"),),
)
DDL = (
    "create table sales (\n  id bigint primary key,\n"
    "  customer_id bigint references customers(id),\n"
    "  sold_at date, -- 2026-03-01, 2026-03-02\n  amount double -- 1.5..980.0\n);\n"
    "create table customers (\n  id bigint primary key,\n  name varchar, -- Ana, Bruno\n"
    "  city varchar -- Recife, Olinda\n);"
)

BY_CITY = QueryResult(
    (("city", "VARCHAR"), ("total", "DOUBLE")),
    (("Recife", 18230.5), ("Olinda", 9120.0), ("Caruaru", 4410.75)),
    3,
    False,
)
AVERAGE = QueryResult((("average_ticket", "DOUBLE"),), ((87.4,),), 1, False)
BY_DAY = QueryResult(
    (("day", "DATE"), ("sales", "BIGINT")),
    tuple((f"2026-03-{d:02d}", 40 + (d * 7) % 23) for d in range(1, 31)),
    30,
    False,
)
ALL_SALES = QueryResult(
    (("id", "BIGINT"), ("amount", "DOUBLE")),
    tuple((i, round(1.5 + (i % 979), 2)) for i in range(1, 10_001)),
    48213,
    True,
)


class KeywordTextToSql:
    def __init__(self, token_delay: float):
        self.token_delay = token_delay

    def generate(
        self,
        schema_ddl: str,
        question: str,
        previous: Sequence[Attempt],
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        q = question.lower()
        if "erro" in q or "error" in q:
            sql = f"SELECT missing_column FROM sales -- attempt {len(previous) + 1}"
        elif "ticket" in q or "average" in q or "médio" in q:
            sql = "SELECT avg(amount) AS average_ticket FROM sales"
        elif "dia" in q or "day" in q or "março" in q or "march" in q:
            sql = "SELECT sold_at AS day, count(*) AS sales FROM sales GROUP BY 1 ORDER BY 1"
        elif "tudo" in q or "everything" in q or "truncat" in q:
            sql = "SELECT id, amount FROM sales ORDER BY id"
        else:
            sql = (
                "SELECT c.city, sum(s.amount) AS total FROM sales s\n"
                "JOIN customers c ON c.id = s.customer_id\nGROUP BY 1 ORDER BY 2 DESC"
            )
        if on_token:
            for tok in sql.split(" "):
                on_token(tok + " ")
                time.sleep(self.token_delay)
        return sql

    def prefill_ms(self) -> float:
        return 310.0


class KeywordRunner:
    READ = ("select", "with", "describe", "summarize")

    def validate(self, sql: str) -> str:
        text = sql.strip().rstrip(";")
        if not text.lower().startswith(self.READ):
            raise SqlRejected("only SELECT, WITH, DESCRIBE and SUMMARIZE statements are allowed")
        return text

    def run(self, source_id: str, sql: str, row_limit: int) -> QueryResult:
        s = sql.lower()
        if "missing_column" in s:
            raise QueryFailed('Binder Error: Referenced column "missing_column" not found')
        if "average_ticket" in s:
            return AVERAGE
        if "as day" in s:
            return BY_DAY
        if "order by id" in s:
            return ALL_SALES
        if "city" in s:
            return BY_CITY
        return QueryResult((("value", "INTEGER"),), ((1,),), 1, False)


class MemoryHistory:
    def __init__(self):
        self.rows: dict[str, list[HistoryEntry]] = {}

    def append(self, source_id, question, sql, status, timings) -> HistoryEntry:
        bucket = self.rows.setdefault(source_id, [])
        entry = HistoryEntry(
            len(bucket) + 1,
            datetime.now(),
            question.text,
            question.translated_text,
            sql,
            status,
            dict(timings),
        )
        bucket.append(entry)
        return entry

    def list(self, source_id: str, limit: int = 50) -> tuple[HistoryEntry, ...]:
        return tuple(reversed(self.rows.get(source_id, [])))[:limit]


class StaticCatalog:
    def schema(self, source_id: str) -> Schema:
        return SCHEMA if source_id == "src1" else Schema((PRODUCTS, SHIPMENTS, RETURNS), ())

    def render(self, schema: Schema, question: str | None) -> RenderedSchema:
        return RenderedSchema(DDL, tuple(t.name for t in schema.tables), False)

    def identifiers(self, source_id: str) -> tuple[str, ...]:
        return tuple(c.name for t in SCHEMA.tables for c in t.columns) + tuple(
            t.name for t in SCHEMA.tables
        )

    def invalidate(self, source_id: str) -> None:
        return None


class MemoryLoader:
    def __init__(self, seed: bool = True):
        self.sources = (
            [
                Source(
                    "src1",
                    "sales.duckdb",
                    SourceKind.FILE,
                    "~/data/sales.duckdb",
                    3,
                    datetime.now(),
                ),
                Source("src2", "exports/", SourceKind.FOLDER, "~/data/exports", 3, datetime.now()),
            ]
            if seed
            else []
        )
        self.reloaded: list[str] = []

    def _add(self, name: str, kind: SourceKind, path: str, tables: int) -> Source:
        s = Source(f"src{len(self.sources) + 1}", name, kind, path, tables, datetime.now())
        self.sources.append(s)
        return s

    def load_upload(self, file_name: str, file_path: str) -> Source:
        return self._add(file_name, SourceKind.UPLOAD, file_path, 1)

    def open_file(self, path: str) -> Source:
        return self._add(path.rsplit("/", 1)[-1], SourceKind.FILE, path, 2)

    def load_folder(self, path: str) -> Source:
        return self._add(path.rstrip("/").rsplit("/", 1)[-1] + "/", SourceKind.FOLDER, path, 3)

    def reload(self, source_id: str) -> Source:
        self.reloaded.append(source_id)
        return next(s for s in self.sources if s.id == source_id)

    def list(self) -> tuple[Source, ...]:
        return tuple(self.sources)

    def remove(self, source_id: str) -> None:
        self.sources = [s for s in self.sources if s.id != source_id]


class PortugueseDetector:
    HINTS = ("quant", "qual", "por ", "média", "médio", "vendas", "cliente", "ção", "ã")

    def detect(self, text: str) -> Language:
        t = text.lower()
        return Language.PT if any(h in t for h in self.HINTS) else Language.EN


class EchoTranslator:
    def translate(self, text: str, protected: Sequence[str]) -> str:
        return text


class ReadyStatus:
    def __init__(self, ready: bool = True):
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    def model_id(self) -> str:
        return "XiYanSQL-QwenCoder-3B-2504 (mock)"


def build_fake_services(
    token_delay: float = 0.08, models_ready: bool = True, sources: bool = True
) -> Services:
    catalog = StaticCatalog()
    runner = KeywordRunner()
    history = MemoryHistory()
    ask = AskQuestion(
        PortugueseDetector(),
        EchoTranslator(),
        catalog,
        KeywordTextToSql(token_delay),
        runner,
        history,
    )
    return Services(
        ask=ask,
        run_sql=RunSql(runner, history),
        sources=SourceService(MemoryLoader(seed=sources), catalog),
        history=ListHistory(history),
        model_status=ReadyStatus(models_ready),
    )
