"""Unit and integration tests for North South Sort."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from games_platform.core.db import Database
from games_platform.games.north_south_sort import game as game_module
from games_platform.games.north_south_sort.game import (
    NorthSouthSortGame,
    base_score,
    gap_degrees,
    speed_factor,
)
from games_platform.games.north_south_sort.locations import Location, load_locations
from games_platform.main import create_app

A, B = "player_a", "player_b"


def loc(id_: str, category: str, lat: float, half: float = 0.1) -> Location:
    return Location(
        id=id_,
        category=category,  # type: ignore[arg-type]
        name_en=f"{id_} en",
        name_de=f"{id_} de",
        lat=lat,
        lon=10.0,
        min_lat=lat - half,
        max_lat=lat + half,
        min_lon=9.9,
        max_lon=10.1,
        bounds_source="default",
        description_en=f"{id_} desc",
        description_de=f"{id_} Beschreibung",
        wikipedia_en=f"https://en.wikipedia.org/wiki/{id_}",
        wikipedia_de=None,
        country_en="Testland",
        country_de="Testland",
        continent="europe",
        fame=3,
        sitelinks=50,
    )


FAKE = [
    loc("C1", "city", 50.0),
    loc("C2", "city", 40.0),
    loc("C3", "city", 60.0),
    loc("C4", "city", 30.0),
    loc("L1", "landmark", 45.0),
    loc("L2", "landmark", 55.0),
    loc("L3", "landmark", 35.0),
    loc("E1", "event", 52.0),
    loc("E2", "event", 20.0),
    loc("E3", "event", 70.0),
]


@pytest.fixture(autouse=True)
def fake_locations(monkeypatch: pytest.MonkeyPatch) -> None:
    by_id = {x.id: x for x in FAKE}
    pools: dict[tuple[str, str], list[str]] = defaultdict(list)
    for x in FAKE:
        pools[(x.continent, x.category)].append(x.id)
        pools[("world", x.category)].append(x.id)
    frozen = {k: tuple(v) for k, v in pools.items()}
    monkeypatch.setattr(game_module, "locations_by_id", lambda: by_id)
    monkeypatch.setattr(game_module, "_pools", lambda: frozen)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(game_module, "_now", c)
    return c


def new_state(
    config: dict[str, Any] | None = None, players: list[str] | None = None
) -> tuple[NorthSouthSortGame, dict[str, Any]]:
    game = NorthSouthSortGame(rng=random.Random(1))
    state = game.create_initial_state(config or {}, players or [A, B])
    return game, state


def setup_board(state: dict[str, Any], axis: list[str], hands: dict[str, dict]) -> None:
    """Force a known axis and hands (ids not dealt elsewhere)."""
    state["axis"] = [{"id": i, "player_id": None} for i in axis]
    state["hands"] = hands
    state["used_ids"] = list(axis) + [i for h in hands.values() for i in h.values() if i]


def act(game: NorthSouthSortGame, state: dict, player: str, action: dict):
    return game.apply_action(state, {}, player, action, 1.0)


def test_initial_state_has_start_city_and_hands() -> None:
    _, state = new_state()
    assert len(state["axis"]) == 1
    start = state["axis"][0]["id"]
    assert start.startswith("C")
    for pid in (A, B):
        hand = state["hands"][pid]
        assert set(hand) == {"city", "landmark", "event"}
        assert hand["city"].startswith("C") and hand["event"].startswith("E")
    dealt = [start] + [i for h in state["hands"].values() for i in h.values()]
    assert len(dealt) == len(set(dealt)) == len(state["used_ids"])
    assert state["current_player_id"] == A and state["round"] == 1


def test_start_city_even_without_city_category() -> None:
    _, state = new_state({"categories": ["event"]})
    assert state["axis"][0]["id"].startswith("C")
    assert set(state["hands"][A]) == {"event"}


def test_correct_placement_scores_value_inserts_and_refills() -> None:
    game, state = new_state()
    setup_board(state, ["C1"], {A: {"landmark": "L2"}, B: {"landmark": "L1"}})
    out = act(game, state, A, {"type": "place", "location_id": "L2", "slot": 1})
    assert out.points_delta == 2 and out.is_correct_entry and not out.is_mistake
    assert [e["id"] for e in out.state["axis"]] == ["C1", "L2"]
    assert out.state["axis"][1]["player_id"] == A
    assert out.state["hands"][A]["landmark"] == "L3"  # the only one left
    assert out.state["current_player_id"] == B
    assert out.events[0]["type"] == "location_placed" and out.events[0]["correct"]
    assert out.events[0]["card"]["lat"] == 55.0
    assert out.state["player_scores"][A] == 2


@pytest.mark.parametrize(
    ("gap", "base"),
    [(40, 1), (10, 1), (5, 2), (4, 3), (2, 5), (1, 10), (0.5, 20), (0.1, 20), (0, 20)],
)
def test_base_score(gap: float, base: int) -> None:
    assert base_score(gap) == base


def test_gap_degrees_runs_to_the_poles() -> None:
    c1 = loc("X", "city", 50.0)
    c2 = loc("Y", "city", 40.0)
    assert gap_degrees(c2, c1) == 10
    assert gap_degrees(c1, None) == 40
    assert gap_degrees(None, c2) == 130


def test_narrow_gap_scores_base_times_category(monkeypatch: pytest.MonkeyPatch) -> None:
    game, state = new_state()
    between = loc("L9", "landmark", 51.0)
    by_id = {**game_module.locations_by_id(), "L9": between}
    monkeypatch.setattr(game_module, "locations_by_id", lambda: by_id)
    setup_board(state, ["C1", "E1"], {A: {"landmark": "L9"}, B: {"landmark": "L1"}})
    out = act(game, state, A, {"type": "place", "location_id": "L9", "slot": 1})
    # Gap 50°–52° = 2° → base 5, landmark ×2.
    assert out.points_delta == 10
    assert out.events[0]["base"] == 5 and out.events[0]["multiplier"] == 2


def test_wrong_in_narrow_gap_costs_category_value(monkeypatch: pytest.MonkeyPatch) -> None:
    game, state = new_state()
    setup_board(state, ["C1", "E1"], {A: {"event": "E3"}, B: {"event": "E2"}})
    out = act(game, state, A, {"type": "place", "location_id": "E3", "slot": 1})
    assert out.points_delta == -3


def test_overlapping_bounds_count_as_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    game, state = new_state()
    state["categories"] = ["city", "event"]
    # A wide card centred north of C1 still fits south of it because the boxes overlap.
    wide = loc("E9", "event", 50.5, half=1.0)
    by_id = {**game_module.locations_by_id(), "E9": wide}
    monkeypatch.setattr(game_module, "locations_by_id", lambda: by_id)
    setup_board(state, ["C1"], {A: {"event": "E9"}, B: {"event": "E1"}})
    out = act(game, state, A, {"type": "place", "location_id": "E9", "slot": 0})
    assert out.is_correct_entry


def test_wrong_placement_is_discarded_and_hidden() -> None:
    game, state = new_state()
    setup_board(state, ["C2", "C1"], {A: {"event": "E3"}, B: {"event": "E2"}})
    out = act(game, state, A, {"type": "place", "location_id": "E3", "slot": 0})
    assert out.points_delta == -3 and out.is_mistake and not out.is_correct_entry
    assert [e["id"] for e in out.state["axis"]] == ["C2", "C1"]
    assert out.state["discarded"] == [{"id": "E3", "player_id": A}]
    assert A in out.state["round_failures"]
    event = out.events[0]
    assert not event["correct"] and event["slot"] == 0
    assert "lat" not in event["card"] and "country" not in event["card"]

    view = game.get_public_view(out.state, {})
    assert view["discarded"] == [] and view["discarded_count"] == 1
    assert "used_ids" not in view
    assert all(
        "lat" not in card and "country" not in card
        for hand in view["hands"].values()
        for card in hand
    )

    out.state["finished"] = True
    view = game.get_public_view(out.state, {})
    assert view["discarded"][0]["lat"] == 70.0


def test_view_language() -> None:
    game, state = new_state({"language": "en"})
    view = game.get_public_view(state, {})
    assert view["axis"][0]["name"].endswith(" en")
    assert view["axis"][0]["wikipedia"].startswith("https://en.")


@pytest.mark.parametrize(("elapsed", "factor"), [(5, 2.0), (10, 2.0), (15, 1.5), (30, 1.0)])
def test_timed_speed_factor(clock: Clock, elapsed: int, factor: float) -> None:
    assert speed_factor(elapsed) == factor
    game, state = new_state({"timed": True})
    setup_board(state, ["C1"], {A: {"city": "C3"}, B: {"city": "C2"}})
    clock.now += timedelta(seconds=elapsed)
    out = act(game, state, A, {"type": "place", "location_id": "C3", "slot": 1})
    assert out.points_delta == pytest.approx(1 * factor)


def test_untimed_has_no_speed_bonus(clock: Clock) -> None:
    game, state = new_state()
    setup_board(state, ["C1"], {A: {"city": "C3"}, B: {"city": "C2"}})
    out = act(game, state, A, {"type": "place", "location_id": "C3", "slot": 1})
    assert out.points_delta == 1


def test_rejections() -> None:
    game, state = new_state()
    setup_board(state, ["C1"], {A: {"city": "C3"}, B: {"city": "C2"}})
    out = act(game, state, B, {"type": "skip"})
    assert out.events[0]["reason"] == "not_your_turn"
    out = act(game, state, A, {"type": "place", "location_id": "C2", "slot": 0})
    assert out.events[0]["reason"] == "not_in_hand"
    out = act(game, state, A, {"type": "place", "location_id": "C3", "slot": 5})
    assert out.events[0]["reason"] == "invalid_slot"
    out = act(game, state, A, {"type": "bogus"})
    assert out.events[0]["reason"] == "invalid_action"
    assert out.points_delta == 0 and not out.is_finished


def test_skip_and_draw_hand() -> None:
    game, state = new_state()
    out = act(game, state, A, {"type": "skip"})
    assert out.state["current_player_id"] == B and out.state["round_failures"] == [A]

    # A late joiner (added to turn_order by the room manager) draws a hand.
    state = out.state
    state["turn_order"].append("late")
    out = act(game, state, "late", {"type": "draw_hand"})
    assert set(out.state["hands"]["late"]) == {"city", "landmark", "event"}
    again = act(game, out.state, "late", {"type": "draw_hand"})
    assert again.events[0]["reason"] == "has_hand"


def test_skip_swaps_whole_hand_and_returns_old_cards() -> None:
    game, state = new_state()
    setup_board(
        state,
        ["C1"],
        {A: {"city": "C2", "landmark": "L1", "event": "E1"}, B: {"city": "C3"}},
    )
    out = act(game, state, A, {"type": "skip"})
    hand = out.state["hands"][A]
    assert hand["city"] == "C4" and hand["landmark"] in {"L2", "L3"}
    assert hand["event"] in {"E2", "E3"}
    used = set(out.state["used_ids"])
    assert not {"C2", "L1", "E1"} & used  # old cards are back in the pool
    assert set(hand.values()) <= used and "C3" in used


def test_skip_keeps_card_when_pool_is_empty() -> None:
    game, state = new_state({"categories": ["city"]})
    setup_board(state, ["C1"], {A: {"city": "C2"}, B: {"city": "C3"}})
    state["used_ids"] = ["C1", "C2", "C3", "C4"]
    out = act(game, state, A, {"type": "skip"})
    assert out.state["hands"][A]["city"] == "C2"


def test_end_after_rounds() -> None:
    game, state = new_state({"end_condition": "rounds", "end_target": 1})
    out = act(game, state, A, {"type": "skip"})
    assert not out.is_finished
    out = act(game, out.state, B, {"type": "skip"})
    assert out.is_finished and out.state["finished"]
    assert out.events[-1] == {"type": "game_over"}
    assert act(game, out.state, A, {"type": "skip"}).events[0]["reason"] == "finished"


def test_rounds_counter_advances() -> None:
    game, state = new_state({"end_condition": "rounds", "end_target": 3})
    for player in (A, B):
        state = act(game, state, player, {"type": "skip"}).state
    assert state["round"] == 2 and state["round_failures"] == []


def test_end_on_points() -> None:
    game, state = new_state({"end_condition": "points", "end_target": 20})
    setup_board(state, ["C1"], {A: {"event": "E3"}, B: {"event": "E2"}})
    state["player_scores"][A] = 18
    out = act(game, state, A, {"type": "place", "location_id": "E3", "slot": 1})
    assert out.is_finished and out.state["player_scores"][A] == 21


def test_end_on_failed_round() -> None:
    game, state = new_state({"end_condition": "failed_round"})
    setup_board(state, ["C1"], {A: {"event": "E3"}, B: {"event": "E1"}})
    out = act(game, state, A, {"type": "place", "location_id": "E3", "slot": 0})  # wrong
    out = act(game, out.state, B, {"type": "place", "location_id": "E1", "slot": 1})  # right
    assert not out.is_finished
    state = out.state
    out = act(game, state, A, {"type": "skip"})
    out = act(game, out.state, B, {"type": "skip"})
    assert out.is_finished


def test_end_when_out_of_cards() -> None:
    game, state = new_state({"categories": ["event"]})
    setup_board(state, ["C1"], {A: {"event": "E3"}, B: {"event": None}})
    state["used_ids"] = [x.id for x in FAKE]
    out = act(game, state, A, {"type": "place", "location_id": "E3", "slot": 1})
    assert out.is_finished


def test_on_game_ended_reveals_discarded() -> None:
    game, state = new_state()
    state["discarded"] = [{"id": "E3", "player_id": A}]
    ended = game.on_game_ended(state, {})
    assert ended["finished"] and not state["finished"]
    assert game.get_public_view(ended, {})["discarded"][0]["id"] == "E3"


def test_on_player_removed_drops_hand() -> None:
    game, state = new_state()
    state["round_failures"] = [B]
    state = game.on_player_removed(state, {}, B)
    assert B not in state["hands"] and state["round_failures"] == []


def test_validate_config() -> None:
    game = NorthSouthSortGame()
    cfg = game.validate_config(
        {
            "language": "fr",
            "continent": "antarctica",
            "categories": ["event", "bogus"],
            "end_condition": "points",
            "end_target": 9999,
            "timed": 1,
        }
    )
    assert cfg == {
        "language": "de",
        "continent": "world",
        "categories": ["event"],
        "timed": True,
        "end_condition": "points",
        "end_target": 1000,
    }
    assert game.validate_config({"categories": []})["categories"] == ["city", "landmark", "event"]
    assert game.validate_config({"end_condition": "failed_round"})["end_target"] == 0


def test_real_dataset_pools_cover_every_continent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # use the committed locations.json
    if not load_locations():
        pytest.skip("no dataset")
    for continent in game_module.PLAY_CONTINENTS:
        for category in ("city", "landmark", "event"):
            assert len(game_module.pool(continent, category)) >= 20, (continent, category)


def test_north_south_sort_websocket_lifecycle() -> None:
    app = create_app(database=Database())
    slug = "north-south-sort"
    with TestClient(app) as client:
        assert any(g["slug"] == slug for g in client.get("/api/games").json())
        room_id = client.post(
            "/api/rooms",
            json={
                "game_slug": slug,
                "host_player_id": "host_ns",
                "host_name": "Anna",
                "host_color": "#2563eb",
                "config": {"language": "en"},
            },
        ).json()["room_id"]

        ws_url_1 = f"/ws/{slug}/{room_id}?player_id=host_ns&name=Anna&color=%232563eb"
        ws_url_2 = f"/ws/{slug}/{room_id}?player_id=peer_ns&name=Ben&color=%23dc2626"
        with client.websocket_connect(ws_url_1) as ws1, client.websocket_connect(ws_url_2) as ws2:
            _ = ws1.receive_json()
            _ = ws1.receive_json()
            _ = ws2.receive_json()

            ws1.send_json({"type": "start_game"})
            playing = ws1.receive_json()
            _ = ws2.receive_json()
            assert playing["status"] == "playing"
            state = playing["state"]
            assert state["current_player_id"] == "host_ns"
            assert len(state["axis"]) == 1 and len(state["hands"]["host_ns"]) == 3

            ws1.send_json({"type": "game_action", "action": {"type": "skip"}})
            event = ws1.receive_json()
            assert event["type"] == "turn_skipped"
            _ = ws2.receive_json()
            after = ws1.receive_json()
            assert after["state"]["current_player_id"] == "peer_ns"
