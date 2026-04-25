# ──── Configuration ──────────────────────────────────────────────────────────
#
# 3-layer compose model: core (L1) + deps (L2) + observability (L3)
# Lab services (Splunk, LDAP, Echo EDR, Elastic) moved to analysi-demo-loader/lab/
# --env-file needed because compose looks for .env relative to the compose file.

# Worktree support: detect main project root via git, auto-symlink .env.
# Project name is fixed to "analysi" via deps.yml `name:` field.
# To run an isolated stack from a worktree, override: COMPOSE_PROJECT_NAME=mystack make up
MAIN_PROJECT_ROOT := $(shell dirname $$(git rev-parse --git-common-dir 2>/dev/null))
IS_WORKTREE       := $(shell [ "$$(git rev-parse --git-dir)" != "$$(git rev-parse --git-common-dir)" ] 2>/dev/null && echo 1)

DC      = docker compose --env-file .env -f deployments/compose/core.yml -f deployments/compose/deps.yml
DC_OBS  = $(DC) -f deployments/compose/observability.yml
DC_EC2  = $(DC) -f deployments/compose/ec2.yml

# Configurable flags for `make up`
OBSERVABILITY ?=
DC_UP = $(DC)$(if $(OBSERVABILITY), -f deployments/compose/observability.yml)

# Parameterized service target
SERVICE ?=
TENANT  ?= default


# ──── Help (default target) ──────────────────────────────────────────────────

.DEFAULT_GOAL := help

help:
	@echo "Analysi — Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make up                          Start core services (product + deps + UI)"
	@echo "  make up OBSERVABILITY=1          Include observability layer (Grafana, Prometheus)"
	@echo "  make up-full                     Start all services (core + deps + observability)"
	@echo "  make down                        Stop all services"
	@echo "  make ps                          Show container status"
	@echo "  make logs [SERVICE=api]          Tail logs (all services, or one)"
	@echo "  make restart SERVICE=api         Restart a service"
	@echo "  make rebuild [SERVICE=api]       Rebuild (one service, or all)"
	@echo "  make shell SERVICE=api           Open shell in a service container"
	@echo "  make clean                       Stop and remove all containers + volumes"
	@echo "  make dev                         Quick dev cycle (rebuild integrations + logs)"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate                  Run Flyway migrations (main)"
	@echo "  make db-migrate-test             Run Flyway migrations (test)"
	@echo "  make db-migrate-all              Run both"
	@echo "  make db-repair                   Repair Flyway schema history"
	@echo "  make init-vault                  Initialize Vault transit engines"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test-db-up                  Start isolated test DB for this branch"
	@echo "  make test-db-down                Stop and remove branch test DB"
	@echo "  make test-db-down-all            Stop and remove ALL test DB containers"
	@echo "  make test-db-status              Show running test DB containers"
	@echo "  make test-integration-db         Run DB-only integration tests (no Vault/Valkey/MinIO)"
	@echo "  make test-integration-full       Run ALL integration tests (requires full stack)"
	@echo "  make test-unit                   Run unit tests"
	@echo "  make verify                      Verify all running services are healthy"
	@echo "  make smoke-test                  Run functional smoke test (requires running services)"
	@echo "  make code-quality                Run all code quality checks"
	@echo "  make code-quality-ci             Code quality checks (CI mode, fails on issues)"
	@echo "  make benchmark-api               Benchmark API response times"
	@echo "  make test-eval                   Run all eval tests (~$$12, ~40min)"
	@echo "  make test-eval-quick             Run core eval tests only (~$$3, ~10min)"
	@echo "  make security-scan               Run bandit SAST scanner"
	@echo "  make audit-deps                  Audit Python dependencies for CVEs"
	@echo "  make count-lines                 Count lines of code"
	@echo ""
	@echo "Packaging:"
	@echo "  make package-agents              Package prod agents from skilltree"
	@echo "  make package-skills              Package prod skills from skilltree"
	@echo "  make generate-types              Generate TypeScript types from OpenAPI spec"
	@echo ""
	@echo "CLI:"
	@echo "  make cli-install                 Install CLI dependencies"
	@echo "  make cli-build                   Build the CLI"
	@echo "  make cli-generate                Generate CLI commands from cli-config.yaml"
	@echo "  make cli-test                    Run CLI unit tests"
	@echo "  make cli CMD='alerts list'       Run the CLI"
	@echo ""
	@echo "Integration Tools:"
	@echo "  make flush-tenant-queue [TENANT=default]  Flush Valkey queue for a tenant"
	@echo "  make validate-manifest MANIFEST=<path>    Validate manifest.json"
	@echo ""
	@echo "Schedule Health (Project Symi):"
	@echo "  make schedule-health             Show schedule status and detect problems"
	@echo ""
	@echo "Partition Management (pg_partman):"
	@echo "  make list-partitions             List partition counts per table"
	@echo "  make validate-partitions         Validate partition counts within limits"
	@echo "  make partition-health            Check for data in default partitions / gaps"
	@echo "  make partition-maintenance       Trigger pg_partman maintenance on demand"
	@echo "  make emergency-cleanup           Emergency: drop ALL partitions"
	@echo ""
	@echo "Monitoring:"
	@echo "  make start-monitoring            Start observability stack"
	@echo "  make stop-monitoring             Stop observability stack"
	@echo "  make monitoring-status           Show monitoring stack status"
	@echo ""
	@echo "Kubernetes (local):"
	@echo "  make k8s-preflight               Validate images work on this arch"
	@echo "  make k8s-up                      Full setup: cluster + build + deploy (cold start / dep bump)"
	@echo "  make k8s-build                   Rebuild images and load into kind (after app code changes)"
	@echo "  make k8s-deploy                  Helm install/upgrade only (after chart or Flyway SQL changes)"
	@echo "  make k8s-down                    Delete kind cluster"
	@echo "  make k8s-status                  Show pod/service status"
	@echo "  make k8s-logs [SERVICE=api]      Tail pod logs"
	@echo "  make k8s-verify                  Verify all pods healthy + API reachable"
	@echo "  make k8s-smoke-test              Full functional smoke test against K8s"
	@echo ""
	@echo "  Inner-loop guide — what to run after which change:"
	@echo "    Helm chart / values / flyway SQL     →  make k8s-deploy       (fast, ~20s)"
	@echo "    Python or TypeScript app code        →  make k8s-build && make k8s-deploy"
	@echo "    Dependency image bump (postgres, …)  →  make k8s-up           (re-loads deps)"
	@echo "    First run / new worktree             →  make k8s-up"
	@echo ""
	@echo "EC2 Demo:"
	@echo "  make ec2-help                    Show all EC2 deployment commands"
	@echo ""
	@echo "Docker Maintenance:"
	@echo "  make fix-docker-disk-space       Clean Docker cache/volumes/images"
	@echo "  make docker-disk-usage           Show Docker disk usage"


# ──── Development ────────────────────────────────────────────────────────────

# Ensure .env exists. In a worktree, bootstrap from .env.nightly (safe CI defaults)
# rather than symlinking the main checkout's .env (which may contain real API keys).
_ensure-env:
	@if [ ! -f .env ]; then \
		if [ -f .env.nightly ]; then \
			cp .env.nightly .env; \
			echo "Created .env from .env.nightly (safe defaults, no real secrets)."; \
			echo "Add API keys to .env as needed — it is gitignored."; \
		else \
			echo "ERROR: No .env file. Copy .env.example to .env and fill in values."; \
			exit 1; \
		fi; \
	fi

# Block compose commands in worktrees — agents must use Kind (k8s-* targets)
_require-main-checkout:
	@if [ -n "$(IS_WORKTREE)" ]; then \
		echo ""; \
		echo "ERROR: Docker Compose is not available in worktrees."; \
		echo ""; \
		echo "Worktrees must use Kind/Kubernetes instead:"; \
		echo "  make k8s-up       Full setup (cluster + build + deploy)"; \
		echo "  make k8s-down     Delete cluster"; \
		echo "  make k8s-build    Rebuild images"; \
		echo "  make k8s-deploy   Helm upgrade only"; \
		echo "  make k8s-status   Show pod status"; \
		echo "  make k8s-logs     Tail logs"; \
		echo "  make k8s-verify   Health check"; \
		echo ""; \
		exit 1; \
	fi

up: _require-main-checkout _ensure-env
	$(DC_UP) up -d --remove-orphans
	@echo ""
	@echo "Services started! (project: analysi)"
	@. ./.env 2>/dev/null; \
	 echo "   API: http://localhost:$${BACKEND_API_EXTERNAL_PORT:-8001}/    UI: http://localhost:$${UI_EXTERNAL_PORT:-5173}/"

up-full: _require-main-checkout
	$(DC_OBS) up -d --remove-orphans
	@echo ""
	@echo "Full stack started! (project: analysi)"
	@. ./.env 2>/dev/null; \
	 echo "   API: http://localhost:$${BACKEND_API_EXTERNAL_PORT:-8001}/    UI: http://localhost:$${UI_EXTERNAL_PORT:-5173}/"
	@echo ""
	@echo "Lab services (Splunk, LDAP, Echo EDR, Elastic) are managed by analysi-demo-loader."
	@echo "   cd ../analysi-demo-loader && make lab-up"

down: _require-main-checkout
	@$(DC_EC2) down 2>/dev/null || true
	$(DC_OBS) down --remove-orphans

ps: _require-main-checkout
	@bash scripts/observability/container_status.sh

logs: _require-main-checkout
ifdef SERVICE
	$(DC_OBS) logs --tail 100 -f $(SERVICE)
else
	$(DC_OBS) logs --tail 100 -f
endif

restart: _require-main-checkout
	@if [ -z "$(SERVICE)" ]; then echo "Usage: make restart SERVICE=<name>"; echo "Services: api, alerts-worker, integrations-worker, notifications-worker, keycloak, vault, ui, postgres, valkey, minio"; exit 1; fi
	$(DC_OBS) restart $(SERVICE)

rebuild: _require-main-checkout
ifdef SERVICE
	$(DC_OBS) up -d --build --no-deps $(SERVICE)
else
	$(DC_OBS) up -d --build
endif

shell: _require-main-checkout
	@if [ -z "$(SERVICE)" ]; then echo "Usage: make shell SERVICE=<name>"; echo "Services: api, alerts-worker, integrations-worker, notifications-worker"; exit 1; fi
	$(DC_OBS) exec $(SERVICE) /bin/bash

clean: _require-main-checkout
	@echo "This will stop ALL containers and DELETE ALL volumes (databases, caches, etc.)."
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" != "yes" ]; then \
		echo "Aborted."; \
		exit 1; \
	fi
	$(DC_OBS) down -v --remove-orphans

dev: rebuild-integrations logs-integrations


# ──── Database ───────────────────────────────────────────────────────────────

db-migrate: _require-main-checkout
	@echo "Running Flyway migrations (main)..."
	$(DC) run --rm flyway
	@echo "Done."

db-migrate-test: _require-main-checkout
	@echo "Running Flyway migrations (test)..."
	$(DC) run --rm flyway-test
	@echo "Done."

db-migrate-all: _require-main-checkout db-migrate db-migrate-test

db-repair: _require-main-checkout
	@echo "Repairing Flyway schema history..."
	$(DC) run --rm --entrypoint="" flyway sh -c "flyway -url=jdbc:postgresql://\$${POSTGRES_HOST}:\$${POSTGRES_PORT}/\$${POSTGRES_DB} -user=\$${POSTGRES_USER} -password=\$${POSTGRES_PASSWORD} repair"
	$(DC) run --rm --entrypoint="" flyway-test sh -c "flyway -url=jdbc:postgresql://\$${POSTGRES_HOST}:\$${POSTGRES_PORT}/analysi_test -user=\$${POSTGRES_USER} -password=\$${POSTGRES_PASSWORD} repair"
	@echo "Done."

init-vault: _require-main-checkout
	@echo "Initializing Vault transit engines and encryption keys..."
	$(DC) exec vault sh /vault/scripts/init-vault.sh
	@echo "Done."


# ──── Testing & Quality ──────────────────────────────────────────────────────

test-unit:
	poetry run pytest tests/unit/ -q

test-db-clean:
	@echo "Dropping all ephemeral test databases (analysi_test_*)..."
	@PGPASSWORD=$${TEST_DB_PASSWORD:-devpassword} psql \
		-h $${TEST_DB_HOST:-localhost} \
		-p $${TEST_DB_PORT:-5434} \
		-U $${TEST_DB_USER:-dev} \
		-d postgres \
		-t -A -c "SELECT datname FROM pg_database WHERE datname LIKE 'analysi_test_%'" \
		| while read -r db; do \
			echo "  Dropping $$db..."; \
			PGPASSWORD=$${TEST_DB_PASSWORD:-devpassword} psql \
				-h $${TEST_DB_HOST:-localhost} \
				-p $${TEST_DB_PORT:-5434} \
				-U $${TEST_DB_USER:-dev} \
				-d postgres \
				-c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$$db' AND pid != pg_backend_pid();" \
				-c "DROP DATABASE IF EXISTS \"$$db\";" > /dev/null 2>&1; \
		done
	@echo "Done."

# ──── Branch-Isolated Test Database ──────────────────────────────────────────

test-db-up:
	@bash scripts/make/test-db.sh up

test-db-down:
	@bash scripts/make/test-db.sh down

test-db-down-all:
	@bash scripts/make/test-db.sh down-all

test-db-status:
	@bash scripts/make/test-db.sh status

verify:
	@bash scripts/smoke_tests/verify.sh


test-integration-db:
	@echo "Running DB-only integration tests (excludes Vault/Valkey/MinIO/external API tests)..."
	poetry run pytest tests/integration/ -m "integration and not requires_full_stack and not requires_api" -q --tb=short

test-integration-full:
	@echo "Running ALL integration tests (requires full stack: Vault, Valkey, MinIO)..."
	poetry run pytest tests/integration/ -m "integration" -q --tb=short

test-eval:
	@echo "Running all eval tests (requires ANTHROPIC_API_KEY, ~$$12, ~40min)..."
	poetry run pytest tests/eval/ -v -m eval

test-eval-quick:
	@echo "Running core eval tests (requires ANTHROPIC_API_KEY, ~$$3, ~10min)..."
	poetry run pytest tests/eval/test_00_sdk_sanity.py tests/eval/test_first_subgraph.py tests/eval/test_phase1_db_skills.py -v -m eval

smoke-test:
	@echo "Running functional smoke test..."
	poetry run python scripts/smoke_tests/functional_test.py

code-quality: audit-test-hygiene detect-flakiness detect-bare-httpx lint-logging check-partition-sync
	@echo "All code quality checks passed."

code-quality-ci:
	@echo "Running code quality checks (CI mode)..."
	poetry run python scripts/code_quality_tools/test_hygiene_audit.py --fail-on-high
	poetry run python scripts/code_quality_tools/test_flakiness_detector.py --fail-on-critical
	poetry run python scripts/code_quality_tools/detect_bare_httpx.py --fail-on-issues
	poetry run python scripts/code_quality_tools/check_partition_table_sync.py --fail-on-issues
	@echo "CI code quality checks passed."

audit-test-hygiene:
	poetry run python scripts/code_quality_tools/test_hygiene_audit.py

detect-flakiness:
	poetry run python scripts/code_quality_tools/test_flakiness_detector.py

detect-bare-httpx:
	poetry run python scripts/code_quality_tools/detect_bare_httpx.py

lint-logging:
	poetry run python scripts/code_quality_tools/detect_stdlib_logging.py

check-partition-sync:
	poetry run python scripts/code_quality_tools/check_partition_table_sync.py

count-lines:
	poetry run python scripts/code_quality_tools/count_lines_of_code.py

benchmark-api:
	python scripts/code_quality_tools/api_benchmark.py --rounds 10

benchmark-api-ci:
	python scripts/code_quality_tools/api_benchmark.py --rounds 15 --ci

security-scan:
	poetry run bandit -r src/analysi/ -ll --exclude src/analysi/tests

audit-deps:
	@IGNORE_ARGS=""; \
	if [ -f .pip-audit-ignore.txt ]; then \
		while IFS= read -r cve; do \
			case "$$cve" in \#*|"") continue ;; esac; \
			IGNORE_ARGS="$$IGNORE_ARGS --ignore-vuln $$cve"; \
		done < .pip-audit-ignore.txt; \
	fi; \
	poetry run pip-audit $$IGNORE_ARGS


# ──── Chat Skills Generation ─────────────────────────────────────────────────

generate-chat-skills: generate-api-skill generate-integrations-skill generate-cli-skill  ## Regenerate all auto-generated chat skills
	@echo "All chat skills regenerated."

generate-api-skill:  ## Regenerate api.md from OpenAPI schema
	@poetry run python scripts/generate_chat_skills/generate_api_skill.py

generate-integrations-skill:  ## Regenerate integrations.md from manifest files
	@poetry run python scripts/generate_chat_skills/generate_integrations_skill.py

generate-cli-skill:  ## Regenerate cli.md from CLI config
	@poetry run python scripts/generate_chat_skills/generate_cli_skill.py

check-chat-skills-freshness:  ## CI: fail if auto-generated skills are stale
	@echo "Checking chat skill freshness..."
	@poetry run python scripts/generate_chat_skills/generate_api_skill.py
	@poetry run python scripts/generate_chat_skills/generate_integrations_skill.py
	@poetry run python scripts/generate_chat_skills/generate_cli_skill.py
	@if git diff --quiet src/analysi/chat/skills/api.md src/analysi/chat/skills/integrations.md src/analysi/chat/skills/cli.md; then \
		echo "✅ All auto-generated chat skills are up to date."; \
	else \
		echo "❌ Auto-generated chat skills are stale. Run 'make generate-chat-skills' and commit."; \
		git diff --stat src/analysi/chat/skills/api.md src/analysi/chat/skills/integrations.md src/analysi/chat/skills/cli.md; \
		exit 1; \
	fi

# ──── Packaging ──────────────────────────────────────────────────────────────

package-agents:
	@python scripts/agents_management/package.py agents

package-skills:
	@python scripts/agents_management/package.py skills

check-skills:
	@python scripts/agents_management/package.py skills --check

# Legacy aliases
package-external-agents: package-agents
package-foundation-skills: package-skills
check-foundation-skills: check-skills

generate-types:
	bash scripts/make/generate_openapi_types.sh

# ──── CLI ─────────────────────────────────────────────────────────────────────

cli-install:
	cd cli && npm install && npm link

cli-build:
	cd cli && npx tsc -b

cli-generate:
	cd cli && npx tsx ./scripts/generate-commands.ts

cli-dev:
	cd cli && node ./bin/dev.js $(CMD)

cli-test: ## Run CLI unit tests
	cd cli && npx vitest run

cli: cli-build ## Run the Analysi CLI (use CMD="alerts list" etc.)
	cd cli && node ./bin/analysi $(CMD)

check-cli-api-sync: ## Verify CLI commands match actual API routes
	poetry run python scripts/code_quality_tools/check_cli_api_sync.py

# ──── Integration Tools ──────────────────────────────────────────────────────

flush-tenant-queue:
	@bash scripts/make/flush-tenant-queue.sh $(TENANT)

# MinIO commands
minio-start: _require-main-checkout
	$(DC) up -d minio minio-init
	@. ./.env 2>/dev/null; \
	 echo "MinIO started: API http://localhost:$${MINIO_EXTERNAL_PORT:-9000}  Console http://localhost:$${MINIO_CONSOLE_EXTERNAL_PORT:-9001}"

minio-restart: _require-main-checkout
	$(DC) restart minio

minio-logs: _require-main-checkout
	$(DC) logs -f minio

minio-rebuild: _require-main-checkout
	$(DC) up -d --build --no-deps minio minio-init

minio-status: _require-main-checkout
	@$(DC) ps minio minio-init

# Integration framework validation
validate-manifest:
	@if [ -z "$(MANIFEST)" ]; then echo "Usage: make validate-manifest MANIFEST=<path>"; exit 1; fi
	poetry run validate-manifest $(MANIFEST)

validate-integration:
	@if [ -z "$(INTEGRATION)" ]; then echo "Usage: make validate-integration INTEGRATION=<path>"; exit 1; fi
	poetry run validate-integration $(INTEGRATION)


# ──── Partition Management (pg_partman) ──────────────────────────────────────

schedule-health:
	poetry run python scripts/database/schedule_health.py

list-partitions:
	poetry run python scripts/database/partition_cleanup.py list

validate-partitions:
	poetry run python scripts/database/partition_cleanup.py validate

partition-health:
	poetry run python scripts/database/partition_cleanup.py health

partition-maintenance:
	poetry run python scripts/database/partition_cleanup.py maintenance

emergency-cleanup:
	@echo "Emergency partition cleanup (requires --confirm flag)"
	@echo "Run: make emergency-cleanup-confirmed"

emergency-cleanup-confirmed:
	poetry run python scripts/database/partition_cleanup.py emergency --confirm


# ──── Monitoring ─────────────────────────────────────────────────────────────

start-monitoring: _require-main-checkout
	@bash scripts/observability/start_monitoring.sh

stop-monitoring: _require-main-checkout
	@bash scripts/observability/stop_monitoring.sh

monitoring-status: _require-main-checkout
	@bash scripts/observability/monitoring_status.sh

start-thermal:
	@bash scripts/monitoring/start_thermal_exporter.sh

stop-thermal:
	@bash scripts/monitoring/stop_thermal_exporter.sh

star-dashboards:
	@bash scripts/observability/star_dashboards.sh

monitoring-all: start-monitoring start-thermal
	@. ./.env 2>/dev/null; \
	 echo "All monitoring started: Prometheus :$${PROMETHEUS_EXTERNAL_PORT:-9090}  Grafana :$${GRAFANA_EXTERNAL_PORT:-3000}"

stop-monitoring-all: stop-monitoring stop-thermal


# ──── Kubernetes (local) ─────────────────────────────────────────────────────
# Inner-loop cheat sheet:
#   Changed Helm chart / values / Flyway SQL  →  make k8s-deploy  (~20s)
#   Changed Python / TypeScript app code      →  make k8s-build && make k8s-deploy
#   Bumped a dep image (postgres, keycloak …) →  make k8s-up      (re-loads deps)
#   First run / new worktree                  →  make k8s-up      (everything)

k8s-preflight:  ## Validate base images and chart render for this host architecture
	@bash scripts/k8s/local.sh preflight

k8s-up:  ## Cold start: create cluster + load deps + build app/UI/pg images + helm install. Use for first run, new worktree, or after a dependency image change.
	@bash scripts/k8s/local.sh up

k8s-down:  ## Delete the kind cluster and all its state
	@bash scripts/k8s/local.sh down

k8s-build:  ## Rebuild app + UI + custom postgres Docker images and load them into the cluster. Does NOT deploy — run k8s-deploy after.
	@bash scripts/k8s/local.sh build

k8s-deploy:  ## Refresh flyway-sql ConfigMap + helm upgrade (falls back to install). No image rebuild. Fast inner loop for chart/values/migration edits.
	@bash scripts/k8s/local.sh deploy

k8s-status:  ## Show pod, service, and ingress status for the release
	@bash scripts/k8s/local.sh status

k8s-verify:  ## Health-check every pod and confirm the API port is reachable
	@bash scripts/k8s/verify.sh

k8s-smoke-test:  ## Run the end-to-end functional smoke test against the Kind deployment
	@echo "Running functional smoke test against K8s..."
	@API_PORT=$$(bash -c '\
		REPO_ROOT="$$(cd "$$(dirname "$$0")/../.." && pwd)"; \
		if [ "$$(git -C "$(CURDIR)" rev-parse --git-dir 2>/dev/null)" != "$$(git -C "$(CURDIR)" rev-parse --git-common-dir 2>/dev/null)" ] 2>/dev/null; then \
			source scripts/k8s/worktree-ports.sh; \
			SLUG=$$(basename "$(CURDIR)" | tr "[:upper:]" "[:lower:]" | sed "s/[^a-z0-9-]/-/g" | cut -c1-20); \
			SLOT=$$(get_worktree_slot "analysi-$$SLUG"); \
			ports_for_slot "$$SLOT"; \
			echo "$$API_HOST_PORT"; \
		else echo 8000; fi') && \
	BACKEND_API_EXTERNAL_PORT=$$API_PORT ANALYSI_ADMIN_API_KEY=dev-admin-api-key \
		poetry run python scripts/smoke_tests/functional_test.py

k8s-logs:  ## Tail pod logs. SERVICE=api|ui|alerts-worker|… scopes to one; omit for all.
ifdef SERVICE
	@bash scripts/k8s/local.sh logs $(SERVICE)
else
	@bash scripts/k8s/local.sh logs
endif



# ──── EKS ───────────────────────────────────────────────────────────────────

eks-up:
	@bash scripts/k8s/eks.sh up

eks-down:
	@bash scripts/k8s/eks.sh down

eks-deploy:
	@bash scripts/k8s/eks.sh deploy

eks-status:
	@bash scripts/k8s/eks.sh status

eks-verify:
	@bash scripts/k8s/eks.sh verify

eks-logs:
ifdef SERVICE
	@bash scripts/k8s/eks.sh logs $(SERVICE)
else
	@bash scripts/k8s/eks.sh logs
endif

eks-bootstrap:
	@bash scripts/k8s/bootstrap-terraform-backend.sh


# ──── Docker Maintenance ─────────────────────────────────────────────────────

fix-docker-disk-space:
	@echo "Current usage:" && docker system df
	@docker builder prune -af && docker volume prune -f && docker image prune -af
	@echo "" && echo "New usage:" && docker system df

docker-disk-usage:
	@docker system df -v


# ──── Deprecated Aliases ─────────────────────────────────────────────────────
# These still work but print a deprecation notice. Will be removed in a future release.

define DEPRECATION_WARNING
	@echo "WARNING: 'make $(1)' is deprecated. Use 'make $(2)' instead."
endef

# Per-service targets → parameterized SERVICE=
restart-api restart-analysis restart-integrations restart-keycloak restart-vault:
	$(call DEPRECATION_WARNING,$@,restart SERVICE=...)
	@$(MAKE) --no-print-directory restart SERVICE=$(patsubst restart-api,api,$(patsubst restart-analysis,alerts-worker,$(patsubst restart-integrations,integrations-worker,$(patsubst restart-keycloak,keycloak,$(patsubst restart-vault,vault,$@)))))

rebuild-api rebuild-analysis rebuild-integrations rebuild-keycloak rebuild-ui:
	$(call DEPRECATION_WARNING,$@,rebuild SERVICE=...)
	@$(MAKE) --no-print-directory rebuild SERVICE=$(patsubst rebuild-api,api,$(patsubst rebuild-analysis,alerts-worker,$(patsubst rebuild-integrations,integrations-worker,$(patsubst rebuild-keycloak,keycloak,$(patsubst rebuild-ui,ui,$@)))))

rebuild-all:
	$(call DEPRECATION_WARNING,$@,rebuild)
	@$(MAKE) --no-print-directory rebuild

logs-api logs-analysis logs-integrations logs-keycloak logs-vault logs-ui:
	$(call DEPRECATION_WARNING,$@,logs SERVICE=...)
	@$(MAKE) --no-print-directory logs SERVICE=$(patsubst logs-api,api,$(patsubst logs-analysis,alerts-worker,$(patsubst logs-integrations,integrations-worker,$(patsubst logs-keycloak,keycloak,$(patsubst logs-vault,vault,$(patsubst logs-ui,ui,$@))))))

shell-api shell-analysis shell-integrations:
	$(call DEPRECATION_WARNING,$@,shell SERVICE=...)
	@$(MAKE) --no-print-directory shell SERVICE=$(patsubst shell-api,api,$(patsubst shell-analysis,alerts-worker,$(patsubst shell-integrations,integrations-worker,$@)))

# Old database target names
migrate:
	$(call DEPRECATION_WARNING,$@,db-migrate)
	@$(MAKE) --no-print-directory db-migrate

migrate-test:
	$(call DEPRECATION_WARNING,$@,db-migrate-test)
	@$(MAKE) --no-print-directory db-migrate-test

migrate-all:
	$(call DEPRECATION_WARNING,$@,db-migrate-all)
	@$(MAKE) --no-print-directory db-migrate-all

flyway-repair:
	$(call DEPRECATION_WARNING,$@,db-repair)
	@$(MAKE) --no-print-directory db-repair

# Historical aliases
restart-connector restart-worker: restart-integrations
restart-alert-worker restart-alerts-worker: restart-analysis
rebuild-connector rebuild-worker: rebuild-integrations
rebuild-alert-worker rebuild-alerts-worker: rebuild-analysis
logs-connector logs-worker: logs-integrations
logs-alert-worker logs-alerts-worker: logs-analysis
code-quality-check: code-quality


# ──── PHONY declarations ─────────────────────────────────────────────────────

.PHONY: help _require-main-checkout _ensure-env \
        up up-full down ps logs restart rebuild shell clean dev \
        db-migrate db-migrate-test db-migrate-all db-repair init-vault \
        test-unit test-db-clean test-db-up test-db-down test-db-down-all test-db-status \
        test-integration-db test-integration-full \
        test-eval test-eval-quick code-quality code-quality-ci benchmark-api benchmark-api-ci \
        security-scan audit-deps audit-test-hygiene detect-flakiness \
        detect-bare-httpx lint-logging check-partition-sync count-lines \
        package-agents package-skills check-skills \
        package-external-agents package-foundation-skills check-foundation-skills \
        generate-types \
        cli-install cli-build cli-generate cli-test cli-dev cli \
        flush-tenant-queue \
        minio-start minio-restart minio-logs minio-rebuild minio-status \
        validate-manifest validate-integration \
        schedule-health \
        list-partitions validate-partitions partition-health partition-maintenance \
        emergency-cleanup emergency-cleanup-confirmed \
        start-monitoring stop-monitoring monitoring-status star-dashboards \
        start-thermal stop-thermal monitoring-all stop-monitoring-all \
        k8s-preflight k8s-up k8s-down k8s-build k8s-deploy k8s-status k8s-verify k8s-smoke-test k8s-logs \
        eks-up eks-down eks-deploy eks-status eks-verify eks-logs eks-bootstrap \
        ec2-up ec2-down ec2-status ec2-health ec2-logs ec2-endpoints \
        ec2-ssh ec2-info ec2-credentials ec2-help \
        fix-docker-disk-space docker-disk-usage \
        restart-api restart-analysis restart-integrations \
        restart-keycloak restart-vault \
        rebuild-api rebuild-analysis rebuild-integrations \
        rebuild-keycloak rebuild-ui rebuild-all \
        logs-api logs-analysis logs-integrations \
        logs-keycloak logs-vault logs-ui \
        shell-api shell-analysis shell-integrations \
        migrate migrate-test migrate-all flyway-repair \
        restart-connector restart-worker restart-alert-worker restart-alerts-worker \
        rebuild-connector rebuild-worker rebuild-alert-worker rebuild-alerts-worker \
        logs-connector logs-worker logs-alert-worker logs-alerts-worker \
        code-quality-check
