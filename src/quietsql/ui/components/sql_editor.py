from collections.abc import Callable

from nicegui import ui

from quietsql.ui.session import SessionState


def render(state: SessionState, on_run: Callable) -> ui.codemirror:
    with ui.row().classes("w-full items-center justify-between"):
        ui.label("SQL").classes("text-xs uppercase tracking-wide text-gray-500")
        run_button = ui.button("Run", on_click=on_run).props("outline data-testid=run-button")
        run_button.mark("run-button")
        run_button.bind_enabled_from(state, "generating", backward=lambda g: not g)
    editor = ui.codemirror(language="SQL", theme="basicLight").classes("w-full h-40 text-sm")
    editor.mark("sql-editor").props("data-testid=sql-editor")
    editor.bind_value(state, "sql")
    return editor
