from collections.abc import Callable

from nicegui import ui

from quietsql.core.models import Language
from quietsql.ui.session import SessionState


def render(state: SessionState, on_ask: Callable, on_cancel: Callable, enabled: bool) -> ui.input:
    with ui.row().classes("w-full items-end gap-2"):
        box = ui.input(placeholder="Ask in Portuguese or English, e.g. quantas vendas por cidade")
        box.classes("flex-grow").mark("question-input").props("data-testid=question-input outlined")
        box.bind_value(state, "question")
        box.set_enabled(enabled)
        box.on("keydown.enter", on_ask)
        ask = ui.button("Ask", on_click=on_ask).mark("ask-button").props("data-testid=ask-button")
        ask.bind_enabled_from(state, "generating", backward=lambda g: not g and enabled)
        cancel = ui.button("Cancel", on_click=on_cancel).props("flat data-testid=cancel-button")
        cancel.mark("cancel-button").bind_visibility_from(state, "generating")
    translated = ui.label().classes("text-xs text-gray-500").mark("translated-text")
    translated.props("data-testid=translated-text")
    translated.bind_visibility_from(
        state, "answer", backward=lambda a: bool(a and a.question.language == Language.PT)
    )

    def format_translation(a):
        if not a:
            return ""
        return f"pt→en: {a.question.translated_text}  ·  {a.timings.translate_ms:.0f} ms"

    translated.bind_text_from(state, "answer", backward=format_translation)
    return box
