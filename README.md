# games.jakob-r.de

**Minimalistic multiplayer games. No ads, no tracking, hosted in Europe (Germany).**

👉 **Play at [games.jakob-r.de](https://games.jakob-r.de)**

[![Live at games.jakob-r.de](https://img.shields.io/badge/live-games.jakob--r.de-1a1917)](https://games.jakob-r.de)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-6e6a63)](LICENSE)
[![Hosted in Europe (Germany)](https://img.shields.io/badge/hosted%20in-Europe%20%28Germany%29%20🇪🇺-FFD23F)](https://games.jakob-r.de)

[games.jakob-r.de](https://games.jakob-r.de) is a small collection of real-time multiplayer games with a scribbly, minimal look. Pick a name, create a room, share the link, and play together.

## Why games.jakob-r.de?

- 💛 **Free to play**: no paid plans, no ads, no tracking
- 🇪🇺 **Hosted in Europe**: runs on servers in Germany (EU)
- 📜 **Source available**: fork and tinker for personal / noncommercial use ([PolyForm Noncommercial](LICENSE))
- ⚡ **Live for everyone**: rooms sync over WebSockets
- 🎨 **Your colour**: set a name and primary colour; peers stay visually distinct

## Games

- **Multiplayer Sudoku** — shared 9×9 board, coloured notes, optional scoring
- **Käsekästchen** — turn-based dots-and-boxes on a customisable grid
- **Co-op Minesweeper** — dig and flag the same minefield together
- **Silbenstreit** — claim letter tiles with words, steal, and surround

## Use it

Open **[games.jakob-r.de](https://games.jakob-r.de)**, start a room, and share the link. That’s it.

## Development

See [IDEA.md](IDEA.md) for the product concept and [ARCHITECTURE.md](ARCHITECTURE.md) for the tech stack.

### Quick start

Requirements: Python 3.13+, [uv](https://docs.astral.sh/uv/), Node 22+, pnpm, Docker (with `docker-compose`), make.

```bash
make dev
```

This creates `.env` from `.env.example`, starts Postgres, and runs backend + frontend. Then open http://localhost:5173 (or whatever `FRONTEND_PORT` is set to).

### Repository

| Path        | What                                              |
| ----------- | ------------------------------------------------- |
| `frontend/` | Svelte 5 + SvelteKit + Tailwind 4 + Rough.js SPA  |
| `backend/`  | FastAPI + Psycopg 3 + WebSockets on PostgreSQL    |

All configuration lives in **one root `.env`** (not checked in). `.env.example` documents every variable.

### Common tasks

| Command                          | What it does                                        |
| -------------------------------- | --------------------------------------------------- |
| `make dev`                       | Full local setup + backend and frontend             |
| `make check`                     | Frontend typecheck / svelte-check                   |
| `make build`                     | Production build                                    |
| `make docker-up` / `docker-down` | Run the production image together with Postgres     |

## Production

The root `Dockerfile` builds one image. FastAPI serves the API, WebSockets and the built frontend. See [ARCHITECTURE.md](ARCHITECTURE.md) for VPS deployment next to nginx-proxy / acme-companion.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE). You may use, modify and share the code for personal and other noncommercial purposes. Commercial use — including republishing with ads, a paywall, or as a paid product under another name — is not allowed.

Source: [github.com/jakob-r/games.jakob-r.de](https://github.com/jakob-r/games.jakob-r.de). Play for free at [games.jakob-r.de](https://games.jakob-r.de).
