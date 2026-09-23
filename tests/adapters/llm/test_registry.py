import re
from pathlib import Path

from quietsql.adapters.llm.registry import REGISTRY, model_path
from quietsql.config import Config


def test_registry_entries_are_complete():
    assert set(REGISTRY) == {"xiyansql-3b", "prem-1b", "opus-mt-roa-en"}
    for spec in REGISTRY.values():
        assert re.fullmatch(r"[0-9a-f]{64}", spec.sha256), spec.key
        assert spec.license and spec.repo and spec.file_name


def test_model_path_under_cache():
    cfg = Config(cache_dir=Path("/tmp/qcache"))
    assert str(model_path(cfg, "xiyansql-3b")).startswith("/tmp/qcache/models/")
    assert model_path(cfg, "opus-mt-roa-en").name == "opus-mt-roa-en-ct2"


def test_keys_match_their_specs():
    for key, spec in REGISTRY.items():
        assert spec.key == key
        assert spec.kind in ("gguf", "ct2")
        assert spec.size_mb > 0
