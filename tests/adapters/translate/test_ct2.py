import os
from pathlib import Path

import pytest

from quietsql.adapters.translate.ct2 import Ct2Translator

MODEL_DIR = Path(os.path.expanduser("~/.cache/quietsql/models/opus-mt-roa-en-ct2"))


@pytest.mark.slow
@pytest.mark.skipif(not MODEL_DIR.exists(), reason="run quietsql download-models first")
def test_translates_portuguese_keeping_identifiers():
    t = Ct2Translator(MODEL_DIR)
    out = t.translate("quantas vendas por cliente em 'Recife' desde 2026-03-01", ["vendas"])
    assert "vendas" in out and "'Recife'" in out and "2026-03-01" in out
    assert "customer" in out.lower() or "client" in out.lower()
