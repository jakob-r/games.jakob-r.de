# --- Frontend: SvelteKit static SPA
FROM node:22-alpine AS frontend
RUN npm install -g pnpm@10.30.3
WORKDIR /fe
# CI silences the pnpm "update available" banner; config files must exist before
# install so the prepare script (`svelte-kit sync`) finds the adapter.
ENV CI=true
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/svelte.config.js frontend/tsconfig.json ./
RUN pnpm install --frozen-lockfile
COPY frontend/ .
RUN pnpm run build

# --- Runtime: uvicorn serves API, WebSocket, and the built frontend
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/games_platform ./games_platform
RUN uv sync --frozen --no-dev

COPY --from=frontend /fe/build /app/public

ENV NODE_ENV=production \
    STATIC_DIR=/app/public \
    BACKEND_PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${BACKEND_PORT}/api/health')" || exit 1

CMD ["sh", "-c", "exec uvicorn games_platform.main:app --host 0.0.0.0 --port ${BACKEND_PORT}"]
