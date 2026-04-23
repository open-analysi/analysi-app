"""Activity Audit Trail REST API endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    AuditPaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.activity_audit import (
    ActivityAuditCreate,
    ActivityAuditResponse,
    AuditSource,
)
from analysi.services.activity_audit_service import ActivityAuditService

logger = get_logger(__name__)
router = APIRouter(
    prefix="/{tenant}/audit-trail",
    tags=["audit-trail"],
    dependencies=[Depends(require_current_user)],
)


def get_service(db: AsyncSession = Depends(get_db)) -> ActivityAuditService:
    """Dependency to get ActivityAuditService instance."""
    repository = ActivityAuditRepository(db)
    return ActivityAuditService(repository)


@router.post(
    "",
    response_model=ApiResponse[ActivityAuditResponse],
    status_code=201,
    dependencies=[Depends(require_permission("audit_trail", "create"))],
)
async def record_activity(
    request: Request,
    data: ActivityAuditCreate,
    tenant: str = Depends(get_tenant_id),
    service: ActivityAuditService = Depends(get_service),
    current_user: CurrentUser = Depends(require_current_user),
) -> ApiResponse[ActivityAuditResponse]:
    """Record an activity audit event.

    This endpoint is used to log user and system actions for audit purposes.
    Events are immutable once created (append-only).

    The actor_id is automatically set from the authenticated user's UUID.
    Any client-supplied actor_id is overridden for security.
    """
    # Override actor_id with the authenticated user's DB UUID
    data.actor_id = current_user.db_user_id or SYSTEM_USER_ID

    logger.debug(
        "Recording activity",
        tenant_id=tenant,
        actor_id=data.actor_id,
        action=data.action,
        resource_type=data.resource_type,
        resource_id=data.resource_id,
    )

    result = await service.record_activity(tenant, data)

    logger.info(
        "Activity recorded",
        tenant_id=tenant,
        event_id=str(result.id),
        action=result.action,
    )

    return api_response(result, request=request)


@router.get(
    "",
    response_model=ApiListResponse[ActivityAuditResponse],
    dependencies=[Depends(require_permission("audit_trail", "read"))],
)
async def list_activities(
    request: Request,
    tenant: str = Depends(get_tenant_id),
    service: ActivityAuditService = Depends(get_service),
    pagination: AuditPaginationParams = Depends(),
    actor_id: UUID | None = Query(None, description="Filter by actor UUID"),
    source: AuditSource | None = Query(None, description="Filter by source subsystem"),
    action: str | None = Query(
        None, description="Filter by action (use % for prefix matching)"
    ),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    from_date: datetime | None = Query(
        None, description="Start of date range (inclusive)"
    ),
    to_date: datetime | None = Query(None, description="End of date range (exclusive)"),
) -> ApiListResponse[ActivityAuditResponse]:
    """List activity audit events with optional filters and pagination.

    Supports filtering by:
    - actor_id: Who performed the action
    - source: Which subsystem logged the event (rest_api, mcp, ui, internal)
    - action: What action was performed (supports prefix matching with %)
    - resource_type: Type of resource (alert, workflow, task, etc.)
    - resource_id: Specific resource ID
    - from_date/to_date: Date range

    Results are ordered by created_at descending (newest first).
    """
    items, total = await service.list_activities(
        tenant_id=tenant,
        actor_id=actor_id,
        source=source.value if source else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        from_date=from_date,
        to_date=to_date,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return api_list_response(items, total=total, request=request, pagination=pagination)


@router.get(
    "/{event_id}",
    response_model=ApiResponse[ActivityAuditResponse],
    dependencies=[Depends(require_permission("audit_trail", "read"))],
)
async def get_activity(
    request: Request,
    event_id: UUID,
    tenant: str = Depends(get_tenant_id),
    service: ActivityAuditService = Depends(get_service),
    created_at: datetime | None = Query(
        None,
        description="Created timestamp for partition hint (improves performance)",
    ),
) -> ApiResponse[ActivityAuditResponse]:
    """Get a single activity audit event by ID.

    Optionally provide created_at for better performance on partitioned table.
    """
    result = await service.get_activity(
        tenant_id=tenant,
        event_id=event_id,
        created_at=created_at,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Activity event not found")

    return api_response(result, request=request)
