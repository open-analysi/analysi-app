# Makefile for the Analysi UI subproject
# Provides convenient targets for running tests and common development tasks.
# The full Docker stack (backend + UI) is orchestrated from the repo-root
# Makefile — run `make up` in the parent directory.

# Color output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help test test-unit test-watch test-coverage test-integration test-api test-all \
        test-e2e test-e2e-ui test-e2e-headed test-e2e-debug \
        clean install dev build lint format check docker-build \
        docker-run docker-stop docker-test docker-clean docker-shell docker-inspect

# Default target
help:
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)        Analysi UI — Make Targets$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(GREEN)Testing Targets:$(NC)"
	@echo "  test              Run unit tests once"
	@echo "  test-unit         Run unit tests once (alias for test)"
	@echo "  test-watch        Run unit tests in watch mode"
	@echo "  test-coverage     Run tests with coverage report"
	@echo "  test-integration  Run API integration tests"
	@echo "  test-api          Run API integration tests (alias)"
	@echo "  test-e2e          Run E2E tests (headless)"
	@echo "  test-e2e-ui       Run E2E tests with Playwright UI"
	@echo "  test-e2e-headed   Run E2E tests in headed mode"
	@echo "  test-e2e-debug    Run E2E tests in debug mode"
	@echo "  test-all          Run all tests (unit + integration + e2e)"
	@echo ""
	@echo "$(GREEN)Development Targets:$(NC)"
	@echo "  install           Install dependencies"
	@echo "  dev               Start development server"
	@echo "  build             Build for production"
	@echo "  preview           Preview production build"
	@echo ""
	@echo "$(GREEN)Code Quality Targets:$(NC)"
	@echo "  lint              Run ESLint"
	@echo "  lint-fix          Run ESLint with auto-fix"
	@echo "  format            Format code with Prettier"
	@echo "  typecheck         Run TypeScript type checking"
	@echo "  check             Run lint, format, and tests"
	@echo ""
	@echo "$(GREEN)Full Stack:$(NC)"
	@echo "  Run 'make up' from the repo root to start backend + UI together."
	@echo ""
	@echo "$(GREEN)Docker Targets (UI Production):$(NC)"
	@echo "  docker-build      Build production Docker image"
	@echo "  docker-run        Run production container"
	@echo "  docker-stop       Stop and remove production container"
	@echo "  docker-test       Build and test production container locally"
	@echo "  docker-clean      Remove Docker images and containers"
	@echo ""
	@echo "$(GREEN)Utility Targets:$(NC)"
	@echo "  clean             Clean build artifacts"
	@echo "  clean-all         Deep clean including node_modules"
	@echo "  status            Show project status"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC) make [target]"
	@echo "$(YELLOW)Example:$(NC) make test-coverage"

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Testing Targets
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

test: test-unit ## Run unit tests once

test-unit: ## Run unit tests once
	@echo "$(BLUE)🧪 Running unit tests...$(NC)"
	@npm run test:once

unit-tests: test-unit ## Alias for test-unit (legacy)

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)👀 Starting test watcher...$(NC)"
	@npm run test

test-coverage: ## Run tests with coverage report
	@echo "$(BLUE)📊 Running tests with coverage...$(NC)"
	@npm run test:coverage
	@echo "$(GREEN)✅ Coverage report generated in ./coverage$(NC)"

test-integration: ## Run API integration tests
	@echo "$(BLUE)🔌 Running API integration tests...$(NC)"
	@chmod +x scripts/run_integration_tests.sh 2>/dev/null || true
	@./scripts/run_integration_tests.sh

test-api: test-integration ## Alias for test-integration
api-tests: test-integration ## Alias for test-integration (legacy)

test-e2e: ## Run E2E tests (headless)
	@echo "$(BLUE)🎭 Running E2E tests (headless)...$(NC)"
	@npx playwright test

test-e2e-ui: ## Run E2E tests with Playwright UI
	@echo "$(BLUE)🎭 Running E2E tests with UI...$(NC)"
	@npx playwright test --ui

test-e2e-headed: ## Run E2E tests in headed mode (see browser)
	@echo "$(BLUE)🎭 Running E2E tests in headed mode...$(NC)"
	@npx playwright test --headed

test-e2e-debug: ## Run E2E tests in debug mode
	@echo "$(BLUE)🎭 Running E2E tests in debug mode...$(NC)"
	@npx playwright test --debug

e2e: test-e2e ## Shortcut for test-e2e

test-all: ## Run all tests (unit + integration + e2e)
	@echo "$(BLUE)🎯 Running all tests...$(NC)"
	@$(MAKE) test-unit
	@$(MAKE) test-integration
	@$(MAKE) test-e2e
	@echo "$(GREEN)✅ All tests completed!$(NC)"

all-tests: test-all ## Alias for test-all (legacy)

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Development Targets
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

install: ## Install dependencies
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	@npm install
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

dev: ## Start development server
	@echo "$(BLUE)🚀 Starting development server...$(NC)"
	@npm run dev

build: ## Build for production
	@echo "$(BLUE)🏗️  Building for production...$(NC)"
	@npm run build
	@echo "$(GREEN)✅ Build completed in ./dist$(NC)"

preview: ## Preview production build
	@echo "$(BLUE)👁️  Starting preview server...$(NC)"
	@npm run preview

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Code Quality Targets
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

lint: ## Run ESLint
	@echo "$(BLUE)🔍 Running ESLint...$(NC)"
	@npm run lint

lint-fix: ## Run ESLint with auto-fix
	@echo "$(BLUE)🔧 Running ESLint with auto-fix...$(NC)"
	@npm run lint:fix

format: ## Format code with Prettier
	@echo "$(BLUE)✨ Formatting code...$(NC)"
	@npm run format

typecheck: ## Run TypeScript type checking
	@echo "$(BLUE)📝 Running TypeScript type check...$(NC)"
	@npx tsc --noEmit

check: ## Run all checks (lint, format, tests)
	@echo "$(BLUE)🔎 Running all checks...$(NC)"
	@npm run check
	@echo "$(GREEN)✅ All checks passed$(NC)"

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Docker Targets - UI Production Build
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# NOTE: Do not use "analysi-ui:latest" here — that is the name compose
# builds for the dev stage (see deployments/compose/core.yml). Colliding
# tags cause compose to reuse our prod build and serve nginx on :8080
# instead of Vite on :5173.
DOCKER_IMAGE := analysi-ui-prod
DOCKER_TAG := latest
DOCKER_CONTAINER := analysi-ui-prod
# Host port for the standalone prod container. 5180 avoids collisions with:
#   5173 — Vite dev (compose) + Playwright "auth" project
#   5174 — Playwright "chromium" e2e server (see playwright.config.ts)
#   8001 — backend API
#   8080 — Keycloak
#   9000/9001 — MinIO
DOCKER_PORT := 5180

docker-build: ## Build production Docker image
	@echo "$(BLUE)🏗️  Building production Docker image...$(NC)"
	@docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) --target production -f ../deployments/docker/ui/Dockerfile .
	@echo "$(GREEN)✅ Docker image built: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"
	@docker images | grep $(DOCKER_IMAGE) | head -1

docker-run: ## Run production container
	@echo "$(BLUE)🚀 Starting production container...$(NC)"
	@docker stop $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker rm $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run -d \
		--name $(DOCKER_CONTAINER) \
		-p $(DOCKER_PORT):8080 \
		$(DOCKER_IMAGE):$(DOCKER_TAG)
	@echo "$(GREEN)✅ Container started: $(DOCKER_CONTAINER)$(NC)"
	@echo "$(YELLOW)   Access at: http://localhost:$(DOCKER_PORT)$(NC)"
	@sleep 2
	@docker ps | grep $(DOCKER_CONTAINER)

docker-stop: ## Stop and remove production container
	@echo "$(BLUE)🛑 Stopping production container...$(NC)"
	@docker stop $(DOCKER_CONTAINER) 2>/dev/null || echo "$(YELLOW)Container not running$(NC)"
	@docker rm $(DOCKER_CONTAINER) 2>/dev/null || echo "$(YELLOW)Container not found$(NC)"
	@echo "$(GREEN)✅ Container stopped and removed$(NC)"

docker-test: ## Build and test production container locally
	@echo "$(BLUE)🧪 Building and testing production container...$(NC)"
	@$(MAKE) docker-build
	@$(MAKE) docker-run
	@echo ""
	@echo "$(BLUE)⏳ Waiting for container to be healthy...$(NC)"
	@sleep 3
	@echo ""
	@echo "$(BLUE)🔍 Testing root endpoint...$(NC)"
	@curl -fsS http://localhost:$(DOCKER_PORT)/ > /dev/null && \
		echo "$(GREEN)✅ UI served successfully$(NC)" || \
		(echo "$(RED)❌ UI did not respond$(NC)" && exit 1)
	@echo ""
	@echo "$(BLUE)📊 Container stats:$(NC)"
	@docker stats --no-stream $(DOCKER_CONTAINER)
	@echo ""
	@echo "$(GREEN)✅ Production container is running successfully!$(NC)"
	@echo "$(YELLOW)   View in browser: http://localhost:$(DOCKER_PORT)$(NC)"
	@echo "$(YELLOW)   Stop with: make docker-stop$(NC)"

docker-clean: ## Remove Docker images and containers
	@echo "$(YELLOW)🧹 Cleaning Docker resources...$(NC)"
	@docker stop $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker rm $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) 2>/dev/null || true
	@echo "$(GREEN)✅ Docker resources cleaned$(NC)"

docker-shell: ## Open shell in running production container
	@echo "$(BLUE)🐚 Opening shell in container...$(NC)"
	@docker exec -it $(DOCKER_CONTAINER) /bin/sh

docker-inspect: ## Inspect production container
	@echo "$(BLUE)🔍 Container inspection:$(NC)"
	@echo ""
	@echo "$(YELLOW)Image:$(NC)"
	@docker images | grep $(DOCKER_IMAGE)
	@echo ""
	@echo "$(YELLOW)Container:$(NC)"
	@docker ps -a | grep $(DOCKER_CONTAINER) || echo "  Container not found"
	@echo ""
	@echo "$(YELLOW)Size:$(NC)"
	@docker images $(DOCKER_IMAGE):$(DOCKER_TAG) --format "  {{.Repository}}:{{.Tag}} - {{.Size}}"
	@echo ""
	@echo "$(YELLOW)Logs (last 20 lines):$(NC)"
	@docker logs --tail 20 $(DOCKER_CONTAINER) 2>/dev/null || echo "  Container not running"

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Utility Targets
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

clean: ## Clean build artifacts
	@echo "$(YELLOW)🧹 Cleaning build artifacts...$(NC)"
	@rm -rf dist coverage .vitest-cache node_modules/.vite
	@echo "$(GREEN)✅ Cleaned: dist, coverage, and cache folders$(NC)"

clean-all: clean ## Deep clean including node_modules
	@echo "$(YELLOW)🧹 Removing node_modules...$(NC)"
	@rm -rf node_modules
	@echo "$(GREEN)✅ Deep clean complete$(NC)"
	@echo "$(YELLOW)   Run 'make install' to reinstall dependencies$(NC)"

status: ## Show project status
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)                  Project Status$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(YELLOW)Node:$(NC) $$(node -v)"
	@echo "$(YELLOW)NPM:$(NC) $$(npm -v)"
	@echo "$(YELLOW)Branch:$(NC) $$(git branch --show-current)"
	@echo ""
	@echo "$(YELLOW)Git Status:$(NC)"
	@git status --short || echo "  Clean working directory"
	@echo ""
	@echo "$(YELLOW)Recent Commits:$(NC)"
	@git log --oneline -3
	@echo ""
	@echo "$(YELLOW)Docker Services:$(NC)"
	@docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | head -5 || echo "  Docker not running"

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## Quick Shortcuts
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

t: test-unit       ## Shortcut for test-unit
tw: test-watch     ## Shortcut for test-watch
tc: test-coverage  ## Shortcut for test-coverage
ti: test-integration ## Shortcut for test-integration
te: test-e2e       ## Shortcut for test-e2e
teu: test-e2e-ui   ## Shortcut for test-e2e-ui
l: lint-fix        ## Shortcut for lint-fix
f: format          ## Shortcut for format
c: check           ## Shortcut for check
d: dev             ## Shortcut for dev
b: build           ## Shortcut for build
db: docker-build   ## Shortcut for docker-build
dr: docker-run     ## Shortcut for docker-run
ds: docker-stop    ## Shortcut for docker-stop
dt: docker-test    ## Shortcut for docker-test