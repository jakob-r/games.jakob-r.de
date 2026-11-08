"""Fragmentory (turn-based territory building with square line cards on an infinite grid)."""

from __future__ import annotations

import copy
import random
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome
from games_platform.games.fragmentory.board import (
    DECK_COUNTS,
    Placement,
    bounding_area,
    cell_key,
    legal_spots,
    make_cell,
    place_card,
    territory_scores,
)

MAX_PLAYERS = 8
COORD_LIMIT = 200


class PlaceAction(BaseModel):
    type: Literal["place"] = "place"
    row: int = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)
    col: int = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)
    rot: int = Field(ge=0, le=3)
    area: int | None = Field(default=None, ge=0, le=3)


class DiscardAction(BaseModel):
    type: Literal["discard"] = "discard"


type FragmentoryAction = PlaceAction | DiscardAction

ACTION_ADAPTER: TypeAdapter[FragmentoryAction] = TypeAdapter(FragmentoryAction)


def new_deck(rng: random.Random | None = None) -> list[str]:
    deck = [card for card, n in DECK_COUNTS.items() for _ in range(n)]
    (rng or random).shuffle(deck)
    return deck


def _rejected(state: dict[str, Any], player_id: str, reason: str) -> ActionOutcome:
    return ActionOutcome(
        state=state,
        events=[{"type": "action_rejected", "player_id": player_id, "reason": reason}],
    )


def total_scores(state: dict[str, Any]) -> dict[str, int]:
    territory: dict[str, int] = state.get("territory") or {}
    penalties: dict[str, int] = state.get("penalties") or {}
    ids = set(state.get("turn_order") or []) | set(territory) | set(penalties)
    return {pid: int(territory.get(pid, 0)) - int(penalties.get(pid, 0)) for pid in ids}


class FragmentoryGame:
    """Self-contained Fragmentory implementation."""

    slug: str = "fragmentory"
    title: str = "Fragmentory"
    description: str = (
        "Turn-based territory game for 1–8 players. Rotate and place square cards with "
        "separation lines, claim an area in your color and grow the biggest territories "
        "without letting the board sprawl."
    )

    def default_config(self) -> dict[str, Any]:
        return {}

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        _ = raw_config
        return {}

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = config
        turn_order: list[str] = list(player_ids or [])[:MAX_PLAYERS]
        deck = new_deck()
        hands: dict[str, str] = {}
        for pid in turn_order:
            if deck:
                hands[pid] = deck.pop()
        return {
            "cells": {cell_key(0, 0): make_cell("t", 0)},
            "deck": deck,
            "hands": hands,
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": turn_order[0] if turn_order else None,
            "territory": {},
            "penalties": {pid: 0 for pid in turn_order},
            "area": 1,
            "move_count": 0,
            "last_move": None,
            "finished": False,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        view = {k: v for k, v in state.items() if k != "deck"}
        deck: list[str] = list(state.get("deck") or [])
        view["deck_counts"] = {card: deck.count(card) for card in DECK_COUNTS}
        view["deck_size"] = len(deck)
        return view

    # ------------------------------------------------------------------ turns

    def _advance_turn(self, state: dict[str, Any], from_player: str | None) -> bool:
        """Move to the next player who holds (or can draw) a card. False when nobody can."""
        order: list[str] = list(state.get("turn_order") or [])
        if not order:
            state["current_player_id"] = None
            return False
        if from_player in order:
            start = order.index(from_player) + 1
        else:
            start = int(state.get("current_turn_index", 0))
        hands: dict[str, str] = state["hands"]
        deck: list[str] = state["deck"]
        for step in range(len(order)):
            idx = (start + step) % len(order)
            pid = order[idx]
            if pid not in hands and deck:
                hands[pid] = deck.pop()
            if pid in hands:
                state["current_turn_index"] = idx
                state["current_player_id"] = pid
                return True
        state["current_player_id"] = None
        return False

    def _ensure_current_has_card(self, state: dict[str, Any]) -> bool:
        pid = state.get("current_player_id")
        if pid and (pid in state["hands"] or state["deck"]):
            if pid not in state["hands"]:
                state["hands"][pid] = state["deck"].pop()
            return True
        return self._advance_turn(state, None)

    # ------------------------------------------------------------------ actions

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier
        parsed = ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)
        if next_state.get("finished"):
            return _rejected(next_state, player_id, "finished")
        if next_state.get("current_player_id") is None:
            self._advance_turn(next_state, None)
        if player_id != next_state.get("current_player_id"):
            return _rejected(next_state, player_id, "not_your_turn")
        if player_id not in next_state["hands"] and not self._ensure_current_has_card(next_state):
            return _rejected(next_state, player_id, "no_card")
        card_type: str = next_state["hands"][player_id]

        match parsed:
            case DiscardAction():
                if legal_spots(next_state["cells"], card_type):
                    return _rejected(next_state, player_id, "card_fits")
                move_entry: dict[str, Any] = {
                    "type": "card_discarded",
                    "player_id": player_id,
                    "card": card_type,
                }
                return self._finish_turn(next_state, player_id, move_entry, None)

            case PlaceAction():
                result = place_card(
                    next_state["cells"],
                    parsed.row,
                    parsed.col,
                    card_type,
                    parsed.rot,
                    parsed.area,
                    player_id,
                    move=int(next_state.get("move_count", 0)) + 1,
                )
                if isinstance(result, str):
                    return _rejected(next_state, player_id, result)
                move_entry = {
                    "type": "card_placed",
                    "player_id": player_id,
                    "card": card_type,
                    "row": parsed.row,
                    "col": parsed.col,
                    "rot": parsed.rot,
                    "area": parsed.area,
                    "penalty": result.penalty,
                    "takeovers": result.takeovers,
                }
                return self._finish_turn(next_state, player_id, move_entry, result)

    def _finish_turn(
        self,
        state: dict[str, Any],
        player_id: str,
        move_entry: dict[str, Any],
        placement: Placement | None,
    ) -> ActionOutcome:
        old_totals = total_scores(state)
        if placement is not None:
            state["cells"] = placement.cells
            state["area"] = bounding_area(placement.cells)
            penalties: dict[str, int] = dict(state.get("penalties") or {})
            penalties[player_id] = int(penalties.get(player_id, 0)) + placement.penalty
            state["penalties"] = penalties
            state["territory"] = territory_scores(placement.cells)

        state["hands"].pop(player_id, None)
        if state["deck"]:
            state["hands"][player_id] = state["deck"].pop()
        # Players who joined mid-game get their card now, so everyone can see it.
        for pid in state.get("turn_order") or []:
            if pid not in state["hands"] and state["deck"]:
                state["hands"][pid] = state["deck"].pop()
        state["move_count"] = int(state.get("move_count", 0)) + 1

        new_totals = total_scores(state)
        deltas = {
            pid: new_totals.get(pid, 0) - old_totals.get(pid, 0)
            for pid in set(old_totals) | set(new_totals)
        }
        move_entry["score_deltas"] = {pid: d for pid, d in deltas.items() if d}
        state["last_move"] = move_entry

        is_finished = not self._advance_turn(state, player_id)
        state["finished"] = is_finished
        event = {**move_entry, "next_player_id": state.get("current_player_id")}
        return ActionOutcome(
            state=state,
            events=[event],
            points_delta=float(deltas.get(player_id, 0)),
            is_correct_entry=True,
            is_finished=is_finished,
            extra_score_deltas={
                pid: float(d) for pid, d in deltas.items() if pid != player_id and d
            },
        )

    # ------------------------------------------------------------------ hooks

    def on_player_removed(
        self, state: dict[str, Any], config: dict[str, Any], player_id: str
    ) -> dict[str, Any]:
        _ = config
        card = state.get("hands", {}).pop(player_id, None)
        if card is not None:
            deck: list[str] = state.setdefault("deck", [])
            deck.insert(random.randint(0, len(deck)), card)
        if state.get("current_player_id"):
            self._ensure_current_has_card(state)
        return state


fragmentory_game = FragmentoryGame()
