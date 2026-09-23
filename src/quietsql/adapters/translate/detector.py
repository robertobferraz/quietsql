import re
import unicodedata

from lingua import Language as LinguaLanguage
from lingua import LanguageDetectorBuilder

from quietsql.core.models import Language

TOKEN = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)


def fold(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


PT_WORDS = {
    "o",
    "a",
    "os",
    "as",
    "do",
    "da",
    "dos",
    "das",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "que",
    "quantos",
    "quantas",
    "quais",
    "qual",
    "quanto",
    "por",
    "para",
    "em",
    "de",
    "com",
    "sem",
    "mais",
    "cada",
    "entre",
    "todos",
    "todas",
    "ultimos",
    "ultimas",
    "mes",
    "ano",
    "dia",
    "cliente",
    "clientes",
    "vendas",
    "listar",
    "mostrar",
    "somar",
    "media",
    "maior",
    "menor",
}
EN_WORDS = {
    "the",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "how",
    "many",
    "much",
    "which",
    "what",
    "who",
    "when",
    "per",
    "each",
    "all",
    "between",
    "last",
    "top",
    "show",
    "list",
    "count",
    "sum",
    "average",
    "sales",
    "customer",
    "customers",
    "and",
    "or",
    "to",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "does",
    "did",
    "not",
    "but",
    "if",
    "then",
    "there",
    "their",
    "its",
    "it",
    "he",
    "she",
    "they",
    "we",
    "you",
    "that",
    "this",
    "these",
    "those",
    "than",
    "over",
    "under",
    "into",
    "about",
    "after",
    "before",
    "during",
    "where",
    "why",
    "name",
    "revenue",
    "orders",
    "products",
    "month",
    "year",
    "day",
    "city",
}
PT_FOLDED = {fold(w) for w in PT_WORDS}
EN_FOLDED = {fold(w) for w in EN_WORDS}


class LinguaDetector:
    def __init__(self) -> None:
        self._detector = (
            LanguageDetectorBuilder.from_languages(
                LinguaLanguage.PORTUGUESE, LinguaLanguage.ENGLISH
            )
            .with_preloaded_language_models()
            .build()
        )

    def detect(self, text: str) -> Language:
        if not text.strip():
            return Language.EN
        words = {fold(token) for token in TOKEN.findall(text)}
        if len(words & EN_FOLDED) > len(words & PT_FOLDED):
            return Language.EN
        found = self._detector.detect_language_of(text)
        return Language.PT if found == LinguaLanguage.PORTUGUESE else Language.EN
