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
