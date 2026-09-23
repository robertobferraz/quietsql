from collections.abc import Callable

from nicegui import ui

from quietsql.app.services import Services
from quietsql.core.models import HistoryEntry, QueryStatus
from quietsql.ui.session import SessionState


def render(
    services: Services,
    state: SessionState,
    on_select_source: Callable[[str], None],
    on_history: Callable[[HistoryEntry], None],
) -> None:
    with ui.column().classes("w-full gap-5 p-3"):
        ui.label("Sources").classes("text-xs uppercase tracking-wide text-gray-500")
        source_list = ui.column().classes("w-full gap-1")
        source_list.mark("source-list").props("data-testid=source-list")
        with source_list:
            for source in services.sources.list():
                active = source.id == state.active_source_id
                row = ui.row().classes(
                    "w-full items-center justify-between rounded px-2 py-1.5 cursor-pointer "
                    + ("bg-gray-200" if active else "hover:bg-gray-100")
                )
                with row:
                    ui.label(source.name).classes("text-sm text-gray-900")
                    ui.label(f"{source.table_count} tables").classes("text-xs text-gray-500")
                row.on("click", lambda _, sid=source.id: on_select_source(sid))

        if state.active_source_id:
            ui.label("Tables").classes("text-xs uppercase tracking-wide text-gray-500")
            schema = services.sources.tables(state.active_source_id)
            table_list = ui.column().classes("w-full gap-1")
            table_list.mark("table-list").props("data-testid=table-list")
            with table_list:
                for table in schema.tables:
                    title = f"{table.name}  ·  {len(table.columns)} cols, {table.row_count:,} rows"
                    with ui.expansion(title).classes("w-full text-sm"):
                        for col in table.columns:
                            examples = ", ".join(col.examples) if col.examples else ""
                            ui.label(f"{col.name} · {col.data_type} · {examples}").classes(
                                "text-xs font-mono text-gray-700"
                            )

            ui.label("History").classes("text-xs uppercase tracking-wide text-gray-500")
            history_list = ui.column().classes("w-full gap-1")
            history_list.mark("history-list").props("data-testid=history-list")
            with history_list:
                entries = services.history(state.active_source_id, limit=30)
                if not entries:
                    ui.label("No questions asked yet.").classes("text-xs text-gray-500")
                for entry in entries:
                    mark = " ✗" if entry.status in (QueryStatus.ERROR, QueryStatus.REJECTED) else ""
                    text = f"{entry.asked_at:%H:%M}  {entry.question[:40]}{mark}"
                    item = ui.label(text).classes(
                        "text-sm truncate cursor-pointer rounded px-2 py-1 hover:bg-gray-100"
                    )
                    item.mark("history-item").props("data-testid=history-item")
                    item.on("click", lambda _, e=entry: on_history(e))
