"""Task Generations API - public endpoint for standalone task creation.

POST /v1/{tenant}/task-generations  -> Create a task generation (enqueues ARQ job)
GET  /v1/{tenant}/task-generations/{id}  -> Poll generation status/progress
GET  /v1/{tenant}/task-generations  -> List standalone task generations for tenant
"""

from typing import Annotated, Any
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.pagination import PaginationParams
from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import (
    CurrentUser,
    require_current_user,
    require_permission,
)
from analysi.auth.messages import INSUFFICIENT_PERMISSIONS
from analysi.auth.permissions import has_permission
from analysi.config.logging import get_logger
from analysi.config.valkey_db import ValkeyDBConfig
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.models.alert import Alert
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.repositories.task_generation_repository import (
    TaskGenerationRepository,
)
from analysi.schemas.task_generation import (
    TaskBuildRequest,
    TaskBuildResponse,
    TaskGenerationResponse,
    TaskGenerationStatus,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/task-generations",
    tags=["task-generations"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


# Dependency injection
async def get_task_generation_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskGenerationRepository:
    return TaskGenerationRepository(session)


@router.post(
    "",
    response_model=ApiResponse[TaskBuildResponse],
    status_code=202,
    dependencies=[Depends(require_permission("tasks", "create"))],
)
async def create_task_generation(
    body: TaskBuildRequest,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repo)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
) -> ApiResponse[TaskBuildResponse]:
    """Submit a task generation request.

    Creates a TaskGeneration record and enqueues an ARQ job on the
    alert-analysis worker, which has the Claude Agent SDK installed.

    Supports two modes:
    - From scratch: Only provide description (and optionally alert_id).
    - With starting point: Provide task_id of an existing task to modify.

    Returns 202 Accepted with the run ID for polling.
    """
    # Validate alert existence if provided
    if body.alert_id:
        stmt = select(Alert).where(
            Alert.id == body.alert_id,
            Alert.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail=f"Alert {body.alert_id} not found for tenant {tenant_id}",
            )

    # Build input_context — always includes description
    input_context: dict[str, Any] = {"description": body.description}

    # If task_id provided, fetch the existing task as starting point
    # Modification mode requires tasks.update permission (router only checks tasks.read)
    if body.task_id:
        if not current_user.is_platform_admin and not has_permission(
            current_user.roles, "tasks", "update"
        ):
            raise HTTPException(
                status_code=403,
                detail=INSUFFICIENT_PERMISSIONS,
            )
        stmt = (
            select(Task)
            .join(Component)
            .where(
                Component.id == body.task_id,
                Component.tenant_id == tenant_id,
            )
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(
                status_code=404,
                detail=f"Task {body.task_id} not found for tenant {tenant_id}",
            )
        # Load component relationship for name/description/cy_name
        await session.refresh(task, ["component"])

        # Block modification of system-only tasks
        if task.component.system_only:
            raise HTTPException(
                status_code=403,
                detail=f"Task {body.task_id} is system-only and cannot be modified",
            )

        input_context["existing_task"] = {
            "task_id": str(task.component_id),
            "cy_name": task.component.cy_name,
            "name": task.component.name,
            "description": task.component.description,
            "script": task.script,
            "directive": task.directive,
            "data_samples": task.data_samples,
            "function": task.function,
            "scope": task.scope,
        }

    # Create tracking record
    creator_id = current_user.db_user_id or SYSTEM_USER_ID
    run = await repo.create_standalone(
        tenant_id=tenant_id,
        description=body.description,
        input_context=input_context,
        alert_id=body.alert_id,
        created_by=creator_id,
    )
    await session.commit()

    # Enqueue ARQ job on the alert-analysis worker (same Redis DB as alert processing)
    redis_settings = ValkeyDBConfig.get_redis_settings(
        database=ValkeyDBConfig.ALERT_PROCESSING_DB
    )
    try:
        redis = await create_pool(redis_settings)
        try:
            job = await redis.enqueue_job(
                "analysi.agentic_orchestration.jobs.task_build_job.execute_task_build",
                str(run.id),
                tenant_id,
                body.description,
                str(body.alert_id) if body.alert_id else None,
                input_context,
                str(creator_id),
            )
            logger.info(
                "enqueued_task_generation_job",
                job_id=job.job_id,
                run_id=str(run.id),
                tenant_id=tenant_id,
                alert_id=str(body.alert_id),
                has_starting_point="existing_task" in input_context,
            )
        finally:
            await redis.aclose()
    except Exception as e:
        # Mark the run as failed so it doesn't stay stuck as 'new' forever
        logger.error(
            "failed_to_enqueue_task_build_job_for_run", id=run.id, error=str(e)
        )
        run.status = TaskGenerationStatus.FAILED
        run.result = {
            "error": f"Failed to enqueue job: {e}",
            "error_type": "EnqueueError",
        }
        await session.commit()
        raise HTTPException(
            status_code=503,
            detail="Task generation service temporarily unavailable. Please retry.",
        )

    return api_response(
        TaskBuildResponse(
            id=run.id,
            status=run.status,
            description=run.description,
            alert_id=run.alert_id,
            task_id=body.task_id,
            created_at=run.created_at,
        ),
        request=request,
    )


@router.get("/{generation_id}", response_model=ApiResponse[TaskGenerationResponse])
async def get_task_generation(
    generation_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repo)],
) -> ApiResponse[TaskGenerationResponse]:
    """Get task generation status, progress, and result.

    Poll this endpoint to track progress of a standalone task generation.
    """
    run = await repo.get_by_id(tenant_id=tenant_id, run_id=generation_id)
    if not run:
        raise HTTPException(status_code=404, detail="Task generation not found")
    # Enforce source='api' — don't expose Kea-internal builds through this endpoint
    if run.source != "api":
        raise HTTPException(status_code=404, detail="Task generation not found")
    return api_response(TaskGenerationResponse.model_validate(run), request=request)


@router.get("", response_model=ApiListResponse[TaskGenerationResponse])
async def list_task_generations(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repo)],
    pagination: PaginationParams = Depends(),
) -> ApiListResponse[TaskGenerationResponse]:
    """List standalone task generations for a tenant.

    Only returns generations created via this API (source='api'),
    not Kea-internal workflow generation builds.
    """
    runs, total = await repo.list_by_source(
        tenant_id=tenant_id,
        source="api",
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return api_list_response(
        [TaskGenerationResponse.model_validate(r) for r in runs],
        total=total,
        pagination=pagination,
        request=request,
    )
