import hashlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from importlib.util import find_spec
from pathlib import Path

from quietsql.adapters.llm.registry import ModelSpec, model_path, resolve_spec
from quietsql.adapters.llm.status import CT2_FILES, ct2_ready
from quietsql.config import Config
from quietsql.core.errors import DownloadFailed

WEIGHT_NAMES = ("model.safetensors", "pytorch_model.bin")
TOKENIZER_NAMES = ("source.spm", "target.spm")
CONVERTER = "ctranslate2.converters.transformers"
CONVERT_PACKAGES = ("transformers", "torch")
CONVERT_HINT = (
    "the CTranslate2 converter needs transformers and torch: "
    "run `uv sync --extra convert` in the quietsql checkout, then download-models again"
)


def _hf_hub_download():
    from huggingface_hub import hf_hub_download

    return hf_hub_download


def _snapshot_download():
    from huggingface_hub import snapshot_download

    return snapshot_download


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_gguf(spec: ModelSpec, target: Path, log: Callable[[str], None]) -> None:
    log(f"downloading {spec.repo}/{spec.file_name} ({spec.size_mb} MB, {spec.license})")
    got = Path(_hf_hub_download()(spec.repo, spec.file_name, local_dir=target.parent))
    if got != target:
        shutil.move(str(got), str(target))
    actual = sha256_of(target)
    if actual != spec.sha256:
        target.unlink()
        raise DownloadFailed(f"sha256 mismatch for {spec.file_name}: {actual}")
    log(f"verified {target.name}")


def _download_ct2(spec: ModelSpec, target: Path, log: Callable[[str], None]) -> None:
    log(f"downloading {spec.repo} for conversion ({spec.size_mb} MB, {spec.license})")
    source = Path(_snapshot_download()(spec.repo))
    weights = next((source / name for name in WEIGHT_NAMES if (source / name).is_file()), None)
    if weights is None:
        raise DownloadFailed(f"no weights found in {spec.repo}")
    actual = sha256_of(weights)
    if actual != spec.sha256:
        raise DownloadFailed(f"sha256 mismatch for {spec.repo}/{weights.name}: {actual}")
    missing = [name for name in CONVERT_PACKAGES if find_spec(name) is None]
    if missing:
        raise DownloadFailed(CONVERT_HINT)
    log("converting to CTranslate2 int8")
    command = [
        sys.executable,
        "-m",
        CONVERTER,
        "--model",
        str(source),
        "--output_dir",
        str(target),
        "--quantization",
        "int8",
        "--force",
    ]
    subprocess.run(command, check=True)
    for name in TOKENIZER_NAMES:
        if (target / name).is_file():
            continue
        origin = source / name
        if not origin.is_file():
            raise DownloadFailed(
                f"{spec.repo} has no {name}; the translator cannot be built from it"
            )
        shutil.copy(origin, target / name)
    missing_files = [name for name in CT2_FILES if not (target / name).is_file()]
    if missing_files:
        raise DownloadFailed(f"conversion left {target.name} without {', '.join(missing_files)}")
    log(f"ready {target.name}")


def _present(spec: ModelSpec, target: Path) -> bool:
    if spec.kind == "ct2":
        return ct2_ready(target)
    return target.is_file() and sha256_of(target) == spec.sha256


def download_models(cfg: Config, keys: Sequence[str], log: Callable[[str], None] = print) -> None:
    specs = [resolve_spec(key) for key in keys]
    (cfg.cache_dir / "models").mkdir(parents=True, exist_ok=True)
    for spec in specs:
        target = model_path(cfg, spec.key)
        if _present(spec, target):
            log(f"already present {target.name}")
            continue
        if spec.kind == "gguf":
            _download_gguf(spec, target, log)
        else:
            _download_ct2(spec, target, log)
