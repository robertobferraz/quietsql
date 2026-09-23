import time
from collections.abc import Callable

from quietsql.app.chart import choose_chart
from quietsql.core.errors import QueryFailed, SqlRejected
from quietsql.core.models import (
    Answer,
    ChartKind,
    ChartSpec,
    Language,
    QueryStatus,
    Question,
    SqlDraft,
    SqlOrigin,
    StageTimings,
)
from quietsql.ports import HistoryStore, QueryRunner


class RunSql:
    def __init__(
        self,
        runner: QueryRunner,
        history: HistoryStore,
        row_limit: int = 10_000,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.runner = runner
        self.history = history
        self.row_limit = row_limit
        self.clock = clock

    def __call__(self, source_id: str, sql: str, question_text: str = "") -> Answer:
        timings = StageTimings()
        question = Question(question_text, Language.EN, question_text)
        text = sql
        t0 = self.clock()
        try:
            text = self.runner.validate(sql)
        except SqlRejected as exc:
            timings.transpile_ms = (self.clock() - t0) * 1000
            return self._failed(source_id, question, text, QueryStatus.REJECTED, str(exc), timings)
        timings.transpile_ms = (self.clock() - t0) * 1000
        t1 = self.clock()
        try:
            result = self.runner.run(source_id, text, self.row_limit)
        except QueryFailed as exc:
            timings.run_ms = (self.clock() - t1) * 1000
            return self._failed(source_id, question, text, QueryStatus.ERROR, str(exc), timings)
        timings.run_ms = (self.clock() - t1) * 1000
        status = QueryStatus.OK if result.rows else QueryStatus.EMPTY
        self.history.append(source_id, question, text, status, timings.as_dict())
        return Answer(
            question,
            SqlDraft(text, SqlOrigin.MANUAL, 1),
            result,
            choose_chart(result),
            timings,
            status,
        )

    def _failed(self, source_id, question, sql, status, error, timings) -> Answer:
        self.history.append(source_id, question, sql, status, timings.as_dict())
        return Answer(
            question,
            SqlDraft(sql, SqlOrigin.MANUAL, 1),
            None,
            ChartSpec(ChartKind.TABLE, None, None),
            timings,
            status,
            error,
        )
