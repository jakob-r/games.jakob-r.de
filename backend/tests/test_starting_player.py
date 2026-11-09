"""Who opens a game: random in a room's first game, then the last game's loser."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest

from games_platform.core.room_manager import RoomManager


class _FakeDb:
    def __init__(self, starter: str | None) -> None:
        self.starter = starter

    async def get_next_starter_id(self, room_id: str) -> str | None:
        return self.starter


def _order(starter: str | None, players: list[str]) -> list[str]:
    manager: Any = RoomManager.__new__(RoomManager)
    manager.db = _FakeDb(starter)
    return asyncio.run(manager._order_for_next_game("room", players))


def test_loser_of_last_game_starts_and_order_rotates() -> None:
    assert _order("c", ["a", "b", "c", "d"]) == ["c", "d", "a", "b"]


@pytest.mark.parametrize("starter", [None, "gone"])
def test_first_game_or_departed_loser_starts_randomly(starter: str | None) -> None:
    random.seed(1)
    openers = {_order(starter, ["a", "b", "c"])[0] for _ in range(50)}
    assert openers == {"a", "b", "c"}
    assert sorted(_order(starter, ["a", "b", "c"])) == ["a", "b", "c"]


def test_single_player_unchanged() -> None:
    assert _order("x", ["a"]) == ["a"]
