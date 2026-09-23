import contextlib
import threading

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.core.errors import QueryFailed, QueryTimeout, SqlRejected
from quietsql.core.models import QueryResult

READ_ROOTS = (exp.Select, exp.Union, exp.Describe)
READ_KEYWORDS = ("select", "with", "describe", "summarize")
REJECT_MESSAGE = "only SELECT, WITH, DESCRIBE and SUMMARIZE statements are allowed"


def _first_keyword(text: str) -> str:
    return text.split(None, 1)[0].lower()


class DuckDbRunner:
    def __init__(self, pool: ConnectionPool, timeout_s: float = 30.0) -> None:
        self.pool = pool
        self.timeout_s = timeout_s

    def validate(self, sql: str) -> str:
        text = sql.strip().rstrip(";").strip()
        if not text:
            raise SqlRejected("empty SQL")
        first = _first_keyword(text)
        if first not in READ_KEYWORDS:
            raise SqlRejected(REJECT_MESSAGE)
        if first == "summarize":
            if ";" in text:
                raise SqlRejected("one statement at a time")
            return text
        expressions = self._parse(text)
        if len(expressions) != 1:
            raise SqlRejected("one statement at a time")
        root = expressions[0]
        if not isinstance(root, READ_ROOTS):
            raise SqlRejected(REJECT_MESSAGE)
        return root.sql(dialect="duckdb", pretty=True)

    def _parse(self, text: str) -> list[exp.Expression]:
        try:
            return [e for e in sqlglot.parse(text, read="postgres") if e is not None]
        except ParseError:
            try:
                return [e for e in sqlglot.parse(text, read="duckdb") if e is not None]
            except ParseError as exc:
                raise SqlRejected(f"could not parse SQL: {exc}") from exc

    def run(self, source_id: str, sql: str, row_limit: int) -> QueryResult:
        text = sql.strip().rstrip(";").strip()
        if not text or _first_keyword(text) not in READ_KEYWORDS:
            raise QueryFailed(REJECT_MESSAGE)
        con = self.pool.read_only(source_id)
        try:
            timer = threading.Timer(self.timeout_s, con.interrupt)
            timer.start()
            try:
                con.execute("BEGIN TRANSACTION")
                types = self._types(con, text)
                cursor = con.execute(text)
                rows = cursor.fetchmany(row_limit + 1)
                names = [d[0] for d in cursor.description]
                truncated = len(rows) > row_limit
                rows = rows[:row_limit]
                total = len(rows)
                if truncated:
                    counted = con.execute(f"SELECT count(*) FROM ({text}) quietsql_count")
                    total = counted.fetchone()[0]
                columns = tuple((n, types.get(n, "UNKNOWN")) for n in names)
                return QueryResult(columns, tuple(tuple(r) for r in rows), int(total), truncated)
            except duckdb.InterruptException as exc:
                raise QueryTimeout(f"query exceeded {self.timeout_s:.0f} s") from exc
            except duckdb.Error as exc:
                raise QueryFailed(str(exc)) from exc
            finally:
                timer.cancel()
                timer.join()
        finally:
            with contextlib.suppress(duckdb.Error):
                con.execute("ROLLBACK")
            con.close()

    @staticmethod
    def _types(con: duckdb.DuckDBPyConnection, text: str) -> dict[str, str]:
        try:
            described = con.execute(f"DESCRIBE {text}").fetchall()
        except duckdb.Error:
            return {}
        return {row[0]: row[1] for row in described}
