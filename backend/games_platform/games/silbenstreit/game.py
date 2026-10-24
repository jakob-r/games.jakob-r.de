"""Silbenstreit (2-player round-based word ownership & tile protection game)."""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome
from games_platform.games.silbenstreit.dictionary import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    generate_board,
    is_valid_word,
    normalize_language,
)

MIN_SIZE = 4
MAX_SIZE = 8
DEFAULT_SIZE = 5


class TilePosition(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class SubmitWordAction(BaseModel):
    type: Literal["submit_word"] = "submit_word"
    positions: list[TilePosition] = Field(default_factory=list)


class PassTurnAction(BaseModel):
    type: Literal["pass_turn"] = "pass_turn"


type SilbenstreitAction = SubmitWordAction | PassTurnAction

SILBENSTREIT_ACTION_ADAPTER: TypeAdapter[SilbenstreitAction] = TypeAdapter(
    SilbenstreitAction
)


def compute_protected_grid(
    size: int,
    owners: list[list[str | None]],
) -> list[list[bool]]:
    """
    A tile owned by a player is 'protected' if all of its in-bounds orthogonal neighbors
    (up, down, left, right) are owned by the same player.
    """
    protected: list[list[bool]] = [[False for _ in range(size)] for _ in range(size)]
    for r in range(size):
        for c in range(size):
            owner = owners[r][c]
            if owner is None:
                continue
            all_same = True
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < size and 0 <= nc < size and owners[nr][nc] != owner:
                    all_same = False
                    break
            protected[r][c] = all_same
    return protected


def compute_board_scores(
    size: int,
    values: list[list[int]],
    owners: list[list[str | None]],
) -> dict[str, int]:
    """Sum the rarity values of all tiles currently owned by each player."""
    totals: dict[str, int] = {}
    for r in range(size):
        for c in range(size):
            owner = owners[r][c]
            if owner is not None:
                totals[owner] = totals.get(owner, 0) + int(values[r][c])
    return totals


def count_unowned_tiles(size: int, owners: list[list[str | None]]) -> int:
    return sum(
        1
        for r in range(size)
        for c in range(size)
        if owners[r][c] is None
    )


class SilbenstreitGame:
    """Self-contained 2-player Silbenstreit implementation."""

    slug: str = "silbenstreit"
    title: str = "Silbenstreit"
    description: str = (
        "2-player word strategy on a 4×4 to 8×8 letter grid. Form valid words to claim "
        "letters in your color, score rarity points (1–10), and surround your tiles to "
        "protect them from being stolen!"
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "size": DEFAULT_SIZE,
            "language": DEFAULT_LANGUAGE,
            "scoring_enabled": True,
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        try:
            size = int(raw_config.get("size", DEFAULT_SIZE))
        except (TypeError, ValueError):
            size = DEFAULT_SIZE
        size = max(MIN_SIZE, min(MAX_SIZE, size))

        language = normalize_language(
            str(raw_config.get("language", DEFAULT_LANGUAGE))
            if raw_config.get("language") is not None
            else DEFAULT_LANGUAGE
        )

        return {
            "size": size,
            "language": language,
            "scoring_enabled": bool(raw_config.get("scoring_enabled", True)),
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        validated = self.validate_config(config)
        size: int = validated["size"]
        language: str = validated["language"]

        letters, values = generate_board(size=size, language=language)
        owners: list[list[str | None]] = [
            [None for _ in range(size)] for _ in range(size)
        ]
        protected: list[list[bool]] = [
            [False for _ in range(size)] for _ in range(size)
        ]

        turn_order: list[str] = list(player_ids or [])[:2]
        current_player_id: str | None = turn_order[0] if turn_order else None

        return {
            "size": size,
            "language": language,
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "letters": letters,
            "values": values,
            "owners": owners,
            "protected": protected,
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": current_player_id,
            "played_words": [],
            "player_scores": {pid: 0 for pid in turn_order},
            "unowned_count": size * size,
            "total_tiles": size * size,
            "consecutive_passes": 0,
            "move_count": 0,
            "last_move": None,
        }

    def get_public_view(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
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

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = config, player_multiplier
        parsed = SILBENSTREIT_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)

        size = int(next_state["size"])
        language = str(next_state.get("language", DEFAULT_LANGUAGE))
        letters: list[list[str]] = next_state["letters"]
        values: list[list[int]] = next_state["values"]
        owners: list[list[str | None]] = next_state["owners"]
        protected: list[list[bool]] = next_state["protected"]
        turn_order: list[str] = list(next_state.get("turn_order") or [])

        if player_id not in turn_order and len(turn_order) < 2:
            turn_order.append(player_id)
            next_state["turn_order"] = turn_order

        current_player_id = next_state.get("current_player_id")
        if current_player_id is None and turn_order:
            current_player_id = turn_order[0]
            next_state["current_player_id"] = current_player_id
            next_state["current_turn_index"] = 0

        if player_id != current_player_id:
            return ActionOutcome(
                state=next_state,
                events=[
                    {
                        "type": "word_rejected",
                        "player_id": player_id,
                        "word": "",
                        "reason": "not_your_turn",
                    }
                ],
            )

        match parsed:
            case PassTurnAction():
                next_state["move_count"] = int(next_state.get("move_count", 0)) + 1
                passes = int(next_state.get("consecutive_passes", 0)) + 1
                next_state["consecutive_passes"] = passes
                self._advance_turn(next_state, player_id)
                pass_limit = max(2, len(turn_order) * 2)
                is_finished = passes >= pass_limit
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
                    is_finished=is_finished,
                )

            case SubmitWordAction():
                positions = parsed.positions
                if len(positions) < 2:
                    return ActionOutcome(
                        state=next_state,
                        events=[
                            {
                                "type": "word_rejected",
                                "player_id": player_id,
                                "word": "",
                                "reason": "too_short",
                            }
                        ],
                    )

                seen_coords: set[tuple[int, int]] = set()
                word_chars: list[str] = []
                for pos in positions:
                    r, c = pos.row, pos.col
                    if not (0 <= r < size and 0 <= c < size):
                        return ActionOutcome(
                            state=next_state,
                            events=[
                                {
                                    "type": "word_rejected",
                                    "player_id": player_id,
                                    "word": "",
                                    "reason": "out_of_bounds",
                                }
                            ],
                        )
                    if (r, c) in seen_coords:
                        return ActionOutcome(
                            state=next_state,
                            events=[
                                {
                                    "type": "word_rejected",
                                    "player_id": player_id,
                                    "word": "",
                                    "reason": "duplicate_tile",
                                }
                            ],
                        )
                    if protected[r][c] and owners[r][c] != player_id:
                        return ActionOutcome(
                            state=next_state,
                            events=[
                                {
                                    "type": "word_rejected",
                                    "player_id": player_id,
                                    "word": "",
                                    "reason": "protected_tile",
                                }
                            ],
                        )
                    seen_coords.add((r, c))
                    word_chars.append(letters[r][c])

                word = "".join(word_chars).upper()
                played_words: list[dict[str, Any]] = list(
                    next_state.get("played_words") or []
                )
                already_used = any(
                    str(entry.get("word", "")).upper() == word for entry in played_words
                )
                if already_used:
                    return ActionOutcome(
                        state=next_state,
                        events=[
                            {
                                "type": "word_rejected",
                                "player_id": player_id,
                                "word": word,
                                "reason": "already_played",
                            }
                        ],
                    )

                if not is_valid_word(word, language):
                    return ActionOutcome(
                        state=next_state,
                        events=[
                            {
                                "type": "word_rejected",
                                "player_id": player_id,
                                "word": word,
                                "reason": "not_in_dictionary",
                            }
                        ],
                    )

                # Valid word! Compute old ownership scores, update tile owners, and recompute protection
                old_scores = compute_board_scores(size, values, owners)

                pos_dicts: list[dict[str, int]] = []
                word_tile_value = 0
                for pos in positions:
                    r, c = pos.row, pos.col
                    owners[r][c] = player_id
                    word_tile_value += int(values[r][c])
                    pos_dicts.append({"row": r, "col": c})

                new_protected = compute_protected_grid(size, owners)
                next_state["protected"] = new_protected

                new_scores = compute_board_scores(size, values, owners)
                for pid in turn_order:
                    new_scores.setdefault(pid, 0)
                next_state["player_scores"] = new_scores

                actor_delta = float(
                    new_scores.get(player_id, 0) - old_scores.get(player_id, 0)
                )
                extra_deltas: dict[str, float] = {}
                for other_id in set(old_scores.keys()) | set(new_scores.keys()):
                    if other_id == player_id:
                        continue
                    diff = float(
                        new_scores.get(other_id, 0) - old_scores.get(other_id, 0)
                    )
                    if diff != 0:
                        extra_deltas[other_id] = diff

                move_number = int(next_state.get("move_count", 0)) + 1
                next_state["move_count"] = move_number
                next_state["consecutive_passes"] = 0

                move_entry = {
                    "word": word,
                    "player_id": player_id,
                    "positions": pos_dicts,
                    "word_points": word_tile_value,
                    "points_delta": actor_delta,
                    "move_number": move_number,
                }
                played_words.append(move_entry)
                next_state["played_words"] = played_words
                next_state["last_move"] = move_entry

                unowned = count_unowned_tiles(size, owners)
                next_state["unowned_count"] = unowned
                is_finished = unowned == 0

                if not is_finished:
                    self._advance_turn(next_state, player_id)

                return ActionOutcome(
                    state=next_state,
                    events=[
                        {
                            "type": "word_played",
                            "word": word,
                            "player_id": player_id,
                            "positions": pos_dicts,
                            "word_points": word_tile_value,
                            "points_delta": actor_delta,
                            "next_player_id": next_state["current_player_id"],
                        }
                    ],
                    points_delta=actor_delta,
                    is_correct_entry=True,
                    is_finished=is_finished,
                    extra_score_deltas=extra_deltas,
                )


silbenstreit_game = SilbenstreitGame()
