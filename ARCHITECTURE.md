# Architecture & Tech Stack

General product concept lives in `idea.md`.

## Tech Stack

### Frontend (No React)
- **Framework**: **Svelte 5** (using Runes: `$state`, `$derived`, `$effect`) with **SvelteKit** and **TypeScript**.
  - Fine-grained reactivity updates individual DOM nodes (ideal for high-frequency multiplayer board and corner-note updates) without Virtual DOM overhead.
  - Built-in `svelte/motion` (`Spring`, `Tween`) and `svelte/transition` primitives for nuanced micro-animations.
- **Styling & Scribbly Visuals**:
  - **Tailwind CSS v4** + native CSS custom properties.
  - **Rough.js** + inline **SVG** with `stroke-dasharray`/`stroke-dashoffset` animations and subtle SVG displacement filters (`#scribble-filter`) for a minimalistic, hand-drawn scribbly look.
- **Color System (`opponent_color`)**:
  - **OKLCH perceptual color space** in `frontend/src/lib/core/color.ts` for `opponent_color(my_color, their_color)`.
  - Ensures perceptual color distance and contrast remain uniform while keeping the UI monochrome by default and using color strictly where helpful (player identity, semantic feedback).
- **Build & Package Manager**: **Vite** + **pnpm**.

### Backend
- **Language & Packaging**: **Python 3.13+** managed with **uv**.
- **Web & Realtime Framework**: **FastAPI** + **Uvicorn** (with native `WebSockets` and `asyncio`).
- **Validation & Protocol**: **Pydantic v2** discriminated unions for typed client/server WebSocket messages and REST endpoints.
- **Database**: **PostgreSQL 17** accessed directly via **Psycopg 3** (`psycopg[binary,pool]` with `AsyncConnectionPool`), configured via `docker-compose.yml` (`postgresql://games:games@localhost:5434/games` by default, overrideable with `DATABASE_URL`).
  - Shared relational tables (`rooms`, `room_players`, `player_stats`) and `JSONB` for game-specific board state so games can be resumed and share room infrastructure without rigid schema coupling.

## Modular Structure & Standalone Extractability

To share components across games while allowing any game to be extracted and run standalone:

1. **Core Layer (`core`)**:
   - **Backend (`backend/games_platform/core/`)**:
     - `db.py`: Psycopg 3 `AsyncConnectionPool` and schema initialization (`rooms`, `room_players`, `player_stats`).
     - `protocol.py`: `GameDefinition` protocol and Pydantic v2 discriminated unions for WebSocket/REST messages.
     - `room_manager.py`: WebSocket room/lobby lifecycle, 10-second streak multiplier tracking (`1.1x`), and PostgreSQL state persistence.
   - **Frontend (`frontend/src/lib/core/`)**:
     - `profile.svelte.ts`: Player profile store (`localStorage` UUID, name, and primary color).
     - `color.ts`: Perceptual OKLCH `opponent_color(my_color, their_color)` resolver.
     - `ws.svelte.ts`: Auto-reconnecting typed WebSocket client.
     - `components/`: `ScribblyBox.svelte`, `ScribblyButton.svelte`, `ProfileBadge.svelte`, and shared `Lobby.svelte`.
2. **Self-Contained Game Modules (`games/<slug>`)**:
   - **Backend (`backend/games_platform/games/sudoku/`)**:
     - `generator.py`: 9x9 Sudoku generator with MRV uniqueness solver and cell difficulty classifier.
     - `game.py`: `SudokuGame` implementing `GameDefinition` (shared board edits, per-player colored corner notes, mistake rejection with `-10` flash, `2 * multiplier` last-in-unit scoring, `5 * multiplier` difficult cell scoring).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.sudoku.standalone:app`).
   - **Frontend (`frontend/src/lib/games/sudoku/`)**:
     - `SudokuGame.svelte`: Mobile-first 9x9 scribbly Sudoku board, corner notes mode, live peer cursors, and 10-second streak multiplier bar.

## Coding Conventions
- Use Python 3.12+ syntax (`type` aliases, generics `def foo[T]()`, built-in `dict`, `list`, `tuple`, `X | Y` unions — do not import legacy `typing` equivalents).
- Use `repr(e)` when logging or printing exceptions.
- Use **Psycopg 3** async pools/cursors directly rather than heavy ORMs.
