import time
from collections.abc import Callable

from quietsql.app.chart import choose_chart
from quietsql.core.errors import QueryFailed, SqlRejected
from quietsql.core.masking import mask, unmask
from quietsql.core.models import (
    Answer,
    Attempt,
    ChartKind,
    ChartSpec,
    Language,
    QueryResult,
    QueryStatus,
    Question,
    RenderedSchema,
    SqlDraft,
    SqlOrigin,
    StageTimings,
)
from quietsql.ports import (
    Catalog,
    HistoryStore,
    LanguageDetector,
    QueryRunner,
    TextToSql,
    Translator,
)

EMPTY_HINT = "query returned 0 rows; check filter values against the examples"
MISSING_TABLE = "does not exist"


class AskQuestion:
    def __init__(
        self,
        detector: LanguageDetector,
        translator: Translator,
        catalog: Catalog,
        text_to_sql: TextToSql,
        runner: QueryRunner,
        history: HistoryStore,
        error_retries: int = 2,
        empty_retries: int = 1,
        row_limit: int = 10_000,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.detector = detector
        self.translator = translator
        self.catalog = catalog
        self.text_to_sql = text_to_sql
        self.runner = runner
        self.history = history
        self.error_retries = error_retries
        self.empty_retries = empty_retries
        self.row_limit = row_limit
        self.clock = clock

    def __call__(
        self,
        source_id: str,
        text: str,
        on_token: Callable[[str], None] | None = None,
    ) -> Answer:
        timings = StageTimings()
        question = self._understand(source_id, text, timings)
        schema = self.catalog.schema(source_id)
        rendered = self.catalog.render(schema, question.translated_text)
        previous: list[Attempt] = []
        errors_left = self.error_retries
        empties_left = self.empty_retries
        attempt = 0
        sql = ""
        last_error = ""
        last_status = QueryStatus.ERROR
        result: QueryResult | None = None

        while True:
            attempt += 1
            if attempt > 1 and on_token:
                on_token("\n")
            sql = self._generate(rendered, question, previous, timings, on_token)
            try:
                normalized = self._validate(sql, timings)
                result = self._run(source_id, normalized, timings)
            except SqlRejected as exc:
                last_error, last_status = str(exc), QueryStatus.REJECTED
                if errors_left == 0:
                    break
                errors_left -= 1
                previous.append(Attempt(sql, last_error))
                continue
            except QueryFailed as exc:
                last_error, last_status = str(exc), QueryStatus.ERROR
                if errors_left == 0:
                    break
                errors_left -= 1
                if rendered.pruned and MISSING_TABLE in last_error:
                    rendered = self.catalog.render(schema, None)
                previous.append(Attempt(sql, last_error))
                continue
            sql = normalized
            if result.rows:
                last_status = QueryStatus.OK
                break
            last_status = QueryStatus.EMPTY
            if empties_left == 0:
                break
            empties_left -= 1
            previous.append(Attempt(sql, EMPTY_HINT))

        draft = SqlDraft(sql, SqlOrigin.MODEL, attempt)
        failed = last_status in (QueryStatus.ERROR, QueryStatus.REJECTED)
        chart = ChartSpec(ChartKind.TABLE, None, None) if failed else choose_chart(result)
        self.history.append(source_id, question, sql, last_status, timings.as_dict())
        return Answer(
            question=question,
            sql=draft,
            result=None if failed else result,
            chart=chart,
            timings=timings,
            status=last_status,
            error=last_error if failed else None,
        )

    def _understand(self, source_id: str, text: str, timings: StageTimings) -> Question:
        t0 = self.clock()
        protected = self.catalog.identifiers(source_id)
        masked, mapping = mask(text, protected)
        language = self.detector.detect(masked)
        timings.detect_ms = (self.clock() - t0) * 1000
        translated = text
        if language is Language.PT:
            t1 = self.clock()
            translated = unmask(self.translator.translate(masked, protected), mapping, text)
            timings.translate_ms = (self.clock() - t1) * 1000
        return Question(text, language, translated)

    def _generate(
        self,
        rendered: RenderedSchema,
        question: Question,
        previous: list[Attempt],
        timings: StageTimings,
        on_token: Callable[[str], None] | None,
    ) -> str:
        t0 = self.clock()
        sql = self.text_to_sql.generate(rendered.ddl, question.translated_text, previous, on_token)
        timings.generate_ms += (self.clock() - t0) * 1000
        timings.prefill_ms = self.text_to_sql.prefill_ms()
        return sql

    def _validate(self, sql: str, timings: StageTimings) -> str:
        t0 = self.clock()
        try:
            return self.runner.validate(sql)
        finally:
            timings.transpile_ms += (self.clock() - t0) * 1000

    def _run(self, source_id: str, sql: str, timings: StageTimings) -> QueryResult:
        t0 = self.clock()
        try:
            return self.runner.run(source_id, sql, self.row_limit)
        finally:
            timings.run_ms += (self.clock() - t0) * 1000
