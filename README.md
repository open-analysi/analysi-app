# Analysi

Security automation platform that processes alerts through AI-powered investigation workflows. Ingests alerts from SIEMs, enriches them via threat intelligence, runs automated investigation playbooks, and produces analyst-ready dispositions.

For background on the problem Analysi solves, see [docs/context/ai-soc-problem.md](docs/context/ai-soc-problem.md).

## Architecture

```
                    ┌─────────────┐
                    │    SIEM     │  (alert source)
                    └──────┬──────┘
                           │ pull_alerts
                    ┌──────▼──────┐
                    │     API     │  FastAPI + {data, meta} envelope
                    └──┬──┬───┬──┘
                       │  │   │
          ┌────────────▼┐ │ ┌─▼────────────────┐
          │   Alerts     │ │ │  Integrations     │
          │   Worker     │ │ │  Worker           │
          └──────┬───────┘ │ └──────────────────┘
                 │         │    ARQ async jobs
          ┌──────▼──────┐  │
          │  Cy Scripts  │  │  ┌──────────────────┐
          │  + LLM calls │  └──▶  Notifications   │
          └──────────────┘     │  Worker (Slack)   │
                               └──────────────────┘
```

**Services:**

| Service | Purpose |
|---------|---------|
| **API** | REST API (FastAPI), MCP server, serves UI and external clients |
| **Alerts Worker** | Alert analysis pipeline — triage, workflow generation, enrichment, disposition |
| **Integrations Worker** | Scheduled actions (pull alerts, health checks) and on-demand tool execution |
| **Notifications Worker** | Slack Socket Mode listener for human-in-the-loop interactions |
| **UI** | Frontend application |
| **PostgreSQL** | Primary data store (pg_partman for partitioned tables, pg_cron for maintenance) |
| **Valkey** | Job queue (ARQ) and caching (Redis-compatible) |
| **Vault** | Credential encryption (Transit engine) |
| **MinIO** | Artifact storage (S3-compatible) |
| **Keycloak** | Identity provider (OIDC, RBAC) |

**Key concepts:**
- **Tasks** — Reusable investigation steps written in Cy (a compiled automation language)
- **Workflows** — DAGs of Tasks that process alerts end-to-end
- **Integrations** — Actions for external tools (Splunk queries, VirusTotal lookups, LDAP queries)
- **Knowledge Units** — Structured data (tables, documents, tools) for enrichment and context
- **Control Events** — Event bus for alert lifecycle coordination and fan-out automation
- **Content Packs** — Portable bundles of tasks, skills, workflows installable via CLI

## Quick Start

Prerequisites: Docker, Make, Poetry (Python 3.13)

```bash
# Start all services (PostgreSQL, Valkey, MinIO, Vault, Keycloak, API, workers, UI)
make up

# Run database migrations
make db-migrate

# Verify everything is healthy
make verify

# View logs
make logs
```

The API is available at `http://localhost:8001`. Health check: `GET /health`.

## Development

```bash
# Run unit tests
make test-unit

# Start per-branch test database for integration tests
make test-db-up
make test-integration-db

# Start full stack with example integrations (SIEM, LDAP, echo EDR)
make up-full

# Rebuild after code changes
make rebuild

# Lint and format
poetry run ruff check --fix
poetry run ruff format

# Code quality audit
make code-quality-check
```

### Testing

All tests run against PostgreSQL — SQLite is not supported.

```bash
make test-unit              # Fast unit tests
make test-db-up             # Start per-branch test database
make test-integration-db    # DB-only integration tests (~1800+)
make test-integration-full  # All integration tests (requires full stack)
make smoke-test             # Post-deploy health checks
make benchmark-api          # API response time benchmarks
make audit-test-hygiene     # Detect flaky test patterns
```

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

Container images are **private** — never pushed to public registries.

## Integrations

Analysi ships with a pluggable integration framework (Naxos) and 40+ built-in integrations. Each integration declares **actions** — capabilities callable from Cy scripts or via scheduled execution. Examples:

| Integration | Archetypes | Capabilities |
|-------------|------------|-------------|
| Splunk | SIEM | SPL queries, notable updates, data model discovery |
| Echo EDR | EDR | Process/network/browser history, isolation, quarantine |
| VirusTotal | Threat Intel | IP/domain/file/URL reputation and scanning |
| AbuseIPDB | Threat Intel | IP reputation lookup and reporting |
| OpenAI | AI | LLM functions (`llm_run`, `llm_summarize`, `llm_extract`) |
| Anthropic | AI | LLM functions via Claude models |
| OpenLDAP | Identity Provider | User/group lookups, authentication context |

## Tech Stack

- **Language:** Python 3.13, [Cy](https://github.com/imarios/cy-language) (compiled automation scripts), TypeScript (CLI)
- **Framework:** FastAPI, SQLAlchemy 2.0 (async), ARQ, Pydantic AI, LangGraph
- **Database:** PostgreSQL 15 (pg_partman, pg_cron), Valkey (Redis-compatible)
- **Infrastructure:** Docker Compose, Helm, Terraform, Kind, EKS
- **Observability:** structlog, OpenTelemetry, Prometheus, Grafana
- **Auth:** Keycloak (OIDC), API keys, RBAC

## License

Proprietary. See LICENSE for details.
