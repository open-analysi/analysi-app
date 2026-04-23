"""
Managed Resources Router.

Convenience endpoints scoped to an integration for managing its
auto-created Tasks and Schedules (alert ingestion, health check).
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
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
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.models.task_run import TaskRun
from analysi.repositories.schedule_repository import ScheduleRepository
from analysi.scheduler.interval import compute_next_run_at
from analysi.schemas.integration import (
    ManagedAdHocRunResult,
    ManagedResourceSummary,
    ManagedRunItem,
    ManagedScheduleDetail,
    ManagedTaskDetail,
)
from analysi.services.managed_resources import (
    list_managed_resources as svc_list_managed_resources,
)
from analysi.services.managed_resources import (
    resolve_managed_resource,
    trigger_ad_hoc_run,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/integrations/{integration_id}/managed",
    tags=["managed-resources"],
    dependencies=[Depends(require_permission("integrations", "read"))],
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ManagedScheduleUpdate(BaseModel):
    """Body for updating a managed resource schedule."""

    schedule_value: str | None = None
    enabled: bool | None = None


class ManagedTaskUpdate(BaseModel):
    """Body for updating a managed resource task."""

    name: str | None = None
    description: str | None = None
    script: str | None = None


class ManagedAdHocRunRequest(BaseModel):
    """Body for triggering an ad-hoc run of a managed resource."""

    params: dict[str, Any] | None = Field(None, description="Optional parameters")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource_to_schema(resource) -> ManagedResourceSummary:
    """Convert a ManagedResource dataclass to a response schema."""
    return ManagedResourceSummary(
        resource_key=resource.resource_key,
        task_id=str(resource.task_id),
        task_name=resource.task_name,
        schedule_id=str(resource.schedule_id) if resource.schedule_id else None,
        schedule=resource.schedule,
        last_run=resource.last_run,
        next_run_at=(
            resource.next_run_at.isoformat() if resource.next_run_at else None
        ),
    )


async def _resolve_or_404(
    session: AsyncSession,
    tenant: str,
    integration_id: str,
    resource_key: str,
):
    """Resolve a managed resource or raise 404."""
    resource = await resolve_managed_resource(
        session, tenant, integration_id, resource_key
    )
    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Managed resource not found",
        )
    return resource


async def _load_managed_task(session: AsyncSession, tenant: str, task_id: UUID) -> Task:
    """Load a Task by component_id with its Component, or raise 404."""
    stmt = (
        select(Task)
        .join(Component, Task.component_id == Component.id)
        .where(
            and_(
                Component.id == task_id,
                Component.tenant_id == tenant,
            )
        )
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.refresh(task, ["component"])
    return task


def _task_to_schema(task: Task, include_created_at: bool = False) -> ManagedTaskDetail:
    """Build a ManagedTaskDetail from a Task with its loaded Component."""
    return ManagedTaskDetail(
        task_id=str(task.component.id),
        name=task.component.name,
        description=task.component.description,
        script=task.script,
        function=task.function,
        scope=task.scope,
        origin_type=task.origin_type,
        integration_id=task.integration_id,
        created_at=(
            task.component.created_at.isoformat() if include_created_at else None
        ),
    )


def _schedule_to_schema(schedule) -> ManagedScheduleDetail:
    """Build a ManagedScheduleDetail from a Schedule model."""
    return ManagedScheduleDetail(
        schedule_id=str(schedule.id),
        schedule_type=schedule.schedule_type,
        schedule_value=schedule.schedule_value,
        enabled=schedule.enabled,
        timezone=schedule.timezone,
        next_run_at=(
            schedule.next_run_at.isoformat() if schedule.next_run_at else None
        ),
        last_run_at=(
            schedule.last_run_at.isoformat() if schedule.last_run_at else None
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ApiResponse[dict[str, ManagedResourceSummary]],
)
async def list_managed_resources_endpoint(
    tenant: str,
    integration_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, ManagedResourceSummary]]:
    """List all managed resources for an integration."""
    resources = await svc_list_managed_resources(session, tenant, integration_id)
    result = {key: _resource_to_schema(r) for key, r in resources.items()}
    return api_response(result, request=request)


@router.get("/{resource_key}/task", response_model=ApiResponse[ManagedTaskDetail])
async def get_managed_task(
    tenant: str,
    integration_id: str,
    resource_key: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ManagedTaskDetail]:
    """Get the Task details for a managed resource."""
    resource = await _resolve_or_404(session, tenant, integration_id, resource_key)
    task = await _load_managed_task(session, tenant, resource.task_id)
    return api_response(_task_to_schema(task, include_created_at=True), request=request)


@router.put(
    "/{resource_key}/task",
    response_model=ApiResponse[ManagedTaskDetail],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def update_managed_task(
    tenant: str,
    integration_id: str,
    resource_key: str,
    body: ManagedTaskUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ManagedTaskDetail]:
    """Update the Task for a managed resource."""
    resource = await _resolve_or_404(session, tenant, integration_id, resource_key)
    task = await _load_managed_task(session, tenant, resource.task_id)

    if body.name is not None:
        task.component.name = body.name
    if body.description is not None:
        task.component.description = body.description
    if body.script is not None:
        task.script = body.script

    await session.flush()
    return api_response(_task_to_schema(task), request=request)


@router.get(
    "/{resource_key}/schedule",
    response_model=ApiResponse[ManagedScheduleDetail],
)
async def get_managed_schedule(
    tenant: str,
    integration_id: str,
    resource_key: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ManagedScheduleDetail]:
    """Get the Schedule for a managed resource."""
    resource = await _resolve_or_404(session, tenant, integration_id, resource_key)

    if resource.schedule_id is None:
        raise HTTPException(
            status_code=404, detail="No schedule for this managed resource"
        )

    repo = ScheduleRepository(session)
    schedule = await repo.get(tenant, resource.schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return api_response(_schedule_to_schema(schedule), request=request)


@router.put(
    "/{resource_key}/schedule",
    response_model=ApiResponse[ManagedScheduleDetail],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def update_managed_schedule(
    tenant: str,
    integration_id: str,
    resource_key: str,
    body: ManagedScheduleUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ManagedScheduleDetail]:
    """Update the Schedule for a managed resource."""
    resource = await _resolve_or_404(session, tenant, integration_id, resource_key)

    if resource.schedule_id is None:
        raise HTTPException(
            status_code=404, detail="No schedule for this managed resource"
        )

    repo = ScheduleRepository(session)
    fields: dict[str, Any] = {}

    if body.schedule_value is not None:
        test_next = compute_next_run_at("every", body.schedule_value)
        if test_next is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid schedule interval: '{body.schedule_value}'",
            )
        fields["schedule_value"] = body.schedule_value

    if body.enabled is not None:
        fields["enabled"] = body.enabled

    schedule = await repo.update(tenant, resource.schedule_id, **fields)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Recompute next_run_at only when interval or enabled status changes
    if "schedule_value" in fields or "enabled" in fields:
        if schedule.enabled:
            new_next = compute_next_run_at(
                schedule.schedule_type, schedule.schedule_value
            )
            await repo.update(tenant, resource.schedule_id, next_run_at=new_next)
            schedule.next_run_at = new_next
        else:
            await repo.update(tenant, resource.schedule_id, next_run_at=None)
            schedule.next_run_at = None

    await session.flush()

    return api_response(_schedule_to_schema(schedule), request=request)


@router.get("/{resource_key}/runs", response_model=ApiListResponse[ManagedRunItem])
async def list_managed_runs(
    tenant: str,
    integration_id: str,
    resource_key: str,
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> ApiListResponse[ManagedRunItem]:
    """List TaskRuns for a managed resource."""
    resource = await _resolve_or_404(session, tenant, integration_id, resource_key)

    query = (
        select(TaskRun)
        .where(
            and_(
                TaskRun.tenant_id == tenant,
                TaskRun.task_id == resource.task_id,
            )
        )
        .order_by(desc(TaskRun.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(query)
    runs = list(result.scalars().all())

    count_q = select(func.count(TaskRun.id)).where(
        and_(
            TaskRun.tenant_id == tenant,
            TaskRun.task_id == resource.task_id,
        )
    )
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    items = [
        ManagedRunItem(
            task_run_id=str(run.id),
            status=run.status,
            run_context=run.run_context,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            created_at=run.created_at.isoformat(),
        )
        for run in runs
    ]

    pagination = PaginationParams(limit=limit, offset=skip)
    return api_list_response(items, total=total, request=request, pagination=pagination)


@router.post(
    "/{resource_key}/run",
    response_model=ApiResponse[ManagedAdHocRunResult],
    status_code=202,
    dependencies=[Depends(require_permission("integrations", "execute"))],
)
async def trigger_managed_run(
    tenant: str,
    integration_id: str,
    resource_key: str,
    request: Request,
    body: ManagedAdHocRunRequest | None = None,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[ManagedAdHocRunResult]:
    """Trigger an ad-hoc run of a managed resource."""
    params = body.params if body else None

    try:
        result = await trigger_ad_hoc_run(
            session, tenant, integration_id, resource_key, params
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Managed resource not found")

    await session.commit()
    return api_response(ManagedAdHocRunResult(**result), request=request)
