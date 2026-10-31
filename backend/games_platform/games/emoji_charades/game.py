"""Emoji Charades: one explainer describes a secret word with emoji sentences, others guess."""

from __future__ import annotations

import copy
import random
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from games_platform.core.protocol import ActionOutcome
from games_platform.games.emoji_charades.matching import is_close, is_match
from games_platform.games.emoji_charades.words import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    WORDS,
    WordEntry,
    normalize_language,
)

MODES = ("in_person", "remote")
DEFAULT_MODE = "in_person"
DEFAULT_ROUND_SECONDS = 120
MIN_ROUND_SECONDS = 30
MAX_ROUND_SECONDS = 600
CHOICE_COUNT = 3
MAX_SENTENCES = 5
MAX_EMOJIS_PER_SENTENCE = 16
MAX_EMOJI_LENGTH = 16
MAX_GUESS_LENGTH = 80
MAX_GUESS_FEED = 50
# Clients fire time_up from their own clock; tolerate a little drift.
TIME_UP_GRACE_SECONDS = 1.0

type Emoji = Annotated[str, Field(min_length=1, max_length=MAX_EMOJI_LENGTH)]
type Sentence = Annotated[list[Emoji], Field(max_length=MAX_EMOJIS_PER_SENTENCE)]


class ChooseWordAction(BaseModel):
    type: Literal["choose_word"] = "choose_word"
    index: int = Field(ge=0, lt=CHOICE_COUNT)


class SetSentencesAction(BaseModel):
    type: Literal["set_sentences"] = "set_sentences"
    sentences: list[Sentence] = Field(min_length=1, max_length=MAX_SENTENCES)


class GuessAction(BaseModel):
    type: Literal["guess"] = "guess"
    text: str = Field(min_length=1, max_length=MAX_GUESS_LENGTH)


class AwardAction(BaseModel):
    type: Literal["award"] = "award"
    player_id: str = Field(min_length=1)


class GiveUpAction(BaseModel):
    type: Literal["give_up"] = "give_up"


class TimeUpAction(BaseModel):
    type: Literal["time_up"] = "time_up"


class NextRoundAction(BaseModel):
    type: Literal["next_round"] = "next_round"


type EmojiCharadesAction = Annotated[
    ChooseWordAction
    | SetSentencesAction
    | GuessAction
    | AwardAction
    | GiveUpAction
    | TimeUpAction
    | NextRoundAction,
    Field(discriminator="type"),
]

EMOJI_CHARADES_ACTION_ADAPTER: TypeAdapter[EmojiCharadesAction] = TypeAdapter(
    EmojiCharadesAction
)


def pick_choices(
    language: str,
    used_words: list[str],
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Pick CHOICE_COUNT unused words, preferring distinct categories."""
    rng = rng or random.Random()
    pool = WORDS[normalize_language(language)]
    used = set(used_words)
    fresh = [entry for entry in pool if entry.text not in used]
    if len(fresh) < CHOICE_COUNT:
        fresh = list(pool)
    rng.shuffle(fresh)

    picked: list[WordEntry] = []
    seen_categories: set[str] = set()
    for entry in fresh:
        if entry.category not in seen_categories:
            picked.append(entry)
            seen_categories.add(entry.category)
        if len(picked) == CHOICE_COUNT:
            break
    for entry in fresh:
        if len(picked) == CHOICE_COUNT:
            break
        if entry not in picked:
            picked.append(entry)
    return [entry.to_dict() for entry in picked]


class EmojiCharadesGame:
    """Self-contained Emoji Charades implementation (in person or remote, optionally timed)."""

    slug: str = "emoji-charades"
    title: str = "Emoji Charades"
    description: str = (
        "Explain a secret word, movie, or quote using only emoji sentences while everyone "
        "else guesses. Play in person by shouting answers or remotely with typo-tolerant "
        "typed guesses."
    )

    def default_config(self) -> dict[str, Any]:
        return {
            "mode": DEFAULT_MODE,
            "timed": False,
            "round_seconds": DEFAULT_ROUND_SECONDS,
            "language": DEFAULT_LANGUAGE,
            "scoring_enabled": True,
        }

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        mode = str(raw_config.get("mode", DEFAULT_MODE))
        if mode not in MODES:
            mode = DEFAULT_MODE
        try:
            round_seconds = int(raw_config.get("round_seconds", DEFAULT_ROUND_SECONDS))
        except (TypeError, ValueError):
            round_seconds = DEFAULT_ROUND_SECONDS
        round_seconds = max(MIN_ROUND_SECONDS, min(MAX_ROUND_SECONDS, round_seconds))
        return {
            "mode": mode,
            "timed": bool(raw_config.get("timed", False)),
            "round_seconds": round_seconds,
            "language": normalize_language(str(raw_config.get("language") or DEFAULT_LANGUAGE)),
            "scoring_enabled": bool(raw_config.get("scoring_enabled", True)),
        }

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        validated = self.validate_config(config)
        # Random first explainer, then circular in this order.
        turn_order = list(player_ids or [])
        random.shuffle(turn_order)
        explainer_id = turn_order[0] if turn_order else None
        return {
            "language": validated["language"],
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "turn_order": turn_order,
            "current_turn_index": 0,
            "current_player_id": explainer_id,
            "explainer_id": explainer_id,
            "phase": "choosing",
            "round_number": 1,
            "choices": pick_choices(validated["language"], []),
            "word": None,
            "sentences": [[]],
            "deadline": None,
            "guesses": [],
            "last_result": None,
            "used_words": [],
        }

    def get_player_view(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        viewer_id: str | None,
    ) -> dict[str, Any]:
        _ = config
        view = dict(state)
        view.pop("used_words", None)
        is_explainer = viewer_id is not None and viewer_id == state.get("explainer_id")
        if not is_explainer:
            view["choices"] = []
            word = state.get("word")
            if word is not None and state.get("phase") != "reveal":
                # Guessers get the category as a hint, never the answer.
                view["word"] = {"category": word.get("category")}
        return view

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.get_player_view(state, config, None)

    def on_player_removed(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
    ) -> dict[str, Any]:
        _ = config
        if player_id != state.get("explainer_id") or state.get("phase") == "reveal":
            return state
        next_state = copy.deepcopy(state)
        # The room manager already moved current_player_id on to the next explainer.
        self._end_round(next_state, reason="explainer_left", winner_id=None, points={})
        return next_state

    def _next_explainer(self, state: dict[str, Any]) -> str | None:
        turn_order: list[str] = list(state.get("turn_order") or [])
        if not turn_order:
            return None
        explainer_id = state.get("explainer_id")
        if explainer_id in turn_order:
            return turn_order[(turn_order.index(explainer_id) + 1) % len(turn_order)]
        current = state.get("current_player_id")
        return current if current in turn_order else turn_order[0]

    def _end_round(
        self,
        state: dict[str, Any],
        *,
        reason: str,
        winner_id: str | None,
        points: dict[str, float],
    ) -> dict[str, Any]:
        word = state.get("word")
        if reason != "explainer_left":
            next_explainer = self._next_explainer(state)
            state["current_player_id"] = next_explainer
            turn_order: list[str] = list(state.get("turn_order") or [])
            if next_explainer in turn_order:
                state["current_turn_index"] = turn_order.index(next_explainer)
        result = {
            "type": "round_ended",
            "round_number": state.get("round_number", 1),
            "reason": reason,
            "word": word.get("text") if word else None,
            "category": word.get("category") if word else None,
            "explainer_id": state.get("explainer_id"),
            "winner_id": winner_id,
            "points": points,
            "next_player_id": state.get("current_player_id"),
        }
        state["phase"] = "reveal"
        state["deadline"] = None
        state["choices"] = []
        state["last_result"] = result
        return result

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        _ = player_multiplier
        parsed = EMOJI_CHARADES_ACTION_ADAPTER.validate_python(action)
        next_state = copy.deepcopy(state)
        phase = next_state.get("phase")
        explainer_id = next_state.get("explainer_id")
        is_explainer = player_id == explainer_id
        mode = config.get("mode", DEFAULT_MODE)
        timed = bool(config.get("timed", False))

        def rejected(reason: str) -> ActionOutcome:
            return ActionOutcome(
                state=state,
                events=[{"type": "action_rejected", "player_id": player_id, "reason": reason}],
            )

        match parsed:
            case ChooseWordAction():
                if phase != "choosing" or not is_explainer:
                    return rejected("not_allowed")
                choices = next_state.get("choices") or []
                if parsed.index >= len(choices):
                    return rejected("invalid_choice")
                word = choices[parsed.index]
                next_state["word"] = word
                next_state["choices"] = []
                next_state["phase"] = "explaining"
                next_state["sentences"] = [[]]
                next_state["guesses"] = []
                next_state["used_words"] = [*next_state.get("used_words", []), word["text"]]
                if timed:
                    seconds = int(config.get("round_seconds", DEFAULT_ROUND_SECONDS))
                    deadline = datetime.now(UTC) + timedelta(seconds=seconds)
                    next_state["deadline"] = deadline.isoformat()
                return ActionOutcome(
                    state=next_state,
                    events=[{"type": "word_chosen", "explainer_id": player_id}],
                )

            case SetSentencesAction():
                if phase != "explaining" or not is_explainer:
                    return rejected("not_allowed")
                next_state["sentences"] = [list(s) for s in parsed.sentences]
                return ActionOutcome(state=next_state)

            case GuessAction():
                if phase != "explaining" or is_explainer or mode != "remote":
                    return rejected("not_allowed")
                word = next_state.get("word") or {}
                answers = [word.get("text", ""), *word.get("aliases", [])]
                text = parsed.text.strip()
                guesses: list[dict[str, Any]] = list(next_state.get("guesses") or [])
                if is_match(text, answers):
                    points = {player_id: 1.0}
                    extra: dict[str, float] = {}
                    if timed and explainer_id:
                        points[explainer_id] = 1.0
                        extra[explainer_id] = 1.0
                    guesses.append({"player_id": player_id, "correct": True})
                    next_state["guesses"] = guesses[-MAX_GUESS_FEED:]
                    result = self._end_round(
                        next_state, reason="guessed", winner_id=player_id, points=points
                    )
                    return ActionOutcome(
                        state=next_state,
                        events=[result],
                        points_delta=1.0,
                        is_correct_entry=True,
                        extra_score_deltas=extra,
                    )
                close = is_close(text, answers)
                guesses.append({"player_id": player_id, "text": text, "close": close})
                next_state["guesses"] = guesses[-MAX_GUESS_FEED:]
                return ActionOutcome(
                    state=next_state,
                    events=[
                        {"type": "guess_wrong", "player_id": player_id, "text": text, "close": close}
                    ],
                )

            case AwardAction():
                if phase != "explaining" or not is_explainer or mode != "in_person":
                    return rejected("not_allowed")
                winner_id = parsed.player_id
                if winner_id == player_id or winner_id not in (next_state.get("turn_order") or []):
                    return rejected("invalid_player")
                points = {winner_id: 1.0}
                if timed:
                    points[player_id] = 1.0
                result = self._end_round(
                    next_state, reason="guessed", winner_id=winner_id, points=points
                )
                return ActionOutcome(
                    state=next_state,
                    events=[result],
                    points_delta=1.0 if timed else 0.0,
                    is_correct_entry=timed,
                    extra_score_deltas={winner_id: 1.0},
                )

            case GiveUpAction():
                if phase not in ("choosing", "explaining") or not is_explainer:
                    return rejected("not_allowed")
                result = self._end_round(next_state, reason="gave_up", winner_id=None, points={})
                return ActionOutcome(state=next_state, events=[result])

            case TimeUpAction():
                deadline = next_state.get("deadline")
                if phase != "explaining" or not deadline:
                    return rejected("not_allowed")
                remaining = datetime.fromisoformat(deadline) - datetime.now(UTC)
                if remaining.total_seconds() > TIME_UP_GRACE_SECONDS:
                    return rejected("too_early")
                result = self._end_round(next_state, reason="time_up", winner_id=None, points={})
                return ActionOutcome(state=next_state, events=[result])

            case NextRoundAction():
                if phase != "reveal":
                    return rejected("not_allowed")
                next_explainer = next_state.get("current_player_id")
                turn_order = list(next_state.get("turn_order") or [])
                if next_explainer not in turn_order:
                    if not turn_order:
                        return rejected("no_players")
                    next_explainer = turn_order[0]
                    next_state["current_player_id"] = next_explainer
                next_state["current_turn_index"] = turn_order.index(next_explainer)
                next_state["explainer_id"] = next_explainer
                next_state["phase"] = "choosing"
                next_state["round_number"] = int(next_state.get("round_number", 1)) + 1
                next_state["choices"] = pick_choices(
                    str(next_state.get("language", DEFAULT_LANGUAGE)),
                    list(next_state.get("used_words") or []),
                )
                next_state["word"] = None
                next_state["sentences"] = [[]]
                next_state["guesses"] = []
                next_state["deadline"] = None
                return ActionOutcome(
                    state=next_state,
                    events=[{"type": "round_started", "explainer_id": next_explainer}],
                )


emoji_charades_game = EmojiCharadesGame()
