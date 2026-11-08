"""Standalone entrypoint for running North South Sort independently."""

from __future__ import annotations

import uvicorn

from games_platform.main import create_app

app = create_app(enabled_games=["north-south-sort"])

if __name__ == "__main__":
    uvicorn.run(
        "games_platform.games.north_south_sort.standalone:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
