"""Shared word dictionaries and per-language letter rarity scores (1-10).

Languages with a bundled word list (`BUNDLED_WORDLISTS`) use only that list. Others fall back
to `wordfreq` (top 75k tokens) plus curated 2-letter words.
German: enz/german-wordlist (CC0), a full-form list built for word games.
English: ENABLE (public domain), the classic word-game list incl. inflections.
"""

from __future__ import annotations

import functools
import gzip
import unicodedata
from pathlib import Path

from wordfreq import top_n_list, zipf_frequency

SUPPORTED_LANGUAGES: tuple[str, ...] = ("de", "en", "fr", "es")
DEFAULT_LANGUAGE = "de"

_DATA_DIR = Path(__file__).parent / "data"
# Bundled full word lists (one UTF-8 word per line, gzipped); these replace wordfreq.
BUNDLED_WORDLISTS: dict[str, str] = {"de": "de_words.txt.gz", "en": "en_words.txt.gz"}

# Integer rarity scores between 1 and 10 per language (higher = rarer letter).
LETTER_SCORES: dict[str, dict[str, int]] = {
    "en": {
        "E": 1,
        "A": 1,
        "I": 1,
        "O": 1,
        "N": 1,
        "R": 1,
        "T": 1,
        "L": 2,
        "S": 2,
        "U": 2,
        "D": 2,
        "G": 3,
        "B": 3,
        "C": 3,
        "M": 3,
        "P": 3,
        "F": 4,
        "H": 4,
        "V": 5,
        "W": 5,
        "Y": 5,
        "K": 6,
        "J": 8,
        "X": 8,
        "Q": 10,
        "Z": 10,
    },
    "de": {
        "E": 1,
        "N": 1,
        "S": 1,
        "I": 1,
        "R": 1,
        "T": 1,
        "U": 1,
        "A": 1,
        "D": 2,
        "H": 2,
        "G": 2,
        "L": 2,
        "O": 2,
        "M": 3,
        "B": 3,
        "W": 3,
        "Z": 3,
        "C": 4,
        "F": 4,
        "K": 4,
        "P": 4,
        "V": 6,
        "J": 6,
        "X": 8,
        "Y": 10,
        "Q": 10,
    },
    "fr": {
        "E": 1,
        "A": 1,
        "I": 1,
        "S": 1,
        "N": 1,
        "R": 1,
        "T": 1,
        "O": 1,
        "L": 2,
        "U": 2,
        "D": 2,
        "C": 3,
        "M": 3,
        "P": 3,
        "G": 4,
        "B": 4,
        "V": 4,
        "H": 5,
        "F": 5,
        "Q": 7,
        "Y": 8,
        "X": 8,
        "J": 8,
        "K": 10,
        "W": 10,
        "Z": 10,
    },
    "es": {
        "E": 1,
        "A": 1,
        "O": 1,
        "S": 1,
        "R": 1,
        "N": 1,
        "I": 1,
        "D": 2,
        "L": 2,
        "C": 2,
        "T": 2,
        "U": 2,
        "M": 3,
        "P": 3,
        "B": 3,
        "G": 4,
        "V": 4,
        "Y": 5,
        "Q": 6,
        "H": 6,
        "F": 6,
        "Z": 7,
        "J": 8,
        "X": 8,
        "K": 10,
        "W": 10,
    },
}

# Standard valid 2-letter words per language to ensure classic Scrabble-style short plays work reliably.
EXTRA_VALID_WORDS: dict[str, tuple[str, ...]] = {
    "fr": (
        "AA", "AH", "AI", "AN", "AS", "AU", "AY", "BI", "BU", "CA", "CE", "CI", "DA", "DE", "DO", "DU",
        "EH", "EN", "ES", "ET", "EU", "EX", "FA", "FI", "GO", "HA", "HE", "HI", "HO", "IF", "IL", "IN",
        "JE", "KA", "LA", "LE", "LI", "LU", "MA", "ME", "MI", "MU", "NA", "NE", "NI", "NO", "NU", "OC",
        "OH", "OM", "ON", "OR", "OS", "OU", "PI", "PU", "QI", "RA", "RE", "RI", "RU", "SA", "SE", "SI",
        "SU", "TA", "TE", "TI", "TU", "UN", "US", "UT", "VA", "VE", "VS", "VU", "WU", "XI",
    ),
    "es": (
        "AH", "AL", "AR", "AS", "AY", "CA", "CE", "DA", "DE", "DI", "DO", "EA", "EH", "EL", "EN", "ES",
        "ET", "EX", "FA", "FE", "FU", "GE", "HA", "HE", "HI", "ID", "IR", "JA", "JE", "JI", "JO", "JU",
        "KA", "LA", "LE", "LO", "ME", "MI", "MU", "NA", "NI", "NO", "OA", "OC", "OH", "OI", "OS", "OX",
        "PA", "PE", "PI", "PO", "PU", "RO", "SE", "SI", "SO", "SU", "TA", "TE", "TI", "TU", "UF", "UH",
        "UN", "VA", "VE", "VI", "YA", "YO",
    ),
}


def normalize_language(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    cleaned = lang.strip().lower()
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned
    return DEFAULT_LANGUAGE


def get_letter_score(letter: str, language: str) -> int:
    lang = normalize_language(language)
    scores = LETTER_SCORES.get(lang, LETTER_SCORES[DEFAULT_LANGUAGE])
    return scores.get(letter.upper(), 1)


def _strip_accents(raw: str) -> str:
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_word_forms(raw_word: str, language: str) -> list[str]:
    """
    Convert a dictionary token into valid uppercase A-Z forms.
    For German, both stripped-umlaut (BÄR -> BAR) and digraph-expanded (BÄR -> BAER, ß -> SS)
    forms are accepted if purely alphabetical A-Z.
    """
    lowered = raw_word.strip().lower()
    if not lowered or len(lowered) < 2:
        return []

    candidates: set[str] = set()

    # Standard accent-stripped form (with ß -> ss and œ -> oe, æ -> ae)
    base_replaced = (
        lowered.replace("ß", "ss")
        .replace("œ", "oe")
        .replace("æ", "ae")
    )
    stripped = _strip_accents(base_replaced).upper()
    if len(stripped) >= 2 and stripped.isascii() and stripped.isalpha():
        candidates.add(stripped)

    if language == "de" and any(ch in lowered for ch in ("ä", "ö", "ü")):
        expanded = (
            base_replaced.replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
        )
        expanded_clean = _strip_accents(expanded).upper()
        if len(expanded_clean) >= 2 and expanded_clean.isascii() and expanded_clean.isalpha():
            candidates.add(expanded_clean)

    return list(candidates)


def _load_bundled_wordlist(lang: str, filename: str) -> frozenset[str]:
    words: set[str] = set()
    with gzip.open(_DATA_DIR / filename, "rt", encoding="utf-8") as fh:
        for line in fh:
            token = line.strip()
            if not token.isalpha():
                continue
            for form in normalize_word_forms(token, lang):
                if 2 <= len(form) <= 15:
                    words.add(form)
    return frozenset(words)


@functools.lru_cache(maxsize=8)
def get_wordlist(language: str) -> frozenset[str]:
    """Load and cache the normalized uppercase A-Z dictionary for a language."""
    lang = normalize_language(language)
    bundled = BUNDLED_WORDLISTS.get(lang)
    if bundled:
        return _load_bundled_wordlist(lang, bundled)

    words: set[str] = set(EXTRA_VALID_WORDS.get(lang, ()))
    raw_tokens = top_n_list(lang, 75000)
    for token in raw_tokens:
        if not token.isalpha():
            continue
        # For 2-letter words from noisy web corpora, require higher Zipf frequency unless in EXTRA_VALID_WORDS
        if len(token) == 2 and zipf_frequency(token, lang) < 4.3:
            continue
        for form in normalize_word_forms(token, lang):
            if 2 <= len(form) <= 15:
                words.add(form)

    return frozenset(words)


def is_valid_word(word: str, language: str) -> bool:
    """Return True if `word` (2+ uppercase A-Z letters) is in the language dictionary."""
    cleaned = word.strip().upper()
    if len(cleaned) < 2 or not cleaned.isascii() or not cleaned.isalpha():
        return False
    return cleaned in get_wordlist(language)
