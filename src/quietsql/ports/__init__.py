from collections.abc import Callable, Sequence
from typing import Protocol

from quietsql.core.models import (
    Attempt,
    HistoryEntry,
    Language,
    QueryResult,
    QueryStatus,
    Question,
    RenderedSchema,
    Schema,
    Source,
)


class LanguageDetector(Protocol):
    def detect(self, text: str) -> Language: ...


class Translator(Protocol):
    def translate(self, text: str, protected: Sequence[str]) -> str: ...


class TextToSql(Protocol):
    def generate(
        self,
        schema_ddl: str,
        question: str,
        previous: Sequence[Attempt],
        on_token: Callable[[str], None] | None = None,
    ) -> str: ...

    def prefill_ms(self) -> float: ...


class Catalog(Protocol):
    def schema(self, source_id: str) -> Schema: ...

    def render(self, schema: Schema, question: str | None) -> RenderedSchema: ...

    def identifiers(self, source_id: str) -> tuple[str, ...]: ...

    def invalidate(self, source_id: str) -> None: ...


class QueryRunner(Protocol):
    def validate(self, sql: str) -> str: ...

    def run(self, source_id: str, sql: str, row_limit: int) -> QueryResult: ...


class HistoryStore(Protocol):
    def append(
        self,
        source_id: str,
        question: Question,
        sql: str,
        status: QueryStatus,
        timings: dict[str, float],
    ) -> HistoryEntry: ...

    def list(self, source_id: str, limit: int = 50) -> tuple[HistoryEntry, ...]: ...


class SourceLoader(Protocol):
    def load_upload(self, file_name: str, file_path: str) -> Source: ...

    def open_file(self, path: str) -> Source: ...

    def load_folder(self, path: str) -> Source: ...

    def reload(self, source_id: str) -> Source: ...

    def list(self) -> tuple[Source, ...]: ...

    def remove(self, source_id: str) -> None: ...


class ModelStatus(Protocol):
    def ready(self) -> bool: ...

    def model_id(self) -> str: ...
