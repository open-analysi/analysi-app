"""Task management endpoints."""

from typing import Annotated
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
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.workflow import WorkflowRepository
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.task import (
    CheckDeleteResponse,
    ScriptAnalysisRequest,
    ScriptAnalysisResponse,
    SyncEdgesResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from analysi.services.task import TaskService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


async def get_task_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskService:
    """Dependency injection for TaskService."""
    return TaskService(session)


async def get_workflow_repository(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowRepository:
    """Dependency injection for WorkflowRepository."""
    return WorkflowRepository(session)


def _build_task_response(task) -> dict:
    """Build response dict from Task + Component."""
    return {
        # Component fields
        "id": task.component.id,
        "tenant_id": task.component.tenant_id,
        "name": task.component.name,
        "description": task.component.description,
        "version": task.component.version,
        "status": task.component.status,
        "visible": task.component.visible,
        "system_only": task.component.system_only,
        "app": task.component.app,
        "categories": task.component.categories,
        "created_by": task.component.created_by,
        "cy_name": task.component.cy_name,
        # Task fields
        "script": task.script,
        "directive": task.directive,
        "function": task.function,
        "scope": task.scope,
        "schedule": task.schedule,
        "mode": task.mode,
        "llm_config": task.llm_config,
        "data_samples": task.data_samples,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "last_run_at": task.last_run_at,
        "last_used_at": task.component.last_used_at,
    }


@router.post(
    "",
    response_model=ApiResponse[TaskResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "create"))],
)
async def create_task(
    request: Request,
    task_data: TaskCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[TaskResponse]:
    """Create a new task."""
    try:
        task = await service.create_task(tenant_id, task_data, audit_context)
    except ValueError as e:
        logger.error("task_creation_failed", error=str(e))
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail="Task name already exists")
        raise HTTPException(status_code=400, detail="Invalid task definition")

    return api_response(
        TaskResponse.model_validate(_build_task_response(task)), request=request
    )


async def _analyze_script(
    script: str, session: AsyncSession, tenant_id: str
) -> ScriptAnalysisResponse:
    """Shared helper: run static analysis on a Cy script."""
    from cy_language import analyze_script

    from analysi.services.cy_tool_registry import load_tool_registry_async

    try:
        tool_registry = await load_tool_registry_async(session, tenant_id)
        result = analyze_script(code=script, tool_registry=tool_registry)
        return ScriptAnalysisResponse(
            tools_used=result["tools_used"],
            external_variables=result["external_variables"],
        )
    except SyntaxError as e:
        # Return line/col info without exposing internal parser details
        error_msg = (
            f"Syntax error at line {e.lineno}" if e.lineno else "Syntax error in script"
        )
        return ScriptAnalysisResponse(errors=[error_msg])


@router.post("/analyze", response_model=ApiResponse[ScriptAnalysisResponse])
async def analyze_adhoc_script(
    request: Request,
    body: ScriptAnalysisRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[ScriptAnalysisResponse]:
    """Analyze an ad-hoc Cy script for tools used and external variables."""
    result = await _analyze_script(body.script, session, tenant_id)
    return api_response(result, request=request)


@router.post(
    "/sync-edges",
    response_model=ApiResponse[SyncEdgesResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def sync_tool_edges(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
) -> ApiResponse[SyncEdgesResponse]:
    """Backfill KDG 'uses' edges for all tasks in the tenant."""
    from cy_language import analyze_script

    from analysi.services.cy_tool_registry import load_tool_registry_async

    synced = 0
    skipped = 0
    errors: list[str] = []

    tool_registry = await load_tool_registry_async(service.session, tenant_id)

    tasks, _ = await service.list_tasks(tenant_id=tenant_id, skip=0, limit=10000)
    for task in tasks:
        try:
            if not task.script:
                skipped += 1
                continue

            result = analyze_script(code=task.script, tool_registry=tool_registry)
            tool_fqns = result["tools_used"]

            if not tool_fqns:
                skipped += 1
                continue

            # Use a savepoint so one task's failure doesn't corrupt the session
            async with service.session.begin_nested():
                await service._sync_tool_edges(task, tenant_id, tool_fqns)
            synced += 1
        except Exception as exc:
            name = task.component.name if task.component else str(task.id)
            errors.append(f"{name}: {exc}")
            logger.warning("sync_edges_failed", task_name=name, exc_info=True)

    await service.session.commit()

    return api_response(
        SyncEdgesResponse(synced=synced, skipped=skipped, errors=errors),
        request=request,
    )


@router.get("/{id}", response_model=ApiResponse[TaskResponse])
async def get_task(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
) -> ApiResponse[TaskResponse]:
    """Get a task by ID."""
    task = await service.get_task(id, tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return api_response(
        TaskResponse.model_validate(_build_task_response(task)), request=request
    )


@router.get("/{id}/analyze", response_model=ApiResponse[ScriptAnalysisResponse])
async def analyze_saved_task(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[ScriptAnalysisResponse]:
    """Analyze a saved task's script for tools used and external variables."""
    task = await service.get_task(id, tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    response = await _analyze_script(task.script, session, tenant_id)
    response.task_id = task.component.id
    response.cy_name = task.component.cy_name
    return api_response(response, request=request)


@router.put(
    "/{id}",
    response_model=ApiResponse[TaskResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_task(
    request: Request,
    id: UUID,
    update_data: TaskUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[TaskResponse]:
    """Update an existing task."""
    # Check if task exists first
    existing_task = await service.get_task(id, tenant_id)
    if not existing_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check system_only protection
    if existing_task.component.system_only:
        raise HTTPException(
            status_code=403, detail={"error": "Cannot modify system_only task"}
        )

    task = await service.update_task(id, tenant_id, update_data, audit_context)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return api_response(
        TaskResponse.model_validate(_build_task_response(task)), request=request
    )


@router.get("/{id}/check-delete", response_model=ApiResponse[CheckDeleteResponse])
async def check_task_deletable(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    workflow_repo: Annotated[WorkflowRepository, Depends(get_workflow_repository)],
) -> ApiResponse[CheckDeleteResponse]:
    """Check if a task can be deleted."""
    # Check if task exists
    existing_task = await service.get_task(id, tenant_id)
    if not existing_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check system_only protection
    if existing_task.component.system_only:
        return api_response(
            CheckDeleteResponse(
                can_delete=False,
                reason="system_protected",
                message="This is a system task and cannot be deleted.",
            ),
            request=request,
        )

    # Check if task is used by any workflows
    workflows_using_task = await workflow_repo.get_workflows_using_task(
        tenant_id, existing_task.component_id
    )
    if workflows_using_task:
        workflow_names = [w["name"] for w in workflows_using_task]
        return api_response(
            CheckDeleteResponse(
                can_delete=False,
                reason="in_use",
                workflows=workflows_using_task,
                message=f"This task is used by {len(workflows_using_task)} workflow(s): {', '.join(workflow_names)}. "
                "Please remove the task from these workflows or delete the workflows first.",
            ),
            request=request,
        )

    return api_response(
        CheckDeleteResponse(can_delete=True),
        request=request,
    )


@router.delete(
    "/{id}",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "delete"))],
)
async def delete_task(
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    workflow_repo: Annotated[WorkflowRepository, Depends(get_workflow_repository)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> None:
    """Delete a task."""
    # Check if task exists first
    existing_task = await service.get_task(id, tenant_id)
    if not existing_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check system_only protection
    if existing_task.component.system_only:
        raise HTTPException(
            status_code=403, detail={"error": "Cannot delete system_only task"}
        )

    # Check if task is used by any workflows
    workflows_using_task = await workflow_repo.get_workflows_using_task(
        tenant_id, existing_task.component_id
    )
    if workflows_using_task:
        workflow_names = [w["name"] for w in workflows_using_task]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Cannot delete task that is used by workflows",
                "workflows": workflows_using_task,
                "message": f"This task is used by {len(workflows_using_task)} workflow(s): {', '.join(workflow_names)}. "
                "Please remove the task from these workflows or delete the workflows first.",
            },
        )

    success = await service.delete_task(id, tenant_id, audit_context)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")


@router.get("", response_model=ApiListResponse[TaskResponse])
async def list_tasks(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskService, Depends(get_task_service)],
    pagination: PaginationParams = Depends(),
    function: str | None = Query(None, description="Filter by task function"),
    scope: str | None = Query(None, description="Filter by task scope"),
    cy_name: str | None = Query(None, description="Filter by cy_name"),
    categories: list[str] | None = Query(
        None, description="Filter by categories (AND semantics)"
    ),
    q: str | None = Query(
        None, min_length=1, description="Search query for name, description, and tags"
    ),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[TaskResponse]:
    """List tasks with pagination, filtering, and search."""
    if q:
        tasks, result_meta = await service.search_tasks(
            tenant_id=tenant_id,
            query=q,
            skip=pagination.offset,
            limit=pagination.limit,
            categories=categories,
        )
        total = result_meta["total"]
    else:
        tasks, result_meta = await service.list_tasks(
            tenant_id=tenant_id,
            skip=pagination.offset,
            limit=pagination.limit,
            function=function,
            scope=scope,
            cy_name=cy_name,
            categories=categories,
            app=app,
        )
        total = result_meta["total"]

    task_responses = [
        TaskResponse.model_validate(_build_task_response(task)) for task in tasks
    ]

    return api_list_response(
        task_responses, total=total, request=request, pagination=pagination
    )
