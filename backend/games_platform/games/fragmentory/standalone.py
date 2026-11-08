"""Standalone entrypoint for running Fragmentory independently."""

from __future__ import annotations

import uvicorn

from games_platform.main import create_app

app = create_app(enabled_games=["fragmentory"])

if __name__ == "__main__":
    uvicorn.run(
        "games_platform.games.fragmentory.standalone:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
