"""Unit tests for Fragmentory."""

from __future__ import annotations

import random
from typing import Any

from games_platform.games.fragmentory.board import (
    GRAY,
    Placement,
    card_areas,
    cell_key,
    claim_allowed,
    compute_regions,
    fits,
    grows_own_area,
    legal_spots,
    make_cell,
    place_card,
    territory_scores,
)
from games_platform.games.fragmentory.game import FragmentoryGame, total_scores

A, B = "player_a", "player_b"


def start() -> dict[str, dict[str, Any]]:
    return {cell_key(0, 0): make_cell("cross", 0)}


def placed(result: Placement | str) -> dict[str, dict[str, Any]]:
    assert isinstance(result, Placement), result
    return result.cells


def area_at(cells: dict[str, dict[str, Any]], row: int, col: int, half: int) -> int:
    cell = cells[cell_key(row, col)]
    for idx, area in enumerate(card_areas(cell["type"], cell["rot"])):
        if half in area:
            return idx
    raise AssertionError


def test_rotation_moves_lines_and_areas() -> None:
    assert card_areas("curve", 0)[0] == [1, 2]
    assert card_areas("curve", 1)[0] == [3, 4]
    assert card_areas("straight", 1) == [[3, 4, 5, 6], [7, 0, 1, 2]]


def test_sides_must_match_lines() -> None:
    cells = start()
    # The cross has lines on every side, so a straight must point its line at it.
    assert fits(cells, 0, 1, "straight", 1)
    assert not fits(cells, 0, 1, "straight", 0)
    assert not fits(cells, 0, 0, "straight", 1)  # occupied
    assert not fits(cells, 5, 5, "straight", 1)  # not adjacent
    assert (0, 1, 1) in legal_spots(cells, "straight")


def test_claim_takes_over_white_neighbours_and_costs_area() -> None:
    cells = start()
    north = area_at({cell_key(0, 1): make_cell("straight", 1)}, 0, 1, 7)
    result = place_card(cells, 0, 1, "straight", 1, north, A)
    assert isinstance(result, Placement)
    assert result.penalty == 1
    regions = compute_regions(result.cells)
    region = regions.region_of((cell_key(0, 1), north))
    assert region.color == A
    assert region.cards == {cell_key(0, 0), cell_key(0, 1)}
    assert result.cells[cell_key(0, 0)]["owners"][0] == A  # cross NE area took the colour
    assert territory_scores(result.cells) == {A: 2}


def test_cannot_claim_next_to_opponent() -> None:
    cells = placed(place_card(start(), 0, 1, "straight", 1, 1, A))
    # (0, 2): north area touches A's north area.
    regions = compute_regions(cells)
    assert not claim_allowed(cells, regions, 0, 2, "straight", 1, 1, B)
    assert claim_allowed(cells, regions, 0, 2, "straight", 1, 0, B)
    assert place_card(cells, 0, 2, "straight", 1, 1, B) == "claim_not_allowed"
    # Placing without a claim is fine and the unclaimed area joins A's territory.
    cells = placed(place_card(cells, 0, 2, "straight", 1, None, B))
    assert territory_scores(cells) == {A: 3}


def test_no_new_claim_when_the_move_grows_an_own_area() -> None:
    cells = placed(place_card(start(), 0, 1, "straight", 1, 1, A))
    regions = compute_regions(cells)
    # (0, 2) extends A's north area, so A may claim nothing there (not even the south area).
    assert grows_own_area(cells, regions, 0, 2, "straight", 1, A)
    assert not any(claim_allowed(cells, regions, 0, 2, "straight", 1, i, A) for i in (0, 1))
    assert place_card(cells, 0, 2, "straight", 1, 0, A) == "claim_not_allowed"
    assert isinstance(place_card(cells, 0, 2, "straight", 1, None, A), Placement)
    # (0, -1) only touches white areas: a new area may be claimed.
    assert not grows_own_area(cells, regions, 0, -1, "straight", 1, A)
    assert claim_allowed(cells, regions, 0, -1, "straight", 1, 1, A)


def straight(owner_north: str | None = None) -> dict[str, Any]:
    cell = make_cell("straight", 1)  # line west-east: area 0 = south, area 1 = north
    cell["owners"][1] = owner_north
    return cell


def gray_board() -> dict[str, dict[str, Any]]:
    """Cross NE + (0,1) belong to A, cross NW + (0,-1) to B, joined by a line end: gray."""
    cells = start()
    cells[cell_key(0, 0)]["owners"][0] = A
    cells[cell_key(0, 0)]["owners"][3] = B
    cells[cell_key(0, 1)] = straight(A)
    cells[cell_key(0, -1)] = straight(B)
    return placed(place_card(cells, -1, 0, "end", 2, None, A))


def test_tie_turns_gray() -> None:
    cells = gray_board()
    assert compute_regions(cells).region_of((cell_key(0, 0), 0)).color == GRAY
    assert territory_scores(cells) == {}


def test_gray_needs_lead_of_two() -> None:
    # A one-card A area merged into the gray tie: 3 vs 2 stays gray.
    cells = gray_board()
    cells[cell_key(0, 3)] = straight(A)
    cells = placed(place_card(cells, 0, 2, "straight", 1, None, B))
    assert compute_regions(cells).region_of((cell_key(0, 0), 0)).color == GRAY
    # A two-card A area: 4 vs 2 resolves it.
    cells = gray_board()
    cells[cell_key(0, 3)] = straight(A)
    cells[cell_key(0, 4)] = straight(A)
    result = place_card(cells, 0, 2, "straight", 1, None, B)
    assert isinstance(result, Placement)
    assert result.takeovers == [{"winner": A, "losers": [B]}]
    assert compute_regions(result.cells).region_of((cell_key(0, 0), 0)).color == A
    assert territory_scores(result.cells) == {A: 7}


def test_fresh_merge_bigger_side_wins_by_one() -> None:
    cells = start()
    cells[cell_key(0, 0)]["owners"][0] = A
    cells[cell_key(0, 0)]["owners"][3] = B
    cells[cell_key(0, 1)] = straight(A)
    cells[cell_key(0, 2)] = straight(A)  # A: 3 cards
    cells[cell_key(0, -1)] = straight(B)  # B: 2 cards
    result = place_card(cells, -1, 0, "end", 2, None, B)
    assert isinstance(result, Placement)
    assert result.takeovers == [{"winner": A, "losers": [B]}]
    assert territory_scores(result.cells) == {A: 5}


def test_enclosed_region_scores_double() -> None:
    # Four curves whose corners form a closed circle.
    cells = {
        cell_key(0, 0): make_cell("curve", 1),
        cell_key(0, 1): make_cell("curve", 2),
        cell_key(1, 0): make_cell("curve", 0),
        cell_key(1, 1): make_cell("curve", 3),
    }
    for cell in cells.values():
        cell["owners"][0] = A
    regions = compute_regions(cells)
    inner = regions.region_of((cell_key(0, 0), 0))
    assert inner.enclosed
    assert len(inner.cards) == 4
    assert territory_scores(cells) == {A: 8}


def test_single_card_region_scores_nothing() -> None:
    cells = start()
    cells[cell_key(0, 0)]["owners"][0] = A
    assert territory_scores(cells) == {}


def test_game_turns_and_scores() -> None:
    game = FragmentoryGame()
    state = game.create_initial_state({}, [A, B])
    assert state["current_player_id"] == A
    assert len(state["deck"]) == 38 - 2
    view = game.get_public_view(state, {})
    assert "deck" not in view and view["deck_size"] == 36
    assert sum(view["deck_counts"].values()) == 36

    out = game.apply_action(state, {}, B, {"type": "place", "row": 0, "col": 1, "rot": 1}, 1.0)
    assert out.events[0]["reason"] == "not_your_turn"

    state["hands"][A] = "straight"
    out = game.apply_action(
        state, {}, A, {"type": "place", "row": 0, "col": 1, "rot": 1, "area": 1}, 1.0
    )
    assert out.events[0]["type"] == "card_placed"
    assert out.points_delta == 2 - 1  # territory 2, area grew by 1
    assert out.state["current_player_id"] == B
    assert out.state["hands"][A] != "" and len(out.state["deck"]) == 35

    out = game.apply_action(out.state, {}, B, {"type": "discard"}, 1.0)
    assert out.events[0]["reason"] == "card_fits"


def test_mid_game_joiner_gets_a_card_after_the_next_move() -> None:
    game = FragmentoryGame()
    state = game.create_initial_state({}, [A])
    state["turn_order"].append(B)  # what RoomManager does when someone joins
    state["hands"][A] = "straight"
    out = game.apply_action(state, {}, A, {"type": "place", "row": 0, "col": 1, "rot": 1}, 1.0)
    assert B in out.state["hands"]
    assert out.state["current_player_id"] == B


def test_random_game_runs_to_the_end() -> None:
    rng = random.Random(7)
    game = FragmentoryGame()
    players = [A, B, "player_c"]
    state = game.create_initial_state({}, players)
    totals: dict[str, float] = dict.fromkeys(players, 0.0)
    moves = 0
    while not state["finished"]:
        pid = state["current_player_id"]
        card = state["hands"][pid]
        spots = legal_spots(state["cells"], card)
        if spots:
            r, c, rot = rng.choice(spots)
            regions = compute_regions(state["cells"])
            claims = [
                i
                for i in range(len(card_areas(card, rot)))
                if claim_allowed(state["cells"], regions, r, c, card, rot, i, pid)
            ]
            action: dict[str, Any] = {
                "type": "place",
                "row": r,
                "col": c,
                "rot": rot,
                "area": rng.choice([*claims, None]),
            }
        else:
            action = {"type": "discard"}
        out = game.apply_action(state, {}, pid, action, 1.0)
        assert out.events[0]["type"] in ("card_placed", "card_discarded"), out.events
        totals[pid] += out.points_delta
        for other, delta in out.extra_score_deltas.items():
            totals[other] += delta
        state = out.state
        moves += 1
    assert moves == 38
    assert not state["hands"] and not state["deck"]
    assert totals == {pid: float(v) for pid, v in total_scores(state).items()}
