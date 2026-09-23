import hashlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import duckdb

from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.history import USER_TABLES
from quietsql.adapters.duckdb.render import quote
from quietsql.core.errors import SourceRejected
from quietsql.core.models import Source, SourceKind

READERS = {".csv": "read_csv_auto", ".parquet": "read_parquet"}


def sanitize(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    cleaned = re.sub(r"[^a-z0-9_]", "_", stem).strip("_") or "table"
    return f"t_{cleaned}" if cleaned[0].isdigit() else cleaned


def _source_id(path: str) -> str:
    return hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:10]


class FileSourceLoader:
    def __init__(self, pool: ConnectionPool, session_dir: Path) -> None:
        self.pool = pool
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._sources: dict[str, Source] = {}
        self._mtimes: dict[str, dict[str, float]] = {}
        self._tables: dict[str, dict[str, str]] = {}

    def load_upload(self, file_name: str, file_path: str) -> Source:
        suffix = Path(file_name).suffix.lower()
        if suffix not in READERS:
            raise SourceRejected(f"unsupported file type {suffix}; use .csv or .parquet")
        source_id = _source_id(file_path)
        db = self.session_dir / f"{source_id}.duckdb"
        self.pool.register(source_id, str(db))
        with self._registered_only_on_success(source_id, file_name):
            table = self._table_for(source_id, file_path, file_name)
            self._import(source_id, table, file_path, suffix)
            return self._register(source_id, file_name, SourceKind.UPLOAD, file_path)

    def open_file(self, path: str) -> Source:
        if not os.path.isfile(path):
            raise SourceRejected(f"{path} is not a file")
        suffix = Path(path).suffix.lower()
        if suffix in READERS:
            raise SourceRejected(
                f"{suffix} files are loaded through upload, not opened as a database"
            )
        source_id = _source_id(path)
        self.pool.register(source_id, path)
        with self._registered_only_on_success(source_id, path):
            self._require_file_backed(source_id, path)
            return self._register(source_id, Path(path).name, SourceKind.FILE, path)

    def load_folder(self, path: str) -> Source:
        if not os.path.isdir(path):
            raise SourceRejected(f"{path} is not a folder")
        source_id = _source_id(path)
        db = self.session_dir / f"{source_id}.duckdb"
        self.pool.register(source_id, str(db))
        self._mtimes[source_id] = {}
        self._tables[source_id] = {}
        with self._registered_only_on_success(source_id, path):
            self._import_folder(source_id, path)
            name = Path(path.rstrip("/")).name + "/"
            return self._register(source_id, name, SourceKind.FOLDER, path)

    def reload(self, source_id: str) -> Source:
        source = self._sources[source_id]
        if source.kind is SourceKind.FOLDER:
            self._import_folder(source_id, source.path)
        return self._register(source_id, source.name, source.kind, source.path)

    def list(self) -> tuple[Source, ...]:
        return tuple(self._sources.values())

    def remove(self, source_id: str) -> None:
        source = self._sources.pop(source_id, None)
        if source is None:
            return
        path = self.pool.path(source_id)
        self.pool.forget(source_id)
        self._mtimes.pop(source_id, None)
        self._tables.pop(source_id, None)
        if source.kind not in (SourceKind.UPLOAD, SourceKind.FOLDER):
            return
        if self.pool.registered(path) or not os.path.exists(path):
            return
        os.remove(path)

    @contextmanager
    def _registered_only_on_success(self, source_id: str, target: str) -> Iterator[None]:
        try:
            yield
        except SourceRejected:
            self.pool.forget(source_id)
            raise
        except duckdb.Error as exc:
            self.pool.forget(source_id)
            raise SourceRejected(f"{target} could not be read by DuckDB: {exc}") from exc

    def _require_file_backed(self, source_id: str, path: str) -> None:
        con = self.pool.writable(source_id).cursor()
        try:
            backed = con.execute(
                "SELECT count(*) FROM duckdb_databases() WHERE path IS NOT NULL"
            ).fetchone()[0]
        finally:
            con.close()
        if not backed:
            raise SourceRejected(f"{path} is not a DuckDB database file")

    def _table_for(self, source_id: str, file_path: str, file_name: str) -> str:
        tables = self._tables.setdefault(source_id, {})
        known = tables.get(file_path)
        if known is not None:
            return known
        base = sanitize(file_name)
        taken = set(tables.values())
        name = base
        attempt = 1
        while name in taken:
            attempt += 1
            name = f"{base}_{attempt}"
        tables[file_path] = name
        return name

    def _import_folder(self, source_id: str, folder: str) -> None:
        seen = self._mtimes.setdefault(source_id, {})
        with os.scandir(folder) as entries:
            files = sorted(
                (e.path, e.name, e.stat().st_mtime)
                for e in entries
                if e.is_file() and Path(e.name).suffix.lower() in READERS
            )
        for file_path, file_name, mtime in files:
            if seen.get(file_path) == mtime:
                continue
            suffix = Path(file_name).suffix.lower()
            table = self._table_for(source_id, file_path, file_name)
            self._import(source_id, table, file_path, suffix)
            seen[file_path] = mtime

    def _import(self, source_id: str, table: str, file_path: str, suffix: str) -> None:
        reader = READERS[suffix]
        con = self.pool.writable(source_id).cursor()
        try:
            con.execute(
                f"CREATE OR REPLACE TABLE {quote(table)} AS SELECT * FROM {reader}(?)", [file_path]
            )
        finally:
            con.close()

    def _register(self, source_id: str, name: str, kind: SourceKind, path: str) -> Source:
        con = self.pool.writable(source_id).cursor()
        try:
            count = con.execute(
                f"SELECT count(*) FROM duckdb_tables() WHERE {USER_TABLES}"
            ).fetchone()[0]
        finally:
            con.close()
        source = Source(source_id, name, kind, path, int(count), datetime.now())
        self._sources[source_id] = source
        return source
