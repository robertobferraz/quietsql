import pytest

from quietsql.adapters.llm.registry import model_path
from quietsql.adapters.llm.status import FileModelStatus
from quietsql.config import Config
from quietsql.ports import ModelStatus


def test_conforms_to_port(conforms_to_port):
    conforms_to_port(FileModelStatus, ModelStatus)


def _ready_tree(tmp_path):
    cfg = Config(cache_dir=tmp_path)
    gguf = model_path(cfg, cfg.model)
    gguf.parent.mkdir(parents=True, exist_ok=True)
    gguf.write_bytes(b"x")
    ct2 = model_path(cfg, "opus-mt-roa-en")
    ct2.mkdir(parents=True, exist_ok=True)
    for name in ("model.bin", "source.spm", "target.spm"):
        (ct2 / name).write_bytes(b"x")
    return cfg, ct2


def test_not_ready_without_files(tmp_path):
    assert FileModelStatus(Config(cache_dir=tmp_path)).ready() is False


def test_ready_when_both_models_exist(tmp_path):
    cfg, _ = _ready_tree(tmp_path)
    status = FileModelStatus(cfg)
    assert status.ready() is True
    assert status.model_id() == "xiyansql-3b"


def test_ready_requires_every_file_the_translator_opens(tmp_path):
    cfg, ct2 = _ready_tree(tmp_path)
    assert FileModelStatus(cfg).ready() is True
    for name in ("model.bin", "source.spm", "target.spm"):
        (ct2 / name).unlink()
        assert FileModelStatus(cfg).ready() is False
        (ct2 / name).write_bytes(b"x")


def test_unknown_model_key_is_a_configuration_error(tmp_path):
    from quietsql.core.errors import ConfigRejected

    with pytest.raises(ConfigRejected):
        FileModelStatus(Config(cache_dir=tmp_path, model="nope")).ready()
