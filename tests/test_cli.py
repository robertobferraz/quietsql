import pytest

from quietsql.cli import build_parser


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith("QUIETSQL_"):
            monkeypatch.delenv(name, raising=False)


def test_parser_serve_defaults():
    args = build_parser().parse_args(["serve", "--mock", "--no-browser"])
    assert args.command == "serve" and args.mock and args.no_browser and args.port == 8765


def test_parser_download_only():
    args = build_parser().parse_args(["download-models", "--only", "prem-1b"])
    assert args.command == "download-models" and args.only == ["prem-1b"]


def test_parser_rejects_unknown():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nope"])


def test_parser_keeps_empty_flag():
    args = build_parser().parse_args(["serve", "--mock", "--empty"])
    assert args.empty


def test_parser_serve_paths():
    args = build_parser().parse_args(["serve", "--db", "/d/a.duckdb", "--folder", "/d/exports"])
    assert str(args.db) == "/d/a.duckdb" and str(args.folder) == "/d/exports"
    assert not args.mock


def test_main_mock_serve_uses_fake_services(monkeypatch):
    import quietsql.cli as cli
    import quietsql.ui.app as ui_app

    seen = {}

    def fake_run(services, port=8765, open_browser=True):
        seen["services"] = services
        seen["port"] = port
        seen["open_browser"] = open_browser

    monkeypatch.setattr(ui_app, "run", fake_run)
    assert cli.main(["serve", "--mock", "--empty", "--no-browser", "--port", "9999"]) == 0
    assert seen["port"] == 9999 and seen["open_browser"] is False
    assert seen["services"].sources.list() == ()


def test_main_download_models_uses_config_keys(monkeypatch, tmp_path):
    import quietsql.adapters.llm.download as download
    import quietsql.cli as cli

    calls = []
    monkeypatch.setattr(download, "download_models", lambda cfg, keys: calls.append(list(keys)))
    monkeypatch.setenv("QUIETSQL_CACHE_DIR", str(tmp_path))
    assert cli.main(["download-models"]) == 0
    assert calls == [["xiyansql-3b", "opus-mt-roa-en"]]


def test_config_file_port_survives_the_argparse_default(monkeypatch, tmp_path):
    import quietsql.cli as cli
    import quietsql.ui.app as ui_app

    (tmp_path / "config.toml").write_text("port = 9000\n")
    seen = {}
    monkeypatch.setattr(
        ui_app, "run", lambda services, port=8765, open_browser=True: seen.update(port=port)
    )
    cli.main(["serve", "--mock", "--no-browser", "--config", str(tmp_path / "config.toml")])
    assert seen["port"] == 9000


def test_unknown_model_key_is_reported_without_a_traceback(monkeypatch, capsys, tmp_path):
    import quietsql.cli as cli

    (tmp_path / "config.toml").write_text('model = "xiyansql3b"\n')
    monkeypatch.setenv("QUIETSQL_CACHE_DIR", str(tmp_path))
    code = cli.main(["download-models", "--config", str(tmp_path / "config.toml")])
    assert code == 2
    message = capsys.readouterr().err
    assert "xiyansql3b" in message and "xiyansql-3b" in message


def test_bad_db_path_is_reported_without_a_traceback(capsys, tmp_path):
    import quietsql.cli as cli

    code = cli.main(["serve", "--db", str(tmp_path / "missing.duckdb"), "--no-browser"])
    assert code == 2
    assert "missing.duckdb" in capsys.readouterr().err


def test_bad_folder_path_is_reported_without_a_traceback(capsys, tmp_path):
    import quietsql.cli as cli

    code = cli.main(["serve", "--folder", str(tmp_path / "nowhere"), "--no-browser"])
    assert code == 2
    assert "nowhere" in capsys.readouterr().err


def test_download_failure_is_reported_without_a_traceback(monkeypatch, capsys, tmp_path):
    import quietsql.adapters.llm.download as download
    import quietsql.cli as cli
    from quietsql.core.errors import DownloadFailed

    def explode(cfg, keys, log=print):
        raise DownloadFailed("sha256 mismatch for prem-1b.gguf: deadbeef")

    monkeypatch.setattr(download, "download_models", explode)
    monkeypatch.setenv("QUIETSQL_CACHE_DIR", str(tmp_path))
    code = cli.main(["download-models"])
    err = capsys.readouterr().err
    assert code == 2
    assert err == "quietsql: sha256 mismatch for prem-1b.gguf: deadbeef\n"
