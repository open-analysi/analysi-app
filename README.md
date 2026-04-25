# Analysi

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Security automation platform that processes alerts through AI-powered investigation workflows. Ingests alerts from SIEMs, enriches them via threat intelligence, runs automated investigation playbooks, and produces analyst-ready dispositions.

For background on the problem Analysi solves, see [docs/context/ai-soc-problem.md](docs/context/ai-soc-problem.md).

## Contents

- [Architecture](#architecture)
  - [Concept](#concept) — one workflow per detection rule
  - [Alert lifecycle](#alert-lifecycle) — rule-driven path from ingest to reaction
  - [Component architecture](#component-architecture) — runtime processes and shared infra
- [Quick Start](#quick-start) — bring the stack up locally
- [Development](#development)
  - [Testing](#testing)
  - [Developer Tools](#developer-tools)
- [Deployment](#deployment)
  - [Local Kubernetes (kind)](#local-kubernetes-kind)
  - [AWS EKS](#aws-eks)
  - [CI/CD](#cicd)
- [Integrations](#integrations) — 101 built-in connectors by archetype
- [Tech Stack](#tech-stack)
- [License](#license)
- [Contributing](#contributing)

## Architecture

### Concept

Every alert in a SIEM/EDR is produced by a **detection rule** (e.g. Splunk's "Suspicious PowerShell Execution"). Analysi keys its investigation knowledge to the rule, not the individual alert — at most one agentic workflow per rule.

The first time a rule fires, Analysi has no workflow for it and synthesizes one autonomously: slow, token-heavy, multi-tool reasoning. The result is saved against the rule. Every subsequent alert from that same rule reuses the saved workflow — cheap and fast.

```mermaid
flowchart TB
    classDef known fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef new fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    classDef terminal fill:#e0e7ff,stroke:#4338ca,color:#312e81

    Alert([Alert arrives]):::terminal
    Q{Do we already know<br/>how to investigate it?}
    Run["Run agentic workflow<br/><b>cheap · fast</b>"]:::known
    Gen["Generate new agentic workflow<br/><b>slow · deep thinking · high tokens</b>"]:::new
    Disp([Disposition]):::terminal

    Alert --> Q
    Q -- yes --> Run
    Q -- no --> Gen --> Run
    Run --> Disp
```

At steady state, the system holds **one agentic workflow per detection rule that has ever fired** in the environment. As rule coverage grows, the rate of expensive synthesis trends toward zero — and the cost of investigating each new alert collapses to the price of replaying a saved workflow.

### Alert lifecycle

The path an alert takes from ingestion to reaction is rule-driven on both ends. Shape vocabulary used below:

- **Parallelogram** — data / event flowing through the system
- **Diamond** — rule engine / decision logic
- **Rectangle** — function / executable step

```mermaid
flowchart TB
    classDef data fill:#86efac,stroke:#15803d,color:#052e16
    classDef logic fill:#fcd34d,stroke:#b45309,color:#451a03
    classDef func fill:#93c5fd,stroke:#1e40af,color:#172554

    Alert[/"Alert<br/>(OCSF)"/]:::data
    Routing{"Alert Routing<br/>Rules"}:::logic
    Run["Workflow<br/>Execution"]:::func
    GenRun["Workflow Generation<br/>+ Execution"]:::func
    Disp[/"Disposition<br/>Control Event"/]:::data
    Reaction{"Event Reaction<br/>Rules"}:::logic
    Action["Reaction Action<br/>(Slack · Jira · SIEM ticket update)"]:::func

    Alert --> Routing
    Routing -- workflow exists --> Run
    Routing -- no workflow --> GenRun
    Run --> Disp
    GenRun --> Disp
    Disp --> Reaction --> Action
```

Two rule engines bracket the agentic core, but they look alike only on the surface — they're populated and matched very differently:

- **Alert Routing Rules** are **auto-generated**, never hand-written. Each rule says "alerts produced by *this detection rule* run *this workflow*". They appear in the database as a side effect of workflow generation: when Analysi synthesizes a workflow for a never-before-seen detection rule, it also writes the routing rule that pins future alerts of the same rule to that workflow. At steady state there is one routing rule per detection rule the system has ever processed.
- **Event Reaction Rules** are **user-configured**. Each rule matches on properties of the disposition control event (verdict, severity, tags, source, etc.) and fans out to side-effects: post to Slack, open a Jira ticket, update the SIEM case, page on-call, etc. The same disposition can fire any number of reactions — and different teams or environments can configure their own.

#### From OCSF alert to detection rule

The "detection rule" the routing engine keys on is extracted from the OCSF Detection Finding event during ingestion:

```
ocsf.finding_info.analytic.name   →   Alert.rule_name
```

(See [`src/analysi/integrations/framework/alert_ingest.py:175`](src/analysi/integrations/framework/alert_ingest.py#L175).) The `rule_name` becomes the unique `title` of an `AnalysisGroup` row ([`src/analysi/models/kea_coordination.py:25`](src/analysi/models/kea_coordination.py#L25)), which the `AlertRoutingRule` table maps to a `workflow_id` ([`src/analysi/models/kea_coordination.py:140`](src/analysi/models/kea_coordination.py#L140)). Routing for a new alert is therefore one lookup: `finding_info.analytic.name` → analysis group → routing rule → workflow.

If the lookup misses (no analysis group, or no routing rule yet), the alert is queued for workflow generation. Once generation completes successfully, both the analysis group and the routing rule exist, and every subsequent alert from the same detection rule takes the cheap path.

### Component architecture

The runtime processes that implement the concept and lifecycle above, and the wires between them:

```mermaid
flowchart TB
    classDef ext fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef svc fill:#dbeafe,stroke:#1d4ed8,color:#1e3a8a
    User(["Analyst"]):::ext
    Slack["Slack"]:::ext
    SIEM["SIEM"]:::ext
    Tools["Threat intel · EDR<br/>IdP · Sandbox · etc."]:::ext

    UI["UI"]:::svc
    CLI["CLI<br/>(analysi)"]:::svc
    API["API<br/>FastAPI · MCP"]:::svc
    IW["⏰ Integrations Worker<br/>cron · polls schedules"]:::svc
    AW["Alerts Worker<br/>Cy scripts + LLM"]:::svc
    NW["Notifications Worker<br/>Slack Socket Mode"]:::svc

    User --> UI
    User --> CLI
    UI --> API
    CLI --> API
    IW -- enqueue jobs --> AW
    AW -->|pull_alerts| SIEM
    AW <-->|enrich| Tools
    API -.->|ad-hoc exec| Tools
    AW <-. HITL pause/resume .-> NW
    NW <--> Slack
```

> The `IW → AW` arrow is mediated by **Valkey** (ARQ queue). All services share **Postgres** for state, **Vault** for credentials, and **MinIO** for artifacts; the API uses **Keycloak** for OIDC. See the service table below.

**Services:**

| Service | Purpose |
|---------|---------|
| **API** | REST API (FastAPI), MCP server, serves UI and external clients |
| **Alerts Worker** | Alert analysis pipeline — triage, workflow generation, enrichment, disposition |
| **Integrations Worker** | Schedule dispatcher — polls the `schedules` table and enqueues jobs (pull alerts, health checks) onto the alerts worker; ad-hoc tool execution runs in-process in the API |
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

### Developer Tools

Core toolchain you need locally:

| Tool | What it's for |
|------|---------------|
| [Docker](https://docs.docker.com/get-docker/) | Runs Compose stack, builds service images, feeds Kind |
| [Make](https://www.gnu.org/software/make/) | Primary task runner — every workflow in this README is a `make` target |
| [Poetry](https://python-poetry.org/) | Python dependency + virtualenv management (`poetry add <pkg>`, `poetry run <cmd>`) |
| [Ruff](https://docs.astral.sh/ruff/) | Python lint + format (`poetry run ruff check --fix`, `ruff format`) |
| [mypy](https://mypy.readthedocs.io/) | Static type checking (`poetry run typecheck`) |
| [pytest](https://docs.pytest.org/) | Test runner (`poetry run test` or `make test-unit`) |
| [Flyway](https://flywaydb.org/) | SQL migrations in `migrations/flyway/sql/` (`make db-migrate`, `make flyway-repair`) |
| [Skilltree](https://github.com/imarios/skilltree) | Generic skill/agent dependency manager that works with any AI coding assistant (Claude Code, Cursor, etc.). `skilltree install` resolves [`skilltree.yaml`](skilltree.yaml) and populates the agent's local config dir. Only skip it if you're coding without an AI assistant. |

Deployment + infra:

| Tool | What it's for |
|------|---------------|
| [Kind](https://kind.sigs.k8s.io/) | Local Kubernetes cluster (required in git worktrees) — `make k8s-up`, `make k8s-status` |
| [Helm](https://helm.sh/) | Kubernetes packaging — charts under `deployments/helm/analysi/` |
| [Terraform](https://www.terraform.io/) | EKS infrastructure (VPC, EKS, ALB, IRSA) under `deployments/terraform/` |
| [kubectl](https://kubernetes.io/docs/reference/kubectl/) | Cluster inspection (`make k8s-logs SERVICE=api`) |

Analysi-specific:

| Tool | What it's for |
|------|---------------|
| Analysi CLI (`cli/`) | TypeScript CLI over the REST API — `make cli-install && make cli-build`, then `make cli CMD="..."` |
| `poetry run validate-manifest <path>` | Validate a single integration `manifest.json` |
| `poetry run validate-integration <path>` | Validate a full integration directory (manifest + action classes + archetypes) |
| `make code-quality-check` | Test hygiene + flakiness detection + line counts |

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

Analysi ships with a pluggable integration framework (**Naxos**) and **101 built-in integrations**. Each integration declares an **archetype** (what kind of tool it is) and **actions** (capabilities callable from Cy scripts or scheduled jobs).

Integrations, grouped by archetype:

| Archetype | # | Examples |
|-----------|---|----------|
| ThreatIntel | 19 | VirusTotal, AbuseIPDB, Recorded Future, MISP, Shodan, GreyNoise, DomainTools |
| EDR | 13 | CrowdStrike, SentinelOne, Defender for Endpoint, Carbon Black, Cortex XDR, Echo EDR |
| NetworkSecurity | 11 | Palo Alto, FortiGate, Check Point, Zscaler, Cloudflare, Cisco Umbrella, Netskope |
| SIEM | 10 | Splunk, Microsoft Sentinel, Elasticsearch, QRadar, Chronicle, Sumo Logic, Exabeam |
| EmailSecurity | 6 | Proofpoint, Mimecast, Abnormal, Google Gmail, Exchange On-Prem, Cofense Triage |
| DatabaseEnrichment | 6 | Censys, SecurityTrails, Have I Been Pwned, NIST NVD, Axonius, PassiveTotal |
| IdentityProvider | 5 | Okta, Microsoft Entra ID, AD LDAP, Duo, CyberArk |
| TicketingSystem | 5 | JIRA, ServiceNow, TheHive, Freshservice, BMC Remedy |
| CloudProvider | 4 | AWS Security, Google Cloud SCC, Defender for Cloud, Wiz |
| Sandbox | 5 | ANY.RUN, Joe Sandbox, WildFire, urlscan.io, CrowdStrike |
| VulnerabilityManagement | 4 | Tenable, Qualys, Rapid7 InsightVM, Nessus |
| AI | 3 | Anthropic (Claude), OpenAI, Google Gemini |
| Communication | 3 | Microsoft Teams, Cisco Webex, Google Chat |
| Lakehouse | 2 | Databricks, Google BigQuery |
| Notification | 2 | Slack, PagerDuty |
| DNS · Geolocation · MacOuiRegistry · QRDecoder · TorExitList · UrlShorteningTools · Whois | 1 each | Global DNS, MaxMind, MAC Vendors, QR Code, Tor, unshorten.me, WHOIS RDAP |

Full list of integration IDs lives in [`src/analysi/integrations/framework/integrations/`](src/analysi/integrations/framework/integrations/). Add new integrations by dropping a directory with a `manifest.json` and an action class — validated via `poetry run validate-integration <path>`.

## Tech Stack

- **Language:** Python 3.12+ (Docker images on 3.13), [Cy](https://github.com/imarios/cy-language) (compiled automation scripts), TypeScript (CLI)
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
