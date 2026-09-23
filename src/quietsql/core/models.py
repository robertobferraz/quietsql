from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum


class Language(StrEnum):
    PT = "pt"
    EN = "en"


class SourceKind(StrEnum):
    UPLOAD = "upload"
    FILE = "file"
    FOLDER = "folder"


class ChartKind(StrEnum):
    TABLE = "table"
    BAR = "bar"
    LINE = "line"
    METRIC = "metric"


class SqlOrigin(StrEnum):
    MODEL = "model"
    MANUAL = "manual"


class QueryStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Question:
    text: str
    language: Language
    translated_text: str


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: SourceKind
    path: str
    table_count: int
    loaded_at: datetime


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    examples: tuple[str, ...] = ()
    is_primary_key: bool = False


@dataclass(frozen=True)
class ForeignKey:
    table: str
    column: str
    referenced_table: str
    referenced_column: str


@dataclass(frozen=True)
class TableInfo:
    name: str
    row_count: int
    columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class Schema:
    tables: tuple[TableInfo, ...]
    foreign_keys: tuple[ForeignKey, ...] = ()


@dataclass(frozen=True)
class RenderedSchema:
    ddl: str
    table_names: tuple[str, ...]
    pruned: bool


@dataclass(frozen=True)
class Attempt:
    sql: str
    error: str


@dataclass(frozen=True)
class SqlDraft:
    text: str
    origin: SqlOrigin
    attempt: int


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple, ...]
    total_rows: int
    truncated: bool


@dataclass(frozen=True)
class ChartSpec:
    kind: ChartKind
    x: str | None
    y: str | None


@dataclass
class StageTimings:
    detect_ms: float = 0.0
    translate_ms: float = 0.0
    prefill_ms: float = 0.0
    generate_ms: float = 0.0
    transpile_ms: float = 0.0
    run_ms: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    asked_at: datetime
    question: str
    translated_text: str
    sql: str
    status: QueryStatus
    timings: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    question: Question
    sql: SqlDraft
    result: QueryResult | None
    chart: ChartSpec
    timings: StageTimings
    status: QueryStatus
    error: str | None = None
