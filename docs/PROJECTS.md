# Projects

Project Naming Theme: Greek Islands

## Completed Projects

- **Naxos**: Plug-n-play connectors framework with a library of integration archetypes (SIEM, EDR, ThreatIntel, etc.)
- **Milos**: Deploying Analysi on AWS for Demos
- **Paros**: Adding an MCP server (SSE endpoint) to our backend server for Task/Cy creation
- **Rodos**: Typechecked Workflows with reusable NodeTemplates, MCP server for workflow creation and validation, Workflow Composer
- **Kea**: Agentic Workflow Builder (AWB) - takes a NAS Alert and creates a fully functioning Analysis Workflow to analyze and prioritize it
- **Hydra**: Skills Management and Knowledge Extraction - LangGraph pipeline that ingests documents into skills. Core DB-based skills infrastructure complete. DB skills integrated into Kea directly.
- **Ithaca**: Task Parallelization and Execution Decoupling — 4 phases: (1) decoupled task execution from DB session (isolated sessions, TaskExecutionResult dataclass), (2) formalized nested task subroutine model, (3) concurrent fan-out execution via asyncio.gather() reducing parallel workflow time from ~8s to ~1.6s, (4) LLM token and cost capture with Feb 2026 pricing registry.
- **Tilos**: Control Event Bus — disposition fan-out system that fires Tasks or Workflows in response to analysis events (e.g., `disposition:ready`). Includes DB schema, repository layer, REST API for rule management, ARQ cron + worker jobs, Slack notification integration, idempotent retry logic, and full unit + integration test coverage.
- **Mikonos**: Authentication & Authorization — Keycloak-based hub IdP, OIDC login, email/password, API keys, RBAC with role/permission matrix, JWT middleware, member management API, UI auth integration, Helm chart bundling.
- **Sifnos**: Unified API Response Contract — standardize all REST API responses to a consistent `{data, meta}` envelope, uniform pagination (`limit/offset`), typed error responses, request-ID middleware. 5 phases across ~29 router files.
- **Syros**: Production Hardening — Phases 1-6: Artifact Store (tech debt, object storage, presigned URLs, API filters). Phases 7-11: Logging & Observability (eliminate print-logging, unify structlog, structured events, correlation propagation, OpenTelemetry foundations, PII hardening).
- **Lefkada**: Packaging, Deployments & Developer Experience — repo reorganization, layered Docker Compose, multi-stage production Dockerfiles, Helm charts, local K8s, GitHub Actions CI/CD, GHCR, AWS deployment foundation. 11 phases (1a-1c, 2a-2b, 3-8).
- **Zakynthos**: Task Feedback System — feedback as KUDocuments with `feedback_for` KDG edges, REST API for feedback CRUD, LLM relevance checking with Valkey cache, prompt augmentation in `llm_run()`. 5 phases.
- **Kalymnos**: Human-in-the-Loop (HITL) — Cy language memoized replay for hi-latency tools, pause/resume propagation through Task/Workflow/Analysis layers, Slack Socket Mode listener (multi-tenant, dedicated container), `hitl_questions` tracking, `human:responded` control event channel.
- **Leros**: Unified Job Execution Framework — shared `@tracked_job` decorator, `RunStatus` enum, generic stuck detection, migrate `asyncio.create_task()` to ARQ, optional unified `job_runs` table. 6 phases.
- **Rhodes**: Product Chatbot — per-tenant context-aware assistant built on Pydantic AI + assistant-ui. AI archetype extension with capability presets, two-layer knowledge (system prompt + KU tools), 8-layer OWASP security, SSE streaming. 9 phases.
- **Delos**: Content Packs & Platform Management — portable content bundles (tasks, skills, KUs, workflows) installable via CLI, `tenant` table for explicit tenant lifecycle, `/platform/v1/` API prefix for platform-admin operations, `/admin/v1/` reorganization, content trust model (built-in skip validation, external require it).
- **Symi**: Unified Scheduler & Actions — deprecate "connectors," unify all integration capabilities as actions with `categories`, generic `schedules` table targeting any Task or Workflow, alert ingestion as an explicit Task (AlertSource archetype → `pull_alerts` → `alerts_to_ocsf` → `ingest_alerts`), `job_runs` audit trail, `task_checkpoints` for cross-run cursor state, convenience schedule endpoints on Tasks/Workflows.
