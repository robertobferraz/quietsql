import threading
from collections.abc import Callable, Sequence

from quietsql.adapters.duckdb.catalog import DuckDbCatalog
from quietsql.adapters.duckdb.connections import ConnectionPool
from quietsql.adapters.duckdb.history import DuckDbHistory
from quietsql.adapters.duckdb.keys import infer_foreign_keys
from quietsql.adapters.duckdb.pruning import select_tables
from quietsql.adapters.duckdb.runner import DuckDbRunner
from quietsql.adapters.llm.registry import model_path, resolve_spec
from quietsql.adapters.llm.status import TRANSLATION_KEY, FileModelStatus
from quietsql.adapters.sources.loader import FileSourceLoader
from quietsql.adapters.translate.detector import LinguaDetector
from quietsql.app.ask_question import AskQuestion
from quietsql.app.history import ListHistory
from quietsql.app.run_sql import RunSql
from quietsql.app.services import Services
from quietsql.app.sources import SourceService
from quietsql.config import Config
from quietsql.core.errors import ModelsMissing
from quietsql.core.models import Attempt

MISSING_MODELS = "models are missing; run `quietsql download-models` first"


class Lazy:
    def __init__(self, factory: Callable[[], object]) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._use_lock = threading.Lock()
        self._inner = None

    def _get(self):
        if self._inner is None:
            with self._lock:
                if self._inner is None:
                    self._inner = self._factory()
        return self._inner


class LazyTextToSql(Lazy):
    def generate(
        self,
        schema_ddl: str,
        question: str,
        previous: Sequence[Attempt],
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        model = self._get()
        with self._use_lock:
            return model.generate(schema_ddl, question, previous, on_token)

    def prefill_ms(self) -> float:
        return self._get().prefill_ms() if self._inner is not None else 0.0


class LazyTranslator(Lazy):
    def translate(self, text: str, protected: Sequence[str]) -> str:
        return self._get().translate(text, protected)


def build_services(cfg: Config) -> Services:
    resolve_spec(cfg.model)
    status = FileModelStatus(cfg)
    pool = ConnectionPool()
    catalog = DuckDbCatalog(pool, cfg.schema_budget_tokens, infer_foreign_keys, select_tables)
    runner = DuckDbRunner(pool, cfg.query_timeout_s)
    history = DuckDbHistory(pool)
    loader = FileSourceLoader(pool, cfg.cache_dir / "sessions")

    def make_text_to_sql():
        if not status.ready():
            raise ModelsMissing(MISSING_MODELS)
        from quietsql.adapters.llm.llamacpp import LlamaCppTextToSql

        return LlamaCppTextToSql(model_path(cfg, cfg.model), cfg.n_ctx, cfg.threads, cfg.max_tokens)

    def make_translator():
        if not status.ready():
            raise ModelsMissing(MISSING_MODELS)
        from quietsql.adapters.translate.ct2 import Ct2Translator

        return Ct2Translator(model_path(cfg, TRANSLATION_KEY), cfg.threads or 4)

    ask = AskQuestion(
        LinguaDetector(),
        LazyTranslator(make_translator),
        catalog,
        LazyTextToSql(make_text_to_sql),
        runner,
        history,
    )
    return Services(
        ask=ask,
        run_sql=RunSql(runner, history),
        sources=SourceService(loader, catalog, cfg.max_tables),
        history=ListHistory(history),
        model_status=status,
    )
