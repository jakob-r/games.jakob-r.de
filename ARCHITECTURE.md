# Architecture & Tech Stack

General product concept lives in `idea.md`.

## Tech Stack

### Frontend (No React)
- **Framework**: **Svelte 5** (using Runes: `$state`, `$derived`, `$effect`) with **SvelteKit** and **TypeScript**.
  - Fine-grained reactivity updates individual DOM nodes (ideal for high-frequency multiplayer board and corner-note updates) without Virtual DOM overhead.
  - Built-in `svelte/motion` (`Spring`, `Tween`) and `svelte/transition` primitives for nuanced micro-animations.
- **SEO & game hubs**: Shared catalog in `frontend/src/lib/games/catalog.ts` plus scribbly `GameLogo.svelte` icons. Each game has a prerendered hub at `/{slug}` (`GameHub.svelte`: description, create room, open sessions for that game). Landing and hubs emit per-page title/description/canonical/OG/JSON-LD via `SeoHead.svelte`. `static/robots.txt` + `static/sitemap.xml` list those URLs. Room play stays at `/{slug}/{roomId}` via adapter-static `200.html` SPA fallback. FastAPI serves prerendered `{slug}.html` (or `{slug}/index.html`) for hubs and falls back to `200.html` for room routes.
- **Styling & Scribbly Visuals**:
  - **Tailwind CSS v4** + native CSS custom properties.
  - **Rough.js** + inline **SVG** with `stroke-dasharray`/`stroke-dashoffset` animations and subtle SVG displacement filters (`#scribble-filter`) for a minimalistic, hand-drawn scribbly look.
- **Color System (`opponent_color`)**:
  - **OKLCH perceptual color space** in `frontend/src/lib/core/color.ts` for `opponent_color(my_color, their_color)`.
  - Keeps other players' colors unchanged unless they are perceptually too similar to `my_color`, in which case it deterministically assigns a distinct color from `PRESET_PLAYER_COLORS`.
- **Build & Package Manager**: **Vite** + **pnpm**; production uses `@sveltejs/adapter-static` (SPA fallback) so FastAPI can serve the built site.

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
     - `db.py`: Psycopg 3 `AsyncConnectionPool`, schema initialization (`rooms`, `room_players`, `player_stats`, `app_settings`, `push_subscriptions`), and expired room cleanup (2 days without moves, 1 year with moves).
     - `protocol.py`: `GameDefinition` protocol and Pydantic v2 discriminated unions for WebSocket/REST messages.
     - `push.py`: `WebPushService` for auto-generated/persisted VAPID keys and asynchronous `pywebpush` turn-notification delivery. Endpoints are limited to known push-service hosts (at most 5 per player). Pushes use a 5-minute TTL and a per-room Topic so a later turn replaces a queued alert. Set `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` when more than one process serves the app.
     - `protocol.py` optional game hooks (looked up with `getattr`): `get_player_view(state, config, viewer_id)` makes `RoomManager` send each connection its own `room_state` (hidden information such as a secret word; REST snapshots use `viewer_id=None`), and `on_player_removed(state, config, player_id)` runs after the shared `turn_order` fix-up when someone leaves mid-game.
     - `room_manager.py`: WebSocket room/lobby lifecycle, host-only `end_game` message (playing → finished with final scores, usable by any game), non-creator player leave handling (including automatic leave when a new player joins a running game and disconnects without acting) and host player removal (creators cannot leave a room, only delete it or remove other players), 10-second streak multiplier tracking (`1.1x` starting after first right entry), turn-change Web Push dispatch, and PostgreSQL state persistence.
   - **Frontend (`frontend/src/lib/core/`)**:
     - `profile.svelte.ts`: Player profile store (`localStorage` UUID, name configuration tracking, and primary color).
     - `color.ts`: Perceptual OKLCH similarity check and preset-palette `opponent_color(my_color, their_color)` resolver.
     - `ws.svelte.ts`: Auto-reconnecting typed WebSocket client.
     - `notifications.svelte.ts` + `static/sw.js`: Opt-in turn notifications combining the client `Notification` API, tab title `🔔` indicator, and Service Worker Web Push subscriptions.
     - `components/`: `ScribblyBox.svelte`, `ScribblyButton.svelte`, `ProfileBadge.svelte`, `NamePromptModal.svelte`, `RemovePlayerModal.svelte`, `PlayerBar.svelte`, `TurnNotificationBell.svelte`, `RoomShell.svelte`, and shared `Lobby.svelte`.
2. **Self-Contained Game Modules (`games/<slug>`)**:
   - **Backend (`backend/games_platform/games/sudoku/`)**:
     - `generator.py`: 9x9 Sudoku generator with MRV uniqueness solver and cell difficulty classifier.
     - `game.py`: `SudokuGame` implementing `GameDefinition` (shared board edits, per-player colored corner notes, mistake rejection with `-10` flash, `2 * multiplier` last-in-unit scoring, `5 * multiplier` difficult cell scoring).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.sudoku.standalone:app`).
   - **Frontend (`frontend/src/lib/games/sudoku/`)**:
     - `SudokuGame.svelte`: Mobile-first 9x9 scribbly Sudoku board, corner notes mode, live peer cursors, and 10-second streak multiplier bar.
   - **Backend (`backend/games_platform/games/kaesekaestchen/`)**:
     - `game.py`: `KaesekaestchenGame` implementing `GameDefinition` (configurable `3×3` to `12×12` grid, flood-fill custom enclosed board shapes and pre-drawn border edges, round-based turn order, bonus turn on closing 1 or 2 squares, `+1` point per closed square).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.kaesekaestchen.standalone:app`).
   - **Frontend (`frontend/src/lib/games/kaesekaestchen/`)**:
     - `KaesekaestchenGame.svelte`: Interactive lobby custom outline editor (with shape presets and click/drag edge drawing) and scribbly SVG Dots & Boxes game canvas with player-colored lines and hatched square claims.
   - **Backend (`backend/games_platform/games/minesweeper/`)**:
     - `game.py`: `MinesweeperGame` implementing `GameDefinition` (difficulty presets, deferred first-click-safe mine placement, flood-fill reveals, flag/challenge scoring with `extra_score_deltas`, win on all-safe-cleared or all-mines-secured).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.minesweeper.standalone:app`).
   - **Frontend (`frontend/src/lib/games/minesweeper/`)**:
     - `MinesweeperGame.svelte`: Mobile-first dig/flag modes, long-press flagging, player-colored flags, boom FX on mine hits, and challenge confirm for opponent flags.
   - **Backend (`backend/games_platform/games/silbenstreit/`)**:
     - `dictionary.py`: `wordfreq`-backed dictionary validation, per-language `1–10` letter rarity scores, and syllable-sampled board generator (`4×4` to `8×8` in `de`, `en`, `fr`, `es`) ensuring orthographic clusters like `QU` stay accompanied.
     - `game.py`: `SilbenstreitGame` implementing `GameDefinition` (round-based word submission, tile ownership transfer, `extra_score_deltas` board-ownership scoring, orthogonal tile protection, and word reuse prevention).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.silbenstreit.standalone:app`).
   - **Frontend (`frontend/src/lib/games/silbenstreit/`)**:
     - `SilbenstreitGame.svelte`: Mobile-first `4×4`–`8×8` scribbly letter grid with rarity badges, protected tile indicators, keyboard & tap word composer, and played words history.

   - **Backend (`backend/games_platform/games/emoji_charades/`)** (slug `emoji-charades`):
     - `words.py`: Curated German/English word lists (`"Text|alias|alias"` per line) across object, food, animal, brand, person, movie, TV show, and quote categories.
     - `matching.py`: Typo-tolerant guess matching (accent/umlaut/ß folding, leading-article stripping, length-scaled Levenshtein threshold) plus a looser `is_close` hint.
     - `game.py`: `EmojiCharadesGame` (`in_person`/`remote` modes, optional timer, choosing → explaining → reveal phases, circular explainers via `turn_order` with `current_player_id` = explainer or next explainer so turn pushes fire, `+1` guesser and `+1` explainer when timed). Uses `get_player_view` to hide the word and choices from guessers and `on_player_removed` to end a round whose explainer left. Timed rounds have no server timer task: clients send `time_up` at the deadline and the server only accepts it once the deadline has passed.
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.emoji_charades.standalone:app`).
   - **Frontend (`frontend/src/lib/games/emoji-charades/`)**:
     - `emojis.ts`: The tunable emoji palette (Concepts and Actions as antonym pairs; Shapes, Colors, Foods, Animals, Countries as lists).
     - `EmojiCharadesGame.svelte`: Word picker, multi-sentence emoji editor (tap to select, move, delete; add/remove sentences), guess input with close hints, in-person award chips, reveal card, and host end-game.

`ActionOutcome.extra_score_deltas` lets a single action credit other players (minesweeper flag challenges); `RoomManager` applies those deltas after the actor's score update.

## Coding Conventions
- Always keep the root `Makefile` up to date so the entire local stack (database, backend, frontend) can be started with `make dev`.
- Use Python 3.12+ syntax (`type` aliases, generics `def foo[T]()`, built-in `dict`, `list`, `tuple`, `X | Y` unions — do not import legacy `typing` equivalents).
- Use `repr(e)` when logging or printing exceptions.
- Use **Psycopg 3** async pools/cursors directly rather than heavy ORMs.

## Production

The root `Dockerfile` builds one image: SvelteKit (`adapter-static`) is compiled into `/app/public`, and uvicorn serves the API, WebSockets, and that SPA on `BACKEND_PORT` (default `8000`). Schema init runs on DB connect (no separate migrate step). `docker-compose.yml` keeps Postgres always available for local `make db`; the `app` service sits behind the Compose `app` profile:

```bash
make docker-up
```

### VPS deployment with Docker Compose

Same pattern as [retromode](https://github.com/jakob-r/retromode): own stack next to an existing [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) with acme-companion.

- `postgres`: PostgreSQL with a named volume, published only on `127.0.0.1`
- `app`: production image; joins the proxy's Docker network and advertises `VIRTUAL_HOST`, so nginx-proxy routes the hostname (including WebSockets) and Let's Encrypt issues the cert. Until the first cert exists, the app serves ACME challenges from the companion's webroot volume (`ACME_WEBROOT`).

Leave the proxy's Compose file alone and don't edit nginx by hand. DNS for `VIRTUAL_HOST` must already point at the VPS.

1. On the VPS: clone the repo, `cp .env.example .env`, set a strong `POSTGRES_PASSWORD` (Compose overrides `DATABASE_URL` to the internal `postgres` service), then uncomment and fill in `VIRTUAL_HOST`, `LETSENCRYPT_HOST`, `LETSENCRYPT_EMAIL`, `PROXY_NETWORK` (`docker network ls | grep proxy`) and `PROXY_HTML_VOLUME` (`docker volume ls | grep html`).
2. Build and start:

   ```bash
   docker compose --profile app up -d --build
   ```

   Or from the Makefile: `make docker-up`.

3. Check: `docker compose --profile app ps` and `docker compose --profile app logs -f app`. Redeploy with `git pull` plus step 2.

Local image smoke-test (without a real nginx-proxy): create stand-ins once (`docker network create docker_compose_proxy-tier` and `docker volume create docker_compose_html`), then `make docker-up` and hit `http://127.0.0.1:8082`.
