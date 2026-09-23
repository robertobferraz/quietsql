import json
import threading
from datetime import datetime

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.render import quote
from quietsql.core.models import HistoryEntry, QueryStatus, Question

TABLE = "_quietsql_history"
SEQUENCE = "_quietsql_history_id"
CREATE_SEQUENCE = f"CREATE SEQUENCE IF NOT EXISTS {quote(SEQUENCE)} START 1"
CREATE_TABLE = (
    f"CREATE TABLE IF NOT EXISTS {quote(TABLE)}("
    "id BIGINT, asked_at TIMESTAMP, question VARCHAR, translated VARCHAR, "
    "sql VARCHAR, status VARCHAR, timings JSON)"
)
INSERT = f"INSERT INTO {quote(TABLE)} VALUES (nextval('{SEQUENCE}'), ?, ?, ?, ?, ?, ?) RETURNING id"
USER_TABLES = f"NOT internal AND table_name <> '{TABLE}'"
SELECT = (
    "SELECT id, asked_at, question, translated, sql, status, timings "
    f"FROM {quote(TABLE)} ORDER BY id DESC LIMIT ?"
)


class DuckDbHistory:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool
        self._schema_lock = threading.Lock()

    def append(
        self,
        source_id: str,
        question: Question,
        sql: str,
        status: QueryStatus,
        timings: dict[str, float],
    ) -> HistoryEntry:
        asked_at = datetime.now()
        con = self._prepared(source_id)
        try:
            entry_id = con.execute(
                INSERT,
                [
                    asked_at,
                    question.text,
                    question.translated_text,
                    sql,
                    status.value,
                    json.dumps(timings),
                ],
            ).fetchone()[0]
        finally:
            con.close()
        return HistoryEntry(
            int(entry_id),
            asked_at,
            question.text,
            question.translated_text,
            sql,
            status,
            dict(timings),
        )

    def list(self, source_id: str, limit: int = 50) -> tuple[HistoryEntry, ...]:
        con = self._prepared(source_id)
        try:
            rows = con.execute(SELECT, [limit]).fetchall()
        finally:
            con.close()
        return tuple(
            HistoryEntry(int(i), a, q, t, s, QueryStatus(st), json.loads(tm or "{}"))
            for i, a, q, t, s, st, tm in rows
        )

    def _prepared(self, source_id: str):
        con = self.pool.writable(source_id).cursor()
        with self._schema_lock:
            con.execute(CREATE_SEQUENCE)
            con.execute(CREATE_TABLE)
        return con
