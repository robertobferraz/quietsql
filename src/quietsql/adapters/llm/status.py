from pathlib import Path

from quietsql.adapters.llm.registry import model_path
from quietsql.config import Config

TRANSLATION_KEY = "opus-mt-roa-en"
CT2_FILES = ("model.bin", "source.spm", "target.spm")


def ct2_ready(directory: Path) -> bool:
    return all((directory / name).is_file() for name in CT2_FILES)


class FileModelStatus:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def ready(self) -> bool:
        gguf = model_path(self.cfg, self.cfg.model)
        return gguf.is_file() and ct2_ready(model_path(self.cfg, TRANSLATION_KEY))

    def model_id(self) -> str:
        return self.cfg.model
