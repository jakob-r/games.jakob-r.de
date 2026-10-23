# Architecture & Tech Stack

General product concept lives in `idea.md`.

## Tech Stack

### Frontend (No React)
- **Framework**: **Svelte 5** (using Runes: `$state`, `$derived`, `$effect`) with **SvelteKit** and **TypeScript**.
  - Fine-grained reactivity updates individual DOM nodes (ideal for high-frequency multiplayer board and corner-note updates) without Virtual DOM overhead.
  - Built-in `svelte/motion` (`Spring`, `Tween`) and `svelte/transition` primitives for nuanced micro-animations.
- **Styling & Scribbly Visuals**:
  - **Tailwind CSS v4** + native CSS custom properties.
  - **Rough.js** + inline **SVG** with `stroke-dasharray`/`stroke-dashoffset` animations and subtle SVG displacement filters for a minimalistic, hand-drawn scribbly look.
- **Color System (`opponent_color`)**:
  - **OKLCH perceptual color space** (via lightweight math or `culori`) for `opponent_color(my_color, their_color)`.
  - Ensures perceptual color distance and contrast remain uniform while keeping the UI monochrome by default and using color strictly where helpful (player identity, semantic feedback).
- **Build & Package Manager**: **Vite** + **pnpm** (or npm).

### Backend
- **Language & Packaging**: **Python 3.13** managed with **uv**.
- **Web & Realtime Framework**: **FastAPI** + **Uvicorn** (with native `WebSockets` and `asyncio`).
- **Validation & Protocol**: **Pydantic v2** discriminated unions for typed client/server WebSocket messages and REST endpoints.
- **Database**: **PostgreSQL** accessed directly via **Psycopg 3** (`psycopg[binary,pool]` with `AsyncConnectionPool`).
  - Shared relational tables for rooms, players, and personal stats/history; `JSONB` for game-specific board state so games can be resumed and share room infrastructure without rigid schema coupling.

## Modular Structure & Standalone Extractability

To share components across games while allowing any game to be extracted and run standalone:

1. **Core Layer (`core`)**:
   - **Backend (`backend/games_platform/core/`)**: WebSocket room/lobby manager, connection lifecycle, player session handling, reconnection/resume tokens, and shared database pool.
   - **Frontend (`frontend/src/lib/core/`)**: Player profile store (`localStorage` name & primary color), `opponent_color(my_color, their_color)` perceptual resolver, lobby ready-check component, WebSocket client with auto-reconnect, and scribbly UI primitives.
2. **Self-Contained Game Modules (`games/<slug>`)**:
   - **Backend (`backend/games_platform/games/<slug>/`)**: Implements a `GameDefinition` protocol (`create_initial_state`, `apply_action`, `get_public_view`, `compute_score`) with zero dependencies on other games. Can be mounted into the main platform app or run standalone with a thin wrapper.
   - **Frontend (`frontend/src/lib/games/<slug>/`)**: Self-contained Svelte components and state logic for the specific game (e.g., `sudoku`), consuming core primitives via props/context.

## Coding Conventions
- Use Python 3.12+ syntax (`type` aliases, generics `def foo[T]()`, built-in `dict`, `list`, `tuple`, `X | Y` unions — do not import legacy `typing` equivalents).
- Use `repr(e)` when logging or printing exceptions.
- Use **Psycopg 3** async pools/cursors directly rather than heavy ORMs.
