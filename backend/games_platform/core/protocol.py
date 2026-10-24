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
