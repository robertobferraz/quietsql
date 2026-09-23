from quietsql.core.models import ChartKind, QueryStatus
from quietsql.ui.fake_services import build_fake_services


def test_fake_services_answer_by_keyword():
    s = build_fake_services(token_delay=0.0)
    src = s.sources.list()[0]
    assert s.ask(src.id, "vendas por cidade").chart.kind is ChartKind.BAR
    assert s.ask(src.id, "ticket médio").chart.kind is ChartKind.METRIC
    assert s.ask(src.id, "vendas por dia em março").chart.kind is ChartKind.LINE
    failed = s.ask(src.id, "erro")
    assert failed.status is QueryStatus.ERROR and failed.error


def test_fake_services_manual_sql_and_history():
    s = build_fake_services(token_delay=0.0)
    src = s.sources.list()[0]
    assert s.run_sql(src.id, "DELETE FROM sales").status is QueryStatus.REJECTED
    assert s.run_sql(src.id, "SELECT 1").status is QueryStatus.OK
    assert len(s.history(src.id)) == 2
    assert s.model_status.ready()
