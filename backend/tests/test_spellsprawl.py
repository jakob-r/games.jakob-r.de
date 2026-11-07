"""Unit and integration tests for Spellsprawl."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.core.dictionary import get_letter_score
from games_platform.games.spellsprawl import game as game_module
from games_platform.games.spellsprawl.board import bounding_area
from games_platform.games.spellsprawl.game import SpellsprawlGame
from games_platform.main import create_app

WORDS = {"HAUS", "MAUS", "HAT", "AU", "SO", "TOR", "UM", "HUT", "OH"}

A, B = "player_a", "player_b"


@pytest.fixture(autouse=True)
def fake_dictionary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_module, "is_valid_word", lambda word, lang: word in WORDS)


def new_state(config: dict[str, Any] | None = None) -> tuple[SpellsprawlGame, dict[str, Any]]:
    game = SpellsprawlGame()
    return game, game.create_initial_state(config or {"language": "de"}, [A, B])


def submit(
    game: SpellsprawlGame,
    state: dict[str, Any],
    player: str,
    row: int,
    col: int,
    letters: str,
    direction: str = "right",
    skip: set[int] | None = None,
):
    """Place `letters` from (row, col) along direction, skipping indices in `skip` (existing)."""
    dr, dc = (0, 1) if direction == "right" else (1, 0)
    placements = [
        {"row": row + i * dr, "col": col + i * dc, "letter": ch}
        for i, ch in enumerate(letters)
        if i not in (skip or set())
    ]
    return game.apply_action(
        state,
        {},
        player,
        {"type": "submit_word", "placements": placements, "direction": direction},
        1.0,
    )


def reason(outcome) -> str:
    return outcome.events[0]["reason"]


def score(letter: str) -> int:
    return get_letter_score(letter, "de")


def test_first_word_scores_zero_and_turn_advances() -> None:
    game, state = new_state()
    out = submit(game, state, A, 0, 0, "HAUS")
    assert out.events[0]["type"] == "word_played"
    assert out.points_delta == 0
    assert out.state["current_player_id"] == B
    assert out.state["cells"]["0,3"]["letter"] == "S"
    assert out.state["area"] == 4


def test_reusing_letters_scores_their_rarity() -> None:
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "HAUS").state
    # MAUS down through the A of HAUS at (0,1): M at (-1,1), A existing, U, S new.
    out = submit(game, state, B, -1, 1, "MAUS", "down", skip={1})
    assert out.events[0]["type"] == "word_played"
    assert out.points_delta == score("A")
    assert out.state["player_scores"][B] == score("A")
    assert out.state["area"] == 4 * 4


def test_island_word_scores_zero() -> None:
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "HAUS").state
    out = submit(game, state, B, 10, 10, "TOR")
    assert out.events[0]["type"] == "word_played"
    assert out.points_delta == 0


def test_cross_words_are_validated_and_scored() -> None:
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "HAT").state  # H(0,0) A(0,1) T(0,2)

    # "UM" in row 1 from col 1: U under A forms AU (valid), M under T forms TM (invalid).
    bad = submit(game, state, B, 1, 1, "UM")
    assert reason(bad) == "not_in_dictionary"
    assert bad.events[0]["word"] == "TM"
    assert bad.state["current_player_id"] == B

    # A single letter whose run in the given direction is too short extends the other way.
    single = game.apply_action(
        state,
        {},
        B,
        {"type": "submit_word", "placements": [{"row": 1, "col": 1, "letter": "U"}]},
        1.0,
    )
    assert single.events[0]["type"] == "word_played"
    assert single.events[0]["word"] == "AU"
    assert single.points_delta == score("A")

    # "HUT" in row 1 reusing that U: the new H under H forms the invalid cross-word HH.
    out = submit(game, single.state, A, 1, 0, "HUT", skip={1})
    assert reason(out) == "not_in_dictionary"
    assert out.events[0]["word"] == "HH"


def test_scoring_counts_existing_letters_in_cross_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_module, "is_valid_word", lambda word, lang: word in WORDS | {"OR"})
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "SO").state  # S(0,0) O(0,1)
    state = submit(game, state, B, 5, 5, "OH").state
    # "TOR" in row 1 from col -1 forms cross-words SO (repeating a played word is fine) and OR.
    out = submit(game, state, A, 1, -1, "TOR")
    assert out.events[0]["type"] == "word_played"
    assert sorted(out.events[0]["cross_words"]) == ["OR", "SO"]
    assert out.points_delta == score("S") + score("O")


def test_geometry_rejections() -> None:
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "HAUS").state

    def place(cells: list[tuple[int, int, str]]):
        return game.apply_action(
            state,
            {},
            B,
            {
                "type": "submit_word",
                "placements": [{"row": r, "col": c, "letter": ch} for r, c, ch in cells],
            },
            1.0,
        )

    assert reason(place([(0, 0, "M")])) == "occupied"
    assert reason(place([(5, 5, "T"), (6, 6, "O")])) == "not_in_line"
    assert reason(place([(5, 5, "T"), (5, 7, "O")])) == "gap"
    assert reason(place([(5, 5, "T")])) == "too_short"
    assert reason(place([(5, 5, "1"), (5, 6, "O")])) == "invalid_letter"
    assert reason(place([])) == "empty"
    # Letters touching the end of HAUS extend it into one run, HAUSTO.
    assert reason(place([(0, 4, "T"), (0, 5, "O")])) == "not_in_dictionary"


def test_already_played_word_rejected() -> None:
    game, state = new_state()
    state = submit(game, state, A, 0, 0, "HAUS").state
    out = submit(game, state, B, 5, 0, "HAUS")
    assert reason(out) == "already_played"


def test_not_your_turn_and_late_join() -> None:
    game, state = new_state()
    out = submit(game, state, B, 0, 0, "HAUS")
    assert reason(out) == "not_your_turn"
    late = game.apply_action(state, {}, "player_c", {"type": "pass_turn"}, 1.0)
    assert "player_c" in late.state["turn_order"]


def test_end_conditions() -> None:
    game, state = new_state({"end_condition": "words", "end_target": 5})
    for i, word in enumerate(["HAUS", "MAUS", "HAT", "TOR", "HUT"]):
        player = A if i % 2 == 0 else B
        out = submit(game, state, player, i * 3, 0, word)
        state = out.state
        assert out.is_finished == (i == 4)

    game, state = new_state({"end_condition": "area", "end_target": 50})
    state = submit(game, state, A, 0, 0, "HAUS").state
    out = submit(game, state, B, 20, 20, "TOR")
    assert out.state["area"] > 50
    assert out.is_finished

    game, state = new_state({"end_condition": "points", "end_target": 50})
    state["player_scores"][B] = 49
    state = submit(game, state, A, 0, 0, "HAUS").state
    out = submit(game, state, B, -1, 1, "MAUS", "down", skip={1})
    assert out.is_finished


def test_pass_limit_ends_game() -> None:
    game, state = new_state()
    finished = []
    for i in range(4):
        out = game.apply_action(state, {}, A if i % 2 == 0 else B, {"type": "pass_turn"}, 1.0)
        state = out.state
        finished.append(out.is_finished)
    assert finished == [False, False, False, True]


def test_config_validation() -> None:
    game = SpellsprawlGame()
    assert game.validate_config({}) == {
        "language": "de",
        "end_condition": "words",
        "end_target": 50,
    }
    cfg = game.validate_config({"language": "EN", "end_condition": "area", "end_target": 1})
    assert cfg == {"language": "en", "end_condition": "area", "end_target": 50}
    assert game.validate_config({"end_condition": "nope"})["end_condition"] == "words"


def test_bounding_area() -> None:
    assert bounding_area({}) == 0
    cells = {"0,0": {"letter": "A"}, "-2,3": {"letter": "B"}}
    assert bounding_area(cells) == 3 * 4


def test_spellsprawl_websocket_lifecycle() -> None:
    app = create_app(database=Database())
    with TestClient(app) as client:
        assert any(g["slug"] == "spellsprawl" for g in client.get("/api/games").json())
        room_id = client.post(
            "/api/rooms",
            json={
                "game_slug": "spellsprawl",
                "host_player_id": "host_sp",
                "host_name": "Anna",
                "host_color": "#2563eb",
                "config": {"language": "de"},
            },
        ).json()["room_id"]

        ws_url_1 = f"/ws/spellsprawl/{room_id}?player_id=host_sp&name=Anna&color=%232563eb"
        ws_url_2 = f"/ws/spellsprawl/{room_id}?player_id=peer_sp&name=Ben&color=%23dc2626"
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            ws1.send_json({"type": "start_game"})
            playing = ws1.receive_json()
            _ = ws2.receive_json()
            assert playing["status"] == "playing"
            assert playing["state"]["current_player_id"] == "host_sp"
            assert playing["state"]["letter_scores"]["Q"] == 10

            ws1.send_json(
                {
                    "type": "game_action",
                    "action": {
                        "type": "submit_word",
                        "placements": [
                            {"row": 0, "col": i, "letter": ch} for i, ch in enumerate("HAUS")
                        ],
                    },
                }
            )
            event = ws1.receive_json()
            assert event["type"] == "word_played"
            _ = ws2.receive_json()
            after = ws1.receive_json()
            assert after["state"]["current_player_id"] == "peer_sp"
            assert after["state"]["cells"]["0,0"]["letter"] == "H"
