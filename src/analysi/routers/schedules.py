"""Schedules REST API.

Generic CRUD for schedules plus convenience endpoints on Tasks and Workflows.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    PaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.schedule_repository import ScheduleRepository
from analysi.scheduler.interval import compute_next_run_at
from analysi.schemas.schedule import (
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
    TargetScheduleCreate,
)

logger = get_logger(__name__)

router = APIRouter(
    tags=["schedules"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_interval(schedule_type: str, schedule_value: str) -> None:
    """Raise 400 if the interval cannot be parsed."""
    result = compute_next_run_at(schedule_type, schedule_value)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid schedule interval: '{schedule_value}' for type '{schedule_type}'",
        )


async def _create_schedule_row(
    session: AsyncSession,
    tenant_id: str,
    target_type: str,
    target_id: UUID,
    schedule_type: str,
    schedule_value: str,
    timezone: str = "UTC",
    enabled: bool = False,
    params: dict | None = None,
    origin_type: str = "user",
    integration_id: str | None = None,
) -> ScheduleResponse:
    """Shared creation logic for generic + convenience endpoints."""
    _validate_interval(schedule_type, schedule_value)

    next_run_at = (
        compute_next_run_at(schedule_type, schedule_value) if enabled else None
    )

    repo = ScheduleRepository(session)
    schedule = await repo.create(
        tenant_id=tenant_id,
        target_type=target_type,
        target_id=target_id,
        schedule_type=schedule_type,
        schedule_value=schedule_value,
        timezone=timezone,
        enabled=enabled,
        params=params,
        origin_type=origin_type,
        integration_id=integration_id,
        next_run_at=next_run_at,
    )
    # Build response BEFORE commit to avoid expired-attribute errors
    response = ScheduleResponse.model_validate(schedule)
    await session.commit()
    return response


async def _update_schedule_fields(
    session: AsyncSession,
    tenant_id: str,
    schedule_id: UUID,
    body: ScheduleUpdate,
) -> ScheduleResponse:
    """Shared update logic: apply fields, recompute next_run_at, return response."""
    repo = ScheduleRepository(session)
    fields = body.model_dump(exclude_unset=True)

    if "schedule_value" in fields:
        _validate_interval("every", fields["schedule_value"])

    schedule = await repo.update(tenant_id, schedule_id, **fields)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Recompute next_run_at if interval or enabled changed
    if "schedule_value" in fields or "enabled" in fields:
        if schedule.enabled:
            new_next = compute_next_run_at(
                schedule.schedule_type, schedule.schedule_value
            )
            await repo.update(tenant_id, schedule_id, next_run_at=new_next)
            schedule.next_run_at = new_next
        else:
            await repo.update(tenant_id, schedule_id, next_run_at=None)
            schedule.next_run_at = None

    # Refresh to ensure all attributes are loaded before serialization
    await session.refresh(schedule)
    response = ScheduleResponse.model_validate(schedule)
    await session.commit()
    return response


async def _get_target_schedule_or_404(
    session: AsyncSession,
    tenant_id: str,
    target_type: str,
    target_id: UUID,
    entity_name: str = "target",
) -> "Schedule":  # noqa: F821 — forward ref for type checker
    """Look up a schedule by target; raise 404 if none exists."""
    repo = ScheduleRepository(session)
    schedule = await repo.get_by_target(tenant_id, target_type, target_id)
    if schedule is None:
        raise HTTPException(
            status_code=404,
            detail=f"No schedule found for this {entity_name}",
        )
    return schedule


# ---------------------------------------------------------------------------
# Generic schedules CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/{tenant}/schedules",
    response_model=ApiListResponse[ScheduleResponse],
)
async def list_schedules(
    request: Request,
    target_type: str | None = Query(None, description="Filter by 'task' or 'workflow'"),
    integration_id: str | None = Query(None, description="Filter by integration ID"),
    origin_type: str | None = Query(None, description="Filter by origin type"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiListResponse[ScheduleResponse]:
    """List schedules with optional filters."""
    repo = ScheduleRepository(session)
    schedules = await repo.list_by_tenant(
        tenant_id,
        target_type=target_type,
        integration_id=integration_id,
        origin_type=origin_type,
        enabled=enabled,
        limit=limit,
        offset=skip,
    )
    items = [ScheduleResponse.model_validate(s) for s in schedules]
    pagination = PaginationParams(limit=limit, offset=skip)
    return api_list_response(
        items,
        total=len(items),
        request=request,
        pagination=pagination,
    )


@router.post(
    "/{tenant}/schedules",
    response_model=ApiResponse[ScheduleResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def create_schedule(
    body: ScheduleCreate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Create a new schedule."""
    schedule_resp = await _create_schedule_row(
        session=session,
        tenant_id=tenant_id,
        target_type=body.target_type,
        target_id=body.target_id,
        schedule_type=body.schedule_type,
        schedule_value=body.schedule_value,
        timezone=body.timezone,
        enabled=body.enabled,
        params=body.params,
        origin_type=body.origin_type,
        integration_id=body.integration_id,
    )
    return api_response(schedule_resp, request=request)


@router.patch(
    "/{tenant}/schedules/{schedule_id}",
    response_model=ApiResponse[ScheduleResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_schedule(
    schedule_id: UUID,
    body: ScheduleUpdate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Update a schedule."""
    resp = await _update_schedule_fields(session, tenant_id, schedule_id, body)
    return api_response(resp, request=request)


@router.delete(
    "/{tenant}/schedules/{schedule_id}",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def delete_schedule(
    schedule_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a schedule."""
    repo = ScheduleRepository(session)
    deleted = await repo.delete(tenant_id, schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await session.commit()


# ---------------------------------------------------------------------------
# Task convenience endpoints (1:1 task <-> schedule)
# ---------------------------------------------------------------------------


@router.post(
    "/{tenant}/tasks/{task_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def create_task_schedule(
    task_id: UUID,
    body: TargetScheduleCreate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Attach a schedule to a task (1:1 relationship)."""
    repo = ScheduleRepository(session)
    existing = await repo.get_by_target(tenant_id, "task", task_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Task already has a schedule. Use PATCH to modify or DELETE to replace.",
        )

    schedule_resp = await _create_schedule_row(
        session=session,
        tenant_id=tenant_id,
        target_type="task",
        target_id=task_id,
        schedule_type=body.schedule_type,
        schedule_value=body.schedule_value,
        timezone=body.timezone,
        enabled=body.enabled,
        params=body.params,
    )
    return api_response(schedule_resp, request=request)


@router.get(
    "/{tenant}/tasks/{task_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
)
async def get_task_schedule(
    task_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Get the schedule attached to a task (404 if none)."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "task", task_id, "task"
    )
    return api_response(ScheduleResponse.model_validate(schedule), request=request)


@router.patch(
    "/{tenant}/tasks/{task_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_task_schedule(
    task_id: UUID,
    body: ScheduleUpdate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Update the schedule attached to a task."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "task", task_id, "task"
    )
    resp = await _update_schedule_fields(session, tenant_id, schedule.id, body)
    return api_response(resp, request=request)


@router.delete(
    "/{tenant}/tasks/{task_id}/schedule",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def delete_task_schedule(
    task_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Remove the schedule from a task."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "task", task_id, "task"
    )
    repo = ScheduleRepository(session)
    await repo.delete(tenant_id, schedule.id)
    await session.commit()


# ---------------------------------------------------------------------------
# Workflow convenience endpoints (1:1 workflow <-> schedule)
# ---------------------------------------------------------------------------


@router.post(
    "/{tenant}/workflows/{workflow_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def create_workflow_schedule(
    workflow_id: UUID,
    body: TargetScheduleCreate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Attach a schedule to a workflow (1:1 relationship)."""
    repo = ScheduleRepository(session)
    existing = await repo.get_by_target(tenant_id, "workflow", workflow_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Workflow already has a schedule. Use PATCH to modify or DELETE to replace.",
        )

    schedule_resp = await _create_schedule_row(
        session=session,
        tenant_id=tenant_id,
        target_type="workflow",
        target_id=workflow_id,
        schedule_type=body.schedule_type,
        schedule_value=body.schedule_value,
        timezone=body.timezone,
        enabled=body.enabled,
        params=body.params,
    )
    return api_response(schedule_resp, request=request)


@router.get(
    "/{tenant}/workflows/{workflow_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
)
async def get_workflow_schedule(
    workflow_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Get the schedule attached to a workflow (404 if none)."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "workflow", workflow_id, "workflow"
    )
    return api_response(ScheduleResponse.model_validate(schedule), request=request)


@router.patch(
    "/{tenant}/workflows/{workflow_id}/schedule",
    response_model=ApiResponse[ScheduleResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_workflow_schedule(
    workflow_id: UUID,
    body: ScheduleUpdate,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ScheduleResponse]:
    """Update the schedule attached to a workflow."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "workflow", workflow_id, "workflow"
    )
    resp = await _update_schedule_fields(session, tenant_id, schedule.id, body)
    return api_response(resp, request=request)


@router.delete(
    "/{tenant}/workflows/{workflow_id}/schedule",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def delete_workflow_schedule(
    workflow_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Remove the schedule from a workflow."""
    schedule = await _get_target_schedule_or_404(
        session, tenant_id, "workflow", workflow_id, "workflow"
    )
    repo = ScheduleRepository(session)
    await repo.delete(tenant_id, schedule.id)
    await session.commit()
