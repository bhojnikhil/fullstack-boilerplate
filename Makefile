.PHONY: help up down logs build migrate migration db-shell test clean fresh

# Color output
CYAN := \033[0;36m
GREEN := \033[0;32m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(CYAN)Full-Stack Boilerplate$(NC)"
	@echo ""
	@echo "$(GREEN)Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Docker Commands:$(NC)"
	@echo "  $(CYAN)make up$(NC)              Start all services (API, DB, Frontend)"
	@echo "  $(CYAN)make down$(NC)            Stop all services"
	@echo "  $(CYAN)make logs$(NC)            View service logs (follow mode)"
	@echo "  $(CYAN)make build$(NC)           Rebuild all containers"
	@echo "  $(CYAN)make fresh$(NC)           Complete reset (clean + rebuild + migrate)"
	@echo ""
	@echo "$(GREEN)Database Commands:$(NC)"
	@echo "  $(CYAN)make migrate$(NC)         Run pending migrations"
	@echo "  $(CYAN)make migration NAME=...$(NC) Create new migration"
	@echo "  $(CYAN)make db-shell$(NC)        Connect to PostgreSQL shell"
	@echo ""
	@echo "$(GREEN)Development Commands:$(NC)"
	@echo "  $(CYAN)make test$(NC)            Run backend tests"
	@echo "  $(CYAN)make test-frontend$(NC)   Run frontend tests"
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  $(CYAN)make migration NAME='add_column'$(NC)"
	@echo "  $(CYAN)make test$(NC)"
	@echo "  $(CYAN)make fresh$(NC)"

# ======================== Docker Commands ========================

up: ## Start all services
	cd infra && docker-compose --profile dev up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "  Frontend: http://localhost:3000"
	@echo "  API: http://localhost:8000"
	@echo "  API Docs: http://localhost:8000/docs"

down: ## Stop all services
	cd infra && docker-compose --profile dev down
	@echo "$(GREEN)✓ Services stopped$(NC)"

logs: ## View all service logs (follow)
	cd infra && docker-compose --profile dev logs -f

build: ## Rebuild all containers
	cd infra && docker-compose --profile dev build
	@echo "$(GREEN)✓ Containers rebuilt$(NC)"

# ======================== Database Commands ========================

migrate: ## Run pending migrations
	cd infra && docker-compose exec api-dev alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(NC)"

migration: ## Create a new migration (use: make migration NAME='description')
	@if [ -z "$(NAME)" ]; then \
		echo "Error: NAME is required"; \
		echo "Usage: make migration NAME='your_migration_name'"; \
		exit 1; \
	fi
	cd infra && docker-compose exec api-dev alembic revision --autogenerate -m "$(NAME)"
	@echo "$(GREEN)✓ Migration created$(NC)"

db-shell: ## Connect to PostgreSQL shell
	cd infra && docker-compose exec db psql -U postgres -d {{PROJECT_NAME}}

# ======================== Development Commands ========================

test: ## Run backend tests
	cd infra && docker-compose exec api-dev pytest
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-coverage: ## Run backend tests with coverage report
	cd infra && docker-compose exec api-dev pytest --cov=app
	@echo "$(GREEN)✓ Coverage report generated$(NC)"

test-frontend: ## Run frontend tests
	cd client && npm test

lint-backend: ## Run backend linting
	cd infra && docker-compose exec api-dev ruff check app
	@echo "$(GREEN)✓ Backend linting complete$(NC)"

lint-frontend: ## Run frontend linting
	cd client && npm run lint

format-backend: ## Format backend code
	cd infra && docker-compose exec api-dev ruff format app
	@echo "$(GREEN)✓ Backend code formatted$(NC)"

format-frontend: ## Format frontend code
	cd client && npm run format

# ======================== Full Reset ========================

fresh: down build migrate up ## Complete reset (stop, rebuild, migrate, start)
	@echo ""
	@echo "$(GREEN)✓ Fresh start complete!$(NC)"
	@echo "  Frontend: http://localhost:3000"
	@echo "  API: http://localhost:8000"
	@echo "  Docs: http://localhost:8000/docs"

.SILENT: help logs
