"""Spellsprawl (1-8 player round-based word game on an infinite grid; only reused letters score)."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.dictionary import (
    DEFAULT_LANGUAGE,
    LETTER_SCORES,
    SUPPORTED_LANGUAGES,
    get_letter_score,
    is_valid_word,
    normalize_language,
)
from games_platform.core.protocol import ActionOutcome
from games_platform.games.spellsprawl.board import (
    MAX_WORD_LENGTH,
    Placement,
    Rejection,
    bounding_area,
    cell_key,
    evaluate_placement,
)

MAX_PLAYERS = 8

type EndCondition = Literal["words", "points", "area"]

END_CONDITIONS: tuple[EndCondition, ...] = ("words", "points", "area")
DEFAULT_END_CONDITION: EndCondition = "words"
END_TARGETS: dict[str, tuple[int, int, int]] = {
    # condition: (default, min, max)
    "words": (50, 5, 200),
    "points": (500, 50, 2000),
    "area": (500, 50, 5000),
}


class LetterPlacement(BaseModel):
    row: int
    col: int
    letter: str = Field(min_length=1, max_length=1)


class SubmitWordAction(BaseModel):
    type: Literal["submit_word"] = "submit_word"
    placements: list[LetterPlacement] = Field(default_factory=list, max_length=MAX_WORD_LENGTH)
    direction: Literal["right", "down"] = "right"


class PassTurnAction(BaseModel):
    type: Literal["pass_turn"] = "pass_turn"


type SpellsprawlAction = SubmitWordAction | PassTurnAction

SPELLSPRAWL_ACTION_ADAPTER: TypeAdapter[SpellsprawlAction] = TypeAdapter(SpellsprawlAction)


def _rejected(state: dict[str, Any], player_id: str, reason: str, word: str = "") -> ActionOutcome:
    return ActionOutcome(
        state=state,
        events=[{"type": "word_rejected", "player_id": player_id, "word": word, "reason": reason}],
    )


class SpellsprawlGame:
    """Self-contained 1-to-8-player Spellsprawl implementation."""

    slug: str = "spellsprawl"
    title: str = "Spellsprawl"
    description: str = (
        "1–8 player word game on an endless grid. Spell words anywhere, but only letters "
        "that were already on the grid score points — reuse rare letters to win."
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "language": DEFAULT_LANGUAGE,
            "end_condition": DEFAULT_END_CONDITION,
            "end_target": END_TARGETS[DEFAULT_END_CONDITION][0],
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        language = normalize_language(str(raw_config.get("language") or DEFAULT_LANGUAGE))
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
            "end_condition": condition,
            "end_target": max(low, min(high, target)),
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        validated = self.validate_config(config)
        language: str = validated["language"]
        turn_order: list[str] = list(player_ids or [])[:MAX_PLAYERS]
        return {
            "language": language,
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "letter_scores": dict(LETTER_SCORES[language]),
            "end_condition": validated["end_condition"],
            "end_target": validated["end_target"],
            "cells": {},
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": turn_order[0] if turn_order else None,
            "played_words": [],
            "player_scores": {pid: 0 for pid in turn_order},
            "words_played": 0,
            "area": 0,
            "consecutive_passes": 0,
            "move_count": 0,
            "last_move": None,
        }

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        _ = config
        return state

    def _advance_turn(self, state: dict[str, Any], player_id: str) -> None:
        turn_order: list[str] = list(state.get("turn_order") or [])
        if not turn_order:
            return
        curr_idx = (
            turn_order.index(player_id)
            if player_id in turn_order
            else int(state.get("current_turn_index", 0))
        )
        next_idx = (curr_idx + 1) % len(turn_order)
        state["current_turn_index"] = next_idx
        state["current_player_id"] = turn_order[next_idx]

    def _end_reached(self, state: dict[str, Any], player_id: str) -> bool:
        target = int(state.get("end_target", 0))
        match state.get("end_condition"):
            case "words":
                return int(state["words_played"]) >= target
            case "points":
                return int(state["player_scores"].get(player_id, 0)) >= target
            case "area":
                return int(state["area"]) > target
        return False

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier
        parsed = SPELLSPRAWL_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)
        turn_order: list[str] = list(next_state.get("turn_order") or [])

        if player_id not in turn_order and len(turn_order) < MAX_PLAYERS:
            turn_order.append(player_id)
            next_state["turn_order"] = turn_order

        current_player_id = next_state.get("current_player_id")
        if current_player_id is None and turn_order:
            current_player_id = turn_order[0]
            next_state["current_player_id"] = current_player_id
            next_state["current_turn_index"] = 0

        if player_id != current_player_id:
            return _rejected(next_state, player_id, "not_your_turn")

        match parsed:
            case PassTurnAction():
                passes = int(next_state.get("consecutive_passes", 0)) + 1
                next_state["consecutive_passes"] = passes
                next_state["move_count"] = int(next_state.get("move_count", 0)) + 1
                next_state["last_move"] = {"type": "turn_passed", "player_id": player_id}
                self._advance_turn(next_state, player_id)
                return ActionOutcome(
                    state=next_state,
                    events=[
                        {
                            "type": "turn_passed",
                            "player_id": player_id,
                            "next_player_id": next_state["current_player_id"],
                            "consecutive_passes": passes,
                        }
                    ],
                    is_finished=passes >= max(2, len(turn_order) * 2),
                )

            case SubmitWordAction():
                return self._submit_word(next_state, player_id, parsed)

    def _submit_word(
        self, state: dict[str, Any], player_id: str, action: SubmitWordAction
    ) -> ActionOutcome:
        language = str(state.get("language", DEFAULT_LANGUAGE))
        cells: dict[str, dict[str, Any]] = state["cells"]
        result = evaluate_placement(
            cells,
            [(p.row, p.col, p.letter.upper()) for p in action.placements],
            action.direction,
            lambda ch: get_letter_score(ch, language),
        )
        if isinstance(result, Rejection):
            return _rejected(state, player_id, result.reason, result.word)
        placement: Placement = result

        main_word = placement.main.word
        played_words: list[dict[str, Any]] = list(state.get("played_words") or [])
        if any(str(entry.get("word", "")) == main_word for entry in played_words):
            return _rejected(state, player_id, "already_played", main_word)
        for formed in [placement.main, *placement.cross_words]:
            if not is_valid_word(formed.word, language):
                return _rejected(state, player_id, "not_in_dictionary", formed.word)

        move_number = int(state.get("move_count", 0)) + 1
        for p in action.placements:
            cells[cell_key(p.row, p.col)] = {
                "letter": p.letter.upper(),
                "player_id": player_id,
                "move": move_number,
            }

        points = placement.points
        scores: dict[str, int] = dict(state.get("player_scores") or {})
        scores[player_id] = int(scores.get(player_id, 0)) + points
        state["player_scores"] = scores
        state["move_count"] = move_number
        state["words_played"] = int(state.get("words_played", 0)) + 1
        state["area"] = bounding_area(cells)
        state["consecutive_passes"] = 0

        move_entry = {
            "word": main_word,
            "cross_words": [w.word for w in placement.cross_words],
            "player_id": player_id,
            "positions": [{"row": r, "col": c} for r, c in placement.main.positions],
            "placed": [{"row": p.row, "col": p.col} for p in action.placements],
            "points": points,
            "move_number": move_number,
        }
        played_words.append(move_entry)
        state["played_words"] = played_words
        state["last_move"] = move_entry

        is_finished = self._end_reached(state, player_id)
        if not is_finished:
            self._advance_turn(state, player_id)

        return ActionOutcome(
            state=state,
            events=[
                {
                    "type": "word_played",
                    "player_id": player_id,
                    "word": main_word,
                    "cross_words": move_entry["cross_words"],
                    "points": points,
                    "next_player_id": state["current_player_id"],
                }
            ],
            points_delta=float(points),
            is_correct_entry=True,
            is_finished=is_finished,
        )


spellsprawl_game = SpellsprawlGame()
