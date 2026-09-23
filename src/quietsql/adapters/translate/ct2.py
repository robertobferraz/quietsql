from collections.abc import Sequence
from pathlib import Path

import ctranslate2
import sentencepiece

from quietsql.core.masking import mask, unmask


class Ct2Translator:
    def __init__(self, model_dir: Path, threads: int = 4) -> None:
        self.translator = ctranslate2.Translator(
            str(model_dir), device="cpu", inter_threads=1, intra_threads=threads
        )
        self.source_sp = sentencepiece.SentencePieceProcessor(
            model_file=str(model_dir / "source.spm")
        )
        self.target_sp = sentencepiece.SentencePieceProcessor(
            model_file=str(model_dir / "target.spm")
        )

    def translate(self, text: str, protected: Sequence[str]) -> str:
        masked, mapping = mask(text, protected)
        tokens = self.source_sp.encode(masked, out_type=str)
        result = self.translator.translate_batch([tokens], beam_size=2, max_decoding_length=128)
        output = self.target_sp.decode(result[0].hypotheses[0])
        return unmask(output, mapping, text)
