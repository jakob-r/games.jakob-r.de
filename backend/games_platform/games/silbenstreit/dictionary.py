"""Language dictionaries, letter rarity scores (1-10), and syllable-based board generation."""

from __future__ import annotations

import functools
import random
import unicodedata
from dataclasses import dataclass

from wordfreq import top_n_list, zipf_frequency

SUPPORTED_LANGUAGES: tuple[str, ...] = ("de", "en", "fr", "es")
DEFAULT_LANGUAGE = "de"

VOWELS = frozenset("AEIOU")

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
    "en": (
        "AA", "AB", "AD", "AE", "AG", "AH", "AI", "AL", "AM", "AN", "AR", "AS", "AT", "AW", "AX", "AY",
        "BA", "BE", "BI", "BO", "BY", "DA", "DE", "DO", "ED", "EF", "EH", "EL", "EM", "EN", "ER", "ES",
        "ET", "EW", "EX", "FA", "FE", "GI", "GO", "HA", "HE", "HI", "HM", "HO", "ID", "IF", "IN", "IS",
        "IT", "JO", "KA", "KI", "LA", "LI", "LO", "MA", "ME", "MI", "MM", "MO", "MU", "MY", "NA", "NE",
        "NO", "NU", "OD", "OE", "OF", "OH", "OI", "OK", "OM", "ON", "OP", "OR", "OS", "OW", "OX", "OY",
        "PA", "PE", "PI", "PO", "QI", "RE", "SH", "SI", "SO", "TA", "TE", "TI", "TO", "UH", "UM", "UN",
        "UP", "US", "UT", "WE", "WO", "XI", "XU", "YA", "YE", "YO", "ZA",
    ),
    "de": (
        "AB", "AI", "AM", "AN", "AS", "AU", "BI", "DA", "DU", "EI", "ER", "ES", "ET", "EX", "FA", "GO",
        "HA", "HE", "HI", "HM", "HO", "HU", "IM", "IN", "JA", "JE", "JO", "LA", "MI", "MY", "NA", "NE",
        "NO", "NU", "OB", "OD", "OH", "OK", "ON", "OP", "OS", "PI", "PO", "QI", "RE", "SO", "TU", "UI",
        "UL", "UM", "UN", "UR", "UZ", "WO", "XI", "YL", "ZU",
    ),
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

# Fallback syllables per length and language to ensure rich pools for every length 2..4.
FALLBACK_SYLLABLES: dict[str, tuple[str, ...]] = {
    "de": (
        "ER", "EN", "CH", "TE", "DE", "GE", "UN", "IN", "AN", "AU", "EI", "BE", "ZU", "SO", "DA", "WO",
        "SCH", "EIN", "ICH", "UND", "DER", "DIE", "DAS", "VER", "MIT", "AUF", "AUS", "VOR", "BER", "TER",
        "QUA", "QUE", "QUI", "QUO", "MAX", "BOX", "TAXI", "ZUG", "ZEIT", "KOPF", "JAGD", "VOGT", "TYP",
        "SCHA", "SCHE", "SCHI", "SCHO", "SCHU", "NACH", "DOCH", "BUCH", "HOCH", "KANN", "WENN", "DANN",
    ),
    "en": (
        "TH", "HE", "IN", "ER", "AN", "RE", "ON", "AT", "EN", "ND", "TI", "ES", "OR", "TE", "OF", "ED",
        "THE", "AND", "ING", "ENT", "ION", "HER", "FOR", "THA", "NTH", "INT", "ERE", "TIO", "TER", "EST",
        "QUA", "QUE", "QUI", "QUO", "MAX", "BOX", "TAX", "JAZ", "ZOO", "ZIP", "KEY", "JOY", "VEX", "WAX",
        "TION", "THAT", "THER", "WITH", "MENT", "NESS", "ABLE", "FROM", "HAVE", "THIS", "WILL", "YOUR",
    ),
    "fr": (
        "ES", "LE", "DE", "RE", "EN", "ON", "NT", "TE", "OU", "AN", "AI", "SE", "IT", "ME", "NE", "LA",
        "LES", "DES", "QUE", "QUI", "QUA", "QUO", "UNE", "PAR", "SUR", "PAS", "SON", "POU", "DAN", "MAI",
        "POUR", "DANS", "PLUS", "TOUT", "AVEC", "FAIT", "BIEN", "SANS", "DEUX", "JEUX", "VOIX", "PRIX",
        "ZOU", "SKI", "WAX", "YEU", "JOY", "KIL",
    ),
    "es": (
        "DE", "LA", "EL", "EN", "ES", "OS", "AS", "AR", "ER", "IR", "UN", "AL", "SE", "NO", "SI", "ME",
        "QUE", "QUI", "LOS", "LAS", "DEL", "CON", "POR", "UNA", "PAR", "MAS", "SUS", "SON", "DOS", "VER",
        "PARA", "COMO", "PERO", "TODO", "ESTA", "BIEN", "VIDA", "CASA", "ZONA", "JUE", "TAXI", "KILO",
        "WEB", "YATE", "HOY", "FAZ",
    ),
}


@dataclass(frozen=True)
class SyllablePool:
    by_length: dict[int, tuple[tuple[str, ...], tuple[float, ...]]]
    rare_by_length: dict[int, tuple[tuple[str, ...], tuple[float, ...]]]


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


def extract_syllables(word: str) -> list[str]:
    """
    Segment an uppercase A-Z word into 2..4 letter orthographic syllables.
    Keeps multi-letter clusters (especially QU, SCH, CH, CK, PH, SH, TH) intact
    and guarantees that 'Q' never appears in a syllable without 'U'.
    """
    w = word.upper()
    n = len(w)
    if n < 2:
        return []

    if n <= 4:
        if "Q" in w and "QU" not in w:
            return []
        vowel_count = sum(1 for ch in w if ch in VOWELS)
        max_vowels = 2 if ("QU" in w and n == 3) else max(1, n // 2)
        if vowel_count == 0 or vowel_count > max_vowels:
            return []
        return [w]

    # Group atomic multi-letter units so we never split QU, SCH, CH, CK, PH, SH, TH
    units: list[str] = []
    i = 0
    while i < n:
        if w[i : i + 3] == "SCH":
            units.append("SCH")
            i += 3
        elif w[i : i + 2] in ("QU", "CH", "CK", "PH", "SH", "TH", "WH", "GH"):
            units.append(w[i : i + 2])
            i += 2
        else:
            units.append(w[i])
            i += 1

    # Merge units into chunks of 2..4 characters containing a vowel nucleus
    syllables: list[str] = []
    buf = ""
    has_vowel = False

    for u in units:
        u_has_vowel = any(ch in VOWELS or ch == "Y" for ch in u)
        # Keep QU attached to the following vowel
        if buf.endswith("QU") and not has_vowel:
            buf += u
            has_vowel = has_vowel or u_has_vowel
            continue

        if len(buf) + len(u) <= 3:
            buf += u
            has_vowel = has_vowel or u_has_vowel
        elif len(buf) + len(u) == 4 and (not has_vowel or not u_has_vowel):
            buf += u
            has_vowel = has_vowel or u_has_vowel
            syllables.append(buf)
            buf = ""
            has_vowel = False
        else:
            if buf:
                syllables.append(buf)
            buf = u
            has_vowel = u_has_vowel

    if buf:
        if len(buf) == 1 and syllables and len(syllables[-1]) + 1 <= 4:
            syllables[-1] = syllables[-1] + buf
        elif len(buf) >= 2:
            syllables.append(buf)

    valid: list[str] = []
    for syl in syllables:
        if not (2 <= len(syl) <= 4):
            continue
        if "Q" in syl and "QU" not in syl:
            continue
        vowel_count = sum(1 for ch in syl if ch in VOWELS)
        # Every syllable must have at least 1 vowel and at least 1 consonant,
        # and at most half vowels (e.g. 2-letter: 1V+1C; 3-letter: 1V+2C; 4-letter: <=2V+>=2C)
        # Exception: 'QU' + 1 vowel in a 3-letter syllable (like QUE/QUI/QUA) has 2 vowels ('U' + vowel)
        max_vowels = 2 if ("QU" in syl and len(syl) == 3) else max(1, len(syl) // 2)
        if vowel_count == 0 or vowel_count > max_vowels:
            continue
        valid.append(syl)

    return valid


@functools.lru_cache(maxsize=8)
def get_wordlist(language: str) -> frozenset[str]:
    """Load and cache the normalized uppercase A-Z dictionary for a language."""
    lang = normalize_language(language)
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


@functools.lru_cache(maxsize=8)
def get_syllable_pool(language: str) -> SyllablePool:
    """Build and cache weighted orthographic syllable pools (lengths 2, 3, 4) for `language`."""
    lang = normalize_language(language)
    scores = LETTER_SCORES[lang]
    raw_weights: dict[str, float] = {}

    # Seed from top 15,000 words in the language
    for token in top_n_list(lang, 15000):
        if not token.isalpha():
            continue
        zipf = zipf_frequency(token, lang)
        if zipf < 2.5:
            continue
        freq = 10.0 ** (zipf - 6.0)
        for form in normalize_word_forms(token, lang):
            for syl in extract_syllables(form):
                raw_weights[syl] = raw_weights.get(syl, 0.0) + freq

    for syl in FALLBACK_SYLLABLES.get(lang, ()):
        if 2 <= len(syl) <= 4 and ("Q" not in syl or "QU" in syl):
            vowel_count = sum(1 for ch in syl if ch in VOWELS)
            max_vowels = 2 if ("QU" in syl and len(syl) == 3) else max(1, len(syl) // 2)
            if 1 <= vowel_count <= max_vowels:
                raw_weights[syl] = raw_weights.get(syl, 0.0) + 1e-4

    by_length: dict[int, tuple[tuple[str, ...], tuple[float, ...]]] = {}
    rare_by_length: dict[int, tuple[tuple[str, ...], tuple[float, ...]]] = {}

    for length in (2, 3, 4):
        items = [
            (syl, (w ** 0.55))
            for syl, w in sorted(raw_weights.items())
            if len(syl) == length
        ]
        sylls = tuple(s for s, _ in items)
        weights = tuple(w for _, w in items)
        by_length[length] = (sylls, weights)

        rare_items = [
            (s, w)
            for s, w in items
            if any(scores.get(ch, 1) >= 6 for ch in s)
        ]
        rare_by_length[length] = (
            tuple(s for s, _ in rare_items),
            tuple(w for _, w in rare_items),
        )

    return SyllablePool(by_length=by_length, rare_by_length=rare_by_length)


MAX_LETTER_OCCURRENCES = 4


def _allowed_syllable_lengths(remaining: int) -> list[int]:
    """
    Return syllable lengths (in {2, 3, 4}) that can be subtracted from `remaining`
    without leaving a remainder of 1.
    """
    return [
        length
        for length in (2, 3, 4)
        if length <= remaining and (remaining - length) != 1
    ]


def _counts_fit(counts: dict[str, int], letters: str, *, max_count: int) -> bool:
    """Return True if adding `letters` would keep every character at most `max_count`."""
    extra: dict[str, int] = {}
    for ch in letters:
        next_count = counts.get(ch, 0) + extra.get(ch, 0) + 1
        if next_count > max_count:
            return False
        extra[ch] = extra.get(ch, 0) + 1
    return True


def _pick_fitting_syllable(
    rng: random.Random,
    sylls: tuple[str, ...],
    weights: tuple[float, ...],
    counts: dict[str, int],
    *,
    max_count: int,
    max_tries: int = 24,
) -> str | None:
    """Sample a syllable that respects per-letter occurrence limits."""
    if not sylls:
        return None
    for _ in range(max_tries):
        chosen = rng.choices(sylls, weights=weights, k=1)[0]
        if _counts_fit(counts, chosen, max_count=max_count):
            return chosen
    # Exhaustive fallback when random sampling keeps missing fitting syllables
    eligible = [
        (syl, w)
        for syl, w in zip(sylls, weights, strict=True)
        if _counts_fit(counts, syl, max_count=max_count)
    ]
    if not eligible:
        return None
    eligible_sylls, eligible_weights = zip(*eligible, strict=True)
    return rng.choices(tuple(eligible_sylls), weights=tuple(eligible_weights), k=1)[0]


def _apply_syllable(candidate: list[str], counts: dict[str, int], syl: str) -> None:
    candidate.extend(syl)
    for ch in syl:
        counts[ch] = counts.get(ch, 0) + 1


def generate_board(
    size: int,
    language: str,
    *,
    rng: random.Random | None = None,
) -> tuple[list[list[str]], list[list[int]]]:
    """
    Generate a `size x size` grid of uppercase letters and their 1-10 rarity values
    by sampling whole syllables (2..4 letters) according to dampened language frequencies,
    keeping a balanced vowel share (~30%..42%) and at most 4 of any single letter.
    """
    rng = rng or random.Random()
    lang = normalize_language(language)
    pool = get_syllable_pool(lang)
    scores = LETTER_SCORES[lang]
    alphabet = tuple(scores.keys())

    total_cells = size * size
    sampled_letters: list[str] = []

    for attempt in range(8):
        candidate: list[str] = []
        counts: dict[str, int] = {}

        # 1. Guarantee at least one rare-letter syllable (score >= 6, e.g. QU, X, Y, Z, J, K, V)
        rare_lengths = [
            length
            for length in _allowed_syllable_lengths(total_cells)
            if pool.rare_by_length.get(length, ((), ()))[0]
        ]
        if rare_lengths:
            len_weights = [4.0 if length == 3 else 1.5 for length in rare_lengths]
            chosen_len = rng.choices(rare_lengths, weights=len_weights, k=1)[0]
            rare_sylls, rare_weights = pool.rare_by_length[chosen_len]
            first_syl = _pick_fitting_syllable(
                rng, rare_sylls, rare_weights, counts, max_count=MAX_LETTER_OCCURRENCES
            )
            if first_syl is not None:
                _apply_syllable(candidate, counts, first_syl)

        # 2. Fill remaining cells with whole syllables so no cluster (like QU) is ever truncated
        while len(candidate) < total_cells:
            remaining = total_cells - len(candidate)
            valid_lengths = [
                length
                for length in _allowed_syllable_lengths(remaining)
                if pool.by_length.get(length, ((), ()))[0]
            ]
            chosen_syl: str | None = None
            if valid_lengths:
                # Strongly favor 3-letter syllables for natural consonant balance
                len_weights = [
                    5.0 if length == 3 else (2.0 if length == 4 else 1.0)
                    for length in valid_lengths
                ]
                for _ in range(6):
                    chosen_len = rng.choices(valid_lengths, weights=len_weights, k=1)[0]
                    sylls, weights = pool.by_length[chosen_len]
                    chosen_syl = _pick_fitting_syllable(
                        rng, sylls, weights, counts, max_count=MAX_LETTER_OCCURRENCES
                    )
                    if chosen_syl is not None:
                        break

            if chosen_syl is not None:
                _apply_syllable(candidate, counts, chosen_syl)
                continue

            # Single-letter fill when no fitting syllable remains
            under_cap = [ch for ch in alphabet if counts.get(ch, 0) < MAX_LETTER_OCCURRENCES]
            if not under_cap:
                under_cap = list(alphabet)
            # Prefer vowels when vowel share is low, consonants when high
            vowel_count = sum(1 for ch in candidate if ch in VOWELS)
            target_vowel = len(candidate) > 0 and (vowel_count / len(candidate)) < 0.32
            preferred = [ch for ch in under_cap if (ch in VOWELS) == target_vowel] or under_cap
            ch = rng.choice(preferred)
            candidate.append(ch)
            counts[ch] = counts.get(ch, 0) + 1

        sampled_letters = candidate[:total_cells]
        vowel_ratio = sum(1 for ch in sampled_letters if ch in VOWELS) / total_cells
        if 0.25 <= vowel_ratio <= 0.44 or attempt == 7:
            break

    rng.shuffle(sampled_letters)

    letters_grid: list[list[str]] = []
    values_grid: list[list[int]] = []
    for r in range(size):
        row_letters = sampled_letters[r * size : (r + 1) * size]
        row_values = [scores.get(ch, 1) for ch in row_letters]
        letters_grid.append(row_letters)
        values_grid.append(row_values)

    return letters_grid, values_grid
