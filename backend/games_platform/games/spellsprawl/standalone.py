"""Standalone entrypoint for running Spellsprawl independently."""

from __future__ import annotations

import uvicorn

from games_platform.main import create_app

app = create_app(enabled_games=["spellsprawl"])

if __name__ == "__main__":
    uvicorn.run(
        "games_platform.games.spellsprawl.standalone:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
