"""A player joining a game that is being played alone gets the turn right away."""

from __future__ import annotations

from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.games.fragmentory.game import fragmentory_game
from games_platform.games.north_south_sort.game import north_south_sort_game
from games_platform.main import create_app


def _receive_state(ws) -> dict:
    while True:
        msg = ws.receive_json()
        if msg["type"] == "room_state":
            return msg


def _start_solo_and_join(game_slug: str, config: dict, extra_peer: bool = False) -> list[dict]:
    """Host starts alone, then peers join; returns the game state after each join."""
    app = create_app(database=Database())
    states: list[dict] = []
    with TestClient(app) as client:
        room_id = client.post(
            "/api/rooms",
            json={
                "game_slug": game_slug,
                "host_player_id": "host_1",
                "host_name": "Alice",
                "host_color": "#2563eb",
                "config": config,
            },
        ).json()["room_id"]
        url = f"/ws/{game_slug}/{room_id}?color=%23dc2626"
        with client.websocket_connect(f"{url}&player_id=host_1&name=Alice") as ws1:
            _receive_state(ws1)
            ws1.send_json({"type": "start_game"})
            started = _receive_state(ws1)
            assert started["state"]["current_player_id"] == "host_1"
            with client.websocket_connect(f"{url}&player_id=peer_2&name=Bob") as ws2:
                states.append(_receive_state(ws2)["state"])
                if extra_peer:
                    with client.websocket_connect(f"{url}&player_id=peer_3&name=Cid") as ws3:
                        states.append(_receive_state(ws3)["state"])
    return states


def test_joiner_of_solo_silbenstreit_gets_the_turn() -> None:
    (state,) = _start_solo_and_join("silbenstreit", {"size": 5, "language": "de"})
    assert state["turn_order"] == ["host_1", "peer_2"]
    assert state["current_player_id"] == "peer_2"
    assert state["current_turn_index"] == 1


def test_third_player_does_not_take_the_turn() -> None:
    _, state = _start_solo_and_join("spellsprawl", {}, extra_peer=True)
    assert state["turn_order"] == ["host_1", "peer_2", "peer_3"]
    assert state["current_player_id"] == "peer_2"


def test_emoji_charades_keeps_its_explainer() -> None:
    (state,) = _start_solo_and_join("emoji-charades", {})
    assert state["current_player_id"] == "host_1"


def test_north_south_sort_deals_the_joiner_and_restarts_the_clock() -> None:
    state = north_south_sort_game.create_initial_state({}, player_ids=["a"])
    state["turn_started_at"] = "2000-01-01T00:00:00+00:00"
    state["turn_order"] = ["a", "b"]
    state["current_player_id"] = "b"
    state = north_south_sort_game.on_player_joined(state, {}, "b")
    assert state["hands"]["b"]
    assert state["turn_started_at"] != "2000-01-01T00:00:00+00:00"


def test_fragmentory_deals_the_joiner_a_card() -> None:
    state = fragmentory_game.create_initial_state({}, player_ids=["a"])
    state["turn_order"] = ["a", "b"]
    state["current_player_id"] = "b"
    state["current_turn_index"] = 1
    state = fragmentory_game.on_player_joined(state, {}, "b")
    assert "b" in state["hands"]
