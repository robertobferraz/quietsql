from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from quietsql.core.models import (
    Attempt,
    ColumnInfo,
    ForeignKey,
    HistoryEntry,
    Language,
    QueryResult,
    QueryStatus,
    Question,
    RenderedSchema,
    Schema,
    Source,
    SourceKind,
    TableInfo,
)


def sample_schema() -> Schema:
    sales = TableInfo(
        "sales",
        48213,
        (
            ColumnInfo("id", "BIGINT", is_primary_key=True),
            ColumnInfo("customer_id", "BIGINT"),
            ColumnInfo("sold_at", "DATE", ("2026-03-01", "2026-03-02", "2026-03-03")),
            ColumnInfo("amount", "DOUBLE", ("1.5..980.0",)),
        ),
    )
    customers = TableInfo(
        "customers",
        900,
        (
            ColumnInfo("id", "BIGINT", is_primary_key=True),
            ColumnInfo("name", "VARCHAR", ("Ana", "Bruno", "Carla")),
            ColumnInfo("city", "VARCHAR", ("Recife", "Olinda")),
        ),
    )
    return Schema((sales, customers), (ForeignKey("sales", "customer_id", "customers", "id"),))


@dataclass
class GenerateCall:
    schema_ddl: str
    question: str
    previous: list[Attempt]


class FakeTextToSql:
    def __init__(self, outputs: list[str], prefill: float = 12.0):
        self.outputs = list(outputs)
        self.calls: list[GenerateCall] = []
        self._prefill = prefill

    def generate(
        self,
        schema_ddl: str,
        question: str,
        previous: Sequence[Attempt],
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        self.calls.append(GenerateCall(schema_ddl, question, list(previous)))
        out = self.outputs.pop(0)
        if on_token:
            for tok in out.split():
                on_token(tok)
        return out

    def prefill_ms(self) -> float:
        return self._prefill


class FakeDetector:
    def __init__(self, language: Language):
        self.language = language
        self.seen: list[str] = []

    def detect(self, text: str) -> Language:
        self.seen.append(text)
        return self.language


class FakeTranslator:
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping
        self.protected_seen: list[tuple[str, ...]] = []
        self.texts_seen: list[str] = []

    def translate(self, text: str, protected: Sequence[str]) -> str:
        self.protected_seen.append(tuple(protected))
        self.texts_seen.append(text)
        return self.mapping.get(text, text)


class FakeCatalog:
    def __init__(
        self,
        schema: Schema,
        ddl: str,
        identifiers: tuple[str, ...],
        pruned: bool = False,
    ):
        self._schema = schema
        self._ddl = ddl
        self._identifiers = identifiers
        self._pruned = pruned
        self.render_calls: list[str | None] = []
        self.invalidated: list[str] = []

    def schema(self, source_id: str) -> Schema:
        return self._schema

    def render(self, schema: Schema, question: str | None) -> RenderedSchema:
        self.render_calls.append(question)
        pruned = self._pruned and question is not None
        return RenderedSchema(self._ddl, tuple(t.name for t in schema.tables), pruned)

    def identifiers(self, source_id: str) -> tuple[str, ...]:
        return self._identifiers

    def invalidate(self, source_id: str) -> None:
        self.invalidated.append(source_id)


class FakeRunner:
    def __init__(self, results: list[QueryResult | Exception], reject: Exception | None = None):
        self.results = list(results)
        self.reject = reject
        self.validated: list[str] = []
        self.ran: list[str] = []

    def validate(self, sql: str) -> str:
        self.validated.append(sql)
        if self.reject:
            raise self.reject
        return sql.strip().rstrip(";")

    def run(self, source_id: str, sql: str, row_limit: int) -> QueryResult:
        self.ran.append(sql)
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeHistory:
    def __init__(self):
        self.entries: dict[str, list[HistoryEntry]] = {}

    def append(
        self,
        source_id: str,
        question: Question,
        sql: str,
        status: QueryStatus,
        timings: dict[str, float],
    ) -> HistoryEntry:
        bucket = self.entries.setdefault(source_id, [])
        entry = HistoryEntry(
            len(bucket) + 1,
            datetime(2026, 9, 18, 12, 0, len(bucket)),
            question.text,
            question.translated_text,
            sql,
            status,
            dict(timings),
        )
        bucket.append(entry)
        return entry

    def list(self, source_id: str, limit: int = 50) -> tuple[HistoryEntry, ...]:
        return tuple(reversed(self.entries.get(source_id, [])))[:limit]


@dataclass
class FakeLoader:
    sources: list[Source] = field(default_factory=list)
    reloaded: list[str] = field(default_factory=list)

    def _add(self, name: str, kind: SourceKind, path: str, tables: int) -> Source:
        s = Source(f"src{len(self.sources) + 1}", name, kind, path, tables, datetime(2026, 9, 18))
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


class FakeModelStatus:
    def __init__(self, ready: bool = True):
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    def model_id(self) -> str:
        return "fake-model"
