"""FastAPI application factory with REST and WebSocket endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from games_platform.core.db import Database, db
from games_platform.core.protocol import CreateRoomRequest, GameDefinition
from games_platform.core.room_manager import RoomManager
from games_platform.games.sudoku.game import sudoku_game

logger = logging.getLogger(__name__)

ALL_GAMES: dict[str, GameDefinition] = {
    sudoku_game.slug: sudoku_game,
}


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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await active_db.connect()
        try:
            yield
        finally:
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
            await manager.disconnect(room_id, conn)

    return app


app = create_app()
