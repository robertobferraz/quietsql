from nicegui import ui

from quietsql.core.models import Answer, ChartKind, QueryResult, QueryStatus
from quietsql.ui.components import states

KINDS = {"table": "Table", "bar": "Bar", "line": "Line", "metric": "Metric"}


def _rows(result: QueryResult) -> list[dict]:
    names = [c for c, _ in result.columns]
    return [dict(zip(names, row, strict=True)) for row in result.rows]


def _figure(kind: ChartKind, result: QueryResult, x: str, y: str) -> dict:
    names = [c for c, _ in result.columns]
    xi, yi = names.index(x), names.index(y)
    xs = [row[xi] for row in result.rows]
    ys = [row[yi] for row in result.rows]
    trace_type = "bar" if kind is ChartKind.BAR else "scatter"
    trace = {"type": trace_type, "x": xs, "y": ys}
    if kind is ChartKind.LINE:
        trace["mode"] = "lines+markers"
    layout = {
        "margin": {"l": 40, "r": 10, "t": 10, "b": 40},
        "xaxis": {"title": x},
        "yaxis": {"title": y},
    }
    return {"data": [trace], "layout": layout}


def render(container: ui.element, answer: Answer | None, chart_kind: ChartKind) -> None:
    container.clear()
    if answer is None:
        return
    with container:
        if answer.status in (QueryStatus.ERROR, QueryStatus.REJECTED):
            states.error_banner(answer.error or "unknown error")
            return
        result = answer.result
        if result is None or not result.rows:
            states.empty_result()
            return
        count = ui.label().classes("text-xs text-gray-500").mark("result-count")
        count.props("data-testid=result-count")
        if result.truncated:
            count.set_text(f"{result.total_rows:,} rows · showing {len(result.rows):,}")
        else:
            count.set_text(f"{result.total_rows:,} rows")
        if chart_kind is ChartKind.METRIC and answer.chart.y:
            names = [c for c, _ in result.columns]
            value = result.rows[0][names.index(answer.chart.y)]
            with ui.card().classes("items-center px-10 py-6"):
                ui.label(f"{value:,.2f}" if isinstance(value, float) else f"{value:,}").classes(
                    "text-4xl font-semibold"
                )
                ui.label(answer.chart.y).classes("text-gray-500")
        elif chart_kind in (ChartKind.BAR, ChartKind.LINE) and answer.chart.x and answer.chart.y:
            figure = _figure(chart_kind, result, answer.chart.x, answer.chart.y)
            ui.plotly(figure).classes("w-full h-72")
        else:
            if chart_kind is not ChartKind.TABLE:
                note = (
                    f"{KINDS[chart_kind.value]} needs one category or time column and one "
                    "number; this result doesn't have that shape, showing the table instead."
                )
                ui.label(note).classes("text-xs text-gray-500 mb-1")
            columns = [{"headerName": c, "field": c, "sortable": True} for c, _ in result.columns]
            grid = ui.aggrid({"columnDefs": columns, "rowData": _rows(result), "pagination": True})
            grid.classes("w-full h-96").mark("result-grid").props("data-testid=result-grid")
