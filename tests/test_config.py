from pathlib import Path

from quietsql.config import Config, load_config


def test_defaults():
    cfg = load_config(path=Path("/nonexistent"), env={})
    assert cfg.model == "xiyansql-3b" and cfg.max_tokens == 120 and cfg.port == 8765


def test_precedence_file_env_overrides(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('model = "prem-1b"\nport = 9000\nmax_tokens = 80\n')
    cfg = load_config(path=f, env={"QUIETSQL_PORT": "9100"}, overrides={"max_tokens": 60})
    assert cfg.model == "prem-1b" and cfg.port == 9100 and cfg.max_tokens == 60


def test_paths_expand_user():
    cfg = load_config(path=Path("/nonexistent"), env={"QUIETSQL_CACHE_DIR": "~/x"})
    assert cfg.cache_dir == Path("~/x").expanduser()
    assert isinstance(Config().cache_dir, Path)


def test_none_overrides_are_ignored(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text("port = 9000\n")
    cfg = load_config(path=f, env={}, overrides={"port": None})
    assert cfg.port == 9000


def test_threads_auto_is_none():
    cfg = load_config(path=Path("/nonexistent"), env={"QUIETSQL_THREADS": "auto"})
    assert cfg.threads is None
    assert load_config(path=Path("/nonexistent"), env={"QUIETSQL_THREADS": "6"}).threads == 6


def test_file_is_read_from_config_dir_when_no_path(tmp_path):
    (tmp_path / "config.toml").write_text('model = "prem-1b"\n')
    cfg = load_config(path=None, env={"QUIETSQL_CONFIG_DIR": str(tmp_path)})
    assert cfg.model == "prem-1b"


def test_query_timeout_is_float():
    cfg = load_config(path=Path("/nonexistent"), env={"QUIETSQL_QUERY_TIMEOUT_S": "12"})
    assert cfg.query_timeout_s == 12.0
    assert isinstance(cfg.query_timeout_s, float)
