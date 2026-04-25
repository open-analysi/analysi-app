"""Task Generations Internal API endpoints (Kea internal).

These endpoints are used by the orchestration layer for tracking
parallel task building progress during workflow generation.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.pagination import PaginationParams
from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.task_generation_repository import (
    TaskGenerationRepository,
)
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.task_generation import (
    TaskGenerationCreate,
    TaskGenerationProgressAppend,
    TaskGenerationResponse,
    TaskGenerationStatusUpdate,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/task-generations-internal",
    tags=["task-generations-internal"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


# Dependency injection
async def get_task_generation_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskGenerationRepository:
    """Dependency injection for TaskGenerationRepository."""
    return TaskGenerationRepository(session)


# Endpoints
@router.post(
    "",
    response_model=ApiResponse[TaskGenerationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "create"))],
)
async def create_task_generation(
    run_data: TaskGenerationCreate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repository)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[TaskGenerationResponse]:
    """Create a new task generation record (Kea internal).

    Called before each parallel task in Stage 3 (Task Building) to create
    a record for tracking progress and results.

    For standalone task builds, use POST /v1/{tenant}/task-generations instead.
    """
    if run_data.workflow_generation_id is None:
        raise HTTPException(
            status_code=400,
            detail="workflow_generation_id is required. "
            "For standalone builds, use POST /v1/{tenant}/task-generations.",
        )
    # Always derive created_by from authenticated user (prevent impersonation)
    run = await repo.create(
        tenant_id=tenant_id,
        workflow_generation_id=run_data.workflow_generation_id,
        input_context=run_data.input_context,
        created_by=audit_context.actor_user_id,
    )
    return api_response(TaskGenerationResponse.model_validate(run), request=request)


@router.get("/{run_id}", response_model=ApiResponse[TaskGenerationResponse])
async def get_task_generation_internal(
    run_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repository)],
) -> ApiResponse[TaskGenerationResponse]:
    """Get a task generation by ID."""
    run = await repo.get_by_id(tenant_id=tenant_id, run_id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Task generation not found")
    return api_response(TaskGenerationResponse.model_validate(run), request=request)


@router.get("", response_model=ApiListResponse[TaskGenerationResponse])
async def list_task_generations_internal(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repository)],
    workflow_generation_id: UUID | None = None,
    pagination: PaginationParams = Depends(),
) -> ApiListResponse[TaskGenerationResponse]:
    """List task generations, optionally filtered by workflow generation."""
    if workflow_generation_id:
        runs = await repo.list_by_workflow_generation(
            tenant_id=tenant_id,
            workflow_generation_id=workflow_generation_id,
        )
        total = len(runs)
    else:
        # List all runs with pagination
        runs, total = await repo.list_all(
            tenant_id=tenant_id,
            limit=pagination.limit,
            offset=pagination.offset,
        )

    run_responses = [TaskGenerationResponse.model_validate(r) for r in runs]
    return api_list_response(
        run_responses,
        total=total,
        pagination=pagination,
        request=request,
    )


@router.patch(
    "/{run_id}/status",
    response_model=ApiResponse[TaskGenerationResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_task_generation_status(
    run_id: UUID,
    status_update: TaskGenerationStatusUpdate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repository)],
) -> ApiResponse[TaskGenerationResponse]:
    """Update task generation status and optionally result.

    Called when task building completes (completed/failed) or is cancelled.
    """
    run = await repo.update_status(
        tenant_id=tenant_id,
        run_id=run_id,
        status=status_update.status.value,
        result=status_update.result,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Task generation not found")
    return api_response(TaskGenerationResponse.model_validate(run), request=request)


@router.post(
    "/{run_id}/progress",
    response_model=ApiResponse[TaskGenerationResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def append_progress_messages(
    run_id: UUID,
    progress_data: TaskGenerationProgressAppend,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[TaskGenerationRepository, Depends(get_task_generation_repository)],
) -> ApiResponse[TaskGenerationResponse]:
    """Append progress messages to a task generation.

    Messages are appended to the progress_messages array with FIFO limit (100 max).
    Older messages are dropped when the limit is exceeded.
    """
    # Convert Pydantic models to dicts for storage
    messages = [msg.model_dump(mode="json") for msg in progress_data.messages]

    run = await repo.append_progress_messages(
        tenant_id=tenant_id,
        run_id=run_id,
        messages=messages,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Task generation not found")
    return api_response(TaskGenerationResponse.model_validate(run), request=request)
