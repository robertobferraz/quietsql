import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_FILE = "config.toml"
PATH_FIELDS = ("cache_dir", "config_dir")
AUTO = (None, "", "auto")


def _home(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


@dataclass
class Config:
    model: str = "xiyansql-3b"
    fallback_model: str = "prem-1b"
    threads: int | None = None
    n_ctx: int = 4096
    max_tokens: int = 120
    query_timeout_s: float = 30.0
    max_tables: int = 30
    schema_budget_tokens: int = 1000
    port: int = 8765
    cache_dir: Path = field(default_factory=lambda: _home(".cache", "quietsql"))
    config_dir: Path = field(default_factory=lambda: _home(".config", "quietsql"))


def _coerce(name: str, value, current):
    if name in PATH_FIELDS:
        return Path(str(value)).expanduser()
    if name == "threads":
        return None if value in AUTO else int(value)
    if isinstance(current, bool):
        return str(value).lower() in ("1", "true", "yes")
    if isinstance(current, float):
        return float(value)
    if isinstance(current, int):
        return int(value)
    return value


def _env_key(name: str) -> str:
    return f"QUIETSQL_{name.upper()}"


def _from_env(env: Mapping[str, str]) -> dict:
    return {f.name: env[_env_key(f.name)] for f in fields(Config) if _env_key(f.name) in env}


def load_config(
    path: Path | None = None,
    env: Mapping[str, str] = os.environ,
    overrides: dict | None = None,
) -> Config:
    cfg = Config()
    defaults = Config()
    from_env = _from_env(env)
    if "config_dir" in from_env:
        cfg.config_dir = _coerce("config_dir", from_env["config_dir"], cfg.config_dir)
    file_path = Path(path) if path is not None else cfg.config_dir / CONFIG_FILE
    values: dict = {}
    if file_path.is_file():
        values.update(tomllib.loads(file_path.read_text()))
    values.update(from_env)
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    for f in fields(Config):
        if f.name in values:
            setattr(cfg, f.name, _coerce(f.name, values[f.name], getattr(defaults, f.name)))
    return cfg
