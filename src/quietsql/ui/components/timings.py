from nicegui import ui

from quietsql.core.models import StageTimings

ORDER = ("detect", "translate", "prefill", "generate", "transpile", "run")


def format_timings(t: StageTimings) -> str:
    d = t.as_dict()
    parts = []
    for name in ORDER:
        ms = d[f"{name}_ms"]
        parts.append(f"{name} {ms / 1000:.1f} s" if ms >= 1000 else f"{name} {ms:.0f} ms")
    return " · ".join(parts)


def render() -> ui.label:
    label = ui.label("").classes("text-xs text-gray-500 font-mono").mark("timings")
    label.props("data-testid=timings")
    return label
