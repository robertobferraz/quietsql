from collections.abc import Callable

from nicegui import ui


def models_missing() -> ui.element:
    with ui.element("div").classes(
        "w-full rounded-lg bg-amber-50 border border-amber-300 px-4 py-3"
    ) as box:
        box.mark("state-models-missing").props("data-testid=state-models-missing")
        ui.label("Models are not downloaded.").classes("font-medium text-amber-900")
        message = "Run quietsql download-models once, then restart."
        ui.label(message).classes("text-amber-800 text-sm")
    return box


def empty_source(on_upload: Callable, on_file: Callable, on_folder: Callable) -> ui.element:
    with ui.column().classes("w-full items-center gap-3 py-20") as box:
        box.mark("state-empty").props("data-testid=state-empty")
        ui.label("No data source yet").classes("text-xl font-medium text-gray-900")
        hint = "Load a file to start asking questions. Everything stays on this machine."
        ui.label(hint).classes("text-gray-600")
        with ui.row().classes("gap-2 mt-2"):
            ui.button("Upload CSV or Parquet", on_click=on_upload).props("outline")
            ui.button("Open .duckdb file", on_click=on_file).props("outline")
            ui.button("Open folder", on_click=on_folder).props("outline")
    return box


def error_banner(message: str) -> ui.element:
    with ui.element("div").classes(
        "w-full rounded-lg bg-red-50 border border-red-300 px-4 py-3"
    ) as box:
        box.mark("state-error").props("data-testid=state-error")
        ui.label(message).classes("text-red-900 font-mono text-sm whitespace-pre-wrap")
    return box


def empty_result() -> ui.element:
    label = ui.label("No rows. Try rephrasing or check the example values in the sidebar.")
    label.classes("text-gray-600 py-6").mark("state-empty-result")
    label.props("data-testid=state-empty-result")
    return label
