.DEFAULT_GOAL := help

# All Docker targets use the root docker-compose.yml
# (services: postgres, api, client).
COMPOSE ?= docker compose

CYAN := \033[0;36m
GREEN := \033[0;32m
NC := \033[0m

.PHONY: help up down logs ps build fresh migrate migration db-shell \
	test test-coverage lint lint-backend lint-frontend \
	typecheck typecheck-backend typecheck-frontend \
	format format-backend format-frontend

help: ## Show this help message
	@printf "$(GREEN)Available commands:$(NC)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'

# ============================== Docker ======================================

up: ## Start postgres, api and client in the background
	$(COMPOSE) up -d
	@printf "$(GREEN)✓ Services started$(NC)\n"
	@echo "  Frontend: http://localhost:3000"
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

fresh: ## Full reset: stop, delete the database volume, rebuild, start, migrate
	$(COMPOSE) down -v
	$(COMPOSE) build
	$(COMPOSE) up -d --wait postgres api
	$(COMPOSE) up -d
	$(COMPOSE) exec api alembic upgrade head
	@printf "$(GREEN)✓ Fresh start complete$(NC)\n"

# ============================== Database ====================================

migrate: ## Apply pending Alembic migrations (requires `make up`)
	$(COMPOSE) exec api alembic upgrade head

migration: ## Create an Alembic migration: make migration NAME='add_column'
	@if [ -z "$(NAME)" ]; then \
		echo "Usage: make migration NAME='your_migration_name'"; \
		exit 1; \
	fi
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(NAME)"

db-shell: ## Open a psql shell on the dev database
	$(COMPOSE) exec postgres psql -U postgres -d boilerplate

# ============================== Quality =====================================

test: ## Run backend tests (inside the api container)
	$(COMPOSE) exec api pytest

test-coverage: ## Run backend tests with an HTML coverage report (api/htmlcov)
	$(COMPOSE) exec api pytest --cov=app --cov-report=term-missing --cov-report=html

lint: lint-backend lint-frontend ## Lint backend and frontend

lint-backend: ## Ruff lint (inside the api container)
	$(COMPOSE) exec api ruff check .

lint-frontend: ## ESLint via `next lint` (on the host; needs `npm ci` in client/)
	cd client && npm run lint

typecheck: typecheck-backend typecheck-frontend ## Type-check backend and frontend

typecheck-backend: ## mypy (inside the api container)
	$(COMPOSE) exec api mypy app

typecheck-frontend: ## tsc --noEmit (on the host; needs `npm ci` in client/)
	cd client && npm run type-check

format: format-backend format-frontend ## Format backend and frontend code

format-backend: ## Ruff format (inside the api container)
	$(COMPOSE) exec api ruff format .

format-frontend: ## Prettier (on the host; needs `npm ci` in client/)
	cd client && npm run format
