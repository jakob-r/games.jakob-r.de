"""Unit and integration tests for Emoji Charades."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from games_platform.core.db import Database
from games_platform.games.emoji_charades.game import (
    CHOICE_COUNT,
    MAX_EMOJIS_PER_SENTENCE,
    EmojiCharadesGame,
    pick_choices,
)
from games_platform.games.emoji_charades.matching import is_close, is_match
from games_platform.games.emoji_charades.words import CATEGORIES, SUPPORTED_LANGUAGES, WORDS
from games_platform.main import create_app

GAME = EmojiCharadesGame()


def _config(**overrides: Any) -> dict[str, Any]:
    return GAME.validate_config({**GAME.default_config(), **overrides})


def _state(config: dict[str, Any], players: tuple[str, ...] = ("a", "b", "c")) -> dict[str, Any]:
    state = GAME.create_initial_state(config, list(players))
    state["turn_order"] = list(players)
    state["current_player_id"] = players[0]
    state["explainer_id"] = players[0]
    return state


def _explaining(config: dict[str, Any], players: tuple[str, ...] = ("a", "b", "c")) -> dict[str, Any]:
    state = _state(config, players)
    outcome = GAME.apply_action(state, config, players[0], {"type": "choose_word", "index": 0}, 1.0)
    assert outcome.state["phase"] == "explaining"
    return outcome.state


def test_matching_tolerates_typos_umlauts_articles_and_aliases() -> None:
    assert is_match("pizzza", ["Pizza"])
    assert is_match("doener", ["Döner"])
    assert is_match("doner", ["Döner"])
    assert is_match("Herr der Ringe", ["Der Herr der Ringe"])
    assert is_match("the godfather", ["Der Pate", "The Godfather"])
    assert is_match("Strasse", ["Straße"])
    assert is_match("spider man", ["Spider-Man"])
    assert is_match("Houston we have a problem", ["Houston, we have a problem"])
    assert not is_match("hund", ["Hai"])
    assert not is_match("cat", ["Bat"])
    assert not is_match("Lion", ["The Lion King"])
    assert is_close("Lion", ["The Lion King"])
    assert is_close("potter", ["Harry Potter"])
    assert not is_close("banana", ["Harry Potter"])


def test_word_lists_cover_every_category() -> None:
    for lang in SUPPORTED_LANGUAGES:
        texts = [entry.text for entry in WORDS[lang]]
        assert len(texts) == len(set(texts)), lang
        for category in CATEGORIES:
            assert sum(1 for e in WORDS[lang] if e.category == category) >= CHOICE_COUNT


def test_pick_choices_prefers_distinct_unused_categories() -> None:
    used = [entry.text for entry in WORDS["en"][:-2]]
    choices = pick_choices("en", used)
    assert len(choices) == CHOICE_COUNT
    choices = pick_choices("de", [])
    assert len({c["category"] for c in choices}) == CHOICE_COUNT


def test_config_validation() -> None:
    cfg = GAME.validate_config({"mode": "nope", "round_seconds": 5, "language": "fr"})
    assert cfg["mode"] == "in_person"
    assert cfg["round_seconds"] == 30
    assert cfg["language"] == "de"
    assert GAME.validate_config({"round_seconds": 9999})["round_seconds"] == 600


def test_player_view_hides_word_and_choices_from_guessers() -> None:
    config = _config(mode="remote")
    state = _state(config)
    assert len(GAME.get_player_view(state, config, "a")["choices"]) == CHOICE_COUNT
    assert GAME.get_player_view(state, config, "b")["choices"] == []
    assert GAME.get_public_view(state, config)["choices"] == []
    assert "used_words" not in GAME.get_player_view(state, config, "a")

    state = _explaining(config)
    word = state["word"]
    assert GAME.get_player_view(state, config, "a")["word"]["text"] == word["text"]
    guesser_view = GAME.get_player_view(state, config, "b")
    assert guesser_view["word"] == {"category": word["category"]}
    assert word["text"] not in str(guesser_view)

    outcome = GAME.apply_action(state, config, "a", {"type": "give_up"}, 1.0)
    assert GAME.get_player_view(outcome.state, config, "b")["word"]["text"] == word["text"]


def test_remote_round_wrong_close_and_correct_guess() -> None:
    config = _config(mode="remote")
    state = _explaining(config)
    word = state["word"]["text"]

    outcome = GAME.apply_action(
        state, config, "a", {"type": "set_sentences", "sentences": [["🦁", "👑"], ["🎬"]]}, 1.0
    )
    state = outcome.state
    assert state["sentences"] == [["🦁", "👑"], ["🎬"]]

    rejected = GAME.apply_action(state, config, "b", {"type": "set_sentences", "sentences": [[]]}, 1.0)
    assert rejected.state is state
    assert rejected.events[0]["type"] == "action_rejected"

    assert GAME.apply_action(state, config, "a", {"type": "guess", "text": word}, 1.0).events[0][
        "reason"
    ] == "not_allowed"

    wrong = GAME.apply_action(state, config, "b", {"type": "guess", "text": "xyzzy"}, 1.0)
    assert wrong.events[0]["type"] == "guess_wrong"
    assert wrong.points_delta == 0
    state = wrong.state
    assert state["guesses"][-1]["text"] == "xyzzy"

    right = GAME.apply_action(state, config, "c", {"type": "guess", "text": word.lower()}, 1.0)
    assert right.is_correct_entry
    assert right.points_delta == 1.0
    assert right.extra_score_deltas == {}
    assert right.state["phase"] == "reveal"
    assert right.state["current_player_id"] == "b"
    assert right.events[0]["type"] == "round_ended"
    assert right.events[0]["winner_id"] == "c"
    assert right.events[0]["word"] == word
    assert word not in str(right.state["guesses"])


def test_timed_remote_guess_also_scores_explainer() -> None:
    config = _config(mode="remote", timed=True)
    state = _explaining(config)
    assert state["deadline"] is not None
    outcome = GAME.apply_action(state, config, "b", {"type": "guess", "text": state["word"]["text"]}, 1.0)
    assert outcome.points_delta == 1.0
    assert outcome.extra_score_deltas == {"a": 1.0}


def test_in_person_award_scoring() -> None:
    config = _config(mode="in_person")
    state = _explaining(config)
    assert GAME.apply_action(state, config, "b", {"type": "guess", "text": "x"}, 1.0).events[0][
        "reason"
    ] == "not_allowed"
    assert GAME.apply_action(state, config, "a", {"type": "award", "player_id": "a"}, 1.0).events[0][
        "reason"
    ] == "invalid_player"

    untimed = GAME.apply_action(state, config, "a", {"type": "award", "player_id": "c"}, 1.0)
    assert not untimed.is_correct_entry
    assert untimed.points_delta == 0
    assert untimed.extra_score_deltas == {"c": 1.0}
    assert untimed.state["phase"] == "reveal"

    timed_config = _config(mode="in_person", timed=True)
    timed_state = _explaining(timed_config)
    timed = GAME.apply_action(timed_state, timed_config, "a", {"type": "award", "player_id": "b"}, 1.0)
    assert timed.is_correct_entry
    assert timed.points_delta == 1.0
    assert timed.extra_score_deltas == {"b": 1.0}


def test_time_up_only_after_deadline() -> None:
    config = _config(timed=True)
    state = _explaining(config)
    early = GAME.apply_action(state, config, "b", {"type": "time_up"}, 1.0)
    assert early.events[0]["reason"] == "too_early"

    state["deadline"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    late = GAME.apply_action(state, config, "b", {"type": "time_up"}, 1.0)
    assert late.state["phase"] == "reveal"
    assert late.events[0]["reason"] == "time_up"

    untimed_config = _config(timed=False)
    untimed = _explaining(untimed_config)
    assert GAME.apply_action(untimed, untimed_config, "b", {"type": "time_up"}, 1.0).events[0][
        "reason"
    ] == "not_allowed"


def test_explainers_rotate_circularly_including_mid_game_joiner() -> None:
    config = _config()
    state = _state(config, ("a", "b"))
    seen: list[str] = []
    for joiner_round in range(5):
        if joiner_round == 1:
            state["turn_order"].append("late")
        seen.append(state["explainer_id"])
        state = GAME.apply_action(state, config, state["explainer_id"], {"type": "give_up"}, 1.0).state
        state = GAME.apply_action(state, config, "anyone", {"type": "next_round"}, 1.0).state
        assert state["phase"] == "choosing"
    assert seen == ["a", "b", "late", "a", "b"]
    assert state["round_number"] == 6


def test_used_words_are_not_offered_again() -> None:
    config = _config()
    state = _explaining(config)
    chosen = state["word"]["text"]
    for _ in range(10):
        state = GAME.apply_action(state, config, state["explainer_id"], {"type": "give_up"}, 1.0).state
        state = GAME.apply_action(state, config, "a", {"type": "next_round"}, 1.0).state
        assert chosen not in [c["text"] for c in state["choices"]]


def test_sentence_limits() -> None:
    config = _config()
    state = _explaining(config)
    with pytest.raises(ValidationError):
        GAME.apply_action(
            state,
            config,
            "a",
            {"type": "set_sentences", "sentences": [["😀"] * (MAX_EMOJIS_PER_SENTENCE + 1)]},
            1.0,
        )


def test_explainer_removed_mid_round_ends_round() -> None:
    config = _config()
    state = _explaining(config)
    # Simulate the room manager's shared turn_order fix-up.
    state["turn_order"] = ["b", "c"]
    state["current_player_id"] = "b"
    after = GAME.on_player_removed(state, config, "a")
    assert after["phase"] == "reveal"
    assert after["last_result"]["reason"] == "explainer_left"
    assert after["current_player_id"] == "b"
    assert GAME.on_player_removed(state, config, "c") is state


def _recv_state(ws: Any) -> dict[str, Any]:
    while True:
        msg = ws.receive_json()
        if msg["type"] == "room_state":
            return msg


def test_websocket_per_viewer_state_and_host_end_game() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        assert any(g["slug"] == "emoji-charades" for g in client.get("/api/games").json())
        create_res = client.post(
            "/api/rooms",
            json={
                "game_slug": "emoji-charades",
                "host_player_id": "host_e1",
                "host_name": "Anna",
                "host_color": "#2563eb",
                "config": {"mode": "remote"},
            },
        )
        assert create_res.status_code == 200
        room_id = create_res.json()["room_id"]

        ws_url_1 = f"/ws/emoji-charades/{room_id}?player_id=host_e1&name=Anna&color=%232563eb"
        ws_url_2 = f"/ws/emoji-charades/{room_id}?player_id=peer_e2&name=Ben&color=%23dc2626"

        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _recv_state(ws1)
            _recv_state(ws1)
            _recv_state(ws2)

            ws1.send_json({"type": "start_game"})
            s1 = _recv_state(ws1)
            s2 = _recv_state(ws2)
            assert s1["status"] == "playing"
            explainer_id = s1["state"]["explainer_id"]
            by_id = {"host_e1": (ws1, s1), "peer_e2": (ws2, s2)}
            explainer_ws, explainer_state = by_id[explainer_id]
            guesser_id = "peer_e2" if explainer_id == "host_e1" else "host_e1"
            guesser_ws, guesser_state = by_id[guesser_id]
            assert len(explainer_state["state"]["choices"]) == CHOICE_COUNT
            assert guesser_state["state"]["choices"] == []

            explainer_ws.send_json(
                {"type": "game_action", "action": {"type": "choose_word", "index": 0}}
            )
            e_view = _recv_state(explainer_ws)["state"]
            g_view = _recv_state(guesser_ws)["state"]
            word = e_view["word"]["text"]
            assert g_view["word"] == {"category": e_view["word"]["category"]}
            rest = client.get(f"/api/rooms/{room_id}").json()
            assert word not in str(rest["state"])

            guesser_ws.send_json(
                {"type": "game_action", "action": {"type": "guess", "text": word}}
            )
            reveal = _recv_state(guesser_ws)
            _recv_state(explainer_ws)
            assert reveal["state"]["phase"] == "reveal"
            scores = {p["player_id"]: p["score"] for p in reveal["players"]}
            assert scores[guesser_id] == 1
            assert scores[explainer_id] == 0

            ws2.send_json({"type": "end_game"})
            assert ws2.receive_json()["type"] == "error"

            ws1.send_json({"type": "end_game"})
            assert _recv_state(ws1)["status"] == "finished"
            assert _recv_state(ws2)["status"] == "finished"
