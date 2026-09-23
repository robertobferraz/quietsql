import argparse
import sys
from pathlib import Path

from quietsql import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quietsql")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start the local web app")
    serve.add_argument("--mock", action="store_true", help="run with fake data and no models")
    serve.add_argument("--empty", action="store_true", help="start the mock app with no sources")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--db", type=Path, help="open a .duckdb file at startup")
    serve.add_argument("--folder", type=Path, help="load a folder of CSV/Parquet files at startup")
    serve.add_argument("--config", type=Path)
    download = sub.add_parser(
        "download-models", help="download and verify the models (only network step)"
    )
    download.add_argument("--only", nargs="+", default=None)
    download.add_argument("--config", type=Path)
    return parser


def _overrides(args: argparse.Namespace) -> dict:
    if args.command != "serve":
        return {}
    default = build_parser().parse_args(["serve"]).port
    return {} if args.port == default else {"port": args.port}


def main(argv: list[str] | None = None) -> int:
    from quietsql.core.errors import ConfigRejected, DownloadFailed, SourceRejected

    try:
        return _run(build_parser().parse_args(argv))
    except (ConfigRejected, DownloadFailed, SourceRejected) as exc:
        print(f"quietsql: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    from quietsql.config import load_config

    cfg = load_config(args.config, overrides=_overrides(args))
    if args.command == "download-models":
        from quietsql.adapters.llm import download
        from quietsql.adapters.llm.status import TRANSLATION_KEY

        download.download_models(cfg, args.only or [cfg.model, TRANSLATION_KEY])
        return 0
    from quietsql.ui import app

    if args.mock:
        from quietsql.ui.fake_services import build_fake_services

        services = build_fake_services(sources=not args.empty)
    else:
        from quietsql.wiring import build_services

        services = build_services(cfg)
        if args.db:
            services.sources.open_file(str(args.db))
        if args.folder:
            services.sources.open_folder(str(args.folder))
    app.run(services, port=cfg.port, open_browser=not args.no_browser)
    return 0
