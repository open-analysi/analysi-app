+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Docker, Helm, CI/CD (Project Lefkada)"
+++

# Packaging, Deployments & Developer Experience

Spec Version: 1
Project: Lefkada

## Problem Statement

The repository has grown organically across 10+ projects. All 15 Docker services live in a single 543-line docker-compose.yaml. Dockerfiles, Terraform, and scripts are scattered across `docker/`, `scripts/ec2/`, and the project root. There is no CI/CD pipeline, no container registry, no Helm charts, and no way to spin up a test environment automatically. This makes the project hard to contribute to, hard to deploy, and impossible to run automated tests in CI.

## Goals

- **G1**: Clean, layered repo structure that separates core product from optional infrastructure
- **G2**: Composable local development — developers choose what they need (core-only, full, observability)
- **G3**: Production-ready container images pushed to GitHub Container Registry (GHCR)
- **G4**: Helm charts for Kubernetes deployment (local and cloud)
- **G5**: GitHub Actions CI/CD pipeline (build, test, push images, PR checks)
- **G6**: Local Kubernetes development with kind + Helm
- **G7**: AWS EKS deployment replacing EC2 demo — all-in-cluster, modular Terraform, persistent volumes
- **G8**: Easy onboarding for open-source contributors

## Non-Goals

- **NG1**: Moving `src/` directory structure — source code layout stays as-is
- **NG2**: Merging UI repo into this repo (planned separately, but we prepare for it)
- **NG3**: Managed AWS services (RDS, S3, ElastiCache) — Phase 8 is all-in-cluster; managed services are a future variant
- **NG4**: GitOps (ArgoCD/Flux) — future work
- **NG5**: Custom CLI tool to replace Makefile — Makefile is sufficient for now

## Requirements

### Repo Organization

- **R1**: All deployment configuration lives under `deployments/` at the repo root
- **R2**: Docker Compose files split into four layers matching the infrastructure model: `core.yml` (Layer 1: API, workers, Flyway), `deps.yml` (Layer 2: Postgres, Valkey, Vault, Keycloak, MinIO), `integrations.yml` (Layer 3: Splunk, LDAP, echo-server), `observability.yml` (Layer 4: Prometheus, Grafana). Each layer maps to one compose file. Core Product stays the same across deployments; Core Dependencies vary by environment (e.g., container Postgres locally → RDS in cloud).
- **R3**: Each service gets its own directory under `deployments/docker/` with a single multi-stage `Dockerfile` containing named stages: `base` (shared foundation — deps, system packages), `dev` (volume mounts, --reload), `production` (COPY source, non-root user). Compose uses `build.target` to select the stage.
- **R4**: Docker service configs (postgres init, keycloak realm, vault scripts, etc.) live under `deployments/docker/configs/`
- **R5**: Terraform lives under `deployments/terraform/` with modular structure
- **R6**: Helm charts live under `deployments/helm/`
- **R7**: Environment manifest (`deployments/environments.yaml`) declares supported Helm environments and compose layer options

### Environment-Driven Deployment

Two deployment methods, each with its own configuration mechanism:

**Docker Compose (local dev only)**:
- Single `.env` file for local development configuration
- `.env.test` for unit test overrides (e.g., test database connection)
- No `.env` variants for non-local environments — those use Helm/K8s
- `INTEGRATIONS` / `OBSERVABILITY` flags control additive compose layers

**Helm/Kubernetes (staging, production, CI)**:
- Environment differences via values files: `values/local.yaml`, `values/aws-hybrid.yaml`, `values/prod-full.yaml`
- Secrets from Vault or Kubernetes Secrets — never from `.env` files
- Same `INTEGRATIONS` / `OBSERVABILITY` concept via Helm values

| Environment | Postgres | Object Storage | Valkey | Vault | Deployment Method |
|-------------|----------|----------------|--------|-------|-------------------|
| `local` | container | MinIO | container | container | Docker Compose |
| `aws-hybrid` | Aurora | S3 | container | container | Helm/K8s |
| `prod-full` | Aurora | S3 | ElastiCache | Vault | Helm/K8s |

- **R8**: `make up` starts core services locally (core.yml + deps.yml — Layers 1+2)
- **R9**: `make up INTEGRATIONS=true` adds integration layer (+ integrations.yml — Layer 3)
- **R10**: `make up OBSERVABILITY=true` adds observability layer (+ observability.yml — Layer 4)
- **R11**: `make up-full` = `make up INTEGRATIONS=true OBSERVABILITY=true` (all 4 layers)
- **R12**: All existing Makefile targets continue to work (backwards compatibility during transition)

Example commands:
```bash
make up                                          # local, core only
make up INTEGRATIONS=true                        # local + Splunk/LDAP
make up OBSERVABILITY=true                       # local + monitoring
make up-full                                     # local, everything
make k8s-up                                      # local kind cluster via Helm
```

### Multi-Instance / Worktree Support

- **R12a**: Multiple instances can run simultaneously on the same machine (e.g., two git worktrees)
- **R12b**: `COMPOSE_PROJECT_NAME` derived automatically from worktree directory name or branch, overridable via env var
- **R12c**: All host ports configurable via `.env` — no hardcoded ports in compose files
- **R12d**: Each instance gets isolated volumes (namespaced by project name — Docker Compose default when project name differs)
- **R12e**: `make up` auto-detects project name from current directory; `make up PROJECT=feature-x` overrides
- **R12f**: Port presets for common scenarios: `.env` ships with default ports, `.env.worktree-example` ships with offset ports (+10 for each service)

### Container Images

- **R13**: Single multi-stage `Dockerfile` per service with named stages: `base` (shared foundation — deps, system packages), `dev` (FROM base — volume mounts, --reload), `production` (FROM base — COPY source, non-root user). Dev and prod both inherit from the same base stage, guaranteeing no dependency drift.
- **R14**: CI builds the `production` target for each service. Compose dev services use `build.target: dev`. BuildKit handles stage caching natively — no `depends_on` needed for base.
- **R15**: All images tagged with git SHA and `latest`
- **R16**: Images pushed to `ghcr.io/<org>/analysi-*` namespace

### Helm & Kubernetes

- **R17**: Helm chart for core product (API, alert-worker, integrations-worker, migrations job)
- **R18**: Helm chart for core dependencies (Postgres, Valkey, Vault, Keycloak) — uses standard sub-charts
- **R19**: Values files per environment, aligned with compose ENV names: `local.yaml`, `aws-hybrid.yaml`, `prod-full.yaml`
- **R20**: Local K8s via `kind` with `make k8s-up` / `make k8s-down`
- **R21**: Smoke tests validate deployment health after Helm install

### CI/CD

- **R22**: GitHub Actions workflow: on PR — lint, unit test, build images
- **R23**: GitHub Actions workflow: on merge to main — build + push images to GHCR
- **R24**: GitHub Actions workflow: integration tests (needs discussion — GH runners vs EKS)

### AWS (Foundation)

- **R25**: Terraform refactored into reusable modules: `network`, `eks`, `rds`, `s3`
- **R26**: Environment-specific tfvars: `dev`, `prod-cheap`, `prod-full`
- **R27**: Existing EC2/Milos deployment preserved as a deployment option

### Makefile Standards

Per the `general-coding` skill's Makefile patterns reference:

- **R28**: Unprefixed targets (`up`, `down`, `logs`, `restart`, `verify`) are the daily-driver compose commands. Prefix only for different orchestration methods (`k8s-`, `aws-`) or different domains (`db-`, `test-`)
- **R29**: Configurable defaults with `?=` for all user-overridable values (PROJECT, INTEGRATIONS, OBSERVABILITY)
- **R30**: Sectioned layout with `# ───` separators: Configuration, Development, Kubernetes, Database, Observability, Code Quality, AWS, etc.
- **R31**: Complex target logic (>1 line) extracted to `scripts/make/` shell scripts
- **R32**: Composite targets for workflows: `up-full`, `deploy: build test up verify`
- **R33**: Safety prompts on destructive operations (`clean`, `db-reset`, `k8s-down`)
- **R34**: Self-documenting `help` as default target with grouped sections
- **R35**: Backwards-compatibility aliases for renamed targets during transition (deprecated, removed in a later phase)

Target layout (~20 targets total):

```
# ──── Development (compose, daily driver) ─────────────
up                     # core services (flags: ENV, INTEGRATIONS, OBSERVABILITY)
up-full                # everything
down
logs                   # all logs, or: make logs SERVICE=api
restart                # make restart SERVICE=api
rebuild                # make rebuild SERVICE=alert-worker
status
verify
clean                  # destructive — safety prompt

# ──── Database ────────────────────────────────────────
db-migrate
db-reset               # destructive — safety prompt

# ──── Kubernetes ──────────────────────────────────────
k8s-up
k8s-down               # destructive — safety prompt
k8s-status

# ──── AWS ─────────────────────────────────────────────
aws-deploy
aws-destroy            # destructive — safety prompt
aws-status

# ──── Testing & Quality ──────────────────────────────
test
test-e2e
code-quality
```

Parameterized targets use `SERVICE=` instead of one target per service:
```bash
make logs SERVICE=splunk      # instead of: make logs-splunk
make restart SERVICE=api      # instead of: make restart-api
make rebuild SERVICE=api      # instead of: make rebuild-api
```

Integration/observability utility scripts (not Makefile targets):
```
scripts/integrations/ldap-search.sh
scripts/integrations/ldap-add-test-data.sh
scripts/integrations/splunk-search.sh
```

## Constraints

- **C1**: Python 3.12 across all containers (existing requirement, enforced)
- **C2**: Source code (`src/`) not moved — only deployment/infra files reorganized
- **C3**: All existing tests must pass after each phase
- **C4**: `docker-compose up` must work after each phase (no broken states between phases)
- **C5**: UI was initially a separate repo; it has since been folded in-tree at `ui/` and is built alongside the backend

## Infrastructure Layers

Each layer maps to one compose file. Layers 1-2 are always required; Layers 3-4 are additive.

```
Layer 1: Core Product — core.yml (always required, same across all deployments)
  - analysi-api              (REST API, business logic)
  - analysi-alert-worker     (alert processing worker)
  - analysi-flyway           (database migration job)

Layer 2: Core Dependencies — deps.yml (always required, implementation varies by environment)
  - PostgreSQL     (container locally → RDS/Aurora in cloud)
  - Valkey         (container locally → ElastiCache in cloud)
  - Vault          (container locally → managed Vault in cloud)
  - Keycloak       (container locally → managed IdP in cloud)
  - MinIO          (container locally → S3 in cloud)

Layer 3: Integration Infrastructure — integrations.yml (optional, dev/test only)
  - Splunk                     (SIEM for testing alert ingestion)
  - OpenLDAP                   (directory service for testing)
  - Echo Server                (mock integration endpoint)
  - Integrations Worker        (connector execution worker)

Layer 4: Observability — observability.yml (optional)
  - Prometheus + exporters
  - Grafana
  - PgAdmin
  - Postgres Exporter
```

**Deployment variation model**: Core Product (Layer 1) is identical everywhere — same Python services, same business logic. Core Dependencies (Layer 2) vary by environment: local dev uses containers, cloud deployments swap in managed services (RDS, S3, ElastiCache). This split lets teams run `core.yml` against either local containers or remote managed services by changing only which `deps.yml` variant they use.

## Target Directory Structure

```
repo/
  src/                           # Unchanged
  tests/                         # Unchanged
  migrations/                    # Unchanged

  deployments/
    docker/
      api/
        Dockerfile               # Multi-stage: base -> dev / production
      alert-worker/
        Dockerfile               # Multi-stage: base -> dev / production
      integrations-worker/
        Dockerfile               # Multi-stage: base -> dev / production
      ui/
        Dockerfile               # Dev Vite server (future: add production stage)
      echo-server/               # Mock integration endpoint (own Dockerfile + Python source)
        Dockerfile
      configs/
        postgres/                # init scripts, postgresql.conf
        keycloak/                # realm JSON
        vault/                   # scripts, config
        splunk/                  # apps, init scripts
        minio/                   # init scripts
        valkey/                  # valkey.conf
        grafana/                 # provisioning
        prometheus/              # prometheus.yml
        pgadmin/                 # server config

    compose/
      core.yml                # Layer 1: Core Product (API, workers, Flyway)
      deps.yml                   # Layer 2: Core Dependencies (Postgres, Valkey, Vault, Keycloak, MinIO)
      integrations.yml           # Layer 3: Integration Infrastructure (Splunk, LDAP, echo-server)
      observability.yml          # Layer 4: Observability (Prometheus, Grafana)
      .env.example               # Reference env file

    helm/
      analysi/                   # Main umbrella chart
        Chart.yaml
        values.yaml              # Defaults
        values/
          local.yaml
          aws-hybrid.yaml
          prod-full.yaml
        templates/
          api/
          alert-worker/
          integrations-worker/
          migrations/
        charts/                  # Sub-chart dependencies

    terraform/
      modules/
        network/                 # VPC, subnets, security groups
        eks/                     # EKS cluster
        rds/                     # PostgreSQL RDS
        s3/                      # S3 buckets
        ec2/                     # Single-instance (Milos-style)
      environments/
        dev/
        prod-cheap/
        prod-full/

    environments.yaml            # Manifest of supported environments

  scripts/                       # Cleaned up
    make/                        # Shell scripts backing Makefile targets
    code_quality_tools/          # Stays
    monitoring/                  # Stays
    smoke_tests/                 # New: post-deploy verification
    integrations/                # Utility scripts: ldap-search, splunk-search, etc.
    e2e/                         # Existing e2e scripts

  .github/
    workflows/
      ci.yml                     # PR checks
      release.yml                # Build + push to GHCR
```

## Testing Checklist

- [ ] After repo reorg: all existing unit + integration tests pass
- [ ] After repo reorg: `make up` starts all services, no errors in logs
- [ ] After compose split: `make up` (core only) starts in <60s, uses <4GB RAM
- [ ] After compose split: `make up-full` starts everything, equivalent to current behavior
- [ ] Production Dockerfiles: `docker build` succeeds for all services
- [ ] Production images: containers start and pass health checks without volume mounts
- [ ] Smoke tests: `make verify` hits health endpoints, returns 200
- [ ] Helm: `helm lint` and `helm template` pass
- [ ] Local K8s: `make k8s-up` deploys to kind, APIs accessible on localhost
- [ ] GitHub Actions: PR triggers lint+test+build, no manual intervention
- [ ] GitHub Actions: merge to main pushes tagged images to GHCR

## Open Questions

- **Q1**: CI test environments — GitHub Actions runners with docker-compose, or spin up ephemeral K8s? (Phase 7-8 decision, discuss with team)
- **Q2**: Splunk container uses 6GB RAM and x86 emulation on ARM. Should it be excluded from default CI? (Leaning: yes, integration-only opt-in)
- **Q3**: ~~Should we adopt `docker compose` (v2, no hyphen) everywhere?~~ **Resolved: yes**, adopted in Phase 2
- **Q4**: Monorepo — when UI joins, does it get its own Dockerfile under `deployments/docker/` or a separate `services/ui/` directory? (Deferred to UI merge project)

## Future Work

- GitOps with ArgoCD or Flux
- Helm chart publishing to a chart registry
- Minikube for realistic local K8s testing (LoadBalancers, persistent volumes, ingress)
- Developer environment generator CLI
- PR-based ephemeral environments with auto-cleanup
- Demo-loader as a separate containerized tool
