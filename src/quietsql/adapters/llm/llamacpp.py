import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from llama_cpp import Llama

from quietsql.adapters.llm.extract import extract_sql
from quietsql.adapters.llm.prompt import build_prompt
from quietsql.core.models import Attempt

STOP = [";", "```", "<|im_end|>", "<|endoftext|>"]


class LlamaCppTextToSql:
    def __init__(
        self,
        model_path: Path,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        max_tokens: int = 120,
    ) -> None:
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads or max(1, (os.cpu_count() or 4) - 1),
            verbose=False,
        )
        self.max_tokens = max_tokens
        self._prefill_ms = 0.0

    def generate(
        self,
        schema_ddl: str,
        question: str,
        previous: Sequence[Attempt],
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        prompt = build_prompt(schema_ddl, question, previous)
        if on_token:
            on_token("SELECT")
        started = time.perf_counter()
        first = True
        pieces: list[str] = []
        stream = self.llm(
            prompt, max_tokens=self.max_tokens, stop=STOP, stream=True, temperature=0.0
        )
        try:
            for chunk in stream:
                if first:
                    self._prefill_ms = (time.perf_counter() - started) * 1000
                    first = False
                text = chunk["choices"][0]["text"]
                pieces.append(text)
                if on_token:
                    on_token(text)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
        return extract_sql("SELECT" + "".join(pieces))

    def prefill_ms(self) -> float:
        return self._prefill_ms
