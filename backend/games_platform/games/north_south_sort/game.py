"""North South Sort (turn-based: place locations on a shared north–south axis)."""

from __future__ import annotations

import copy
import random
from collections import defaultdict
from datetime import UTC, datetime
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from games_platform.core.protocol import ActionOutcome
from games_platform.games.north_south_sort.locations import (
    CATEGORIES,
    CATEGORY_POINTS,
    Location,
    load_locations,
)

MAX_PLAYERS = 8
LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"
PLAY_CONTINENTS = (
    "world",
    "europe",
    "asia",
    "africa",
    "north_america",
    "south_america",
    "oceania",
)
DEFAULT_CONTINENT = "world"

type EndCondition = Literal["rounds", "points", "failed_round"]

END_CONDITIONS: tuple[EndCondition, ...] = ("rounds", "points", "failed_round")
DEFAULT_END_CONDITION: EndCondition = "rounds"
END_TARGETS: dict[str, tuple[int, int, int]] = {
    # condition: (default, min, max); failed_round has no target
    "rounds": (10, 1, 50),
    "points": (20, 5, 200),
    "failed_round": (0, 0, 0),
}

# Timed mode: (seconds since turn start, multiplier) for correct placements.
SPEED_STEPS: tuple[tuple[float, float], ...] = ((10.0, 2.0), (20.0, 1.5))


def _now() -> datetime:
    return datetime.now(UTC)


def speed_factor(elapsed_seconds: float) -> float:
    for limit, factor in SPEED_STEPS:
        if elapsed_seconds <= limit:
            return factor
    return 1.0


class PlaceAction(BaseModel):
    type: Literal["place"] = "place"
    location_id: str = Field(min_length=1, max_length=20)
    slot: int = Field(ge=0)


class SkipAction(BaseModel):
    type: Literal["skip"] = "skip"


class DrawHandAction(BaseModel):
    type: Literal["draw_hand"] = "draw_hand"


type NorthSouthSortAction = PlaceAction | SkipAction | DrawHandAction

ACTION_ADAPTER: TypeAdapter[NorthSouthSortAction] = TypeAdapter(NorthSouthSortAction)


# --------------------------------------------------------------------------- location index


@cache
def locations_by_id() -> dict[str, Location]:
    return {loc.id: loc for loc in load_locations()}


@cache
def _pools() -> dict[tuple[str, str], tuple[str, ...]]:
    pools: dict[tuple[str, str], list[str]] = defaultdict(list)
    for loc in load_locations():
        pools[(loc.continent, loc.category)].append(loc.id)
        pools[("world", loc.category)].append(loc.id)
    return {key: tuple(ids) for key, ids in pools.items()}


def pool(continent: str, category: str) -> tuple[str, ...]:
    return _pools().get((continent, category), ())


def is_correct_slot(card: Location, south: Location | None, north: Location | None) -> bool:
    """Whether ``card`` fits between ``south`` and ``north``, with bounding-box tolerance."""
    fits_south = south is None or card.max_lat >= south.min_lat
    fits_north = north is None or card.min_lat <= north.max_lat
    return fits_south and fits_north


def _rejected(state: dict[str, Any], player_id: str, reason: str) -> ActionOutcome:
    return ActionOutcome(
        state=state,
        events=[{"type": "action_rejected", "player_id": player_id, "reason": reason}],
    )


class NorthSouthSortGame:
    """Players take turns placing location cards north or south of the ones on the axis."""

    slug: str = "north-south-sort"
    title: str = "North South Sort"
    description: str = (
        "1–8 player geography game. Place cities, landmarks and historical events on a shared "
        "north–south axis — the harder the card, the more it scores, and misses cost points."
    )

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    # ----------------------------------------------------------------------- config

    def default_config(self) -> dict[str, Any]:
        return {
            "language": DEFAULT_LANGUAGE,
            "continent": DEFAULT_CONTINENT,
            "categories": list(CATEGORIES),
            "timed": False,
            "end_condition": DEFAULT_END_CONDITION,
            "end_target": END_TARGETS[DEFAULT_END_CONDITION][0],
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        language = str(raw_config.get("language") or DEFAULT_LANGUAGE)
        if language not in LANGUAGES:
            language = DEFAULT_LANGUAGE
        continent = str(raw_config.get("continent") or DEFAULT_CONTINENT)
        if continent not in PLAY_CONTINENTS:
            continent = DEFAULT_CONTINENT
        raw_categories = raw_config.get("categories")
        if not isinstance(raw_categories, list):
            raw_categories = list(CATEGORIES)
        categories = [c for c in CATEGORIES if c in raw_categories] or list(CATEGORIES)
        condition = str(raw_config.get("end_condition", DEFAULT_END_CONDITION))
        if condition not in END_CONDITIONS:
            condition = DEFAULT_END_CONDITION
        default, low, high = END_TARGETS[condition]
        try:
            target = int(raw_config.get("end_target", default))
        except (TypeError, ValueError):
            target = default
        return {
            "language": language,
            "continent": continent,
            "categories": categories,
            "timed": bool(raw_config.get("timed", False)),
            "end_condition": condition,
            "end_target": max(low, min(high, target)),
        }

    # ----------------------------------------------------------------------- state

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        cfg = self.validate_config(config)
        turn_order: list[str] = list(player_ids or [])[:MAX_PLAYERS]
        state: dict[str, Any] = {
            "language": cfg["language"],
            "continent": cfg["continent"],
            "categories": cfg["categories"],
            "timed": cfg["timed"],
            "end_condition": cfg["end_condition"],
            "end_target": cfg["end_target"],
            "axis": [],
            "hands": {},
            "used_ids": [],
            "discarded": [],
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": turn_order[0] if turn_order else None,
            "turn_started_at": _now().isoformat(),
            "round": 1,
            "round_failures": [],
            "player_scores": {pid: 0.0 for pid in turn_order},
            "finished": False,
            "move_count": 0,
            "last_move": None,
        }
        start = self._draw(state, "city")
        if start is not None:
            state["axis"].append({"id": start, "player_id": None})
        for pid in turn_order:
            self._deal_hand(state, pid)
        return state

    def _draw(self, state: dict[str, Any], category: str) -> str | None:
        used = set(state["used_ids"])
        candidates = [i for i in pool(state["continent"], category) if i not in used]
        if not candidates:
            return None
        choice = self.rng.choice(candidates)
        state["used_ids"].append(choice)
        return choice

    def _deal_hand(self, state: dict[str, Any], player_id: str) -> None:
        state["hands"][player_id] = {c: self._draw(state, c) for c in state["categories"]}

    # ----------------------------------------------------------------------- views

    def _card(self, loc_id: str, language: str, *, reveal: bool) -> dict[str, Any]:
        loc = locations_by_id()[loc_id]
        de = language == "de"
        card: dict[str, Any] = {
            "id": loc.id,
            "category": loc.category,
            "points": CATEGORY_POINTS[loc.category],
            "name": loc.name_de if de else loc.name_en,
            "country": (loc.country_de if de else loc.country_en) or "",
        }
        if reveal:
            card.update(
                lat=loc.lat,
                lon=loc.lon,
                description=loc.description_de if de else loc.description_en,
                wikipedia=(loc.wikipedia_de if de else None) or loc.wikipedia_en,
            )
        return card

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        language = str(state.get("language", DEFAULT_LANGUAGE))
        finished = bool(state.get("finished"))
        view = {
            k: v for k, v in state.items() if k not in ("used_ids", "axis", "hands", "discarded")
        }
        view["axis"] = [
            {**self._card(e["id"], language, reveal=True), "player_id": e["player_id"]}
            for e in state.get("axis", [])
        ]
        view["hands"] = {
            pid: [
                self._card(loc_id, language, reveal=False)
                for loc_id in hand.values()
                if loc_id is not None
            ]
            for pid, hand in (state.get("hands") or {}).items()
        }
        view["discarded_count"] = len(state.get("discarded", []))
        view["discarded"] = (
            [
                {**self._card(e["id"], language, reveal=True), "player_id": e["player_id"]}
                for e in state.get("discarded", [])
            ]
            if finished
            else []
        )
        return view

    # ----------------------------------------------------------------------- actions

    def _advance_turn(self, state: dict[str, Any], player_id: str) -> bool:
        """Move to the next player; return True when the game ends at a round boundary."""
        turn_order: list[str] = list(state.get("turn_order") or [])
        if not turn_order:
            return False
        curr_idx = (
            turn_order.index(player_id)
            if player_id in turn_order
            else int(state.get("current_turn_index", 0))
        )
        next_idx = (curr_idx + 1) % len(turn_order)
        state["current_turn_index"] = next_idx
        state["current_player_id"] = turn_order[next_idx]
        state["turn_started_at"] = _now().isoformat()
        if next_idx != 0:
            return False
        # A full round is complete.
        failures = set(state.get("round_failures") or [])
        if state["end_condition"] == "failed_round" and set(turn_order) <= failures:
            return True
        if state["end_condition"] == "rounds" and int(state["round"]) >= int(state["end_target"]):
            return True
        state["round"] = int(state["round"]) + 1
        state["round_failures"] = []
        return False

    def _out_of_cards(self, state: dict[str, Any]) -> bool:
        return all(
            loc_id is None
            for pid in state.get("turn_order", [])
            for loc_id in (state["hands"].get(pid) or {}).values()
        )

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier  # speed bonus is our own, not the platform streak
        next_state = copy.deepcopy(state)
        try:
            parsed = ACTION_ADAPTER.validate_python(action)
        except ValidationError:
            return _rejected(next_state, player_id, "invalid_action")
        if next_state.get("finished"):
            return _rejected(next_state, player_id, "finished")

        turn_order: list[str] = next_state.setdefault("turn_order", [])
        if player_id not in turn_order and len(turn_order) < MAX_PLAYERS:
            turn_order.append(player_id)
        if next_state.get("current_player_id") is None and turn_order:
            next_state["current_player_id"] = turn_order[0]
            next_state["current_turn_index"] = 0

        if isinstance(parsed, DrawHandAction):
            if player_id not in turn_order or next_state["hands"].get(player_id):
                return _rejected(next_state, player_id, "has_hand")
            self._deal_hand(next_state, player_id)
            next_state.setdefault("player_scores", {}).setdefault(player_id, 0.0)
            return ActionOutcome(state=next_state)

        if player_id != next_state.get("current_player_id"):
            return _rejected(next_state, player_id, "not_your_turn")

        match parsed:
            case SkipAction():
                return self._skip(next_state, player_id)
            case PlaceAction():
                return self._place(next_state, player_id, parsed)
        return _rejected(next_state, player_id, "invalid_action")  # pragma: no cover

    def _skip(self, state: dict[str, Any], player_id: str) -> ActionOutcome:
        if player_id not in state["round_failures"]:
            state["round_failures"].append(player_id)
        state["move_count"] = int(state.get("move_count", 0)) + 1
        state["last_move"] = {"type": "turn_skipped", "player_id": player_id}
        ended = self._advance_turn(state, player_id)
        return self._outcome(
            state,
            [{"type": "turn_skipped", "player_id": player_id}],
            ended=ended,
        )

    def _place(self, state: dict[str, Any], player_id: str, action: PlaceAction) -> ActionOutcome:
        hand: dict[str, str | None] = state["hands"].get(player_id) or {}
        category = next((c for c, loc_id in hand.items() if loc_id == action.location_id), None)
        if category is None:
            return _rejected(state, player_id, "not_in_hand")
        axis: list[dict[str, Any]] = state["axis"]
        if action.slot > len(axis):
            return _rejected(state, player_id, "invalid_slot")

        locs = locations_by_id()
        card = locs[action.location_id]
        south = locs[axis[action.slot - 1]["id"]] if action.slot > 0 else None
        north = locs[axis[action.slot]["id"]] if action.slot < len(axis) else None
        correct = is_correct_slot(card, south, north)
        value = CATEGORY_POINTS[card.category]

        if correct:
            factor = 1.0
            if state.get("timed"):
                started = datetime.fromisoformat(state["turn_started_at"])
                factor = speed_factor((_now() - started).total_seconds())
            points = round(value * factor, 2)
            axis.insert(action.slot, {"id": card.id, "player_id": player_id})
        else:
            factor = 1.0
            points = -float(value)
            state["discarded"].append({"id": card.id, "player_id": player_id})
            if player_id not in state["round_failures"]:
                state["round_failures"].append(player_id)

        scores = state.setdefault("player_scores", {})
        scores[player_id] = round(float(scores.get(player_id, 0.0)) + points, 2)
        hand[category] = self._draw(state, category)
        language = str(state.get("language", DEFAULT_LANGUAGE))
        move = {
            "type": "location_placed",
            "player_id": player_id,
            "correct": correct,
            "points": points,
            "factor": factor,
            # A wrong card stays hidden: name only, no position.
            "card": self._card(card.id, language, reveal=correct),
            "slot": action.slot if correct else None,
        }
        state["move_count"] = int(state.get("move_count", 0)) + 1
        state["last_move"] = move

        ended = state["end_condition"] == "points" and scores[player_id] >= int(state["end_target"])
        if not ended:
            ended = self._advance_turn(state, player_id)
        return self._outcome(
            state,
            [move],
            ended=ended,
            points=points,
            correct=correct,
        )

    def _outcome(
        self,
        state: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        ended: bool,
        points: float = 0.0,
        correct: bool | None = None,
    ) -> ActionOutcome:
        ended = ended or self._out_of_cards(state)
        if ended:
            state["finished"] = True
            events.append({"type": "game_over"})
        return ActionOutcome(
            state=state,
            events=events,
            points_delta=points,
            is_correct_entry=correct is True,
            is_mistake=correct is False,
            is_finished=ended,
        )

    # ----------------------------------------------------------------------- hooks

    def on_game_ended(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        return {**state, "finished": True}

    def on_player_removed(
        self, state: dict[str, Any], config: dict[str, Any], player_id: str
    ) -> dict[str, Any]:
        _ = config
        state.get("hands", {}).pop(player_id, None)
        if player_id in state.get("round_failures", []):
            state["round_failures"].remove(player_id)
        # The turn may have moved to someone else: give them a fresh clock.
        state["turn_started_at"] = _now().isoformat()
        return state


north_south_sort_game = NorthSouthSortGame()
