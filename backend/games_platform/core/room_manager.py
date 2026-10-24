"""WebSocket room manager, multiplier decay/boost handling, and state broadcasting."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from pydantic import TypeAdapter, ValidationError

from games_platform.core.db import Database
from games_platform.core.protocol import (
    ClientMessage,
    CursorMoveMessage,
    GameActionMessage,
    GameDefinition,
    PlayerSyncMessage,
    ReturnToLobbyMessage,
    SetReadyMessage,
    StartGameMessage,
    UpdateConfigMessage,
)

logger = logging.getLogger(__name__)

CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
MULTIPLIER_WINDOW_SECONDS = 10.0
MULTIPLIER_FACTOR = 1.1


def generate_room_id(length: int = 6) -> str:
    """Generate a URL-friendly unambiguous room code."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def compute_effective_multiplier(
    stored_multiplier: float,
    last_correct_at: datetime | None,
    now: datetime,
) -> float:
    """Return active multiplier if within the 10-second window, else 1.0."""
    if last_correct_at is None:
        return 1.0
    elapsed = (now - last_correct_at).total_seconds()
    if elapsed <= MULTIPLIER_WINDOW_SECONDS:
        return stored_multiplier
    return 1.0


class RoomConnection:
    """Represents a live WebSocket connection in a room."""

    def __init__(self, websocket: WebSocket, player_id: str) -> None:
        self.websocket = websocket
        self.player_id = player_id


class RoomManager:
    """Manages active WebSocket connections and coordinates state persistence per room."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.games: dict[str, GameDefinition] = {}
        self.connections: dict[str, list[RoomConnection]] = {}
        self.cursors: dict[str, dict[str, dict[str, int | None]]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def register_game(self, game: GameDefinition) -> None:
        self.games[game.slug] = game

    def get_game(self, slug: str) -> GameDefinition:
        if slug not in self.games:
            raise KeyError(f"Unknown game slug: {slug}")
        return self.games[slug]

    def _get_lock(self, room_id: str) -> asyncio.Lock:
        if room_id not in self.locks:
            self.locks[room_id] = asyncio.Lock()
        return self.locks[room_id]

    async def create_room(
        self,
        *,
        game_slug: str,
        host_player_id: str,
        host_name: str,
        host_color: str,
        raw_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        game = self.get_game(game_slug)
        config = game.validate_config(raw_config or game.default_config())
        room_id = generate_room_id()
        for _ in range(5):
            if await self.db.get_room(room_id) is None:
                break
            room_id = generate_room_id()

        room = await self.db.create_room(
            room_id=room_id,
            game_slug=game_slug,
            status="lobby",
            config=config,
            state={},
            host_player_id=host_player_id,
        )
        await self.db.upsert_room_player(
            room_id=room_id,
            player_id=host_player_id,
            name=host_name,
            color=host_color,
        )
        return room

    async def delete_room(self, room_id: str, player_id: str) -> bool:
        async with self._get_lock(room_id):
            room = await self.db.get_room(room_id)
            if room is None:
                return False
            if room["host_player_id"] != player_id:
                raise PermissionError("Only the player who started this game can delete it.")

            deleted = await self.db.delete_room(room_id)
            conns = list(self.connections.pop(room_id, []))
            self.cursors.pop(room_id, None)
            for conn in conns:
                try:
                    await conn.websocket.send_json(
                        {"type": "room_deleted", "room_id": room_id}
                    )
                    await conn.websocket.close(code=4004, reason="Room deleted")
                except (RuntimeError, OSError) as e:
                    logger.debug("WebSocket close failed for %s: %s", conn.player_id, repr(e))

        self.locks.pop(room_id, None)
        return deleted

    def _connected_player_ids(self, room_id: str) -> set[str]:
        return {c.player_id for c in self.connections.get(room_id, [])}

    async def build_room_snapshot(self, room_id: str) -> dict[str, Any] | None:
        room = await self.db.get_room(room_id)
        if room is None:
            return None

        game = self.get_game(room["game_slug"])
        players_rows = await self.db.get_room_players(room_id)
        connected_ids = self._connected_player_ids(room_id)
        room_cursors = self.cursors.get(room_id, {})
        now = datetime.now(UTC)

        players_payload: list[dict[str, Any]] = []
        for p in players_rows:
            last_correct_at: datetime | None = p["last_correct_at"]
            eff_mult = compute_effective_multiplier(float(p["multiplier"]), last_correct_at, now)
            remaining_ms = 0
            if last_correct_at is not None:
                elapsed = (now - last_correct_at).total_seconds()
                if elapsed < MULTIPLIER_WINDOW_SECONDS:
                    remaining_ms = int((MULTIPLIER_WINDOW_SECONDS - elapsed) * 1000)

            players_payload.append(
                {
                    "player_id": p["player_id"],
                    "name": p["name"],
                    "color": p["color"],
                    "is_ready": bool(p["is_ready"]),
                    "is_connected": p["player_id"] in connected_ids,
                    "score": round(float(p["score"]), 2),
                    "multiplier": round(eff_mult, 4),
                    "multiplier_remaining_ms": remaining_ms,
                    "last_correct_at": last_correct_at.isoformat() if last_correct_at else None,
                    "cursor": room_cursors.get(p["player_id"]),
                }
            )

        public_state = (
            game.get_public_view(room["state"], room["config"])
            if room["status"] in ("playing", "finished") and room["state"]
            else {}
        )

        return {
            "type": "room_state",
            "room_id": room["id"],
            "game_slug": room["game_slug"],
            "status": room["status"],
            "host_player_id": room["host_player_id"],
            "config": room["config"],
            "state": public_state,
            "players": players_payload,
            "server_time": now.isoformat(),
        }

    async def broadcast(self, room_id: str, message: dict[str, Any]) -> None:
        conns = list(self.connections.get(room_id, []))
        stale: list[RoomConnection] = []
        for conn in conns:
            try:
                await conn.websocket.send_json(message)
            except (RuntimeError, OSError) as e:
                logger.debug("WebSocket send failed for %s: %s", conn.player_id, repr(e))
                stale.append(conn)
        if stale:
            for s in stale:
                self._remove_connection(room_id, s)

    async def broadcast_room_state(self, room_id: str) -> None:
        snapshot = await self.build_room_snapshot(room_id)
        if snapshot is not None:
            await self.broadcast(room_id, snapshot)

    def _remove_connection(self, room_id: str, conn: RoomConnection) -> None:
        conns = self.connections.get(room_id, [])
        if conn in conns:
            conns.remove(conn)
        if not conns and room_id in self.connections:
            del self.connections[room_id]

    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        player_id: str,
        name: str,
        color: str,
    ) -> RoomConnection:
        await websocket.accept()
        conn = RoomConnection(websocket=websocket, player_id=player_id)
        self.connections.setdefault(room_id, []).append(conn)
        await self.db.upsert_room_player(
            room_id=room_id,
            player_id=player_id,
            name=name,
            color=color,
        )
        room = await self.db.get_room(room_id)
        if (
            room is not None
            and room["status"] == "playing"
            and isinstance(room["state"], dict)
            and "turn_order" in room["state"]
        ):
            state = dict(room["state"])
            turn_order: list[str] = list(state.get("turn_order") or [])
            if player_id not in turn_order:
                turn_order.append(player_id)
                state["turn_order"] = turn_order
                if not state.get("current_player_id"):
                    state["current_player_id"] = turn_order[0]
                await self.db.update_room(room_id, state=state)
        await self.broadcast_room_state(room_id)
        return conn

    async def disconnect(self, room_id: str, conn: RoomConnection) -> None:
        self._remove_connection(room_id, conn)
        if room_id in self.cursors and conn.player_id in self.cursors[room_id]:
            del self.cursors[room_id][conn.player_id]
        await self.broadcast_room_state(room_id)

    async def handle_client_message(
        self,
        room_id: str,
        conn: RoomConnection,
        raw_data: dict[str, Any],
    ) -> None:
        try:
            msg = CLIENT_MESSAGE_ADAPTER.validate_python(raw_data)
        except ValidationError as e:
            logger.warning("Invalid WS message in room %s: %s", room_id, repr(e))
            await conn.websocket.send_json({"type": "error", "message": f"Invalid message: {e!r}"})
            return

        async with self._get_lock(room_id):
            room = await self.db.get_room(room_id)
            if room is None:
                await conn.websocket.send_json({"type": "error", "message": "Room not found"})
                return

            game = self.get_game(room["game_slug"])

            match msg:
                case PlayerSyncMessage():
                    conn.player_id = msg.player_id
                    await self.db.upsert_room_player(
                        room_id=room_id,
                        player_id=msg.player_id,
                        name=msg.name,
                        color=msg.color,
                    )
                    if (
                        room["status"] == "playing"
                        and isinstance(room["state"], dict)
                        and "turn_order" in room["state"]
                    ):
                        state = dict(room["state"])
                        turn_order: list[str] = list(state.get("turn_order") or [])
                        if msg.player_id not in turn_order:
                            turn_order.append(msg.player_id)
                            state["turn_order"] = turn_order
                            if not state.get("current_player_id"):
                                state["current_player_id"] = turn_order[0]
                            await self.db.update_room(room_id, state=state)
                    await self.broadcast_room_state(room_id)

                case SetReadyMessage():
                    await self.db.set_player_ready(room_id, conn.player_id, msg.is_ready)
                    await self.broadcast_room_state(room_id)

                case UpdateConfigMessage():
                    if room["host_player_id"] != conn.player_id:
                        await conn.websocket.send_json(
                            {"type": "error", "message": "Only the host can update game settings."}
                        )
                        return
                    if room["status"] != "lobby":
                        return
                    merged = {**room["config"], **msg.config}
                    validated = game.validate_config(merged)
                    await self.db.update_room(room_id, config=validated)
                    await self.broadcast_room_state(room_id)

                case StartGameMessage():
                    if room["host_player_id"] != conn.player_id:
                        await conn.websocket.send_json(
                            {"type": "error", "message": "Only the host can start the game."}
                        )
                        return
                    players_rows = await self.db.get_room_players(room_id)
                    player_ids = [p["player_id"] for p in players_rows]
                    initial_state = game.create_initial_state(
                        room["config"],
                        player_ids=player_ids,
                    )
                    await self.db.reset_room_scores(room_id)
                    await self.db.update_room(room_id, status="playing", state=initial_state)
                    await self.broadcast_room_state(room_id)

                case ReturnToLobbyMessage():
                    if room["host_player_id"] != conn.player_id:
                        return
                    await self.db.update_room(room_id, status="lobby", state={})
                    await self.broadcast_room_state(room_id)

                case CursorMoveMessage():
                    self.cursors.setdefault(room_id, {})[conn.player_id] = {
                        "row": msg.row,
                        "col": msg.col,
                    }
                    await self.broadcast(
                        room_id,
                        {
                            "type": "cursor_update",
                            "player_id": conn.player_id,
                            "row": msg.row,
                            "col": msg.col,
                        },
                    )

                case GameActionMessage():
                    if room["status"] != "playing":
                        return
                    await self._handle_game_action(room, game, conn.player_id, msg.action)

    async def _handle_game_action(
        self,
        room: dict[str, Any],
        game: GameDefinition,
        player_id: str,
        action: dict[str, Any],
    ) -> None:
        room_id = room["id"]
        players = await self.db.get_room_players(room_id)
        player_row = next((p for p in players if p["player_id"] == player_id), None)
        if player_row is None:
            return

        now = datetime.now(UTC)
        last_correct_at: datetime | None = player_row["last_correct_at"]
        stored_mult = float(player_row["multiplier"])
        scoring_enabled = bool(room["config"].get("scoring_enabled", True))

        # Multiplier rule from idea.md:
        # - For doing correct entries within 10 seconds user gets multiplier = 1.1 * multiplier
        # - Multiplier is reset to 1 after 10 seconds.
        if last_correct_at is not None and (now - last_correct_at).total_seconds() <= MULTIPLIER_WINDOW_SECONDS:
            active_multiplier = round(stored_mult * MULTIPLIER_FACTOR, 4)
        else:
            active_multiplier = 1.0

        outcome = game.apply_action(
            state=room["state"],
            config=room["config"],
            player_id=player_id,
            action=action,
            player_multiplier=active_multiplier,
        )

        new_score = float(player_row["score"])
        new_mult = stored_mult
        new_last_correct = last_correct_at

        if outcome.is_mistake:
            if scoring_enabled:
                new_score = round(new_score + outcome.points_delta, 2)
            new_mult = 1.0
            new_last_correct = None
            await self.db.update_player_score(
                room_id,
                player_id,
                score=new_score,
                multiplier=new_mult,
                last_correct_at=new_last_correct,
            )
        elif outcome.is_correct_entry:
            if scoring_enabled:
                new_score = round(new_score + outcome.points_delta, 2)
            new_mult = active_multiplier
            new_last_correct = now
            await self.db.update_player_score(
                room_id,
                player_id,
                score=new_score,
                multiplier=new_mult,
                last_correct_at=new_last_correct,
            )

        if scoring_enabled and outcome.extra_score_deltas:
            for other_id, delta in outcome.extra_score_deltas.items():
                if other_id == player_id or delta == 0:
                    continue
                other = next((p for p in players if p["player_id"] == other_id), None)
                if other is None:
                    continue
                other_score = round(float(other["score"]) + float(delta), 2)
                await self.db.update_player_score(
                    room_id,
                    other_id,
                    score=other_score,
                    multiplier=float(other["multiplier"]),
                    last_correct_at=other["last_correct_at"],
                )

        new_status = "finished" if outcome.is_finished else room["status"]
        await self.db.update_room(room_id, status=new_status, state=outcome.state)

        if outcome.is_finished and room["status"] != "finished":
            await self.db.record_game_finished(room_id, room["game_slug"])

        for event in outcome.events:
            await self.broadcast(room_id, event)

        await self.broadcast_room_state(room_id)
