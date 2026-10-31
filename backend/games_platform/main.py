"""FastAPI application factory with REST and WebSocket endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg import Error as PsycopgError

from games_platform.core.db import Database, db
from games_platform.core.protocol import (
    CreateRoomRequest,
    GameDefinition,
    PushSubscribeRequest,
)
from games_platform.core.push import (
    MAX_PUSH_SUBSCRIPTIONS_PER_PLAYER,
    PushEndpointError,
    validate_push_endpoint,
)
from games_platform.core.room_manager import RoomManager
from games_platform.games.emoji_charades.game import emoji_charades_game
from games_platform.games.kaesekaestchen.game import kaesekaestchen_game
from games_platform.games.minesweeper.game import minesweeper_game
from games_platform.games.silbenstreit.game import silbenstreit_game
from games_platform.games.sudoku.game import sudoku_game

logger = logging.getLogger(__name__)

ALL_GAMES: dict[str, GameDefinition] = {
    sudoku_game.slug: sudoku_game,
    kaesekaestchen_game.slug: kaesekaestchen_game,
    minesweeper_game.slug: minesweeper_game,
    silbenstreit_game.slug: silbenstreit_game,
    emoji_charades_game.slug: emoji_charades_game,
}


def _mount_static(app: FastAPI) -> None:
    """Serve ACME challenges and the built SPA when STATIC_DIR is set (production)."""
    acme_webroot = os.environ.get("ACME_WEBROOT", "").strip()
    if acme_webroot:
        challenge_dir = Path(acme_webroot) / ".well-known" / "acme-challenge"
        if challenge_dir.is_dir():
            # nginx-proxy forwards ACME HTTP-01 here until the first cert exists.
            app.mount(
                "/.well-known/acme-challenge",
                StaticFiles(directory=challenge_dir),
                name="acme",
            )

    static_dir = os.environ.get("STATIC_DIR", "").strip()
    if not static_dir:
        return
    root = Path(static_dir)
    index_html = root / "index.html"
    spa_fallback_html = root / "200.html"
    if not spa_fallback_html.is_file():
        spa_fallback_html = index_html
    if not spa_fallback_html.is_file():
        logger.warning("STATIC_DIR=%s has no 200.html/index.html; skipping SPA mount", static_dir)
        return

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str = "") -> FileResponse:
        if full_path.startswith(("api/", "ws/", ".well-known/")):
            raise HTTPException(status_code=404, detail="Not found")
        root_resolved = root.resolve()
        candidate = (root / full_path).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Not found") from e
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if full_path:
            # adapter-static prerender: /sudoku → sudoku.html (or sudoku/index.html)
            flat_html = (root / f"{full_path}.html").resolve()
            try:
                flat_html.relative_to(root_resolved)
            except ValueError as e:
                raise HTTPException(status_code=404, detail="Not found") from e
            if flat_html.is_file():
                return FileResponse(flat_html)
            nested_index = candidate / "index.html"
            if nested_index.is_file():
                return FileResponse(nested_index)
        if not full_path and index_html.is_file():
            return FileResponse(index_html)
        return FileResponse(spa_fallback_html)


def create_app(
    *,
    database: Database | None = None,
    enabled_games: list[str] | None = None,
) -> FastAPI:
    active_db = database or db
    manager = RoomManager(active_db)

    slugs = enabled_games or list(ALL_GAMES.keys())
    for slug in slugs:
        if slug in ALL_GAMES:
            manager.register_game(ALL_GAMES[slug])

    async def _periodic_cleanup() -> None:
        while True:
            try:
                deleted = await manager.cleanup_expired_rooms()
                if deleted:
                    logger.info("Auto-deleted %d expired room(s): %s", len(deleted), deleted)
            except (PsycopgError, OSError, RuntimeError) as e:
                logger.error("Error cleaning up expired rooms: %s", repr(e))
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await active_db.connect()
        cleanup_task = asyncio.create_task(_periodic_cleanup())
        try:
            yield
        finally:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
            await active_db.close()

    app = FastAPI(
        title="games.jakob-r.de API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.db = active_db
    app.state.room_manager = manager

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/games")
    async def list_games() -> list[dict[str, Any]]:
        return [
            {
                "slug": g.slug,
                "title": g.title,
                "description": g.description,
                "default_config": g.default_config(),
            }
            for g in manager.games.values()
        ]

    @app.post("/api/rooms")
    async def create_room(req: CreateRoomRequest) -> dict[str, Any]:
        if req.game_slug not in manager.games:
            raise HTTPException(status_code=404, detail=f"Unknown game: {req.game_slug}")
        try:
            room = await manager.create_room(
                game_slug=req.game_slug,
                host_player_id=req.host_player_id,
                host_name=req.host_name,
                host_color=req.host_color,
                raw_config=req.config,
            )
        except Exception as e:
            logger.error("Failed to create room: %s", repr(e))
            raise HTTPException(status_code=500, detail=f"Failed to create room: {e!r}") from e

        snapshot = await manager.build_room_snapshot(room["id"])
        assert snapshot is not None
        return snapshot

    @app.get("/api/rooms/{room_id}")
    async def get_room(room_id: str) -> dict[str, Any]:
        snapshot = await manager.build_room_snapshot(room_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Room not found")
        return snapshot

    @app.delete("/api/rooms/{room_id}")
    async def delete_room(
        room_id: str,
        player_id: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        try:
            deleted = await manager.delete_room(room_id=room_id, player_id=player_id)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        if not deleted:
            raise HTTPException(status_code=404, detail="Room not found")
        return {"status": "deleted", "room_id": room_id}

    @app.delete("/api/rooms/{room_id}/players/{player_id}")
    async def leave_room(
        room_id: str,
        player_id: str,
        actor_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            left = await manager.leave_room(
                room_id=room_id,
                player_id=player_id,
                actor_id=actor_id,
            )
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        if not left:
            raise HTTPException(status_code=404, detail="Room or player not found")
        status_label = "removed" if actor_id and actor_id != player_id else "left"
        return {"status": status_label, "room_id": room_id, "player_id": player_id}

    @app.get("/api/notifications/vapid-public-key")
    async def get_vapid_public_key() -> dict[str, str]:
        public_key = await manager.push.get_public_key()
        return {"public_key": public_key}

    @app.get("/api/rooms/{room_id}/notifications/status")
    async def get_room_notification_status(
        room_id: str,
        player_id: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        room = await active_db.get_room(room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        subs = await active_db.get_push_subscriptions(room_id, player_id)
        return {
            "room_id": room_id,
            "player_id": player_id,
            "subscribed": len(subs) > 0,
            "count": len(subs),
        }

    @app.post("/api/rooms/{room_id}/notifications/subscribe")
    async def subscribe_room_notifications(
        room_id: str,
        req: PushSubscribeRequest,
    ) -> dict[str, Any]:
        room = await active_db.get_room(room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        players = await active_db.get_room_players(room_id)
        if not any(p["player_id"] == req.player_id for p in players):
            raise HTTPException(status_code=403, detail="Player is not in this room")
        try:
            endpoint = validate_push_endpoint(req.endpoint)
        except PushEndpointError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        existing = await active_db.get_push_subscriptions(room_id, req.player_id)
        already_stored = any(str(sub["endpoint"]) == endpoint for sub in existing)
        if not already_stored and len(existing) >= MAX_PUSH_SUBSCRIPTIONS_PER_PLAYER:
            raise HTTPException(
                status_code=409,
                detail="Too many push subscriptions for this player",
            )
        if req.player_id in manager._connected_player_ids(room_id):
            manager.mark_player_active(room_id, req.player_id)
        await active_db.upsert_push_subscription(
            room_id=room_id,
            player_id=req.player_id,
            endpoint=endpoint,
            p256dh=req.keys.p256dh,
            auth=req.keys.auth,
        )
        return {
            "status": "subscribed",
            "room_id": room_id,
            "player_id": req.player_id,
        }

    @app.delete("/api/rooms/{room_id}/notifications/subscribe")
    async def unsubscribe_room_notifications(
        room_id: str,
        player_id: str = Query(..., min_length=1),
        endpoint: str | None = Query(default=None),
    ) -> dict[str, Any]:
        deleted = await active_db.delete_push_subscriptions(
            room_id=room_id,
            player_id=player_id,
            endpoint=endpoint,
        )
        return {
            "status": "unsubscribed",
            "room_id": room_id,
            "player_id": player_id,
            "deleted": deleted,
        }

    @app.get("/api/players/{player_id}/recent")
    async def get_player_recent_rooms(
        player_id: str,
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        rows = await active_db.get_recent_rooms_for_player(player_id, limit=limit)
        return [
            {
                "room_id": r["room_id"],
                "game_slug": r["game_slug"],
                "status": r["status"],
                "config": r["config"],
                "host_player_id": r["host_player_id"],
                "score": round(float(r["score"]), 2),
                "player_count": int(r["player_count"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]

    @app.get("/api/players/{player_id}/stats")
    async def get_player_stats(player_id: str) -> dict[str, Any]:
        rows = await active_db.get_player_stats(player_id)
        recent = await active_db.get_recent_rooms_for_player(player_id, limit=100)
        total_rooms_joined = len(recent)
        active_rooms = sum(1 for r in recent if r["status"] in ("lobby", "playing"))
        completed_games = sum(int(r["games_played"]) for r in rows)
        games_won = sum(int(r["games_won"]) for r in rows)
        total_score = round(sum(float(r["total_score"]) for r in rows), 2)
        best_score = round(max((float(r["best_score"]) for r in rows), default=0.0), 2)

        return {
            "player_id": player_id,
            "summary": {
                "rooms_joined": total_rooms_joined,
                "active_rooms": active_rooms,
                "games_completed": completed_games,
                "games_won": games_won,
                "total_score": total_score,
                "best_score": best_score,
            },
            "by_game": [
                {
                    "game_slug": r["game_slug"],
                    "games_played": int(r["games_played"]),
                    "games_won": int(r["games_won"]),
                    "total_score": round(float(r["total_score"]), 2),
                    "best_score": round(float(r["best_score"]), 2),
                }
                for r in rows
            ],
        }

    @app.websocket("/ws/{game_slug}/{room_id}")
    async def room_websocket(
        websocket: WebSocket,
        game_slug: str,
        room_id: str,
        player_id: str = Query(default="anonymous"),
        name: str = Query(default="Player"),
        color: str = Query(default="#2563eb"),
    ) -> None:
        room = await active_db.get_room(room_id)
        if room is None or room["game_slug"] != game_slug:
            await websocket.close(code=4004, reason="Room not found")
            return

        conn = await manager.connect(
            websocket=websocket,
            room_id=room_id,
            player_id=player_id,
            name=name,
            color=color,
        )
        try:
            while True:
                raw_data = await websocket.receive_json()
                await manager.handle_client_message(room_id, conn, raw_data)
        except WebSocketDisconnect:
            pass
        except (RuntimeError, OSError, ValueError) as e:
            logger.error("WebSocket error in room %s: %s", room_id, repr(e))
        finally:
            with anyio.CancelScope(shield=True):
                await manager.disconnect(room_id, conn)

    # After API/WS routes so the SPA catch-all does not shadow them.
    _mount_static(app)

    return app


app = create_app()
