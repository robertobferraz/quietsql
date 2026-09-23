from tests.fakes import FakeHistory, FakeRunner

from quietsql.app.run_sql import RunSql
from quietsql.core.errors import QueryFailed, SqlRejected
from quietsql.core.models import QueryResult, QueryStatus, SqlOrigin

ONE = QueryResult((("n", "BIGINT"),), ((1,),), 1, False)


def test_manual_sql_runs_and_records_manual_origin():
    history = FakeHistory()
    run = RunSql(FakeRunner([ONE]), history)
    answer = run("s1", "SELECT 1;", question_text="edited by hand")
    assert answer.status is QueryStatus.OK
    assert answer.sql.origin is SqlOrigin.MANUAL
    assert answer.sql.text == "SELECT 1"
    assert history.list("s1")[0].question == "edited by hand"


def test_manual_rejected():
    answer = RunSql(FakeRunner([], reject=SqlRejected("nope")), FakeHistory())("s1", "DROP x")
    assert answer.status is QueryStatus.REJECTED and answer.error == "nope"
    assert answer.timings.transpile_ms > 0


def test_manual_failed():
    answer = RunSql(FakeRunner([QueryFailed("boom")]), FakeHistory())("s1", "SELECT x")
    assert answer.status is QueryStatus.ERROR and answer.error == "boom" and answer.result is None
