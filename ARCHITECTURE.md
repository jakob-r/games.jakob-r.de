# Architecture & Tech Stack

General product concept lives in `idea.md`.

## Tech Stack

### Frontend (No React)
- **Framework**: **Svelte 5** (using Runes: `$state`, `$derived`, `$effect`) with **SvelteKit** and **TypeScript**.
  - Fine-grained reactivity updates individual DOM nodes (ideal for high-frequency multiplayer board and corner-note updates) without Virtual DOM overhead.
  - Built-in `svelte/motion` (`Spring`, `Tween`) and `svelte/transition` primitives for nuanced micro-animations.
- **SEO & game hubs**: Shared catalog in `frontend/src/lib/games/catalog.ts` plus scribbly `GameLogo.svelte` icons. The landing page lists games in catalog order and, after load, re-sorts them by `play_count` from `GET /api/games` (number of non-lobby rooms per game still in the DB, i.e. roughly games started in the last year). Each game has a prerendered hub at `/{slug}` (`GameHub.svelte`: description, create room, open sessions for that game). Landing and hubs emit per-page title/description/canonical/OG/JSON-LD via `SeoHead.svelte`. `static/robots.txt` + `static/sitemap.xml` list those URLs. Room play stays at `/{slug}/{roomId}` via adapter-static `200.html` SPA fallback. FastAPI serves prerendered `{slug}.html` (or `{slug}/index.html`) for hubs and falls back to `200.html` for room routes.
- **Styling & Scribbly Visuals**:
  - **Tailwind CSS v4** + native CSS custom properties.
  - **Fonts are self-hosted** via `@fontsource/*` packages imported in `+layout.svelte` (bundled by Vite). No third-party requests (no Google Fonts, CDNs, analytics); keep it that way.
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
  - Shared relational tables (`rooms`, `room_players`, `player_stats`, plus `users`, `auth_sessions`, `auth_email_tokens`, `oauth_accounts`) and `JSONB` for game-specific board state so games can be resumed and share room infrastructure without rigid schema coupling.

## Accounts (optional)

Playing stays anonymous by default (random `player_id` in `localStorage`). Accounts are additive: `users.player_id` is the stable id, so stats and recent rooms follow the account. Sign-up adopts the browser's current anonymous id unless taken; after login the frontend (`auth.svelte.ts`) switches `profile.playerId` to the account's id and generates a fresh anonymous id on sign-out.

- Backend (`core/auth.py`, `auth_api.py`, `oauth.py`, `mail.py`, routes under `/api/auth`): email + password (argon2), Google OpenID Connect (authorization code + PKCE, hand-written with `httpx`; a signed `games_oauth` cookie binds the flow to the browser), email verification and password reset via single-use hashed tokens. Sessions are opaque random tokens stored hashed in `auth_sessions` (HttpOnly, SameSite=Lax cookie `games_session`, 30 days sliding, `Secure` when `PUBLIC_BASE_URL` is https) — no JWTs. Password change/reset revokes all sessions. Rate limits are in memory and keyed by email, never by IP. If Google signs in to an address that was registered but never verified, the unverified password is dropped (prevents pre-registration takeover). Deleting an account removes its stats, push subscriptions and hosted rooms.
- CORS is limited to `PUBLIC_BASE_URL`, `http://localhost:5173` and the comma-separated `CORS_EXTRA_ORIGINS` (e.g. `capacitor://localhost`) because cookies carry login state. The `SameSite=Lax` session cookie is not sent from a native shell's origin, so cross-origin clients use token transport instead: they send `X-Session-Transport: token`, get `session_token` in the JSON body of register/login/password change (no cookie), store it in `localStorage` (`games_session_token`, only when `crossOrigin` in `server.ts`) and send `Authorization: Bearer <token>`. The backend accepts the cookie first, then the bearer header; same hashed `auth_sessions` rows, sliding expiry and revocation. Browsers never see the token. Google sign-in still sets the cookie and needs a native hand-off (deep link) before it works in the app.
- Frontend routes: `/login` (sign in / sign up / forgot), `/account`, `/verify-email`, `/reset-password` (SPA fallback, `noindex`).
- Mail goes out via the SMTP server of Linevast (domain registrar and email provider; named in the privacy page). Config via env, see `.env.example` (`PUBLIC_BASE_URL`, `AUTH_MAIL_BACKEND`, `SMTP_*`, `GOOGLE_CLIENT_*`). Not implemented: change email, Apple sign-in.

## Modular Structure & Standalone Extractability

To share components across games while allowing any game to be extracted and run standalone:

1. **Core Layer (`core`)**:
   - **Backend (`backend/games_platform/core/`)**:
     - `db.py`: Psycopg 3 `AsyncConnectionPool`, schema initialization (`rooms`, `room_players`, `player_stats`, `app_settings`, `push_subscriptions`), and expired room cleanup (2 days without moves, 1 year with moves) plus `player_stats` untouched for 1 year. The app container runs uvicorn with `--no-access-log` (no IPs logged by the app; data retention is described in the privacy page `frontend/src/routes/privacy/+page.svelte`).
     - `protocol.py`: `GameDefinition` protocol and Pydantic v2 discriminated unions for WebSocket/REST messages.
     - `push.py`: `WebPushService` for auto-generated/persisted VAPID keys and asynchronous `pywebpush` turn-notification delivery. Endpoints are limited to known push-service hosts (at most 5 per player). Pushes use a 5-minute TTL and a per-room Topic so a later turn replaces a queued alert. Set `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` when more than one process serves the app.
     - `protocol.py` optional game hooks (looked up with `getattr`): `get_player_view(state, config, viewer_id)` makes `RoomManager` send each connection its own `room_state` (hidden information such as a secret word; REST snapshots use `viewer_id=None`), and `on_player_removed(state, config, player_id)` runs after the shared `turn_order` fix-up when someone leaves mid-game.
     - Bot players (hooks `get_bot_players(config)` and async `bot_turn(room_id, state, config, bot_id)`): bots have ids prefixed `ai:` (`is_bot_id`), get a ready `room_players` row (score, player bar, `is_bot` in snapshots, always shown as connected) that `RoomManager` syncs on room create, config update and game start. They are never in `turn_order`, cannot be removed by the host or claimed by a client, and are skipped in `player_stats`. After each human game action `RoomManager` restarts a per-room `BOT_DEBOUNCE_SECONDS` (1 s) timer; when it runs out, `bot_turn` runs without the room lock (it may call an LLM) and a returned action is applied like a player action. Only one bot run per room at a time; changes during a run trigger one more run afterwards.
     - `llm.py`: Minimal async OpenRouter chat client (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, default `deepseek/deepseek-v4.1-flash`; reasoning off, `provider.data_collection=deny`), same setup as eventmat.
     - `room_manager.py`: WebSocket room/lobby lifecycle, host-only `end_game` message (playing → finished with final scores, usable by any game), non-creator player leave handling (including automatic leave when a new player joins a running game and disconnects without acting) and host player removal (creators cannot leave a room, only delete it or remove other players), 10-second streak multiplier tracking (`1.1x` starting after first right entry), turn-change Web Push dispatch, and PostgreSQL state persistence.
   - **Frontend (`frontend/src/lib/core/`)**:
     - `profile.svelte.ts`: Player profile store (`localStorage` UUID, name configuration tracking, and primary color).
     - `color.ts`: Perceptual OKLCH similarity check and preset-palette `opponent_color(my_color, their_color)` resolver.
     - `ws.svelte.ts`: Auto-reconnecting typed WebSocket client.
     - `server.ts`: `apiUrl`, `wsUrl`, `publicUrl`/`currentPublicUrl`. All API, WebSocket and share-link URLs go through it. Empty `VITE_SERVER_ORIGIN` (default) keeps them same-origin; a native shell (planned Capacitor iOS app, page origin `capacitor://localhost`) builds with `VITE_SERVER_ORIGIN=https://games.jakob-r.de` so it talks to the same server and shares the same rooms as web players.
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
   - **Shared dictionary (`backend/games_platform/core/dictionary.py`)**: `wordfreq`-backed word lists (`de`, `en`, `fr`, `es`, normalized to A–Z), `is_valid_word`, and per-language `1–10` letter rarity scores (`LETTER_SCORES`, `get_letter_score`). Used by Silbenstreit and Spellsprawl.
   - **Backend (`backend/games_platform/games/silbenstreit/`)**:
     - `dictionary.py`: Re-exports the shared dictionary and adds the syllable-sampled board generator (`4×4` to `8×8` in `de`, `en`, `fr`, `es`) ensuring orthographic clusters like `QU` stay accompanied.
     - `game.py`: `SilbenstreitGame` implementing `GameDefinition` (round-based word submission, tile ownership transfer, `extra_score_deltas` board-ownership scoring, orthogonal tile protection, and word reuse prevention).
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.silbenstreit.standalone:app`).
   - **Frontend (`frontend/src/lib/games/silbenstreit/`)**:
     - `SilbenstreitGame.svelte`: Mobile-first `4×4`–`8×8` scribbly letter grid with rarity badges, protected tile indicators, keyboard & tap word composer, and played words history.

   - **Backend (`backend/games_platform/games/emoji_charades/`)** (slug `emoji-charades`):
     - `words.py`: Curated German/English word lists (`"Text|alias|alias"` per line) across object, food, animal, brand, person, movie, TV show, and quote categories.
     - `matching.py`: Typo-tolerant guess matching (accent/umlaut/ß folding, leading-article stripping, length-scaled Levenshtein threshold) plus a looser `is_close` hint.
     - `ai_player.py`: Optional AI guesser (`ai:emoji-charades`). The prompt is built from `get_player_view(..., bot_id)` only (emoji sentences, category if shown, wrong guesses so far); it asks again only when the hints change (`hint_signature`). It types guesses in both modes and never explains. Config `ai_player` is forced off and `ai_available` is false while `OPENROUTER_API_KEY` is unset (the lobby hides the toggle).
     - `game.py`: `EmojiCharadesGame` (`in_person`/`remote` modes, optional timer, optional category hint for guessers (`show_category`), choosing → explaining → reveal phases, circular explainers via `turn_order` with `current_player_id` = explainer or next explainer so turn pushes fire, `+1` guesser and `+1` explainer when timed). Uses `get_player_view` to hide the word and choices from guessers and `on_player_removed` to end a round whose explainer left. Timed rounds have no server timer task: clients send `time_up` at the deadline and the server only accepts it once the deadline has passed.
     - `standalone.py`: Standalone FastAPI entrypoint (`uv run uvicorn games_platform.games.emoji_charades.standalone:app`).
   - **Frontend (`frontend/src/lib/games/emoji-charades/`)**:
     - `emojis.ts`: The tunable emoji palette (Concepts and Actions as antonym pairs; People, Things, Shapes, Colors, Foods, Animals, Countries as lists).
     - `EmojiCharadesGame.svelte`: Word picker, multi-sentence emoji editor (tap to select, move, delete; add/remove sentences), guess input with close hints, in-person award chips, reveal card, and host end-game.

   - **Backend (`backend/games_platform/games/spellsprawl/`)**:
     - `board.py`: Pure logic for the sparse infinite grid (`cells` keyed `"row,col"`, coordinates clamped to ±1000): placement geometry (one line, gaps only filled by existing letters), main word as the full run, Scrabble-style cross-words, score = rarity of pre-existing letters in main + cross-words, and bounding-box area.
     - `game.py`: `SpellsprawlGame` (1–8 players, round-based via `turn_order`, all formed words must be in the dictionary, main words cannot repeat, islands allowed, pass turn; ends on `words` / `points` / `area` targets or when everyone passed twice). State includes `letter_scores` so the client can preview points.
     - `standalone.py`: Standalone FastAPI entrypoint.
   - **Frontend (`frontend/src/lib/games/spellsprawl/`)**:
     - `board.ts`: Client mirror of the run/cross-word logic for the live preview only (server stays authoritative).
     - `SpellsprawlGame.svelte`: Scrollable/zoomable grid (bounding box + margin, padded to fill the viewport; letters absolutely positioned over a CSS grid background, taps hit-tested by coordinates). Typing goes through an off-screen `<input>` (system keyboard on mobile; input diffed against a one-space sentinel so Android virtual keyboards work). Tap a cell to start, tap it again or use →/↓ to switch direction (locked after two new letters); typing a letter equal to an existing cell consumes it, otherwise existing cells are skipped; tap a pending letter to overwrite, Backspace / Escape / Enter.

`ActionOutcome.extra_score_deltas` lets a single action credit other players (minesweeper flag challenges); `RoomManager` applies those deltas after the actor's score update.

## Coding Conventions
- Always keep the root `Makefile` up to date so the entire local stack (database, backend, frontend) can be started with `make dev`.
- Use Python 3.12+ syntax (`type` aliases, generics `def foo[T]()`, built-in `dict`, `list`, `tuple`, `X | Y` unions — do not import legacy `typing` equivalents).
- Use `repr(e)` when logging or printing exceptions.
- Use **Psycopg 3** async pools/cursors directly rather than heavy ORMs.
- Landing pages end with a small footer: "by jakob-r" (→ https://www.jakob-r.de/coding/), source code, license (if the repo has one), the legal notice on jakob-r.de and the own privacy page `/privacy` (games.jakob-r.de processes data differently from the static jakob-r.de, so it has its own policy; keep it in sync with data handling and the proxy log setup on the VPS: nginx-proxy `LOG_FORMAT` without `$remote_addr`, size-capped json-file logs). Game sessions (`/{slug}/{roomId}`) have no footer.
- PWA: `static/manifest.webmanifest` (standalone, served as `application/manifest+json`) plus `icon-192/512.png`, `apple-touch-icon.png` and `favicon.png`, all rendered from `og/icon.html` by `make icons`. Home-screen install also enables Web Push on iOS 16.4+.
- Share image: `og/og.html` is rendered by `make og` (headless Chrome) to `frontend/static/og.png` (1200×630) and set as `og:image`. jakob-r.de/coding uses a copy of it. Re-render when the site changes noticeably.

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
