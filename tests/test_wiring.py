import threading
import time

import pytest

from quietsql.config import Config
from quietsql.core.errors import Cancelled, ConfigRejected, ModelsMissing
from quietsql.wiring import MISSING_MODELS, LazyTextToSql, LazyTranslator, build_services


@pytest.fixture
def services(tmp_path):
    return build_services(Config(cache_dir=tmp_path / "cache", max_tables=7))


def test_build_services_provides_every_use_case(services):
    assert services.ask and services.run_sql and services.history
    assert services.sources.max_tables == 7
    assert services.model_status.model_id() == "xiyansql-3b"
    assert services.model_status.ready() is False


def test_models_are_not_loaded_at_startup(services):
    assert services.ask.text_to_sql._inner is None
    assert services.ask.translator._inner is None
    assert services.ask.text_to_sql.prefill_ms() == 0.0


def test_generate_without_models_raises_models_missing(services):
    with pytest.raises(ModelsMissing):
        services.ask.text_to_sql.generate("ddl", "question", ())


def test_sources_and_runner_share_one_pool(services, tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir()
    (folder / "sales.csv").write_text("region,amount\nsouth,10\nnorth,5\n")
    source = services.sources.open_folder(str(folder))
    assert services.sources.tables(source.id).tables[0].name == "sales"
    answer = services.run_sql(source.id, "select sum(amount) as total from sales")
    assert answer.result.rows[0][0] == 15
    assert services.history(source.id)[0].sql.startswith("SELECT")


def test_reload_serves_the_new_schema_not_the_cached_one(services, tmp_path):
    folder = tmp_path / "exports"
    folder.mkdir()
    (folder / "sales.csv").write_text("region,amount\nsouth,10\n")
    source = services.sources.open_folder(str(folder))
    assert [t.name for t in services.sources.tables(source.id).tables] == ["sales"]
    (folder / "customers.csv").write_text("id,name\n1,ana\n")
    services.sources.reload(source.id)
    assert [t.name for t in services.sources.tables(source.id).tables] == ["customers", "sales"]


class SlowFactory:
    def __init__(self, fail_times: int = 0):
        self.calls = 0
        self.fail_times = fail_times
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.calls += 1
            failing = self.calls <= self.fail_times
        time.sleep(0.05)
        if failing:
            raise ModelsMissing(MISSING_MODELS)
        return self

    def generate(self, schema_ddl, question, previous, on_token=None):
        return "select 1"

    def prefill_ms(self):
        return 7.0

    def translate(self, text, protected):
        return text


def _hammer(action, workers: int = 8) -> list:
    barrier = threading.Barrier(workers)
    errors: list = []

    def body():
        barrier.wait(timeout=5)
        try:
            action()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=body) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return errors


def test_lazy_text_to_sql_builds_one_model_under_concurrency():
    factory = SlowFactory()
    lazy = LazyTextToSql(factory)
    assert _hammer(lambda: lazy.generate("ddl", "q", ())) == []
    assert factory.calls == 1
    assert lazy.prefill_ms() == 7.0


def test_lazy_translator_builds_one_model_under_concurrency():
    factory = SlowFactory()
    lazy = LazyTranslator(factory)
    assert _hammer(lambda: lazy.translate("oi", ())) == []
    assert factory.calls == 1


def test_failed_factory_does_not_poison_later_attempts():
    factory = SlowFactory(fail_times=1)
    lazy = LazyTextToSql(factory)
    with pytest.raises(ModelsMissing):
        lazy.generate("ddl", "q", ())
    assert lazy.prefill_ms() == 0.0
    assert lazy.generate("ddl", "q", ()) == "select 1"
    assert factory.calls == 2


def test_unknown_model_key_is_a_configuration_error(tmp_path):
    with pytest.raises(ConfigRejected) as exc:
        build_services(Config(cache_dir=tmp_path, model="xiyansql3b"))
    assert "xiyansql3b" in str(exc.value)
    assert "xiyansql-3b" in str(exc.value)


class TrackingModel:
    def __init__(self, fail: Exception | None = None):
        self.active = 0
        self.peak = 0
        self.order: list[str] = []
        self.lock = threading.Lock()
        self.fail = fail

    def generate(self, schema_ddl, question, previous, on_token=None):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.order.append(question)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        if self.fail is not None:
            raise self.fail
        return "select 1"

    def prefill_ms(self):
        return 1.0


def test_generation_never_interleaves_on_the_shared_model():
    model = TrackingModel()
    lazy = LazyTextToSql(lambda: model)
    assert _hammer(lambda: lazy.generate("ddl", "q", ())) == []
    assert model.peak == 1
    assert len(model.order) == 8


def test_a_raising_generation_releases_the_lock():
    model = TrackingModel(fail=Cancelled())
    lazy = LazyTextToSql(lambda: model)
    errors = _hammer(lambda: lazy.generate("ddl", "q", ()))
    assert len(errors) == 8 and all(isinstance(e, Cancelled) for e in errors)
    assert model.peak == 1
    model.fail = None
    assert lazy.generate("ddl", "q", ()) == "select 1"


class BlockingModel:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate(self, schema_ddl, question, previous, on_token=None):
        self.entered.set()
        self.release.wait(timeout=5)
        return "select 1"

    def prefill_ms(self):
        return 1.0


def test_prefill_ms_does_not_wait_for_a_running_generation():
    model = BlockingModel()
    lazy = LazyTextToSql(lambda: model)
    worker = threading.Thread(target=lambda: lazy.generate("ddl", "slow", ()))
    worker.start()
    assert model.entered.wait(timeout=5)
    result: list[float] = []
    checker = threading.Thread(target=lambda: result.append(lazy.prefill_ms()))
    checker.start()
    checker.join(timeout=1)
    assert not checker.is_alive()
    assert result == [1.0]
    model.release.set()
    worker.join(timeout=5)
