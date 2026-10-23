.PHONY: dev db db-down backend frontend install test check

# Start PostgreSQL, Backend (port 8000), and Frontend (port 5173) together
dev: db
	@echo "Starting backend (http://localhost:8000) and frontend (http://localhost:5173)..."
	@trap 'kill 0' INT TERM EXIT; \
		(cd backend && uv run uvicorn games_platform.main:app --reload --port 8000) & \
		(cd frontend && pnpm run dev) & \
		wait

db:
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose up -d; \
	else \
		docker compose up -d; \
	fi

db-down:
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose down; \
	else \
		docker compose down; \
	fi

backend: db
	cd backend && uv run uvicorn games_platform.main:app --reload --port 8000

frontend:
	cd frontend && pnpm run dev

install:
	cd backend && uv sync
	cd frontend && pnpm install

test: db
	cd backend && uv run pytest

check:
	cd backend && uv run ruff check .
	cd frontend && pnpm run check
