from quietsql.core.models import HistoryEntry
from quietsql.ports import HistoryStore


class ListHistory:
    def __init__(self, history: HistoryStore) -> None:
        self.history = history

    def __call__(self, source_id: str, limit: int = 50) -> tuple[HistoryEntry, ...]:
        return self.history.list(source_id, limit)
