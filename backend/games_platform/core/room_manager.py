"""WebSocket room manager, multiplier decay/boost handling, and state broadcasting."""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from pydantic import TypeAdapter, ValidationError

from games_platform.core.db import Database
from games_platform.core.protocol import (
    ClientMessage,
    CursorMoveMessage,
    EndGameMessage,
    GameActionMessage,
    GameDefinition,
    PlayerSyncMessage,
    RemovePlayerMessage,
    ReturnToLobbyMessage,
    SetReadyMessage,
    StartGameMessage,
    UpdateConfigMessage,
    is_bot_id,
)
from games_platform.core.push import WebPushService, format_turn_notification

logger = logging.getLogger(__name__)

CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
MULTIPLIER_WINDOW_SECONDS = 10.0
MULTIPLIER_FACTOR = 1.1
# Bots act once the game state has been quiet (no human action) for this long.
BOT_DEBOUNCE_SECONDS = 3.0


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

    def __init__(self, db: Database, push_service: WebPushService | None = None) -> None:
        self.db = db
        self.push = push_service or WebPushService(db)
        self.games: dict[str, GameDefinition] = {}
        self.connections: dict[str, list[RoomConnection]] = {}
        self.cursors: dict[str, dict[str, dict[str, int | None]]] = {}
        self.midgame_inactive_players: dict[str, set[str]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self._push_tasks: set[asyncio.Task[Any]] = set()
        # Optional NotificationMailer: queues "your turn" mails alongside the push.
        self.mailer: Any = None
        # Bot players: pending debounce timer per room, rooms with a bot run in progress,
        # rooms that changed during that run, and strong refs to all bot tasks.
        self._bot_timers: dict[str, asyncio.Task[Any]] = {}
        self._bot_running: set[str] = set()
        self._bot_dirty: set[str] = set()
        self._bot_tasks: set[asyncio.Task[Any]] = set()

    def mark_player_active(self, room_id: str, player_id: str) -> None:
        """Mark a player as active in a room so closing their tab won't auto-remove them."""
        inactive_set = self.midgame_inactive_players.get(room_id)
        if inactive_set is not None:
            inactive_set.discard(player_id)
            if not inactive_set:
                self.midgame_inactive_players.pop(room_id, None)

    def _schedule_turn_push(
        self,
        *,
        room_id: str,
        game: GameDefinition,
        target_player_id: str,
        actor_name: str | None = None,
        events: list[dict[str, Any]] | None = None,
        reason: str = "action",
    ) -> None:
        payload = format_turn_notification(
            game_slug=game.slug,
            game_title=game.title,
            room_id=room_id,
            actor_name=actor_name,
            events=events,
            reason=reason,
        )
        task = asyncio.create_task(
            self.push.send_to_player(
                room_id=room_id,
                player_id=target_player_id,
                payload=payload,
            )
        )
        self._push_tasks.add(task)
        task.add_done_callback(self._on_push_done)
        if self.mailer is not None:
            mail_task = asyncio.create_task(self.mailer.queue_turn(target_player_id, room_id))
            self._push_tasks.add(mail_task)
            mail_task.add_done_callback(self._on_push_done)

    def is_connected(self, room_id: str, player_id: str) -> bool:
        return player_id in self._connected_player_ids(room_id)

    def _on_push_done(self, task: asyncio.Task[Any]) -> None:
        self._push_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("Turn push failed: %s", repr(exc))

    async def flush_push_tasks(self) -> None:
        """Wait for in-flight turn pushes. Used by tests to avoid racing create_task."""
        pending = [task for task in self._push_tasks if not task.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def flush_bot_tasks(self) -> None:
        """Wait for pending bot timers and runs. Used by tests."""
        while pending := [task for task in self._bot_tasks if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _sync_bot_players(
        self,
        room_id: str,
        game: GameDefinition,
        config: dict[str, Any],
    ) -> None:
        """Make the room's bot rows match game.get_bot_players(config)."""
        get_bot_players = getattr(game, "get_bot_players", None)
        wanted = list(get_bot_players(config)) if get_bot_players is not None else []
        wanted_ids = {bot["player_id"] for bot in wanted}
        for row in await self.db.get_room_players(room_id):
            if is_bot_id(row["player_id"]) and row["player_id"] not in wanted_ids:
                await self.db.remove_room_player(room_id, row["player_id"])
        for bot in wanted:
            await self.db.upsert_room_player(
                room_id=room_id,
                player_id=bot["player_id"],
                name=bot["name"],
                color=bot["color"],
            )
            await self.db.set_player_ready(room_id, bot["player_id"], True)

    def _schedule_bots(self, room_id: str, game: GameDefinition, config: dict[str, Any]) -> None:
        """(Re)start the room's debounce timer; bots act once it runs out."""
        get_bot_players = getattr(game, "get_bot_players", None)
        if getattr(game, "bot_turn", None) is None or get_bot_players is None:
            return
        if not get_bot_players(config):
            return
        timer = self._bot_timers.pop(room_id, None)
        if timer is not None:
            timer.cancel()
        task = asyncio.create_task(self._bot_debounce(room_id, game))
        self._bot_timers[room_id] = task
        self._track_bot_task(task)

    def _track_bot_task(self, task: asyncio.Task[Any]) -> None:
        self._bot_tasks.add(task)
        task.add_done_callback(self._bot_tasks.discard)

    async def _bot_debounce(self, room_id: str, game: GameDefinition) -> None:
        await asyncio.sleep(BOT_DEBOUNCE_SECONDS)
        # From here on a new state change must not cancel the (possibly slow) bot run.
        if self._bot_timers.get(room_id) is asyncio.current_task():
            del self._bot_timers[room_id]
        if room_id in self._bot_running:
            self._bot_dirty.add(room_id)
            return
        self._bot_running.add(room_id)
        try:
            while True:
                self._bot_dirty.discard(room_id)
                await self._run_bots_once(room_id, game)
                if room_id not in self._bot_dirty:
                    break
        finally:
            self._bot_running.discard(room_id)
            self._bot_dirty.discard(room_id)

    async def _run_bots_once(self, room_id: str, game: GameDefinition) -> None:
        room = await self.db.get_room(room_id)
        if room is None or room["status"] != "playing":
            return
        for bot in game.get_bot_players(room["config"]):  # type: ignore[attr-defined]
            bot_id = bot["player_id"]
            try:
                # Without the room lock: the bot may take seconds (LLM call).
                action = await game.bot_turn(  # type: ignore[attr-defined]
                    room_id, room["state"], room["config"], bot_id
                )
            except Exception as e:  # noqa: BLE001 - a broken bot must not kill the room
                logger.warning("Bot %s failed in room %s: %s", bot_id, room_id, repr(e))
                continue
            if action is None:
                continue
            async with self._get_lock(room_id):
                fresh = await self.db.get_room(room_id)
                if fresh is None or fresh["status"] != "playing":
                    return
                # A human changed what the bot reacts to while it was thinking (e.g. a new
                # clue): drop the outdated action. That change restarted the debounce timer,
                # so the bot gets another turn once things are quiet again.
                is_stale = getattr(game, "bot_action_is_stale", None)
                if is_stale is not None and is_stale(room["state"], fresh["state"]):
                    continue
                try:
                    await self._handle_game_action(fresh, game, bot_id, action)
                except ValidationError as e:
                    logger.warning("Invalid bot action in room %s: %s", room_id, repr(e))

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
        await self._sync_bot_players(room_id, game, config)
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
            self.midgame_inactive_players.pop(room_id, None)
            for conn in conns:
                try:
                    await conn.websocket.send_json({"type": "room_deleted", "room_id": room_id})
                    await conn.websocket.close(code=4004, reason="Room deleted")
                except (RuntimeError, OSError) as e:
                    logger.debug("WebSocket close failed for %s: %s", conn.player_id, repr(e))

        self.locks.pop(room_id, None)
        return deleted

    async def _remove_player_locked(
        self,
        room: dict[str, Any],
        player_id: str,
        *,
        actor_id: str | None = None,
    ) -> tuple[bool, bool]:
        """Remove a player while holding the room lock. Returns (removed, empty_room)."""
        room_id = room["id"]
        effective_actor = actor_id or player_id
        if is_bot_id(player_id):
            raise PermissionError("Turn the AI player off in the game settings instead.")

        if effective_actor == player_id:
            if room["host_player_id"] == player_id:
                raise PermissionError("The creator of this room cannot leave it.")
        else:
            if room["host_player_id"] != effective_actor:
                raise PermissionError("Only the creator of this room can remove other players.")
            if room["host_player_id"] == player_id:
                raise PermissionError("The creator of this room cannot be removed.")

        is_kicked = effective_actor != player_id
        removed = await self.db.remove_room_player(room_id, player_id)
        conns = [c for c in self.connections.get(room_id, []) if c.player_id == player_id]
        for conn in conns:
            self._remove_connection(room_id, conn)
            try:
                if is_kicked:
                    await conn.websocket.send_json(
                        {
                            "type": "player_removed",
                            "room_id": room_id,
                            "player_id": player_id,
                        }
                    )
                await conn.websocket.close(
                    code=4003 if is_kicked else 4000,
                    reason="Removed by host" if is_kicked else "Left room",
                )
            except (RuntimeError, OSError) as e:
                logger.debug("WebSocket close failed for %s: %s", conn.player_id, repr(e))

        if room_id in self.cursors:
            self.cursors[room_id].pop(player_id, None)
        if room_id in self.midgame_inactive_players:
            self.midgame_inactive_players[room_id].discard(player_id)
            if not self.midgame_inactive_players[room_id]:
                self.midgame_inactive_players.pop(room_id, None)

        if not removed:
            return False, False

        remaining = await self.db.get_room_players(room_id)
        if not remaining:
            await self.db.delete_room(room_id)
            self.connections.pop(room_id, None)
            self.cursors.pop(room_id, None)
            self.midgame_inactive_players.pop(room_id, None)
            return True, True

        new_state: dict[str, Any] | None = None
        prev_turn_player_id: str | None = None
        next_turn_player_id: str | None = None
        if isinstance(room["state"], dict) and "turn_order" in room["state"]:
            state = dict(room["state"])
            prev_turn_player_id = state.get("current_player_id")
            old_order: list[str] = list(state.get("turn_order") or [])
            if player_id in old_order:
                old_idx = old_order.index(player_id)
                new_order = [pid for pid in old_order if pid != player_id]
                state["turn_order"] = new_order
                if not new_order:
                    state["current_turn_index"] = 0
                    state["current_player_id"] = None
                elif state.get("current_player_id") == player_id:
                    next_idx = old_idx % len(new_order)
                    state["current_turn_index"] = next_idx
                    state["current_player_id"] = new_order[next_idx]
                elif state.get("current_player_id") in new_order:
                    state["current_turn_index"] = new_order.index(state["current_player_id"])
                if room["status"] == "playing":
                    game = self.get_game(room["game_slug"])
                    on_player_removed = getattr(game, "on_player_removed", None)
                    if on_player_removed is not None:
                        state = on_player_removed(state, room["config"], player_id)
                next_turn_player_id = state.get("current_player_id")
                new_state = state

        if new_state is not None:
            await self.db.update_room(
                room_id,
                state=new_state,
            )
            if (
                room["status"] == "playing"
                and next_turn_player_id
                and next_turn_player_id != prev_turn_player_id
            ):
                game = self.get_game(room["game_slug"])
                self._schedule_turn_push(
                    room_id=room_id,
                    game=game,
                    target_player_id=str(next_turn_player_id),
                    reason="player_left",
                )
        await self.broadcast_room_state(room_id)
        return True, False

    async def leave_room(
        self,
        room_id: str,
        player_id: str,
        *,
        actor_id: str | None = None,
    ) -> bool:
        empty_room = False
        async with self._get_lock(room_id):
            room = await self.db.get_room(room_id)
            if room is None:
                return False
            removed, empty_room = await self._remove_player_locked(
                room,
                player_id,
                actor_id=actor_id,
            )

        if empty_room:
            self.locks.pop(room_id, None)
        return removed

    async def cleanup_expired_rooms(self) -> list[str]:
        deleted_ids = await self.db.cleanup_expired_rooms()
        for room_id in deleted_ids:
            conns = list(self.connections.pop(room_id, []))
            self.cursors.pop(room_id, None)
            self.midgame_inactive_players.pop(room_id, None)
            self.locks.pop(room_id, None)
            for conn in conns:
                try:
                    await conn.websocket.send_json({"type": "room_deleted", "room_id": room_id})
                    await conn.websocket.close(code=4004, reason="Room expired")
                except (RuntimeError, OSError) as e:
                    logger.debug("WebSocket close failed for %s: %s", conn.player_id, repr(e))
        return deleted_ids

    def _connected_player_ids(self, room_id: str) -> set[str]:
        return {c.player_id for c in self.connections.get(room_id, [])}

    @staticmethod
    def _view_state(
        game: GameDefinition,
        room: dict[str, Any],
        viewer_id: str | None,
    ) -> dict[str, Any]:
        if room["status"] not in ("playing", "finished") or not room["state"]:
            return {}
        get_player_view = getattr(game, "get_player_view", None)
        if get_player_view is not None:
            return get_player_view(room["state"], room["config"], viewer_id)
        return game.get_public_view(room["state"], room["config"])

    async def build_room_snapshot(
        self,
        room_id: str,
        viewer_id: str | None = None,
    ) -> dict[str, Any] | None:
        loaded = await self._load_room_snapshot(room_id)
        if loaded is None:
            return None
        snapshot, room, game = loaded
        snapshot["state"] = self._view_state(game, room, viewer_id)
        return snapshot

    async def _load_room_snapshot(
        self,
        room_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], GameDefinition] | None:
        """Build the viewer-independent part of a room_state snapshot (without "state")."""
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
                    "is_connected": p["player_id"] in connected_ids or is_bot_id(p["player_id"]),
                    "is_bot": is_bot_id(p["player_id"]),
                    "score": round(float(p["score"]), 2),
                    "multiplier": round(eff_mult, 4),
                    "multiplier_remaining_ms": remaining_ms,
                    "last_correct_at": last_correct_at.isoformat() if last_correct_at else None,
                    "cursor": room_cursors.get(p["player_id"]),
                }
            )

        snapshot = {
            "type": "room_state",
            "room_id": room["id"],
            "game_slug": room["game_slug"],
            "status": room["status"],
            "host_player_id": room["host_player_id"],
            "config": room["config"],
            "state": {},
            "players": players_payload,
            "server_time": now.isoformat(),
        }
        return snapshot, room, game

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
        loaded = await self._load_room_snapshot(room_id)
        if loaded is None:
            return
        snapshot, room, game = loaded
        if getattr(game, "get_player_view", None) is None:
            snapshot["state"] = self._view_state(game, room, None)
            await self.broadcast(room_id, snapshot)
            return

        stale: list[RoomConnection] = []
        for conn in list(self.connections.get(room_id, [])):
            message = {**snapshot, "state": self._view_state(game, room, conn.player_id)}
            try:
                await conn.websocket.send_json(message)
            except (RuntimeError, OSError) as e:
                logger.debug("WebSocket send failed for %s: %s", conn.player_id, repr(e))
                stale.append(conn)
        for s in stale:
            self._remove_connection(room_id, s)

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
        async with self._get_lock(room_id):
            existing_players = await self.db.get_room_players(room_id)
            was_existing = any(p["player_id"] == player_id for p in existing_players)
            self.connections.setdefault(room_id, []).append(conn)
            await self.db.upsert_room_player(
                room_id=room_id,
                player_id=player_id,
                name=name,
                color=color,
            )
            room = await self.db.get_room(room_id)
            if room is not None and room["status"] == "playing":
                if not was_existing and player_id != room["host_player_id"]:
                    self.midgame_inactive_players.setdefault(room_id, set()).add(player_id)
                await self._add_midgame_player(room, player_id)
            await self.broadcast_room_state(room_id)
        return conn

    async def _add_midgame_player(self, room: dict[str, Any], player_id: str) -> None:
        """Append a player joining a running game to ``turn_order``.

        If the game was being played alone (one player in ``turn_order``) and the game sets
        ``solo_turn_goes_to_joiner``, the joiner gets the turn right away. The optional hook
        ``on_player_joined`` then fixes up game state (deal cards, restart a turn clock).
        """
        state = room["state"]
        if not isinstance(state, dict) or "turn_order" not in state:
            return
        turn_order: list[str] = list(state.get("turn_order") or [])
        if player_id in turn_order:
            return
        game = self.get_game(room["game_slug"])
        state = dict(state)
        was_solo = len(turn_order) == 1
        turn_order.append(player_id)
        state["turn_order"] = turn_order
        if was_solo and getattr(game, "solo_turn_goes_to_joiner", False):
            state["current_player_id"] = player_id
            state["current_turn_index"] = turn_order.index(player_id)
        elif not state.get("current_player_id"):
            state["current_player_id"] = turn_order[0]
        hook = getattr(game, "on_player_joined", None)
        if hook is not None:
            state = hook(state, room["config"], player_id)
        await self.db.update_room(room["id"], state=state)

    async def disconnect(self, room_id: str, conn: RoomConnection) -> None:
        empty_room = False
        async with self._get_lock(room_id):
            self._remove_connection(room_id, conn)
            if room_id in self.cursors and conn.player_id in self.cursors[room_id]:
                del self.cursors[room_id][conn.player_id]

            still_connected = conn.player_id in self._connected_player_ids(room_id)
            inactive_set = self.midgame_inactive_players.get(room_id)
            if not still_connected and inactive_set and conn.player_id in inactive_set:
                inactive_set.discard(conn.player_id)
                if not inactive_set:
                    self.midgame_inactive_players.pop(room_id, None)
                room = await self.db.get_room(room_id)
                if room is not None and room["host_player_id"] != conn.player_id:
                    _, empty_room = await self._remove_player_locked(
                        room,
                        conn.player_id,
                    )
                    if empty_room:
                        pass
                else:
                    await self.broadcast_room_state(room_id)
            else:
                await self.broadcast_room_state(room_id)

        if empty_room:
            self.locks.pop(room_id, None)

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
                    if is_bot_id(msg.player_id):
                        await conn.websocket.send_json(
                            {"type": "error", "message": "Reserved player id."}
                        )
                        return
                    old_player_id = conn.player_id
                    existing_players = await self.db.get_room_players(room_id)
                    was_existing = any(p["player_id"] == msg.player_id for p in existing_players)
                    conn.player_id = msg.player_id
                    await self.db.upsert_room_player(
                        room_id=room_id,
                        player_id=msg.player_id,
                        name=msg.name,
                        color=msg.color,
                    )
                    if room["status"] == "playing":
                        inactive_set = self.midgame_inactive_players.get(room_id)
                        if (
                            inactive_set is not None
                            and old_player_id in inactive_set
                            and old_player_id != msg.player_id
                        ):
                            inactive_set.discard(old_player_id)
                            if msg.player_id != room["host_player_id"]:
                                inactive_set.add(msg.player_id)
                        elif not was_existing and msg.player_id != room["host_player_id"]:
                            self.midgame_inactive_players.setdefault(room_id, set()).add(
                                msg.player_id
                            )
                        await self._add_midgame_player(room, msg.player_id)
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
                    await self._sync_bot_players(room_id, game, validated)
                    await self.broadcast_room_state(room_id)

                case StartGameMessage():
                    if room["host_player_id"] != conn.player_id:
                        await conn.websocket.send_json(
                            {"type": "error", "message": "Only the host can start the game."}
                        )
                        return
                    self.midgame_inactive_players.pop(room_id, None)
                    # Re-validate so a bot whose backend support went away is dropped.
                    config = game.validate_config(room["config"])
                    if config != room["config"]:
                        await self.db.update_room(room_id, config=config)
                        room = {**room, "config": config}
                    await self._sync_bot_players(room_id, game, config)
                    players_rows = await self.db.get_room_players(room_id)
                    # Bots never explain or take turns.
                    player_ids = [
                        p["player_id"] for p in players_rows if not is_bot_id(p["player_id"])
                    ]
                    player_ids = await self._order_for_next_game(room_id, player_ids)
                    initial_state = game.create_initial_state(
                        room["config"],
                        player_ids=player_ids,
                    )
                    await self.db.reset_room_scores(room_id)
                    await self.db.update_room(room_id, status="playing", state=initial_state)
                    await self.broadcast_room_state(room_id)
                    opening_player_id = (
                        initial_state.get("current_player_id")
                        if isinstance(initial_state, dict)
                        else None
                    )
                    if opening_player_id and opening_player_id != conn.player_id:
                        self._schedule_turn_push(
                            room_id=room_id,
                            game=game,
                            target_player_id=str(opening_player_id),
                            reason="game_started",
                        )

                case ReturnToLobbyMessage():
                    if room["host_player_id"] != conn.player_id:
                        return
                    self.midgame_inactive_players.pop(room_id, None)
                    await self.db.update_room(room_id, status="lobby", state={})
                    await self.broadcast_room_state(room_id)

                case EndGameMessage():
                    if room["host_player_id"] != conn.player_id:
                        await conn.websocket.send_json(
                            {"type": "error", "message": "Only the host can end the game."}
                        )
                        return
                    if room["status"] != "playing":
                        return
                    game = self.get_game(room["game_slug"])
                    on_game_ended = getattr(game, "on_game_ended", None)
                    if on_game_ended is not None:
                        await self.db.update_room(
                            room_id,
                            status="finished",
                            state=on_game_ended(room["state"], room["config"]),
                        )
                    else:
                        await self.db.update_room(room_id, status="finished")
                    await self.db.record_game_finished(room_id, room["game_slug"])
                    await self.broadcast_room_state(room_id)

                case RemovePlayerMessage():
                    try:
                        await self._remove_player_locked(
                            room,
                            msg.player_id,
                            actor_id=conn.player_id,
                        )
                    except PermissionError as e:
                        await conn.websocket.send_json({"type": "error", "message": str(e)})

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

    async def _order_for_next_game(self, room_id: str, player_ids: list[str]) -> list[str]:
        """Rotate the join order so the right player opens the game.

        The loser of the room's previous game starts; the first game (or when the
        loser has left) starts with a random player. Games take ``turn_order[0]``.
        """
        if len(player_ids) < 2:
            return player_ids
        starter = await self.db.get_next_starter_id(room_id)
        if starter not in player_ids:
            starter = random.choice(player_ids)
        idx = player_ids.index(starter)
        return player_ids[idx:] + player_ids[:idx]

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

        # Multiplier rule:
        # - Starts at 1.0 for the first right entry, then becomes 1.1 after the first right entry,
        #   so subsequent right entries within 10 seconds get 1.1x, 1.21x, etc.
        # - Multiplier is reset to 1.0 after 10 seconds or on a mistake.
        active_multiplier = compute_effective_multiplier(stored_mult, last_correct_at, now)

        prev_turn_player_id = (
            room["state"].get("current_player_id") if isinstance(room["state"], dict) else None
        )
        outcome = game.apply_action(
            state=room["state"],
            config=room["config"],
            player_id=player_id,
            action=action,
            player_multiplier=active_multiplier,
        )

        if outcome.is_correct_entry or outcome.is_mistake or outcome.state != room["state"]:
            self.mark_player_active(room_id, player_id)

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
            new_mult = round(active_multiplier * MULTIPLIER_FACTOR, 4)
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

        if not is_bot_id(player_id) and new_status == "playing":
            self._schedule_bots(room_id, game, room["config"])

        next_turn_player_id = (
            outcome.state.get("current_player_id") if isinstance(outcome.state, dict) else None
        )
        if (
            not outcome.is_finished
            and next_turn_player_id
            and next_turn_player_id != player_id
            and next_turn_player_id != prev_turn_player_id
        ):
            self._schedule_turn_push(
                room_id=room_id,
                game=game,
                target_player_id=str(next_turn_player_id),
                actor_name=str(player_row.get("name") or "Player"),
                events=outcome.events,
                reason="action",
            )
