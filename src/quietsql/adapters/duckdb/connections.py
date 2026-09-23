import threading
from pathlib import Path

import duckdb

from quietsql.core.errors import QueryFailed


def _resolved(db_path: str) -> str:
    return str(Path(db_path).resolve())


class ConnectionPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._paths: dict[str, str] = {}
        self._connections: dict[str, duckdb.DuckDBPyConnection] = {}

    def register(self, source_id: str, db_path: str) -> None:
        with self._lock:
            self.forget(source_id)
            self._paths[source_id] = _resolved(db_path)

    def path(self, source_id: str) -> str:
        with self._lock:
            return self._known(source_id)

    def registered(self, db_path: str) -> bool:
        with self._lock:
            return _resolved(db_path) in self._paths.values()

    def writable(self, source_id: str) -> duckdb.DuckDBPyConnection:
        with self._lock:
            path = self._known(source_id)
            con = self._connections.get(path)
            if con is None:
                con = duckdb.connect(path)
                self._connections[path] = con
            return con

    def read_only(self, source_id: str) -> duckdb.DuckDBPyConnection:
        return self.writable(source_id).cursor()

    def forget(self, source_id: str) -> None:
        with self._lock:
            path = self._paths.pop(source_id, None)
            if path is None or path in self._paths.values():
                return
            con = self._connections.pop(path, None)
            if con is not None:
                con.close()

    def _known(self, source_id: str) -> str:
        path = self._paths.get(source_id)
        if path is None:
            raise QueryFailed(f"unknown source {source_id}")
        return path
