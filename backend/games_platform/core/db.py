"""PostgreSQL connection pool and schema migrations using Psycopg 3."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from psycopg import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "postgresql://games:games@localhost:5434/games"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    game_slug TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'lobby',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    host_player_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rooms_game_slug ON rooms(game_slug);
CREATE INDEX IF NOT EXISTS idx_rooms_updated_at ON rooms(updated_at DESC);

CREATE TABLE IF NOT EXISTS room_players (
    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    is_ready BOOLEAN NOT NULL DEFAULT FALSE,
    score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    last_correct_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (room_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_room_players_player_id ON room_players(player_id, joined_at DESC);

CREATE TABLE IF NOT EXISTS player_stats (
    player_id TEXT NOT NULL,
    game_slug TEXT NOT NULL,
    games_played INTEGER NOT NULL DEFAULT 0,
    games_won INTEGER NOT NULL DEFAULT 0,
    total_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    best_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, game_slug)
);
"""


class Database:
    """Async PostgreSQL wrapper backed by Psycopg 3 AsyncConnectionPool."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        self.pool: AsyncConnectionPool | None = None

    async def connect(self) -> None:
        """Open the connection pool and apply database schema."""
        try:
            self.pool = AsyncConnectionPool(
                conninfo=self.dsn,
                min_size=1,
                max_size=10,
                open=False,
                kwargs={"row_factory": dict_row, "autocommit": True},
            )
            await self.pool.open(wait=True, timeout=10.0)
            await self.init_schema()
            logger.info("Connected to PostgreSQL and verified schema.")
        except (PsycopgError, OSError) as e:
            logger.error("Failed to connect to PostgreSQL: %s", repr(e))
            raise

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool is not None:
            try:
                await self.pool.close()
            except (PsycopgError, OSError) as e:
                logger.error("Error closing PostgreSQL pool: %s", repr(e))
            finally:
                self.pool = None

    def _require_pool(self) -> AsyncConnectionPool:
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized. Call await db.connect() first.")
        return self.pool

    async def init_schema(self) -> None:
        """Ensure all required tables and indexes exist."""
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(SCHEMA_SQL)

    async def create_room(
        self,
        *,
        room_id: str,
        game_slug: str,
        status: str,
        config: dict[str, Any],
        state: dict[str, Any],
        host_player_id: str,
    ) -> dict[str, Any]:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO rooms (id, game_slug, status, config, state, host_player_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, game_slug, status, config, state, host_player_id, created_at, updated_at
                """,
                (room_id, game_slug, status, Jsonb(config), Jsonb(state), host_player_id),
            )
            row = await cur.fetchone()
            assert row is not None
            return dict(row)

    async def get_room(self, room_id: str) -> dict[str, Any] | None:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, game_slug, status, config, state, host_player_id, created_at, updated_at
                FROM rooms
                WHERE id = %s
                """,
                (room_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def update_room(
        self,
        room_id: str,
        *,
        status: str | None = None,
        config: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        host_player_id: str | None = None,
    ) -> dict[str, Any] | None:
        pool = self._require_pool()
        sets: list[str] = ["updated_at = NOW()"]
        params: list[Any] = []
        if status is not None:
            sets.append("status = %s")
            params.append(status)
        if config is not None:
            sets.append("config = %s")
            params.append(Jsonb(config))
        if state is not None:
            sets.append("state = %s")
            params.append(Jsonb(state))
        if host_player_id is not None:
            sets.append("host_player_id = %s")
            params.append(host_player_id)
        params.append(room_id)

        query = f"""
            UPDATE rooms
            SET {", ".join(sets)}
            WHERE id = %s
            RETURNING id, game_slug, status, config, state, host_player_id, created_at, updated_at
        """
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, tuple(params))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def upsert_room_player(
        self,
        *,
        room_id: str,
        player_id: str,
        name: str,
        color: str,
    ) -> dict[str, Any]:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO room_players (room_id, player_id, name, color)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (room_id, player_id) DO UPDATE
                SET name = EXCLUDED.name,
                    color = EXCLUDED.color
                RETURNING room_id, player_id, name, color, is_ready, score, multiplier, last_correct_at, joined_at
                """,
                (room_id, player_id, name, color),
            )
            row = await cur.fetchone()
            assert row is not None
            return dict(row)

    async def get_room_players(self, room_id: str) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT room_id, player_id, name, color, is_ready, score, multiplier, last_correct_at, joined_at
                FROM room_players
                WHERE room_id = %s
                ORDER BY joined_at ASC
                """,
                (room_id,),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_room(self, room_id: str) -> bool:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM rooms
                WHERE id = %s
                RETURNING id
                """,
                (room_id,),
            )
            row = await cur.fetchone()
            return row is not None

    async def remove_room_player(self, room_id: str, player_id: str) -> bool:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM room_players
                WHERE room_id = %s AND player_id = %s
                RETURNING player_id
                """,
                (room_id, player_id),
            )
            row = await cur.fetchone()
            return row is not None

    async def cleanup_expired_rooms(self) -> list[str]:
        """
        Delete rooms that:
        - Have no moves and haven't been updated for > 2 days.
        - Have moves and haven't been updated for > 1 year.
        """
        pool = self._require_pool()
        has_moves_expr = """(
            status != 'lobby'
            AND (
                COALESCE((state->>'history_count')::int, 0) > 0
                OR COALESCE((state->>'move_count')::int, 0) > 0
                OR COALESCE((state->>'safe_revealed')::int, 0) > 0
                OR COALESCE((state->>'mines_hit')::int, 0) > 0
                OR COALESCE((state->>'mines_placed')::boolean, FALSE) IS TRUE
            )
        )"""
        query = f"""
            DELETE FROM rooms
            WHERE (
                NOT {has_moves_expr}
                AND updated_at < NOW() - INTERVAL '2 days'
            )
            OR (
                {has_moves_expr}
                AND updated_at < NOW() - INTERVAL '1 year'
            )
            RETURNING id
        """
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query)
            rows = await cur.fetchall()
            return [str(r["id"]) for r in rows]

    async def set_player_ready(self, room_id: str, player_id: str, is_ready: bool) -> None:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE room_players
                SET is_ready = %s
                WHERE room_id = %s AND player_id = %s
                """,
                (is_ready, room_id, player_id),
            )

    async def update_player_score(
        self,
        room_id: str,
        player_id: str,
        *,
        score: float,
        multiplier: float,
        last_correct_at: datetime | None,
    ) -> None:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE room_players
                SET score = %s,
                    multiplier = %s,
                    last_correct_at = %s
                WHERE room_id = %s AND player_id = %s
                """,
                (score, multiplier, last_correct_at, room_id, player_id),
            )

    async def reset_room_scores(self, room_id: str) -> None:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE room_players
                SET score = 0.0,
                    multiplier = 1.0,
                    last_correct_at = NULL
                WHERE room_id = %s
                """,
                (room_id,),
            )

    async def record_game_finished(
        self,
        room_id: str,
        game_slug: str,
    ) -> None:
        """Increment games_played, games_won, total_score, and best_score for all players in the room."""
        players = await self.get_room_players(room_id)
        if not players:
            return
        max_score = max(float(p["score"]) for p in players)
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            for p in players:
                score = float(p["score"])
                won = 1 if score >= max_score else 0
                await cur.execute(
                    """
                    INSERT INTO player_stats (player_id, game_slug, games_played, games_won, total_score, best_score, updated_at)
                    VALUES (%s, %s, 1, %s, %s, %s, NOW())
                    ON CONFLICT (player_id, game_slug) DO UPDATE
                    SET games_played = player_stats.games_played + 1,
                        games_won = player_stats.games_won + EXCLUDED.games_won,
                        total_score = player_stats.total_score + EXCLUDED.total_score,
                        best_score = GREATEST(player_stats.best_score, EXCLUDED.best_score),
                        updated_at = NOW()
                    """,
                    (p["player_id"], game_slug, won, score, score),
                )

    async def get_recent_rooms_for_player(
        self,
        player_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    r.id AS room_id,
                    r.game_slug,
                    r.status,
                    r.config,
                    r.host_player_id,
                    r.created_at,
                    r.updated_at,
                    rp.score,
                    rp.multiplier,
                    (
                        SELECT COUNT(*)
                        FROM room_players rp2
                        WHERE rp2.room_id = r.id
                    ) AS player_count
                FROM room_players rp
                JOIN rooms r ON r.id = rp.room_id
                WHERE rp.player_id = %s
                ORDER BY r.updated_at DESC
                LIMIT %s
                """,
                (player_id, limit),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_player_stats(self, player_id: str) -> list[dict[str, Any]]:
        pool = self._require_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT player_id, game_slug, games_played, games_won, total_score, best_score, updated_at
                FROM player_stats
                WHERE player_id = %s
                ORDER BY game_slug ASC
                """,
                (player_id,),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


db = Database()
