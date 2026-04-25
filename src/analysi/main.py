import sys
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analysi.api import RequestIdMiddleware, init_error_handling
from analysi.config.logging import configure_logging, get_logger
from analysi.config.settings import settings
from analysi.db.session import close_db_connections, init_db
from analysi.middleware.logging import RequestLoggingMiddleware
from analysi.middleware.security_headers import SecurityHeadersMiddleware
from analysi.middleware.tenant import TenantValidationMiddleware
from analysi.routers import health, invitations, platform, v1
from analysi.schemas.base import ProblemDetail
from analysi.services.partition_management import run_maintenance

# Configure logging and telemetry as early as possible
configure_logging()

try:
    from analysi.config.telemetry import configure_telemetry

    configure_telemetry(service_name="analysi-api")
except ImportError:
    pass  # opentelemetry not installed — tracing disabled
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore
    logger.info("application_startup", service="analysi", version="0.1.0")
    await init_db()
    logger.info("database_initialized")

    # Initialise JWKS client if Keycloak URI is configured
    if settings.ANALYSI_AUTH_JWKS_URI:
        from analysi.auth.jwks import initialize_jwks_client

        initialize_jwks_client(settings.ANALYSI_AUTH_JWKS_URI)
        logger.info("jwks_initialized", jwks_uri=settings.ANALYSI_AUTH_JWKS_URI)
    else:
        logger.info("jwks_skipped_no_uri_configured")

    # Provision system API key if configured (idempotent, all environments)
    if settings.ANALYSI_SYSTEM_API_KEY:
        from analysi.auth.api_key import provision_system_api_key
        from analysi.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await provision_system_api_key(
                raw_key=settings.ANALYSI_SYSTEM_API_KEY,
                tenant_id="default",
                db=session,
            )
            await session.commit()
        logger.info("system_api_key_provisioned")

    # Provision dev API keys (idempotent, dev-mode only)
    if settings.ANALYSI_AUTH_MODE == "dev":
        from analysi.auth.api_key import DevApiKeySpec, provision_dev_api_keys
        from analysi.db.session import AsyncSessionLocal
        from analysi.models.auth import SYSTEM_USER_ID

        # Add new dev keys here — just append a DevApiKeySpec
        specs = (
            [
                DevApiKeySpec(
                    raw_key=settings.ANALYSI_OWNER_API_KEY,
                    role="owner",
                    email="system@analysi.internal",
                    key_name="Owner API Key",
                    user_id=SYSTEM_USER_ID,
                )
            ]
            if settings.ANALYSI_OWNER_API_KEY
            else []
        )

        if settings.ANALYSI_ADMIN_API_KEY:
            specs.append(
                DevApiKeySpec(
                    raw_key=settings.ANALYSI_ADMIN_API_KEY,
                    role="admin",
                    email="dev-admin@analysi.local",
                    key_name="Admin API Key",
                )
            )

        if specs:
            async with AsyncSessionLocal() as session:
                await provision_dev_api_keys(specs, tenant_id="default", db=session)
                await session.commit()
            logger.info("dev_api_keys_provisioned", count=len(specs))

    # Trigger pg_partman maintenance to ensure partitions are current.
    # pg_partman (configured by the baseline migration) handles all partition lifecycle
    # automatically via pg_cron. This on-demand call is a startup safety net.
    try:
        await run_maintenance()
        logger.info("partition_maintenance_completed")
    except Exception as e:
        # Don't block startup if pg_partman maintenance fails — pg_cron will
        # run it on the next hourly schedule and the BGW is a second safety net.
        logger.warning("partition_maintenance_startup_failed", error=str(e)[:200])

    # Register framework tools in KU API
    try:
        from analysi.db.session import get_db
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService.get_instance()

        # Register tools for default tenant
        async for session in get_db():
            tool_count = await registry.register_tools_in_ku_api(session, "default")
            logger.info("framework_tools_registered", count=tool_count)
            break  # Only need one iteration
    except Exception as e:
        logger.error("framework_tool_registration_failed", error=str(e))
        # Don't fail startup if tool registration fails

    # Configure MCP execution rate limiter (per-(tenant, user, tool) budget).
    # The redis client is lazy — its constructor doesn't connect, so we
    # install the limiter unconditionally. Real connection failures are
    # caught per-call by check_mcp_rate_limit's degrade-open path. This
    # avoids a permanent disable when Valkey is briefly unreachable at
    # boot (Codex review on PR #42 commit ca51f3add).
    try:
        import redis.asyncio as redis_async

        from analysi.auth.rate_limit import ValkeyRateLimiter
        from analysi.config.valkey_db import ValkeyDBConfig
        from analysi.mcp.rate_limit import set_mcp_limiter

        rl_settings = ValkeyDBConfig.get_redis_settings(ValkeyDBConfig.CACHE_DB)
        rl_client = redis_async.Redis(
            host=rl_settings.host,
            port=rl_settings.port,
            db=rl_settings.database,
            password=rl_settings.password,
            decode_responses=True,
        )
        # Default budget: 60 invocations/min per (tenant, user, tool).
        # Generous for legitimate use, tight enough to bound abuse.
        set_mcp_limiter(
            ValkeyRateLimiter(
                rl_client,
                max_attempts=60,
                window_seconds=60,
                key_prefix="mcp",
            )
        )
        logger.info("mcp_rate_limiter_configured", max_per_minute=60)
    except Exception as e:
        # Only failures of the import / settings lookup itself reach here.
        # Connection errors at request time are handled per-call.
        logger.warning("mcp_rate_limiter_setup_failed", error=str(e)[:200])

    # Start MCP session manager (unified analysi server)
    from analysi.mcp.router import _mcp_server

    async with _mcp_server.session_manager.run():
        logger.info("mcp_session_manager_started")
        yield

    logger.info("application_shutdown")
    await close_db_connections()


# Default error responses — ensures ProblemDetail appears in OpenAPI spec
_error_responses: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDetail}
    for status in (400, 401, 403, 404, 409, 422, 500, 503)
}

_openapi_tags = [
    # Alerts & routing
    {
        "name": "alerts",
        "description": "Security alerts from external sources (SIEM, EDR) — ingest, search, track analysis lifecycle, and manage dispositions",
    },
    {
        "name": "alert-routing",
        "description": "Analysis groups, routing rules, and workflow generation tracking that control how incoming alerts are assigned to Workflows",
    },
    # Tasks
    {
        "name": "tasks",
        "description": "Cy script definitions that each perform a single investigation or automation step — CRUD and script analysis",
    },
    {
        "name": "task-execution",
        "description": "Run saved Tasks or ad-hoc Cy scripts with any input — track status, retrieve logs, enrichments, and LLM usage",
    },
    {
        "name": "task-assist",
        "description": "LLM-powered Cy script autocomplete for the Task authoring editor",
    },
    {
        "name": "task-feedback",
        "description": "Analyst-authored guidance attached to Tasks (e.g., 'always check VT before closing') — stored as Knowledge Units in the KDG",
    },
    {
        "name": "task-building-runs",
        "description": "Internal progress tracking for AI-driven Task building jobs (used by workflow generation)",
    },
    {
        "name": "task-generations",
        "description": "Request AI to generate or modify a Task from a description or alert example — poll for progress and results",
    },
    # Workflows
    {
        "name": "workflows",
        "description": "DAG-based pipelines of Tasks — define, compose from shorthand, validate types, and manage node templates",
    },
    {
        "name": "workflow-execution",
        "description": "Run Workflows with any input, poll status, inspect per-node results, view the execution graph, or cancel",
    },
    # Integrations
    {
        "name": "integrations",
        "description": "Configured connections to external tools (SIEM, EDR, ticketing) — CRUD, health monitoring, connector discovery, runs, and schedules",
    },
    {
        "name": "integration-execution",
        "description": "Test-execute a single integration action (e.g., IP reputation lookup) and optionally capture its output schema",
    },
    # Knowledge
    {
        "name": "knowledge-units",
        "description": "Reusable knowledge (documents, lookup tables, search indexes) referenced by Tasks and Skills",
    },
    {
        "name": "skills",
        "description": "Packaged knowledge modules used by the platform's agentic runs — workflow generation, automatic alert triage, and similar AI-driven operations",
    },
    {
        "name": "content-reviews",
        "description": "Safety and quality gate for content added to Skills — runs content checks and optional LLM extraction before approval",
    },
    {
        "name": "kdg",
        "description": "Knowledge Dependency Graph — queryable graph of relationships between Tasks, Skills, and Knowledge Units",
    },
    # Credentials & secrets
    {
        "name": "credentials",
        "description": "Vault-backed encrypted secrets used to authenticate with integrations — store, rotate, decrypt, and associate",
    },
    # Chat
    {
        "name": "chat",
        "description": "Conversational AI assistant — manage conversations and stream messages via SSE",
    },
    # Control events
    {
        "name": "control-events",
        "description": "Transactional event bus — view event history, manually emit events, and monitor processing status",
    },
    {
        "name": "control-event-channels",
        "description": "Discover available event channels (system like disposition:ready, or custom) with their payload schemas",
    },
    {
        "name": "control-event-rules",
        "description": "Configurable rules that trigger a Task or Workflow when an event fires on a channel (e.g., create JIRA ticket on disposition)",
    },
    # Audit & operations
    {
        "name": "audit-trail",
        "description": "Immutable, append-only log of significant platform actions — filterable by actor, action, resource, and date range",
    },
    {
        "name": "bulk-operations",
        "description": "Destructive bulk-delete of tenant data (task runs, workflow runs, analyses) — owner role required",
    },
    {
        "name": "packs",
        "description": "Content packs — pre-built bundles of Tasks, Skills, KUs, and Workflows that can be installed or uninstalled as a unit",
    },
    # Auth & identity
    {
        "name": "api-keys",
        "description": "Tenant-scoped API keys for programmatic access — create, list, and revoke",
    },
    {
        "name": "members",
        "description": "Tenant membership management — invite users, assign roles (owner/admin/analyst/viewer), and revoke access",
    },
    {
        "name": "users",
        "description": "Global user identity records (read-only) — look up the current user or batch-resolve user IDs to profiles",
    },
    # Artifacts
    {
        "name": "artifacts",
        "description": "Files and structured outputs produced during Task or Workflow execution — upload, list, download, and delete",
    },
    # Platform admin
    {
        "name": "platform",
        "description": "Platform administration (platform_admin only) — tenant lifecycle, queue stats, DB health, and manual alert pull",
    },
    {"name": "health", "description": "Service health and readiness probes"},
]

app = FastAPI(
    title="Analysi API",
    description="AI Agent Platform for Cybersecurity",
    version="0.1.0",
    lifespan=lifespan,
    responses=_error_responses,
    openapi_tags=_openapi_tags,
)

# Prometheus metrics at /metrics — RED metrics + Python process metrics
from prometheus_fastapi_instrumentator import Instrumentator  # noqa: E402

Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/healthz", "/readyz", "/metrics"],
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
).instrument(app).expose(app, include_in_schema=False, should_gzip=True)

# OpenTelemetry FastAPI instrumentation
# No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset; adds spans per request when set
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass  # opentelemetry not installed — instrumentation disabled

# RFC 9457 error handling (registers exception handlers for HTTPException,
# RequestValidationError, SQLAlchemyError, and unhandled exceptions).
# Must be called before middleware registration so handlers are in place.
init_error_handling(app)

# Add middleware in reverse order (last added = outermost layer)
# NOTE: allow_methods and allow_headers are enumerated explicitly — combining
# wildcards with allow_credentials=True broadens the cross-origin attack
# surface without adding functional value.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Actor-User-Id",
        "X-Request-ID",
    ],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TenantValidationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# RequestIdMiddleware is outermost — generates UUID, measures full duration.
# RequestLoggingMiddleware reads request.state.request_id for correlation_id.
app.add_middleware(RequestIdMiddleware)

app.include_router(health.router)
app.include_router(v1.router, prefix="/v1")
app.include_router(platform.router)
# accept-invite is outside the v1 router (callers aren't members yet)
app.include_router(invitations.router)

# Mount unified MCP Streamable HTTP app with dynamic tenant support
# Handles: /v1/{tenant}/mcp/* (all 25 tools in single analysi server)
from starlette.routing import Mount  # noqa: E402
from starlette.routing import Router as StarletteRouter  # noqa: E402

from analysi.mcp.router import _base_mcp_app  # noqa: E402

mcp_router = StarletteRouter(
    routes=[
        Mount("/{tenant}/mcp", app=_base_mcp_app),
    ]
)
app.mount("/v1", mcp_router)


def start() -> None:
    uvicorn.run(
        "analysi.main:app",
        host="0.0.0.0",  # nosec B104
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )


def dev() -> None:
    uvicorn.run(
        "analysi.main:app",
        host="0.0.0.0",  # nosec B104
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        dev()
    else:
        start()
