.DEFAULT_GOAL := help

# Tools (override if needed, e.g. `make test UV=/path/to/uv`).
UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose

API_DIR := apps/api
# Host-side Python commands (tests, migrations) talk to the compose Postgres.
POSTGRES_PORT ?= 5432
API_PORT ?= 8000
WEB_PORT ?= 3000
export POSTGRES_PORT API_PORT WEB_PORT
NEXT_PUBLIC_API_URL ?= http://localhost:$(API_PORT)
export NEXT_PUBLIC_API_URL

DATABASE_URL ?= postgresql://postgres:postgres@localhost:$(POSTGRES_PORT)/boilerplate
export DATABASE_URL

CYAN := \033[0;36m
GREEN := \033[0;32m
NC := \033[0m

.PHONY: help setup dev up down logs ps build fresh smoke \
	migrate migrate-compose migration db-shell \
	test lint lint-api lint-web typecheck typecheck-api typecheck-web \
	fmt fmt-check build-web

help: ## Show this help message
	@printf "$(GREEN)Available commands:$(NC)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-16s$(NC) %s\n", $$1, $$2}'

# ============================== Setup / dev =================================

setup: ## Install API (uv) and JS (pnpm) dependencies from the lockfiles
	cd $(API_DIR) && $(UV) sync --locked
	$(PNPM) install --frozen-lockfile

dev: migrate-compose ## postgres + api in Docker (hot reload), web dev server on the host
	$(COMPOSE) up -d --wait api
	$(PNPM) turbo run dev --filter web -- --port $(WEB_PORT)

# ============================== Docker ======================================

up: migrate-compose ## Migrate the database, then start api and web in Docker
	$(COMPOSE) up -d
	@printf "$(GREEN)✓ Services started$(NC)\n"
	@echo "  Web:      http://localhost:$(WEB_PORT)"
	@echo "  API:      http://localhost:$(API_PORT)"
	@echo "  API docs: http://localhost:$(API_PORT)/docs"

down: ## Stop all services
	$(COMPOSE) down

logs: ## Follow logs of all services
	$(COMPOSE) logs -f

ps: ## Show service status (including health)
	$(COMPOSE) ps

build: ## Rebuild all images
	$(COMPOSE) build

fresh: ## Full reset: stop, delete the database volume, rebuild, start
	$(COMPOSE) down -v
	$(MAKE) migrate-compose
	$(COMPOSE) up -d --build --wait
	@printf "$(GREEN)✓ Fresh start complete$(NC)\n"

smoke: export COMPOSE_FILE ?= docker-compose.yml:docker-compose.smoke.yml
smoke: ## Check the packaged containers and production API configuration
	@set -eu; \
	SMOKE_SECRET_KEY="$$(openssl rand -hex 32)"; export SMOKE_SECRET_KEY; \
	$(COMPOSE) up -d --build --wait --wait-timeout 180 postgres api web; \
	if [ "$${SMOKE_EXPECT_UNMIGRATED:-0}" = 1 ] && $(COMPOSE) exec -T api python healthcheck.py http://127.0.0.1:8000/ready; then \
		echo "API unexpectedly ready before migrations" >&2; exit 1; \
	fi; \
	$(COMPOSE) run --rm --no-deps api alembic upgrade head; \
	$(COMPOSE) exec -T api python healthcheck.py http://127.0.0.1:8000/ready; \
	./scripts/check-production-api.sh; \
	./scripts/check-containers.sh api web
	@printf "$(GREEN)✓ postgres, api and web are healthy; api and web are non-root and unmounted$(NC) (stop with: make down)\n"

# ============================== Database ====================================

migrate-compose: ## Apply migrations with a one-off Compose container
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) run --rm --build --no-deps api alembic upgrade head

migrate: ## Apply migrations from the host (MIGRATION_DATABASE_URL or DATABASE_URL)
	cd $(API_DIR) && $(UV) run --locked alembic upgrade head

migration: ## Create an Alembic migration: make migration name=add_column
	@if [ -z "$(name)" ]; then echo "Usage: make migration name=your_migration_name"; exit 1; fi
	cd $(API_DIR) && $(UV) run --locked alembic revision --autogenerate -m "$(name)"

db-shell: ## Open a psql shell on the dev database
	$(COMPOSE) exec postgres psql -U postgres -d boilerplate

# ============================== Quality =====================================

test: ## Run API tests against a dedicated Postgres database (override TEST_DATABASE_URL)
ifndef TEST_DATABASE_URL
	$(COMPOSE) up -d --wait postgres
	printf '%s\n' "SELECT 'CREATE DATABASE boilerplate_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'boilerplate_test')" '\gexec' | $(COMPOSE) exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d postgres
endif
	@cd $(API_DIR) && ENV=test DATABASE_URL="$(or $(TEST_DATABASE_URL),postgresql://postgres:postgres@localhost:$(POSTGRES_PORT)/boilerplate_test)" $(UV) run --locked pytest

lint: lint-api lint-web ## Lint everything

lint-api: ## ruff check
	cd $(API_DIR) && $(UV) run --locked ruff check .

lint-web: ## ESLint (via Turborepo)
	$(PNPM) turbo run lint

typecheck: typecheck-api typecheck-web ## Type-check everything

typecheck-api: ## mypy
	cd $(API_DIR) && $(UV) run --locked mypy app healthcheck.py

typecheck-web: ## tsc (via Turborepo)
	$(PNPM) turbo run typecheck

fmt: ## Format everything (ruff format + Prettier)
	cd $(API_DIR) && $(UV) run --locked ruff format .
	$(PNPM) format

fmt-check: ## Check formatting without changing files (what CI runs)
	cd $(API_DIR) && $(UV) run --locked ruff format --check .
	$(PNPM) format:check

build-web: ## Production build of the web app (via Turborepo)
	$(PNPM) turbo run build
