import asyncio
from collections.abc import Callable

from nicegui.testing import User


async def _wait_until(
    condition: Callable[[], bool], *, attempts: int = 20, interval: float = 0.02
) -> None:
    for _ in range(attempts):
        if condition():
            return
        await asyncio.sleep(interval)
    assert condition()


async def test_page_shows_sources_and_tables(user: User, app_with_fakes):
    await user.open("/")
    await user.should_see("quietsql")
    await user.should_see("sales.duckdb")
    await user.should_see("sales")
    await user.should_see("customers")


async def test_ask_streams_sql_and_shows_result(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await user.should_see("sum(s.amount)")
    await user.should_see("Recife")
    await user.should_see("3 rows")
    await user.should_see("generate")


async def test_error_after_retries_shows_banner_and_keeps_sql(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="question-input").type("erro")
    user.find(marker="ask-button").click()
    await user.should_see(marker="state-error")
    await user.should_see("Binder Error")
    editor = next(iter(user.find(marker="sql-editor").elements))
    assert "missing_column" in editor.value


async def test_manual_sql_rejected(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="sql-editor").type("DELETE FROM sales")
    user.find(marker="run-button").click()
    await user.should_see("only SELECT, WITH, DESCRIBE and SUMMARIZE")


async def test_models_missing_banner(user: User):
    from quietsql.ui.app import create_app
    from quietsql.ui.fake_services import build_fake_services

    create_app(build_fake_services(token_delay=0.0, models_ready=False))
    await user.open("/")
    await user.should_see("quietsql download-models")


async def test_cancel_stops_generation_and_keeps_partial_sql(user: User):
    from quietsql.ui.app import create_app
    from quietsql.ui.fake_services import build_fake_services

    create_app(build_fake_services(token_delay=0.05))
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await user.should_see(marker="cancel-button")
    user.find(marker="cancel-button").click()
    await user.should_see("cancelled")
    await user.should_not_see("ORDER BY 2 DESC")


async def test_chart_toggle_rerenders_without_calling_services(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await _wait_until(lambda: len(app_with_fakes.history("src1")) == 1)
    before = len(app_with_fakes.history("src1"))
    toggle = next(iter(user.find(marker="chart-selector").elements))
    with user:
        toggle.value = "table"
    await user.should_see(marker="result-grid")
    assert len(app_with_fakes.history("src1")) == before


async def test_history_replay_restores_question_and_reruns(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await _wait_until(lambda: len(app_with_fakes.history("src1")) == 1)
    before = len(app_with_fakes.history("src1"))
    user.find(marker="history-item", content="vendas por cidade").click()
    await _wait_until(lambda: len(app_with_fakes.history("src1")) > before)
    assert len(app_with_fakes.history("src1")) == before + 1


async def test_truncated_result_shows_comma_separated_count(user: User, app_with_fakes):
    await user.open("/")
    user.find(marker="question-input").type("mostra tudo")
    user.find(marker="ask-button").click()
    await user.should_see("48,213 rows · showing 10,000")


async def test_empty_source_state_reachable(user: User):
    from quietsql.ui.app import create_app
    from quietsql.ui.fake_services import build_fake_services

    create_app(build_fake_services(token_delay=0.0, sources=False))
    await user.open("/")
    await user.should_see(marker="state-empty")


async def test_models_missing_during_ask_shows_banner(user: User):
    from quietsql.core.errors import ModelsMissing
    from quietsql.ui.app import create_app
    from quietsql.ui.fake_services import build_fake_services

    services = build_fake_services(token_delay=0.0)

    def ask(source_id, text, on_token=None):
        raise ModelsMissing("models are missing; run `quietsql download-models` first")

    services.ask = ask
    create_app(services)
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await user.should_see(marker="state-models-missing")
    await user.should_not_see("generating…")


async def test_model_that_fails_to_load_shows_an_error_banner(user: User):
    from quietsql.ui.app import create_app
    from quietsql.ui.fake_services import build_fake_services

    services = build_fake_services(token_delay=0.0)

    def ask(source_id, text, on_token=None):
        raise RuntimeError("failed to load model from file: truncated gguf")

    services.ask = ask
    create_app(services)
    await user.open("/")
    user.find(marker="question-input").type("vendas por cidade")
    user.find(marker="ask-button").click()
    await user.should_see(marker="state-error")
    await user.should_see("truncated gguf")
    await user.should_not_see("generating…")
