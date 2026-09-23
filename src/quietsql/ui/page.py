import tempfile
from collections.abc import Callable
from pathlib import Path

from nicegui import events, run, ui

from quietsql.app.services import Services
from quietsql.core.errors import Cancelled, ModelsMissing, SourceRejected
from quietsql.core.models import Answer, ChartKind, HistoryEntry, Source
from quietsql.ui.components import question_box, result_view, sidebar, sql_editor, states, timings
from quietsql.ui.session import SessionState


class QueryPage:
    def __init__(self, services: Services) -> None:
        self.services = services
        self.state = SessionState()
        self._syncing_chart = False
        sources = services.sources.list()
        self.state.active_source_id = sources[0].id if sources else None

    def build(self) -> None:
        ready = self.services.model_status.ready()
        with ui.header().classes("items-center justify-between bg-white text-gray-900 border-b"):
            with ui.row().classes("items-center gap-3"):
                ui.label("quietsql").classes("text-lg font-semibold")
                self.source_select = ui.select(
                    {s.id: s.name for s in self.services.sources.list()},
                    value=self.state.active_source_id,
                    on_change=lambda e: self.select_source(e.value),
                ).props("dense outlined")
                with ui.button(icon="add").props("flat dense"), ui.menu():
                    ui.menu_item("Upload CSV or Parquet", on_click=self.open_upload)
                    ui.menu_item("Open .duckdb file", on_click=self.open_file_dialog)
                    ui.menu_item("Open folder", on_click=self.open_folder_dialog)
            ui.badge("offline").props("color=green outline")

        self.drawer = ui.left_drawer(value=True).classes("bg-gray-50 border-r").props("width=300")
        self.render_drawer()

        with ui.column().classes("w-full max-w-5xl mx-auto gap-4 p-4"):
            if not ready:
                states.models_missing()
            if self.state.active_source_id is None:
                states.empty_source(
                    self.open_upload, self.open_file_dialog, self.open_folder_dialog
                )
            question_box.render(self.state, self.ask, self.cancel, ready)
            self.editor = sql_editor.render(self.state, self.run_manual)
            self.timings_label = timings.render()
            self.chart_toggle = ui.toggle(
                result_view.KINDS, value="table", on_change=lambda e: self.set_chart(e.value)
            )
            self.chart_toggle.mark("chart-selector").props("data-testid=chart-selector")
            self.result_box = ui.column().classes("w-full")
        ui.timer(0.05, self.flush_tokens)

    def render_drawer(self) -> None:
        self.drawer.clear()
        with self.drawer:
            sidebar.render(self.services, self.state, self.select_source, self.replay)

    def select_source(self, source_id: str) -> None:
        if source_id == self.state.active_source_id:
            return
        self.state.active_source_id = source_id
        self.source_select.value = source_id
        self.render_drawer()

    def flush_tokens(self) -> None:
        if not self.state.pending_tokens:
            return
        tokens, self.state.pending_tokens = self.state.pending_tokens, []
        for tok in tokens:
            if tok == "\n":
                self.state.sql = ""
            else:
                self.state.sql += tok

    def on_token(self, token: str) -> None:
        if self.state.cancel_requested:
            raise Cancelled
        self.state.pending_tokens.append(token)

    async def ask(self) -> None:
        no_question = not self.state.question.strip()
        if self.state.generating or no_question or not self.state.active_source_id:
            return
        self.state.generating = True
        self.state.cancel_requested = False
        self.state.sql = ""
        self.state.answer = None
        self.result_box.clear()
        self.timings_label.set_text("generating…")
        source_id, text = self.state.active_source_id, self.state.question
        try:
            answer = await run.io_bound(self.services.ask, source_id, text, self.on_token)
        except Cancelled:
            self.timings_label.set_text("cancelled")
            return
        except ModelsMissing:
            self.timings_label.set_text("")
            with self.result_box:
                states.models_missing()
            return
        except Exception as exc:
            self.timings_label.set_text("")
            with self.result_box:
                states.error_banner(str(exc) or type(exc).__name__)
            return
        finally:
            self.state.generating = False
        self.flush_tokens()
        self.show(answer)

    def cancel(self) -> None:
        self.state.cancel_requested = True

    async def run_manual(self) -> None:
        no_sql = not self.state.sql.strip()
        if self.state.generating or not self.state.active_source_id or no_sql:
            return
        answer = await run.io_bound(
            self.services.run_sql, self.state.active_source_id, self.state.sql, self.state.question
        )
        self.show(answer)

    def replay(self, entry: HistoryEntry) -> None:
        self.state.question = entry.question
        self.state.sql = entry.sql
        ui.timer(0.01, self.run_manual, once=True)

    def show(self, answer: Answer) -> None:
        self.state.answer = answer
        self.state.sql = answer.sql.text
        self.state.chart_kind = answer.chart.kind
        self._syncing_chart = True
        self.chart_toggle.value = answer.chart.kind.value
        self._syncing_chart = False
        self.timings_label.set_text(timings.format_timings(answer.timings))
        result_view.render(self.result_box, answer, answer.chart.kind)
        self.render_drawer()
        if answer.error:
            ui.run_javascript(f"getElement({self.editor.id})?.editor?.focus()")

    def set_chart(self, value: str) -> None:
        if self._syncing_chart:
            return
        self.state.chart_kind = ChartKind(value)
        result_view.render(self.result_box, self.state.answer, self.state.chart_kind)

    def open_upload(self) -> None:
        with ui.dialog() as dialog, ui.card():
            ui.label("Upload CSV or Parquet")
            spinner = ui.spinner().props("data-testid=state-loading-source")
            spinner.visible = False
            ui.upload(
                on_upload=lambda e: self._uploaded(e, dialog, spinner), auto_upload=True
            ).props("accept=.csv,.parquet")
        dialog.open()

    async def _uploaded(
        self, event: events.UploadEventArguments, dialog: ui.dialog, spinner: ui.spinner
    ) -> None:
        path = str(Path(tempfile.gettempdir()) / f"quietsql-upload-{event.file.name}")
        await event.file.save(path)

        def action() -> Source:
            return self.services.sources.upload(event.file.name, path)

        await self._load(action, dialog, spinner)

    def open_file_dialog(self) -> None:
        self._path_dialog("Path to a .duckdb file", self.services.sources.open_file)

    def open_folder_dialog(self) -> None:
        self._path_dialog(
            "Path to a folder with CSV or Parquet files", self.services.sources.open_folder
        )

    def _path_dialog(self, title: str, loader: Callable[[str], Source]) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-96 gap-3"):
            ui.label(title)
            path = ui.input().classes("w-full").props("outlined dense")
            with ui.row().classes("items-center gap-2"):
                button = ui.button("Open")
                spinner = ui.spinner().props("data-testid=state-loading-source")
                spinner.visible = False
            button.on_click(lambda: self._load(lambda: loader(path.value), dialog, spinner, button))
        dialog.open()

    async def _load(
        self,
        action: Callable[[], Source],
        dialog: ui.dialog,
        spinner: ui.spinner,
        trigger: ui.button | None = None,
    ) -> None:
        spinner.visible = True
        if trigger is not None:
            trigger.visible = False
        try:
            source = await run.io_bound(action)
        except SourceRejected as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            spinner.visible = False
            if trigger is not None:
                trigger.visible = True
        dialog.close()
        self.source_select.options = {s.id: s.name for s in self.services.sources.list()}
        self.source_select.update()
        self.select_source(source.id)
        ui.notify(f"Loaded {source.name}", type="positive")
