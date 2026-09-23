import re
from collections.abc import Sequence

STRING = r"'[^']*'|\"[^\"]*\""
DATE = r"\b\d{4}-\d{2}(?:-\d{2})?\b|\b\d{2}/\d{2}/\d{4}\b"
NUMBER = r"\b\d+(?:[.,]\d+)?\b"
CODE_TOKEN = r"\b[a-zA-Z]+(?:_[a-zA-Z0-9]+)+\b|\b[a-zA-Z_]+\.[a-zA-Z_]+\b"
PLACEHOLDER = re.compile(r"XQ\d+")
MIN_NAME_LEN = 3
FUNCTION_WORDS = {
    "aos",
    "ate",
    "até",
    "cada",
    "como",
    "com",
    "das",
    "dos",
    "esta",
    "este",
    "entre",
    "isso",
    "mais",
    "menos",
    "nas",
    "nos",
    "não",
    "nao",
    "onde",
    "para",
    "pela",
    "pelo",
    "por",
    "que",
    "quando",
    "sem",
    "seu",
    "sobre",
    "sua",
    "uma",
    "uns",
    "about",
    "after",
    "all",
    "also",
    "and",
    "any",
    "are",
    "been",
    "before",
    "being",
    "but",
    "can",
    "did",
    "does",
    "each",
    "for",
    "from",
    "had",
    "has",
    "have",
    "her",
    "his",
    "how",
    "into",
    "its",
    "more",
    "most",
    "not",
    "over",
    "per",
    "same",
    "should",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "under",
    "very",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
}


def protectable(name: str) -> bool:
    if "_" in name or "." in name:
        return True
    return len(name) >= MIN_NAME_LEN and name.lower() not in FUNCTION_WORDS


def _pattern(protected: Sequence[str]) -> re.Pattern:
    names = sorted({p for p in protected if p and protectable(p)}, key=len, reverse=True)
    parts = [STRING, DATE, NUMBER, CODE_TOKEN]
    if names:
        parts.append(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b")
    return re.compile("|".join(parts), re.IGNORECASE)


def mask(text: str, protected: Sequence[str]) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    keys: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        span = match.group(0)
        key = keys.get(span)
        if key is None:
            key = f"XQ{len(mapping) + 1}"
            keys[span] = key
            mapping[key] = span
        return key

    return _pattern(protected).sub(replace, text), mapping


def unmask(text: str, mapping: dict[str, str], original: str) -> str:
    found = PLACEHOLDER.findall(text)
    if any(key not in found for key in mapping):
        return original
    if mapping and any(f not in mapping for f in found):
        return original
    return PLACEHOLDER.sub(lambda match: mapping.get(match.group(0), match.group(0)), text)
