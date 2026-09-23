from dataclasses import dataclass
from pathlib import Path

from quietsql.config import Config
from quietsql.core.errors import ConfigRejected


@dataclass(frozen=True)
class ModelSpec:
    key: str
    kind: str
    repo: str
    file_name: str
    sha256: str
    size_mb: int
    license: str


REGISTRY: dict[str, ModelSpec] = {
    "xiyansql-3b": ModelSpec(
        "xiyansql-3b",
        "gguf",
        "mradermacher/XiYanSQL-QwenCoder-3B-2504-GGUF",
        "XiYanSQL-QwenCoder-3B-2504.Q4_K_M.gguf",
        "de8d9ca0af1c4e0596d5b3fea836204f875458ef1e5b7cf68b21578dcf937a47",
        1841,
        "Apache-2.0",
    ),
    "prem-1b": ModelSpec(
        "prem-1b",
        "gguf",
        "mradermacher/prem-1B-SQL-GGUF",
        "prem-1B-SQL.Q4_K_M.gguf",
        "aad72e9343f8c3e64dff0e9bfa1783bdd8eef2822dc3fda065cff42578ee06bf",
        833,
        "Apache-2.0",
    ),
    "opus-mt-roa-en": ModelSpec(
        "opus-mt-roa-en",
        "ct2",
        "Helsinki-NLP/opus-mt-tc-bible-big-roa-en",
        "opus-mt-roa-en-ct2",
        "4266334d15e1d8b427aabd21d68c4c73b1feab2dd7a0160b4651b1663751a3b0",
        890,
        "Apache-2.0",
    ),
}


def resolve_spec(key: str) -> ModelSpec:
    spec = REGISTRY.get(key)
    if spec is None:
        known = ", ".join(sorted(REGISTRY))
        raise ConfigRejected(f"unknown model {key!r}; known models are {known}")
    return spec


def model_path(cfg: Config, key: str) -> Path:
    return cfg.cache_dir / "models" / resolve_spec(key).file_name
