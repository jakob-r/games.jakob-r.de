"""Typo-tolerant guess matching for Emoji Charades."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

LEADING_ARTICLES = frozenset({"der", "die", "das", "ein", "eine", "the", "a", "an"})
UMLAUT_SPELLINGS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _canonical(text: str) -> str:
    """Lowercase ASCII letters/digits without spaces or a leading article."""
    cleaned = _NON_ALNUM.sub(" ", _strip_accents(text.casefold().replace("ß", "ss")))
    words = cleaned.split()
    if len(words) > 1 and words[0] in LEADING_ARTICLES:
        words = words[1:]
    return "".join(words)


def normalize_variants(text: str) -> set[str]:
    """Canonical forms of an answer: umlauts both stripped (ö→o) and spelled out (ö→oe)."""
    variants = {_canonical(text), _canonical(text.casefold().translate(UMLAUT_SPELLINGS))}
    variants.discard("")
    return variants


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def allowed_typos(answer: str) -> int:
    length = len(answer)
    if length <= 3:
        return 0
    if length <= 6:
        return 1
    if length <= 12:
        return 2
    return 3


def _distances(guess: str, answers: Iterable[str]) -> list[tuple[str, int]]:
    guess_forms = normalize_variants(guess)
    return [
        (target, min(levenshtein(g, target) for g in guess_forms))
        for answer in answers
        for target in normalize_variants(answer)
        if guess_forms
    ]


def is_match(guess: str, answers: Iterable[str]) -> bool:
    return any(dist <= allowed_typos(target) for target, dist in _distances(guess, answers))


def is_close(guess: str, answers: Iterable[str]) -> bool:
    """Near miss worth a "close!" hint (only meaningful when is_match is False)."""
    guess_forms = normalize_variants(guess)
    for target, dist in _distances(guess, answers):
        if len(target) >= 5 and dist <= allowed_typos(target) + 2:
            return True
        if len(target) >= 4 and any(
            len(g) >= 4 and (g in target or target in g) for g in guess_forms
        ):
            return True
    return False
