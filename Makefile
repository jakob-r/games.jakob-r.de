.PHONY: dev db db-down wait-db backend frontend install test check build \
	docker-up docker-down

DOCKER_COMPOSE ?= docker-compose

# Load the root .env (if present) so targets can use POSTGRES_* etc.
-include .env
export

POSTGRES_USER ?= games
POSTGRES_DB ?= games

# Start PostgreSQL, Backend (port 8000), and Frontend (port 5173) together
dev:
	test -f .env || cp .env.example .env
	$(MAKE) db
	$(MAKE) wait-db
	@echo "Starting backend (http://localhost:$${BACKEND_PORT:-8000}) and frontend (http://localhost:$${FRONTEND_PORT:-5173})..."
	@trap 'kill 0' INT TERM EXIT; \
		(cd backend && uv run uvicorn games_platform.main:app --reload --port $${BACKEND_PORT:-8000}) & \
		(cd frontend && pnpm run dev --port $${FRONTEND_PORT:-5173}) & \
		wait

db:
	$(DOCKER_COMPOSE) up -d postgres

wait-db:
	@echo "Waiting for Postgres..."
	@for i in $$(seq 1 20); do \
		$(DOCKER_COMPOSE) exec -T postgres pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) >/dev/null 2>&1 && exit 0; \
		sleep 1; \
	done; \
	echo "Postgres did not become ready (is port $${POSTGRES_PORT:-5434} free?)"; exit 1

db-down:
	$(DOCKER_COMPOSE) down

backend: db wait-db
	cd backend && uv run uvicorn games_platform.main:app --reload --port $${BACKEND_PORT:-8000}

frontend:
	cd frontend && pnpm run dev --port $${FRONTEND_PORT:-5173}

install:
	cd backend && uv sync
	cd frontend && pnpm install

test: db wait-db
	cd backend && uv run pytest

check:
	cd backend && uv run ruff check .
	cd frontend && pnpm run check

build:
	cd frontend && pnpm run build

docker-up:
	test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) --profile app up -d --build

docker-down:
	$(DOCKER_COMPOSE) --profile app down
