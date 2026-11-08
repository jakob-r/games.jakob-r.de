from __future__ import annotations

import pytest

from games_platform.core.dictionary import is_valid_word


@pytest.mark.parametrize(
    "word", ["BETOEREN", "BETOREN", "BETOERT", "HAEUSER", "QUIRLIG", "JA", "ZU", "OEL", "OL"]
)
def test_german_dictionary_knows_rare_and_inflected_words(word: str) -> None:
    assert is_valid_word(word, "de")


@pytest.mark.parametrize("word", ["XYZQ", "QQ", "AAAAAA"])
def test_german_dictionary_rejects_junk(word: str) -> None:
    assert not is_valid_word(word, "de")


@pytest.mark.parametrize("word", ["BEGUILE", "ENCHANTS", "QUAFF", "WIZENED", "AA", "OX"])
def test_english_dictionary_knows_words(word: str) -> None:
    assert is_valid_word(word, "en")


@pytest.mark.parametrize("word", ["JUDITH", "HALLETT", "SJW", "ICRC"])
def test_english_dictionary_rejects_names_and_acronyms(word: str) -> None:
    assert not is_valid_word(word, "en")
