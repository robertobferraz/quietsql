import pytest

from quietsql.adapters.translate.detector import PT_FOLDED, LinguaDetector, fold
from quietsql.core.masking import mask
from quietsql.core.models import Language


@pytest.fixture(scope="module")
def detector():
    return LinguaDetector()


def test_detects_portuguese_and_english(detector):
    assert detector.detect("quantas vendas por cliente em março") is Language.PT
    assert detector.detect("how many sales per customer in march") is Language.EN


def test_empty_or_ambiguous_defaults_to_english(detector):
    assert detector.detect("") is Language.EN
    assert detector.detect("123") is Language.EN


@pytest.mark.parametrize(
    "text",
    [
        "vendas do cliente Recife",
        "clientes cadastrados no sistema",
        "listar produtos vendidos",
        "Variação mensal",
        "Média mensal",
        "média por região",
        "QUANTOS CLIENTES COMPRARAM EM MARÇO",
        "total de pedidos por mes",
        "quais os produtos mais vendidos",
        "ticket médio dos clientes de São Paulo",
    ],
)
def test_detects_portuguese(detector, text):
    assert detector.detect(text) is Language.PT


@pytest.mark.parametrize(
    "text",
    [
        "revenue from São Paulo and Brasília",
        "he traveled from São Paulo to Brasília and Goiânia",
        "compare sales between São Paulo and Brasília last quarter",
        "São Paulo revenue by month",
        "list all customers",
        "top products by revenue",
        "Goiânia population growth",
    ],
)
def test_detects_english(detector, text):
    assert detector.detect(text) is Language.EN


def test_english_place_name_only_sentence_is_accepted_pt_leaning(detector):
    assert detector.detect("Brasília store performance") is Language.PT


SCHEMA_IDENTIFIERS = (
    "city",
    "customer",
    "month",
    "orders",
    "products",
    "revenue",
    "sales",
    "year",
)


@pytest.mark.parametrize(
    "text",
    [
        "quantos orders por city",
        "media de revenue por customer",
        "listar products por month",
        "total de sales por city e month",
        "somar revenue por year",
        "mostrar orders e products",
    ],
)
def test_portuguese_over_english_schema_is_portuguese_once_masked(detector, text):
    masked, _ = mask(text, SCHEMA_IDENTIFIERS)
    assert detector.detect(masked) is Language.PT


def test_english_over_english_schema_stays_english_once_masked(detector):
    masked, _ = mask("how many orders per city", SCHEMA_IDENTIFIERS)
    assert detector.detect(masked) is Language.EN


def test_accented_portuguese_words_match_the_folded_word_set(detector):
    assert fold("média") in PT_FOLDED and fold("mês") in PT_FOLDED
    assert fold("últimos") in PT_FOLDED and fold("últimas") in PT_FOLDED
    assert detector.detect("média por região") is Language.PT
