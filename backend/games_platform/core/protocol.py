"""Core protocol, GameDefinition interface, and Pydantic v2 message models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, Field


@dataclass
class ActionOutcome:
    """Result returned by a GameDefinition.apply_action call."""

    state: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    points_delta: float = 0.0
    is_correct_entry: bool = False
    is_mistake: bool = False
    is_finished: bool = False
    # Additional score changes for other players (e.g. flag challenge transfers).
    extra_score_deltas: dict[str, float] = field(default_factory=dict)


class GameDefinition(Protocol):
    """Protocol that every self-contained game module implements."""

    slug: str
    title: str
    description: str

    def default_config(self) -> dict[str, Any]:
        """Return default room configuration."""
        ...

    def validate_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize room configuration."""
        ...

    def create_initial_state(
        self,
        config: dict[str, Any],
        player_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate initial server-side state when a game starts."""
        ...

    def get_public_view(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Return the client-safe view of the game state (omitting hidden solutions)."""
        ...

    def apply_action(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        player_id: str,
        action: dict[str, Any],
        player_multiplier: float,
    ) -> ActionOutcome:
        """Apply a player action to the state and compute score outcomes."""
        ...


# Optional GameDefinition hooks, looked up with getattr by the RoomManager:
#
# def get_player_view(self, state, config, viewer_id: str | None) -> dict[str, Any]
#     Per-viewer state (e.g. hide a secret word from guessers). When present, every
#     connection gets its own room_state snapshot instead of get_public_view.
#
# def on_player_removed(self, state, config, player_id: str) -> dict[str, Any]
#     Adjust game state after a player left or was removed mid-game (after the
#     shared turn_order fix-up).
#
# solo_turn_goes_to_joiner: bool
#     Turn-based games: when someone joins a running game that was played alone (one
#     player in turn_order) and that player has already moved (state["move_count"] > 0),
#     the joiner gets the turn right away. Before the first move the opener keeps it.
#
# def on_player_joined(self, state, config, player_id: str) -> dict[str, Any]
#     Adjust game state after a player joined mid-game (after the shared turn_order
#     append and the solo hand-over), e.g. deal cards or restart a turn clock.
#
# def on_game_ended(self, state, config) -> dict[str, Any]
#     Adjust game state when the host ends the game early with end_game (e.g. reveal
#     hidden cards on the final screen).
#
# def get_bot_players(self, config) -> list[dict[str, str]]
#     Server-side bot players ({player_id, name, color}; ids start with BOT_ID_PREFIX)
#     the room should have for this config. They get a room_players row (score, player
#     bar) but are never added to turn_order and cannot be removed by the host.
#
# async def bot_turn(self, room_id, state, config, bot_id: str) -> dict[str, Any] | None
#     Called BOT_DEBOUNCE_SECONDS after the last state change by a human. Returns a
#     game action for the bot (applied like a player action) or None. Must only look
#     at what the bot is allowed to see (e.g. get_player_view with viewer_id=bot_id).

BOT_ID_PREFIX = "ai:"


def is_bot_id(player_id: str) -> bool:
    return player_id.startswith(BOT_ID_PREFIX)


# --- Client -> Server WebSocket Messages ---


class PlayerSyncMessage(BaseModel):
    type: Literal["player_sync"] = "player_sync"
    player_id: str
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(min_length=4, max_length=32)


class SetReadyMessage(BaseModel):
    type: Literal["set_ready"] = "set_ready"
    is_ready: bool


class UpdateConfigMessage(BaseModel):
    type: Literal["update_config"] = "update_config"
    config: dict[str, Any]


class StartGameMessage(BaseModel):
    type: Literal["start_game"] = "start_game"


class ReturnToLobbyMessage(BaseModel):
    type: Literal["return_to_lobby"] = "return_to_lobby"


class EndGameMessage(BaseModel):
    type: Literal["end_game"] = "end_game"


class RemovePlayerMessage(BaseModel):
    type: Literal["remove_player"] = "remove_player"
    player_id: str = Field(min_length=1)


class GameActionMessage(BaseModel):
    type: Literal["game_action"] = "game_action"
    action: dict[str, Any]


class CursorMoveMessage(BaseModel):
    type: Literal["cursor_move"] = "cursor_move"
    row: int | None = None
    col: int | None = None


type ClientMessage = Annotated[
    PlayerSyncMessage
    | SetReadyMessage
    | UpdateConfigMessage
    | StartGameMessage
    | ReturnToLobbyMessage
    | EndGameMessage
    | RemovePlayerMessage
    | GameActionMessage
    | CursorMoveMessage,
    Field(discriminator="type"),
]


# --- REST API Models ---


class CreateRoomRequest(BaseModel):
    game_slug: str = "sudoku"
    host_player_id: str
    host_name: str = "Player"
    host_color: str = "#2563eb"
    config: dict[str, Any] = Field(default_factory=dict)


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class PushSubscribeRequest(BaseModel):
    player_id: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    keys: PushSubscriptionKeys
    # Set when switched on from inside a room: counts as activity there.
    room_id: str | None = None


class PlayerPublicInfo(BaseModel):
    player_id: str
    name: str
    color: str
    is_ready: bool
    is_connected: bool
    score: float
    multiplier: float
    last_correct_at: datetime | None = None
    cursor: dict[str, int | None] | None = None
