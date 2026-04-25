# Analysi

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Security automation platform that processes alerts through AI-powered investigation workflows. Ingests alerts from SIEMs, enriches them via threat intelligence, runs automated investigation playbooks, and produces analyst-ready dispositions.

> 📖 **Documentation:** [open-analysi.github.io/analysi-app](https://open-analysi.github.io/analysi-app/) — concepts, alert lifecycle, component architecture, terminology, integrations catalog. This README covers build, install, and tooling only.

## Contents

- [Quick Start](#quick-start)
- [Development](#development)
  - [Testing](#testing)
  - [Developer Tools](#developer-tools)
- [Deployment](#deployment)
  - [Local Kubernetes (kind)](#local-kubernetes-kind)
  - [AWS EKS](#aws-eks)
  - [CI/CD](#cicd)
- [Tech Stack](#tech-stack)
- [License](#license)
- [Contributing](#contributing)

## Quick Start

Prerequisites: Docker, Make, Poetry (Python 3.12+; Docker images use Python 3.13). See [Developer Tools](#developer-tools) for the full toolchain.

```bash
# Start all services (PostgreSQL, Valkey, MinIO, Vault, Keycloak, API, workers, UI)
make up

# Run database migrations (Flyway)
make db-migrate

# Verify everything is healthy
make verify

# View logs
make logs
```

The API is available at `http://localhost:8001`. Health check: `GET /health`.

> **Git worktrees:** `make up` and the other Compose targets are blocked inside git worktrees to avoid port and database conflicts. Use the Kind workflow instead (`make k8s-up`, `make k8s-status`, `make k8s-down`).

## Development

```bash
# Run unit tests
make test-unit

# Start per-branch test database for integration tests
make test-db-up
make test-integration-db

# Start the full stack with observability (Prometheus + Grafana)
# on top of the core services started by `make up`.
make up-full

# Rebuild after code changes (add SERVICE=api to target a single service)
make rebuild

# Lint, format, typecheck
poetry run ruff check --fix
poetry run ruff format
poetry run typecheck

# Code quality audit
make code-quality-check
```

The TypeScript CLI under `cli/` wraps the API for terminal use:

```bash
make cli-install && make cli-build
make cli CMD="auth login"
make cli CMD="status"
```

### Testing

Unit tests run in-process and need no services. Integration tests run against a per-branch PostgreSQL container.

```bash
make test-unit              # Fast unit tests (no services required)
make test-db-up             # Start per-branch test database
make test-integration-db    # DB-only integration tests (~1800+)
make test-integration-full  # All integration tests (requires full stack)
make smoke-test             # Post-deploy health checks
make benchmark-api          # API response time benchmarks
make audit-test-hygiene     # Detect flaky test patterns
```

### Developer Tools

You only need to install four things manually. Everything else is brought in by `poetry install`, runs in a container, or is optional for specific deployment targets.

**Required local installs:**

| Tool | What it's for |
|------|---------------|
| [Docker](https://docs.docker.com/get-docker/) | Runs the Compose stack, builds service images, feeds Kind |
| [Make](https://www.gnu.org/software/make/) | Primary task runner — every workflow in this README is a `make` target |
| [Poetry](https://python-poetry.org/) | Python dependency + virtualenv management (`poetry add <pkg>`, `poetry run <cmd>`) |
| [Skilltree](https://github.com/imarios/skilltree) | Skill/agent dependency manager that works with any AI coding assistant (Claude Code, Cursor, etc.). `skilltree install` resolves [`skilltree.yaml`](skilltree.yaml) and populates the agent's local config dir. Skip if you're coding without an AI assistant. |

**Runs in containers** (no local install needed): Flyway (SQL migrations via `make db-migrate`).

**Optional, install only for the targets you'll use:**

| Tool | When to install |
|------|-----------------|
| [Kind](https://kind.sigs.k8s.io/) | Required for local Kubernetes runs and inside git worktrees — `make k8s-up`, `make k8s-status` |
| [Helm](https://helm.sh/) | Needed if you'll touch the Kubernetes charts under `deployments/helm/analysi/` |
| [kubectl](https://kubernetes.io/docs/reference/kubectl/) | Needed if you'll inspect a running cluster (`make k8s-logs SERVICE=api`) |
| [Terraform](https://www.terraform.io/) | Only needed for AWS EKS deployment — modules under `deployments/terraform/` |

## Deployment

### Local Kubernetes (kind)

```bash
make k8s-up       # Create kind cluster + deploy
make k8s-status   # Check pod health
make k8s-down     # Tear down
```

### AWS EKS

```bash
# One-time: bootstrap S3 + DynamoDB for Terraform state
make eks-bootstrap

# Set GHCR PAT (never store in files)
export TF_VAR_ghcr_pat=ghp_...

# Deploy
make eks-up       # ~15 minutes (VPC, EKS, ALB, Helm)
make eks-verify   # Smoke tests against ALB
make eks-down     # Destroy everything ($0 when idle)
```

Infrastructure: Terraform modules for VPC, EKS (managed node groups), ALB ingress, IRSA, EBS CSI. See `deployments/terraform/` and `deployments/CLAUDE.md` for architecture decisions.

### CI/CD

- **PR checks** (`.github/workflows/ci.yml`): lint, unit tests, image builds (~4.5 min)
- **Release** (`.github/workflows/release.yml`): push to private GHCR on merge to main
- **Docs** (`.github/workflows/docs.yml`): build and deploy MkDocs site to GitHub Pages on push to `main`

Container images are **private** — never pushed to public registries.

## Tech Stack

- **Language:** Python 3.12+ (Docker images on 3.13), [Cy](https://github.com/open-analysi/cy-language) (compiled automation scripts), TypeScript (CLI)
- **Framework:** FastAPI, SQLAlchemy 2.0 (async), ARQ, `pydantic-ai-slim`, LangGraph
- **Database:** PostgreSQL 15 (pg_partman, pg_cron), Flyway migrations, Valkey (Redis-compatible)
- **Infrastructure:** Docker Compose, Helm, Terraform, Kind, EKS
- **Observability:** structlog, OpenTelemetry, Prometheus, Grafana
- **Auth:** Keycloak (OIDC), API keys, RBAC

## License

Analysi is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

In short: you are free to use, modify, and redistribute Analysi. If you run a modified version as a network service, you must make your source code available to users of that service under the same license. See [LICENSE](LICENSE) for the full terms.

## Contributing

Contributions are welcome. All commits must be signed off under the [Developer Certificate of Origin](https://developercertificate.org/) — see [CONTRIBUTING.md](CONTRIBUTING.md) for details.
