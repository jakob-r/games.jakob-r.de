"""Unit and integration tests for Silbenstreit."""

from __future__ import annotations

import random

from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.games.silbenstreit.dictionary import (
    SUPPORTED_LANGUAGES,
    generate_board,
    get_letter_score,
    is_valid_word,
)
from games_platform.games.silbenstreit.game import (
    SilbenstreitGame,
    compute_protected_grid,
)
from games_platform.main import create_app


def test_syllable_board_generation_and_q_accompaniment() -> None:
    """
    Verify board sizes 4..8 across all 4 languages (en, de, fr, es),
    integer letter scores in 1..10, at least one rare letter (score >= 6),
    balanced vowel ratios (<= 48%), and that Q never appears without U on a generated board.
    """
    rng = random.Random(42)
    vowels = set("AEIOU")
    for lang in SUPPORTED_LANGUAGES:
        for size in range(4, 9):
            letters, values = generate_board(size=size, language=lang, rng=rng)
            assert len(letters) == size
            assert len(values) == size
            flat_letters = [ch for row in letters for ch in row]
            flat_values = [val for row in values for val in row]
            assert len(flat_letters) == size * size
            assert all(len(ch) == 1 and ch.isalpha() and ch.isupper() for ch in flat_letters)
            assert all(isinstance(v, int) and 1 <= v <= 10 for v in flat_values)
            assert any(v >= 6 for v in flat_values)
            vowel_ratio = sum(1 for ch in flat_letters if ch in vowels) / len(flat_letters)
            assert 0.20 <= vowel_ratio <= 0.48
            if "Q" in flat_letters:
                assert "U" in flat_letters


def test_dictionary_validation_across_languages() -> None:
    assert is_valid_word("HAUS", "de")
    assert is_valid_word("SPIEL", "de")
    assert is_valid_word("HOUSE", "en")
    assert is_valid_word("MAISON", "fr")
    assert is_valid_word("CASA", "es")
    assert not is_valid_word("A", "en")
    assert not is_valid_word("QZXJV", "en")


def test_protection_and_ownership_stealing() -> None:
    game = SilbenstreitGame()
    config = game.validate_config({"size": 4, "language": "en", "scoring_enabled": True})
    state = game.create_initial_state(config, player_ids=["p1", "p2"])

    # Set up a deterministic 4x4 board where (0,0) can be surrounded by (0,1) and (1,0)
    state["letters"] = [
        ["C", "A", "T", "S"],
        ["O", "R", "E", "D"],
        ["L", "I", "N", "E"],
        ["D", "O", "G", "S"],
    ]
    state["values"] = [
        [get_letter_score(ch, "en") for ch in row] for row in state["letters"]
    ]

    # Turn 1: p1 plays CATS at (0,0), (0,1), (0,2), (0,3) + (1,0) -> let's play "COLD" at (0,0),(1,0),(2,0),(3,0)
    m1 = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 1, "col": 0},
                {"row": 2, "col": 0},
                {"row": 3, "col": 0},
            ],
        },
        player_multiplier=1.0,
    )
    assert m1.is_correct_entry is True
    assert m1.state["current_player_id"] == "p2"
    # (0,0) has orthogonal neighbors (1,0) [owned by p1] and (0,1) [unowned] -> not protected yet
    assert m1.state["protected"][0][0] is False

    # Turn 2: p2 steals (1,0) 'O' by playing "ORE" at (1,0), (1,1), (1,2)
    o_val = state["values"][1][0]
    r_val = state["values"][1][1]
    e_val = state["values"][1][2]
    m2 = game.apply_action(
        state=m1.state,
        config=config,
        player_id="p2",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 1, "col": 0},
                {"row": 1, "col": 1},
                {"row": 1, "col": 2},
            ],
        },
        player_multiplier=1.0,
    )
    assert m2.is_correct_entry is True
    assert m2.points_delta == float(o_val + r_val + e_val)
    # p1 lost ownership of (1,0), so extra_score_deltas credits p1 with -o_val
    assert m2.extra_score_deltas == {"p1": -float(o_val)}
    assert m2.state["owners"][1][0] == "p2"

    # Turn 3: p1 tries to replay "COLD" -> rejected as already_played, stays p1's turn
    dup = game.apply_action(
        state=m2.state,
        config=config,
        player_id="p1",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 1, "col": 0},
                {"row": 2, "col": 0},
                {"row": 3, "col": 0},
            ],
        },
        player_multiplier=1.0,
    )
    assert dup.is_correct_entry is False
    assert dup.events[0]["type"] == "word_rejected"
    assert dup.events[0]["reason"] == "already_played"
    assert dup.state["current_player_id"] == "p1"

    # Turn 3 (retry): p1 plays "CORD" using (0,0) C, (1,0) O, (1,1) R, (1,3) D
    # That gives p1 ownership of (0,0) and (1,0); now let's also include (0,1) A -> "CARD"? No, let's check protection directly:
    owners_grid = [
        ["p1", "p1", None, None],
        ["p1", None, None, None],
        [None, None, None, None],
        [None, None, None, None],
    ]
    prot = compute_protected_grid(4, owners_grid)
    assert prot[0][0] is True  # (0,0) is surrounded by (0,1) and (1,0) which are both 'p1'
    assert prot[0][1] is False  # (0,2) and (1,1) are None

    # Verify p1 CAN reuse their own protected tile (0,0), while p2 CANNOT select p1's protected tile (0,0)
    state_with_prot = m2.state
    state_with_prot["owners"] = owners_grid
    state_with_prot["protected"] = prot

    # p1 reuses their own protected tile (0,0) 'C' to play "CAT" at (0,0),(0,1),(0,2) -> allowed!
    own_prot_attempt = game.apply_action(
        state=state_with_prot,
        config=config,
        player_id="p1",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 0, "col": 1},
                {"row": 0, "col": 2},
            ],
        },
        player_multiplier=1.0,
    )
    assert own_prot_attempt.is_correct_entry is True
    assert own_prot_attempt.state["current_player_id"] == "p2"

    # Now it is p2's turn: p2 tries to use p1's protected tile (0,0) 'C' -> rejected!
    opp_prot_attempt = game.apply_action(
        state=own_prot_attempt.state,
        config=config,
        player_id="p2",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 0, "col": 1},
                {"row": 0, "col": 2},
                {"row": 0, "col": 3},
            ],
        },
        player_multiplier=1.0,
    )
    assert opp_prot_attempt.is_correct_entry is False
    assert opp_prot_attempt.events[0]["reason"] == "protected_tile"


def test_game_ends_when_no_unowned_letters_remain() -> None:
    game = SilbenstreitGame()
    config = game.validate_config({"size": 4, "language": "en"})
    state = game.create_initial_state(config, player_ids=["p1", "p2"])

    state["letters"] = [
        ["C", "A", "T", "S"],
        ["D", "O", "G", "S"],
        ["L", "I", "N", "E"],
        ["B", "I", "R", "D"],
    ]
    # Mark all cells owned except (0,2) 'T' and (0,3) 'S', with (0,0) 'C' and (0,1) 'A' owned by p2 (not protected)
    state["owners"] = [
        ["p2", "p2", None, None],
        ["p1", "p2", "p1", "p2"],
        ["p2", "p1", "p2", "p1"],
        ["p1", "p2", "p1", "p2"],
    ]
    state["protected"] = compute_protected_grid(4, state["owners"])
    state["unowned_count"] = 2

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 0, "col": 1},
                {"row": 0, "col": 2},
                {"row": 0, "col": 3},
            ],
        },
        player_multiplier=1.0,
    )
    assert outcome.is_correct_entry is True
    assert outcome.state["unowned_count"] == 0
    assert outcome.is_finished is True


def test_four_player_turn_rotation_and_multi_steal() -> None:
    game = SilbenstreitGame()
    config = game.validate_config({"size": 4, "language": "en", "scoring_enabled": True})
    state = game.create_initial_state(config, player_ids=["p1", "p2", "p3", "p4"])

    assert state["turn_order"] == ["p1", "p2", "p3", "p4"]
    assert state["current_player_id"] == "p1"

    state["letters"] = [
        ["C", "A", "T", "S"],
        ["D", "O", "G", "S"],
        ["L", "I", "N", "E"],
        ["B", "I", "R", "D"],
    ]
    state["values"] = [
        [get_letter_score(ch, "en") for ch in row] for row in state["letters"]
    ]
    # Pre-assign (0,0) to p2 and (0,1) to p3 so p1 steals from both in one word
    state["owners"][0][0] = "p2"
    state["owners"][0][1] = "p3"

    outcome = game.apply_action(
        state=state,
        config=config,
        player_id="p1",
        action={
            "type": "submit_word",
            "positions": [
                {"row": 0, "col": 0},
                {"row": 0, "col": 1},
                {"row": 0, "col": 2},
            ],
        },
        player_multiplier=1.0,
    )
    assert outcome.is_correct_entry is True
    assert outcome.state["current_player_id"] == "p2"
    assert outcome.extra_score_deltas == {
        "p2": -float(state["values"][0][0]),
        "p3": -float(state["values"][0][1]),
    }


def test_full_multiplayer_silbenstreit_websocket_lifecycle() -> None:
    test_db = Database()
    app = create_app(database=test_db)

    with TestClient(app) as client:
        res = client.get("/api/games")
        assert res.status_code == 200
        games = res.json()
        assert any(g["slug"] == "silbenstreit" for g in games)

        create_res = client.post(
            "/api/rooms",
            json={
                "game_slug": "silbenstreit",
                "host_player_id": "host_s1",
                "host_name": "Anna",
                "host_color": "#2563eb",
                "config": {"size": 4, "language": "de", "scoring_enabled": True},
            },
        )
        assert create_res.status_code == 200
        room_id = create_res.json()["room_id"]

        ws_url_1 = f"/ws/silbenstreit/{room_id}?player_id=host_s1&name=Anna&color=%232563eb"
        ws_url_2 = f"/ws/silbenstreit/{room_id}?player_id=peer_s2&name=Ben&color=%23dc2626"

        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            # Host starts the game
            ws1.send_json({"type": "start_game"})
            playing_1 = ws1.receive_json()
            _ = ws2.receive_json()
            assert playing_1["status"] == "playing"
            assert playing_1["state"]["size"] == 4
            assert playing_1["state"]["language"] == "de"
            assert playing_1["state"]["current_player_id"] == "host_s1"

            # Host passes turn
            ws1.send_json({"type": "game_action", "action": {"type": "pass_turn"}})
            ev_pass = ws1.receive_json()
            assert ev_pass["type"] == "turn_passed"
            _ = ws2.receive_json()

            state_after = ws1.receive_json()
            _ = ws2.receive_json()
            assert state_after["state"]["current_player_id"] == "peer_s2"
