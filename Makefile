.DEFAULT_GOAL := help

# Tools (override if needed, e.g. `make test UV=/path/to/uv`).
UV ?= uv
PNPM ?= pnpm
COMPOSE ?= docker compose

API_DIR := apps/api
# Host-side Python commands (tests, migrations) talk to the compose Postgres.
DATABASE_URL ?= postgresql://postgres:postgres@localhost:5432/boilerplate
export DATABASE_URL

CYAN := \033[0;36m
GREEN := \033[0;32m
NC := \033[0m

.PHONY: help setup dev up down logs ps build fresh smoke \
	migrate migration db-shell \
	test lint lint-api lint-web typecheck typecheck-api typecheck-web \
	fmt fmt-check build-web mobile test-mobile doctor-mobile

help: ## Show this help message
	@printf "$(GREEN)Available commands:$(NC)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-16s$(NC) %s\n", $$1, $$2}'

# ============================== Setup / dev =================================

setup: ## Install API (uv) and JS (pnpm) dependencies from the lockfiles
	cd $(API_DIR) && $(UV) sync --locked
	$(PNPM) install --frozen-lockfile

dev: ## postgres + api in Docker (hot reload), web dev server on the host
	$(COMPOSE) up -d --wait postgres api
	$(PNPM) turbo run dev --filter web

# ============================== Docker ======================================

up: ## Start postgres, api and web in Docker
	$(COMPOSE) up -d
	@printf "$(GREEN)✓ Services started$(NC)\n"
	@echo "  Web:      http://localhost:3000"
	@echo "  API:      http://localhost:8000"
	@echo "  API docs: http://localhost:8000/docs"

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
	$(COMPOSE) up -d --build --wait
	@printf "$(GREEN)✓ Fresh start complete$(NC)\n"

smoke: ## Build + start all services as packaged; require healthy, non-root, no mounts
	$(COMPOSE) -f docker-compose.yml -f docker-compose.smoke.yml up -d --build --wait --wait-timeout 180 postgres api web
	COMPOSE_FILE=docker-compose.yml:docker-compose.smoke.yml ./scripts/check-containers.sh api web
	@printf "$(GREEN)✓ postgres, api and web are healthy, non-root, unmounted$(NC) (stop with: make down)\n"

# ============================== Database ====================================

migrate: ## Apply Alembic migrations (DATABASE_URL, default: compose Postgres)
	cd $(API_DIR) && $(UV) run --locked alembic upgrade head

migration: ## Create an Alembic migration: make migration name=add_column
	@if [ -z "$(name)" ]; then echo "Usage: make migration name=your_migration_name"; exit 1; fi
	cd $(API_DIR) && $(UV) run --locked alembic revision --autogenerate -m "$(name)"

db-shell: ## Open a psql shell on the dev database
	$(COMPOSE) exec postgres psql -U postgres -d boilerplate

# ============================== Quality =====================================

test: ## Run API tests (needs Postgres, e.g. `make up` or `docker compose up -d postgres`)
	cd $(API_DIR) && $(UV) run --locked pytest

test-mobile: ## Mobile unit tests (Jest)
	$(PNPM) turbo run test --filter=mobile

doctor-mobile: ## expo-doctor for the mobile app
	$(PNPM) --filter mobile run doctor:expo

lint: lint-api lint-web ## Lint everything

lint-api: ## ruff check
	cd $(API_DIR) && $(UV) run --locked ruff check .

lint-web: ## ESLint for web + mobile (via Turborepo)
	$(PNPM) turbo run lint

typecheck: typecheck-api typecheck-web ## Type-check everything

typecheck-api: ## mypy
	cd $(API_DIR) && $(UV) run --locked mypy app healthcheck.py

typecheck-web: ## tsc for web + mobile (via Turborepo)
	$(PNPM) turbo run typecheck

fmt: ## Format everything (ruff format + Prettier)
	cd $(API_DIR) && $(UV) run --locked ruff format .
	$(PNPM) format

fmt-check: ## Check formatting without changing files (what CI runs)
	cd $(API_DIR) && $(UV) run --locked ruff format --check .
	$(PNPM) format:check

mobile: ## Start the Expo dev server for apps/mobile
	$(PNPM) --filter mobile start

build-web: ## Production build of the web app (via Turborepo)
	$(PNPM) turbo run build
