"""Friendships between accounts (`/api/friends/*`).

Privacy rules: friends are only added from a shared room, requests need to be
accepted, declining and removing are silent, and nothing here reveals whether a
friend is online or when they were last active.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from games_platform.core.auth import SESSION_COOKIE, AuthService
from games_platform.core.auth_api import RateLimiter
from games_platform.core.db import Database
from games_platform.core.protocol import is_solo_room
from games_platform.core.push import WebPushService, format_invite_notification

logger = logging.getLogger(__name__)

MAX_OUTGOING_REQUESTS = 50
REQUESTS_PER_HOUR = 20
INVITES_PER_DAY = 30
MAX_INVITES_PER_CALL = 20

FriendStatus = Literal["none", "outgoing", "incoming", "friend"]


class FriendError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _name_key(name: str) -> str:
    return name.strip().casefold()


def friend_labels(my_name: str, friends: list[dict[str, Any]]) -> list[str]:
    """Names to show for ``friends`` (sorted by when they were added).

    Names aren't unique: the first friend with a name keeps it, later ones get
    "(2)", "(3)", ... A friend with your own name starts at "(2)".
    """
    mine = _name_key(my_name)
    seen: dict[str, int] = {}
    labels: list[str] = []
    for friend in friends:
        name = str(friend["name"]).strip() or "Player"
        key = _name_key(name)
        seen[key] = seen.get(key, 0) + 1
        number = seen[key] + (1 if key == mine else 0)
        labels.append(name if number == 1 else f"{name} ({number})")
    return labels


class FriendService:
    def __init__(
        self,
        database: Database,
        *,
        push: WebPushService | None = None,
        game_title: Callable[[str], str] = lambda slug: slug,
        mailer: Any = None,
    ) -> None:
        self.db = database
        self.push = push
        self.mailer = mailer
        self.game_title = game_title
        self._tasks: set[asyncio.Task[Any]] = set()

    async def flush(self) -> None:
        """Wait for invite pushes in flight (tests)."""
        if pending := [t for t in self._tasks if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    def _background(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)

        def done(t: asyncio.Task[Any]) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                logger.warning("Invite notification failed: %s", repr(t.exception()))

        task.add_done_callback(done)

    async def _labels(self, cur: Any, viewer_id: int, viewer_name: str) -> dict[int, str]:
        """Friend id -> name as ``viewer`` sees it (numbered duplicates)."""
        await cur.execute(
            """
            SELECT u.id, u.display_name AS name
            FROM friendships f JOIN users u ON u.id = f.friend_id
            WHERE f.user_id = %s
            ORDER BY f.created_at, u.id
            """,
            (viewer_id,),
        )
        rows = await cur.fetchall()
        return {
            int(r["id"]): label
            for r, label in zip(rows, friend_labels(viewer_name, rows), strict=True)
        }

    async def overview(self, user: dict[str, Any]) -> dict[str, Any]:
        """Friends (with display labels) plus incoming and outgoing requests."""
        uid = user["id"]
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT u.id, u.display_name AS name, u.color, f.created_at
                FROM friendships f JOIN users u ON u.id = f.friend_id
                WHERE f.user_id = %s
                ORDER BY f.created_at, u.id
                """,
                (uid,),
            )
            friends = await cur.fetchall()
            await cur.execute(
                """
                SELECT u.id, u.display_name AS name, u.color
                FROM friend_requests r JOIN users u ON u.id = r.from_user_id
                WHERE r.to_user_id = %s AND r.declined_at IS NULL
                ORDER BY r.created_at
                """,
                (uid,),
            )
            incoming = await cur.fetchall()
            # Declined requests still look pending to the sender.
            await cur.execute(
                """
                SELECT u.id, u.display_name AS name, u.color
                FROM friend_requests r JOIN users u ON u.id = r.to_user_id
                WHERE r.from_user_id = %s
                ORDER BY r.created_at
                """,
                (uid,),
            )
            outgoing = await cur.fetchall()

        def person(row: dict[str, Any]) -> dict[str, Any]:
            return {
                "user_id": row["id"],
                "name": str(row["name"]).strip() or "Player",
                "color": row["color"] or "",
            }

        labels = friend_labels(user["display_name"], friends)
        return {
            "friends": [
                {**person(row), "label": label} for row, label in zip(friends, labels, strict=True)
            ],
            "incoming": [person(row) for row in incoming],
            "outgoing": [person(row) for row in outgoing],
        }

    async def room_statuses(self, user: dict[str, Any], room_id: str) -> dict[str, FriendStatus]:
        """Friend status of each co-player with an account, keyed by player id.

        Only for players in the room, so it reveals accounts just to people you
        play with. Players without an account are left out.
        """
        uid = user["id"]
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM room_players WHERE room_id = %s AND player_id = %s",
                (room_id, user["player_id"]),
            )
            if await cur.fetchone() is None:
                return {}
            await cur.execute(
                """
                SELECT
                    u.player_id,
                    EXISTS (
                        SELECT 1 FROM friendships f WHERE f.user_id = %(me)s AND f.friend_id = u.id
                    ) AS is_friend,
                    EXISTS (
                        SELECT 1 FROM friend_requests r
                        WHERE r.from_user_id = %(me)s AND r.to_user_id = u.id
                    ) AS is_outgoing,
                    EXISTS (
                        SELECT 1 FROM friend_requests r
                        WHERE r.from_user_id = u.id AND r.to_user_id = %(me)s
                          AND r.declined_at IS NULL
                    ) AS is_incoming
                FROM room_players rp JOIN users u ON u.player_id = rp.player_id
                WHERE rp.room_id = %(room)s AND u.id <> %(me)s
                """,
                {"me": uid, "room": room_id},
            )
            rows = await cur.fetchall()
        statuses: dict[str, FriendStatus] = {}
        for row in rows:
            if row["is_friend"]:
                statuses[row["player_id"]] = "friend"
            elif row["is_outgoing"]:
                statuses[row["player_id"]] = "outgoing"
            elif row["is_incoming"]:
                statuses[row["player_id"]] = "incoming"
            else:
                statuses[row["player_id"]] = "none"
        return statuses

    async def friends_in_room(self, user: dict[str, Any], room_id: str) -> list[int]:
        """Friends who are players in this room (nothing to invite)."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT f.friend_id FROM friendships f
                JOIN users u ON u.id = f.friend_id
                JOIN room_players rp ON rp.player_id = u.player_id AND rp.room_id = %s
                WHERE f.user_id = %s
                """,
                (room_id, user["id"]),
            )
            return [int(r["friend_id"]) for r in await cur.fetchall()]

    async def invited_in_room(self, user: dict[str, Any], room_id: str) -> list[int]:
        """Friends you already invited to this room."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT to_user_id FROM room_invites WHERE room_id = %s AND from_user_id = %s",
                (room_id, user["id"]),
            )
            return [int(r["to_user_id"]) for r in await cur.fetchall()]

    async def invite(self, user: dict[str, Any], room_id: str, user_ids: list[int]) -> list[int]:
        """Invite friends to a room you are in. Returns the ids newly invited."""
        uid = user["id"]
        wanted = list(dict.fromkeys(user_ids))[:MAX_INVITES_PER_CALL]
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT r.game_slug, r.config FROM rooms r
                JOIN room_players rp ON rp.room_id = r.id AND rp.player_id = %s
                WHERE r.id = %s
                """,
                (user["player_id"], room_id),
            )
            room = await cur.fetchone()
            if room is None:
                raise FriendError(404, "You are not in this room")
            if is_solo_room(room["config"]):
                raise FriendError(400, "Solo games cannot be joined.")
            await cur.execute(
                """
                SELECT COUNT(*) AS n FROM room_invites
                WHERE from_user_id = %s AND created_at > NOW() - INTERVAL '1 day'
                """,
                (uid,),
            )
            row = await cur.fetchone()
            if row is not None and row["n"] + len(wanted) > INVITES_PER_DAY:
                raise FriendError(429, "That's a lot of invites today. Try again tomorrow.")
            # Only friends who aren't in the room yet.
            await cur.execute(
                """
                INSERT INTO room_invites (room_id, from_user_id, to_user_id)
                SELECT %(room)s, %(me)s, u.id
                FROM users u JOIN friendships f ON f.user_id = %(me)s AND f.friend_id = u.id
                WHERE u.id = ANY(%(ids)s)
                  AND NOT EXISTS (
                      SELECT 1 FROM room_players rp
                      WHERE rp.room_id = %(room)s AND rp.player_id = u.player_id
                  )
                ON CONFLICT DO NOTHING
                RETURNING to_user_id
                """,
                {"room": room_id, "me": uid, "ids": wanted},
            )
            invited = [int(r["to_user_id"]) for r in await cur.fetchall()]
            if not invited:
                return []
            await cur.execute(
                "SELECT id, player_id, display_name FROM users WHERE id = ANY(%s)", (invited,)
            )
            recipients = await cur.fetchall()
            targets: list[tuple[dict[str, Any], str]] = []
            for recipient in recipients:
                labels = await self._labels(cur, int(recipient["id"]), recipient["display_name"])
                inviter = labels.get(uid, str(user["display_name"]).strip() or "A friend")
                targets.append((recipient, inviter))
        game_slug = str(room["game_slug"])
        for recipient, inviter in targets:
            self._background(self._notify_invite(uid, recipient, inviter, game_slug, room_id))
        return invited

    async def _notify_invite(
        self,
        from_user_id: int,
        recipient: dict[str, Any],
        inviter: str,
        game_slug: str,
        room_id: str,
    ) -> None:
        if self.push is not None:
            payload = format_invite_notification(
                game_slug=game_slug,
                game_title=self.game_title(game_slug),
                room_id=room_id,
                inviter=inviter,
            )
            await self.push.send_to_player(
                room_id=room_id, player_id=str(recipient["player_id"]), payload=payload
            )
        if self.mailer is not None:
            await self.mailer.send_invite(
                to_user_id=int(recipient["id"]),
                from_user_id=from_user_id,
                inviter=inviter,
                game_slug=game_slug,
                room_id=room_id,
            )

    async def inbox(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        """Open invites to rooms you haven't joined (no timestamps)."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            labels = await self._labels(cur, user["id"], user["display_name"])
            await cur.execute(
                """
                SELECT ri.room_id, ri.from_user_id, r.game_slug, r.status, u.color
                FROM room_invites ri
                JOIN rooms r ON r.id = ri.room_id
                JOIN users u ON u.id = ri.from_user_id
                WHERE ri.to_user_id = %s
                  AND r.status <> 'finished'
                  AND NOT EXISTS (
                      SELECT 1 FROM room_players rp
                      WHERE rp.room_id = ri.room_id AND rp.player_id = %s
                  )
                ORDER BY ri.created_at DESC
                """,
                (user["id"], user["player_id"]),
            )
            rows = await cur.fetchall()
        return [
            {
                "room_id": r["room_id"],
                "game_slug": r["game_slug"],
                "status": r["status"],
                "from": {
                    "user_id": int(r["from_user_id"]),
                    "label": labels[int(r["from_user_id"])],
                    "color": r["color"] or "",
                },
            }
            for r in rows
            if int(r["from_user_id"]) in labels
        ]

    async def lobbies(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        """Rooms friends host that are still in the lobby (no timestamps)."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            labels = await self._labels(cur, user["id"], user["display_name"])
            await cur.execute(
                """
                SELECT r.id AS room_id, r.game_slug, u.id AS host_id, u.color,
                       (SELECT COUNT(*) FROM room_players rp WHERE rp.room_id = r.id) AS players,
                       EXISTS (
                           SELECT 1 FROM room_players rp
                           WHERE rp.room_id = r.id AND rp.player_id = %(pid)s
                       ) AS joined
                FROM rooms r
                JOIN users u ON u.player_id = r.host_player_id
                JOIN friendships f ON f.user_id = %(me)s AND f.friend_id = u.id
                WHERE r.status = 'lobby'
                  AND NOT COALESCE((r.config->>'solo')::boolean, false)
                """,
                {"me": user["id"], "pid": user["player_id"]},
            )
            rows = await cur.fetchall()
        lobbies = [
            {
                "room_id": r["room_id"],
                "game_slug": r["game_slug"],
                "host": {
                    "user_id": int(r["host_id"]),
                    "label": labels[int(r["host_id"])],
                    "color": r["color"] or "",
                },
                "players": int(r["players"]),
                "joined": bool(r["joined"]),
            }
            for r in rows
            if int(r["host_id"]) in labels
        ]
        # Stable order without any notion of recency.
        lobbies.sort(
            key=lambda lb: (lb["game_slug"], lb["host"]["label"].casefold(), lb["room_id"])
        )
        return lobbies

    async def dismiss_invite(self, user: dict[str, Any], room_id: str) -> None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM room_invites WHERE room_id = %s AND to_user_id = %s",
                (room_id, user["id"]),
            )

    async def request(self, user: dict[str, Any], room_id: str, player_id: str) -> FriendStatus:
        """Send a request to a co-player (accepts theirs if they already asked)."""
        statuses = await self.room_statuses(user, room_id)
        status = statuses.get(player_id)
        if status is None:
            raise FriendError(404, "No player with an account in this room")
        if status in ("friend", "outgoing"):
            return status
        uid = user["id"]
        async with self.db.connection() as conn, conn.transaction(), conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE player_id = %s", (player_id,))
            target = await cur.fetchone()
            if target is None:
                raise FriendError(404, "No player with an account in this room")
            target_id = int(target["id"])
            await cur.execute(
                "SELECT 1 FROM friend_requests WHERE from_user_id = %s AND to_user_id = %s",
                (target_id, uid),
            )
            if await cur.fetchone() is not None:
                # They asked first (maybe declined by us earlier): adding them accepts it.
                await self._befriend(cur, uid, target_id)
                return "friend"
            await cur.execute(
                "SELECT COUNT(*) AS n FROM friend_requests WHERE from_user_id = %s", (uid,)
            )
            row = await cur.fetchone()
            if row is not None and row["n"] >= MAX_OUTGOING_REQUESTS:
                raise FriendError(429, "Too many open friend requests")
            await cur.execute(
                """
                INSERT INTO friend_requests (from_user_id, to_user_id) VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (uid, target_id),
            )
        return "outgoing"

    async def _befriend(self, cur: Any, a: int, b: int) -> None:
        await cur.execute(
            """
            DELETE FROM friend_requests
            WHERE (from_user_id = %(a)s AND to_user_id = %(b)s)
               OR (from_user_id = %(b)s AND to_user_id = %(a)s)
            """,
            {"a": a, "b": b},
        )
        await cur.execute(
            """
            INSERT INTO friendships (user_id, friend_id) VALUES (%(a)s, %(b)s), (%(b)s, %(a)s)
            ON CONFLICT DO NOTHING
            """,
            {"a": a, "b": b},
        )

    async def accept(self, user: dict[str, Any], from_user_id: int) -> None:
        async with self.db.connection() as conn, conn.transaction(), conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM friend_requests WHERE from_user_id = %s AND to_user_id = %s",
                (from_user_id, user["id"]),
            )
            if await cur.fetchone() is None:
                raise FriendError(404, "Friend request not found")
            await self._befriend(cur, user["id"], from_user_id)

    async def decline(self, user: dict[str, Any], from_user_id: int) -> None:
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE friend_requests SET declined_at = NOW()
                WHERE from_user_id = %s AND to_user_id = %s AND declined_at IS NULL
                """,
                (from_user_id, user["id"]),
            )

    async def remove(self, user: dict[str, Any], friend_id: int) -> None:
        """End a friendship from either side (the other side isn't told)."""
        async with self.db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM friendships
                WHERE (user_id = %(a)s AND friend_id = %(b)s)
                   OR (user_id = %(b)s AND friend_id = %(a)s)
                """,
                {"a": user["id"], "b": friend_id},
            )
            await cur.execute(
                """
                DELETE FROM room_invites
                WHERE (from_user_id = %(a)s AND to_user_id = %(b)s)
                   OR (from_user_id = %(b)s AND to_user_id = %(a)s)
                """,
                {"a": user["id"], "b": friend_id},
            )


class InviteBody(BaseModel):
    room_id: str = Field(min_length=1, max_length=64)
    user_ids: list[int] = Field(min_length=1, max_length=MAX_INVITES_PER_CALL)


class FriendRequestBody(BaseModel):
    room_id: str = Field(min_length=1, max_length=64)
    player_id: str = Field(min_length=1, max_length=64)


def create_friends_router(auth: AuthService, friends: FriendService) -> APIRouter:
    router = APIRouter(prefix="/api/friends", tags=["friends"])
    limiter = RateLimiter()

    async def require_user(
        raw: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, Any]:
        user = await auth.user_for_session(raw)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in")
        return user

    User = Annotated[dict[str, Any], Depends(require_user)]

    async def run(coro: Any) -> Any:
        try:
            return await coro
        except FriendError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    @router.get("")
    async def overview(user: User) -> dict[str, Any]:
        return await friends.overview(user)

    @router.get("/rooms/{room_id}")
    async def room_statuses(room_id: str, user: User) -> dict[str, Any]:
        return {
            "statuses": await friends.room_statuses(user, room_id),
            "invited": await friends.invited_in_room(user, room_id),
            "friends_here": await friends.friends_in_room(user, room_id),
        }

    @router.post("/invites")
    async def invite(body: InviteBody, user: User) -> dict[str, Any]:
        limiter.check(f"invite:{user['id']}", INVITES_PER_DAY, window=3600)
        return {"invited": await run(friends.invite(user, body.room_id, body.user_ids))}

    @router.get("/inbox")
    async def inbox(user: User) -> dict[str, Any]:
        return {"invites": await friends.inbox(user)}

    @router.get("/lobbies")
    async def lobbies(user: User) -> dict[str, Any]:
        return {"lobbies": await friends.lobbies(user)}

    @router.delete("/invites/{room_id}")
    async def dismiss_invite(room_id: str, user: User) -> dict[str, Any]:
        await friends.dismiss_invite(user, room_id)
        return {"status": "dismissed"}

    @router.post("/requests")
    async def send_request(body: FriendRequestBody, user: User) -> dict[str, Any]:
        limiter.check(f"friend-request:{user['id']}", REQUESTS_PER_HOUR, window=3600)
        status = await run(friends.request(user, body.room_id, body.player_id))
        return {"status": status}

    @router.post("/requests/{from_user_id}/accept")
    async def accept(from_user_id: int, user: User) -> dict[str, Any]:
        await run(friends.accept(user, from_user_id))
        return {"status": "friend"}

    @router.post("/requests/{from_user_id}/decline")
    async def decline(from_user_id: int, user: User) -> dict[str, Any]:
        await friends.decline(user, from_user_id)
        return {"status": "declined"}

    @router.delete("/{friend_id}")
    async def remove(friend_id: int, user: User) -> dict[str, Any]:
        await friends.remove(user, friend_id)
        return {"status": "removed"}

    return router
