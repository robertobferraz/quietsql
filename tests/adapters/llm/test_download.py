import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import quietsql.adapters.llm.download as download
from quietsql.adapters.llm.download import download_models, sha256_of
from quietsql.adapters.llm.registry import REGISTRY, model_path
from quietsql.adapters.llm.status import FileModelStatus
from quietsql.config import Config
from quietsql.core.errors import ConfigRejected, DownloadFailed


@pytest.fixture
def cfg(tmp_path):
    return Config(cache_dir=tmp_path / "cache")


def _write(path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _spec(key, **kwargs):
    return replace(REGISTRY[key], **kwargs)


def test_sha256_of_matches_hashlib(tmp_path):
    digest = _write(tmp_path / "f.bin", b"quietsql" * 1000)
    assert sha256_of(tmp_path / "f.bin") == digest


def test_gguf_download_verifies_digest(monkeypatch, cfg, tmp_path):
    payload = b"gguf-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(REGISTRY, "prem-1b", _spec("prem-1b", sha256=digest))

    def fake_hf_hub_download(repo, file_name, local_dir=None):
        got = tmp_path / "hub" / file_name
        _write(got, payload)
        return str(got)

    monkeypatch.setattr(download, "_hf_hub_download", lambda: fake_hf_hub_download)
    lines = []
    download_models(cfg, ["prem-1b"], log=lines.append)
    target = model_path(cfg, "prem-1b")
    assert target.read_bytes() == payload
    assert any("verified" in line for line in lines)


def test_gguf_mismatch_removes_file_and_raises(monkeypatch, cfg, tmp_path):
    monkeypatch.setitem(REGISTRY, "prem-1b", _spec("prem-1b", sha256="0" * 64))

    def fake_hf_hub_download(repo, file_name, local_dir=None):
        got = tmp_path / "hub" / file_name
        _write(got, b"wrong")
        return str(got)

    monkeypatch.setattr(download, "_hf_hub_download", lambda: fake_hf_hub_download)
    with pytest.raises(DownloadFailed, match="sha256 mismatch"):
        download_models(cfg, ["prem-1b"], log=lambda _: None)
    assert not model_path(cfg, "prem-1b").exists()


def test_already_present_skips_download(monkeypatch, cfg):
    payload = b"present"
    target = model_path(cfg, "prem-1b")
    digest = _write(target, payload)
    monkeypatch.setitem(REGISTRY, "prem-1b", _spec("prem-1b", sha256=digest))

    def explode():
        raise AssertionError("must not download")

    monkeypatch.setattr(download, "_hf_hub_download", explode)
    lines = []
    download_models(cfg, ["prem-1b"], log=lines.append)
    assert any("already present" in line for line in lines)


def test_ct2_converts_snapshot(monkeypatch, cfg, tmp_path):
    source = tmp_path / "snapshot"
    digest = _write(source / "model.safetensors", b"weights")
    _write(source / "source.spm", b"s")
    _write(source / "target.spm", b"t")
    monkeypatch.setitem(REGISTRY, "opus-mt-roa-en", _spec("opus-mt-roa-en", sha256=digest))
    monkeypatch.setattr(download, "_snapshot_download", lambda: lambda repo: str(source))
    monkeypatch.setattr(download, "find_spec", lambda name: object())
    commands = []

    def fake_run(command, check=False):
        commands.append(command)
        out = command[command.index("--output_dir") + 1]
        _write(Path(out) / "model.bin", b"converted")

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    download_models(cfg, ["opus-mt-roa-en"], log=lambda _: None)
    target = model_path(cfg, "opus-mt-roa-en")
    assert (target / "model.bin").exists()
    assert (target / "source.spm").exists() and (target / "target.spm").exists()
    assert "ctranslate2.converters.transformers" in commands[0]


def test_ct2_missing_convert_extra_is_reported_before_converting(monkeypatch, cfg, tmp_path):
    source = tmp_path / "snapshot"
    digest = _write(source / "model.safetensors", b"weights")
    monkeypatch.setitem(REGISTRY, "opus-mt-roa-en", _spec("opus-mt-roa-en", sha256=digest))
    monkeypatch.setattr(download, "_snapshot_download", lambda: lambda repo: str(source))
    monkeypatch.setattr(download, "find_spec", lambda name: None)

    def explode(command, check=False):
        raise AssertionError("must not run the converter")

    monkeypatch.setattr(download.subprocess, "run", explode)
    with pytest.raises(DownloadFailed, match="uv sync --extra convert"):
        download_models(cfg, ["opus-mt-roa-en"], log=lambda _: None)


def test_ct2_conversion_failure_surfaces_as_itself(monkeypatch, cfg, tmp_path):
    source = tmp_path / "snapshot"
    digest = _write(source / "model.safetensors", b"weights")
    monkeypatch.setitem(REGISTRY, "opus-mt-roa-en", _spec("opus-mt-roa-en", sha256=digest))
    monkeypatch.setattr(download, "_snapshot_download", lambda: lambda repo: str(source))
    monkeypatch.setattr(download, "find_spec", lambda name: object())

    def fake_run(command, check=False):
        raise download.subprocess.CalledProcessError(137, command)

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    with pytest.raises(download.subprocess.CalledProcessError):
        download_models(cfg, ["opus-mt-roa-en"], log=lambda _: None)


def test_ct2_missing_tokenizer_fails_loudly(monkeypatch, cfg, tmp_path):
    source = tmp_path / "snapshot"
    digest = _write(source / "model.safetensors", b"weights")
    _write(source / "source.spm", b"s")
    monkeypatch.setitem(REGISTRY, "opus-mt-roa-en", _spec("opus-mt-roa-en", sha256=digest))
    monkeypatch.setattr(download, "_snapshot_download", lambda: lambda repo: str(source))
    monkeypatch.setattr(download, "find_spec", lambda name: object())

    def fake_run(command, check=False):
        out = command[command.index("--output_dir") + 1]
        _write(Path(out) / "model.bin", b"converted")

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    with pytest.raises(DownloadFailed, match="target.spm"):
        download_models(cfg, ["opus-mt-roa-en"], log=lambda _: None)
    assert not FileModelStatus(cfg).ready()


def test_ct2_already_present_skips(monkeypatch, cfg):
    target = model_path(cfg, "opus-mt-roa-en")
    for name in ("model.bin", "source.spm", "target.spm"):
        _write(target / name, b"x")

    def explode():
        raise AssertionError("must not download")

    monkeypatch.setattr(download, "_snapshot_download", explode)
    lines = []
    download_models(cfg, ["opus-mt-roa-en"], log=lines.append)
    assert any("already present" in line for line in lines)


def test_ct2_half_built_directory_is_not_present(monkeypatch, cfg, tmp_path):
    target = model_path(cfg, "opus-mt-roa-en")
    _write(target / "model.bin", b"x")
    source = tmp_path / "snapshot"
    digest = _write(source / "model.safetensors", b"weights")
    _write(source / "source.spm", b"s")
    _write(source / "target.spm", b"t")
    monkeypatch.setitem(REGISTRY, "opus-mt-roa-en", _spec("opus-mt-roa-en", sha256=digest))
    monkeypatch.setattr(download, "_snapshot_download", lambda: lambda repo: str(source))
    monkeypatch.setattr(download, "find_spec", lambda name: object())
    monkeypatch.setattr(download.subprocess, "run", lambda command, check=False: None)
    download_models(cfg, ["opus-mt-roa-en"], log=lambda _: None)
    assert (target / "source.spm").is_file() and (target / "target.spm").is_file()


def test_unknown_key_names_the_valid_ones(cfg):
    with pytest.raises(ConfigRejected) as exc:
        download_models(cfg, ["nope"], log=lambda _: None)
    assert "nope" in str(exc.value) and "xiyansql-3b" in str(exc.value)
