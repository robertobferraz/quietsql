from dataclasses import dataclass

from quietsql.app.ask_question import AskQuestion
from quietsql.app.history import ListHistory
from quietsql.app.run_sql import RunSql
from quietsql.app.sources import SourceService
from quietsql.ports import ModelStatus


@dataclass
class Services:
    ask: AskQuestion
    run_sql: RunSql
    sources: SourceService
    history: ListHistory
    model_status: ModelStatus
