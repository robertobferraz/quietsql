from quietsql.core.errors import SourceRejected
from quietsql.core.models import Schema, Source
from quietsql.ports import Catalog, SourceLoader


class SourceService:
    def __init__(self, loader: SourceLoader, catalog: Catalog, max_tables: int = 30) -> None:
        self.loader = loader
        self.catalog = catalog
        self.max_tables = max_tables

    def upload(self, file_name: str, file_path: str) -> Source:
        return self._accept(self.loader.load_upload(file_name, file_path))

    def open_file(self, path: str) -> Source:
        return self._accept(self.loader.open_file(path))

    def open_folder(self, path: str) -> Source:
        return self._accept(self.loader.load_folder(path))

    def reload(self, source_id: str) -> Source:
        source = self.loader.reload(source_id)
        self.catalog.invalidate(source_id)
        return source

    def list(self) -> tuple[Source, ...]:
        return self.loader.list()

    def remove(self, source_id: str) -> None:
        self.loader.remove(source_id)
        self.catalog.invalidate(source_id)

    def tables(self, source_id: str) -> Schema:
        return self.catalog.schema(source_id)

    def _accept(self, source: Source) -> Source:
        if source.table_count > self.max_tables:
            self.loader.remove(source.id)
            raise SourceRejected(
                f"{source.name} has {source.table_count} tables; the limit is {self.max_tables}"
            )
        self.catalog.invalidate(source.id)
        return source
