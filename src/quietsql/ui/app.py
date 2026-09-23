from nicegui import ui

from quietsql.app.services import Services
from quietsql.ui.page import QueryPage


def create_app(services: Services) -> None:
    @ui.page("/")
    def index() -> None:
        QueryPage(services).build()


def run(services: Services, port: int = 8765, open_browser: bool = True) -> None:
    create_app(services)
    ui.run(
        title="quietsql",
        port=port,
        show=open_browser,
        reload=False,
        favicon="🤫",
        native=False,
    )
