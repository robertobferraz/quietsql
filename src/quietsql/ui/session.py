from dataclasses import dataclass, field

from quietsql.core.models import Answer, ChartKind


@dataclass
class SessionState:
    active_source_id: str | None = None
    question: str = ""
    sql: str = ""
    answer: Answer | None = None
    chart_kind: ChartKind = ChartKind.TABLE
    generating: bool = False
    cancel_requested: bool = False
    pending_tokens: list[str] = field(default_factory=list)
