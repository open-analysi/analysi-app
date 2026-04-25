"""Platform-scoped API endpoints (Project Delos).

All endpoints require platform_admin role (Keycloak realm role).
Prefix: /platform/v1

Includes:
- Tenant lifecycle management (CRUD)
- Queue statistics
- Trigger alert pull
- Database health check
"""

from typing import Annotated

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from analysi.api.pagination import PaginationParams
from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_platform_admin
from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger
from analysi.constants import PackConstants
from analysi.db.session import get_db
from analysi.dependencies.audit import get_audit_context
from analysi.models.auth import Membership
from analysi.models.component import Component
from analysi.models.workflow import Workflow
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.tenant import (
    CascadeDeleteResponse,
    TenantCreate,
    TenantDetailResponse,
    TenantResponse,
)
from analysi.services.tenant import TenantService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/platform/v1",
    tags=["platform"],
    dependencies=[Depends(require_platform_admin)],
)


@router.post(
    "/tenants",
    response_model=ApiResponse[TenantResponse | None],
    status_code=201,
    summary="Create a new tenant",
)
async def create_tenant(
    body: TenantCreate,
    request: Request,
    dry_run: bool = Query(False, description="Validate only, do not persist"),
    db: AsyncSession = Depends(get_db),
    audit_context: Annotated[AuditContext, Depends(get_audit_context)] = None,
    current_user: CurrentUser = Depends(require_platform_admin),
) -> ApiResponse[TenantResponse | None]:
    """Create a new tenant. Pass ?dry_run=true to validate without creating."""
    service = TenantService(db)
    try:
        tenant = await service.create_tenant(
            tenant_id=body.id,
            name=body.name,
            owner_email=body.owner_email,
            dry_run=dry_run,
        )
    except ValueError as e:
        logger.warning("tenant_create_validation_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid tenant configuration")

    if dry_run:
        return api_response(None, request=request)

    await db.commit()

    # Audit trail
    if audit_context:
        audit_repo = ActivityAuditRepository(db)
        await audit_repo.create(
            tenant_id=body.id,
            action="tenant.created",
            resource_type="tenant",
            resource_id=body.id,
            actor_id=audit_context.actor_user_id,
            actor_type=audit_context.actor_type,
            source=audit_context.source,
            details={"name": body.name},
        )
        await db.commit()

    return api_response(TenantResponse.model_validate(tenant), request=request)


@router.get(
    "/tenants",
    response_model=ApiListResponse[TenantResponse],
    summary="List all tenants",
)
async def list_tenants(
    request: Request,
    status: str | None = Query(
        None, description="Filter by status (active, suspended)"
    ),
    has_schedules: bool | None = Query(
        None,
        description="Filter to tenants with enabled integration schedules",
    ),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[TenantResponse]:
    """List all tenants with optional filters.

    Replaces the former GET /admin/v1/tenants-with-schedules endpoint
    when called with ?has_schedules=true.
    """
    service = TenantService(db)
    tenants, total = await service.list_tenants(
        status=status,
        has_schedules=has_schedules,
        skip=pagination.offset,
        limit=pagination.limit,
    )

    return api_list_response(
        [TenantResponse.model_validate(t) for t in tenants],
        total=total,
        request=request,
        pagination=pagination,
    )


@router.get(
    "/tenants/{tenant_id}",
    response_model=ApiResponse[TenantDetailResponse],
    summary="Describe a tenant",
)
async def describe_tenant(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantDetailResponse]:
    """Get detailed tenant information including member and component counts."""
    service = TenantService(db)
    tenant = await service.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Member count
    member_count_result = await db.execute(
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id)
    )
    member_count = member_count_result.scalar() or 0

    # Component counts by kind
    component_counts_result = await db.execute(
        select(Component.kind, func.count())
        .where(Component.tenant_id == tenant_id)
        .group_by(Component.kind)
    )
    component_counts = dict(component_counts_result.all())

    # Workflow count
    workflow_count_result = await db.execute(
        select(func.count())
        .select_from(Workflow)
        .where(Workflow.tenant_id == tenant_id)
    )
    workflow_count = workflow_count_result.scalar() or 0
    component_counts["workflows"] = workflow_count

    # Installed packs (distinct app values != 'default')
    packs_result = await db.execute(
        select(Component.app)
        .where(
            Component.tenant_id == tenant_id, Component.app != PackConstants.DEFAULT_APP
        )
        .distinct()
    )
    packs = [row[0] for row in packs_result.all()]

    workflow_packs_result = await db.execute(
        select(Workflow.app)
        .where(
            Workflow.tenant_id == tenant_id, Workflow.app != PackConstants.DEFAULT_APP
        )
        .distinct()
    )
    packs.extend(row[0] for row in workflow_packs_result.all())
    installed_packs = sorted(set(packs))

    detail = TenantDetailResponse(
        id=tenant.id,
        name=tenant.name,
        status=tenant.status,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        member_count=member_count,
        component_counts=component_counts,
        installed_packs=installed_packs,
    )
    return api_response(detail, request=request)


@router.delete(
    "/tenants/{tenant_id}",
    response_model=ApiResponse[CascadeDeleteResponse],
    summary="Delete a tenant and all its data",
)
async def delete_tenant(
    tenant_id: str,
    request: Request,
    confirm: str = Query(
        ..., description="Must match tenant_id as safety confirmation"
    ),
    db: AsyncSession = Depends(get_db),
    audit_context: Annotated[AuditContext, Depends(get_audit_context)] = None,
) -> ApiResponse[CascadeDeleteResponse]:
    """Cascade delete a tenant and ALL its data. Requires ?confirm={tenant_id}."""
    if confirm != tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Confirmation does not match tenant ID",
        )

    service = TenantService(db)

    try:
        deleted_counts = await service.cascade_delete_tenant(tenant_id)
    except ValueError as e:
        logger.warning("tenant_delete_not_found", error=str(e))
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Audit trail AFTER cascade (the cascade deletes old audit rows for this
    # tenant; this new entry is inserted after and survives the single commit)
    if audit_context:
        audit_repo = ActivityAuditRepository(db)
        await audit_repo.create(
            tenant_id=tenant_id,
            action="tenant.deleted",
            resource_type="tenant",
            resource_id=tenant_id,
            actor_id=audit_context.actor_user_id,
            actor_type=audit_context.actor_type,
            source=audit_context.source,
            details={"action": "cascade_delete", **deleted_counts},
        )

    await db.commit()

    return api_response(
        CascadeDeleteResponse(
            tenant_id=tenant_id,
            tables_affected=len(deleted_counts),
            total_rows_deleted=sum(deleted_counts.values()),
            details=deleted_counts,
        ),
        request=request,
    )


# ---------------------------------------------------------------------------
# Platform operations
# ---------------------------------------------------------------------------


class DatabaseHealth(BaseModel):
    """Database health status."""

    status: str
    database: str


@router.get(
    "/health/db",
    response_model=ApiResponse[DatabaseHealth],
    summary="Database health check",
)
async def database_health(
    request: Request, db: AsyncSession = Depends(get_db)
) -> ApiResponse[DatabaseHealth] | JSONResponse:
    """Database health check — requires platform admin."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return api_response(
            DatabaseHealth(status="healthy", database="connected"),
            request=request,
        )
    except Exception as e:
        logger.error("health_check_db_failure", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "data": {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "error": "Database connection failed",
                },
            },
        )


class QueueStatsResponse(BaseModel):
    """Response model for queue statistics."""

    queue_length: int = Field(description="Total jobs in queue")
    in_progress_jobs: int = Field(description="Jobs currently being processed")
    cron_markers: int = Field(description="Cron job markers (internal)")
    jobs_by_tenant: dict[str, int] = Field(description="Queue breakdown by tenant")


@router.get(
    "/queue/stats",
    response_model=ApiResponse[QueueStatsResponse],
    summary="Get analysis queue statistics",
)
async def get_analysis_queue_stats(
    request: Request,
) -> ApiResponse[QueueStatsResponse]:
    """Get statistics about the alert analysis queue."""
    from analysi.alert_analysis.queue_cleanup import get_queue_stats
    from analysi.config.valkey_db import ValkeyDBConfig

    try:
        redis_settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        stats = await get_queue_stats(redis_settings)

        return api_response(
            QueueStatsResponse(
                queue_length=stats["queue_length"],
                in_progress_jobs=stats["in_progress_jobs"],
                cron_markers=stats["cron_markers"],
                jobs_by_tenant=stats["jobs_by_tenant"],
            ),
            request=request,
        )
    except Exception:
        logger.exception("Failed to get queue stats")
        raise HTTPException(status_code=500, detail="Failed to get queue stats")


class TriggerAlertPullRequest(BaseModel):
    """Request model for triggering alert pull."""

    connector_type: str = Field(
        default="splunk",
        description="Type of connector to trigger (e.g., splunk, crowdstrike)",
    )
    tenant_id: str = Field(
        default="default", description="Tenant ID to pull alerts for"
    )


class TriggerAlertPullResponse(BaseModel):
    """Response model for alert pull trigger."""

    status: str
    job_id: str | None
    connector_type: str
    tenant_id: str
    queue_name: str
    redis_db: int
    message: str


@router.post(
    "/trigger-alert-pull",
    response_model=ApiResponse[TriggerAlertPullResponse],
    summary="Manually trigger alert pull from connector",
)
async def trigger_alert_pull(
    body: TriggerAlertPullRequest,
    request: Request,
) -> ApiResponse[TriggerAlertPullResponse]:
    """Manually trigger an alert pull job for a specific tenant and connector."""
    from analysi.integrations.config import IntegrationConfig

    try:
        redis_settings = IntegrationConfig.get_redis_settings()
        queue_name = IntegrationConfig.get_queue_name(body.tenant_id)
        pool = await create_pool(redis_settings)

        try:
            function_name = (
                "pull_splunk_alerts"
                if body.connector_type == "splunk"
                else "pull_alerts_generic"
            )
            job = await pool.enqueue_job(
                function_name,
                tenant_id=body.tenant_id,
                _queue_name=queue_name,
            )

            logger.info(
                "enqueued_alert_pull_job",
                job_id=job.job_id,
                tenant_id=body.tenant_id,
                connector=body.connector_type,
                queue=queue_name,
            )

            return api_response(
                TriggerAlertPullResponse(
                    status="queued",
                    job_id=job.job_id,
                    connector_type=body.connector_type,
                    tenant_id=body.tenant_id,
                    queue_name=queue_name,
                    redis_db=IntegrationConfig.REDIS_DB,
                    message="Alert pull job queued successfully.",
                ),
                request=request,
            )
        finally:
            await pool.close()

    except Exception:
        logger.exception("Failed to queue alert pull job")
        raise HTTPException(status_code=500, detail="Failed to queue alert pull job")
