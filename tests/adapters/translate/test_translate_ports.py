import pytest

from quietsql.adapters.translate.ct2 import Ct2Translator
from quietsql.adapters.translate.detector import LinguaDetector
from quietsql.ports import LanguageDetector, Translator


@pytest.mark.parametrize(
    ("adapter", "protocol"),
    [(LinguaDetector, LanguageDetector), (Ct2Translator, Translator)],
)
def test_adapter_conforms_to_its_port(conforms_to_port, adapter, protocol):
    conforms_to_port(adapter, protocol)
