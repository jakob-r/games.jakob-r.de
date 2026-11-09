"""Friendships between accounts (`/api/friends/*`).

Privacy rules: friends are only added from a shared room, requests need to be
accepted, declining and removing are silent, and nothing here reveals whether a
friend is online or when they were last active.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from games_platform.core.auth import SESSION_COOKIE, AuthService
from games_platform.core.auth_api import RateLimiter
from games_platform.core.db import Database

MAX_OUTGOING_REQUESTS = 50
REQUESTS_PER_HOUR = 20

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
    def __init__(self, database: Database) -> None:
        self.db = database

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
        return {"statuses": await friends.room_statuses(user, room_id)}

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
