"""
Task Execution Router

API endpoints for task execution and monitoring.
"""

import json
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.task_run import (
    AdHocTaskRunCreate,
    TaskRunCreate,
    TaskRunEnrichmentResponse,
    TaskRunInitiated,
    TaskRunLogsResponse,
    TaskRunResponse,
    TaskRunStatusResponse,
)
from analysi.services.task_run import TaskRunService

router = APIRouter(
    tags=["task-execution"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


@router.get(
    "/{tenant}/task-runs",
    response_model=ApiListResponse[TaskRunResponse],
)
async def list_task_runs(
    request: Request,
    task_id: UUID | None = Query(None, description="Filter by task ID"),
    workflow_run_id: UUID | None = Query(None, description="Filter by workflow run ID"),
    status: str | None = Query(
        None, description="Filter by status (running, completed, failed)"
    ),
    run_context: str | None = Query(
        "analysis,ad_hoc",
        description="Comma-separated run contexts to include (analysis, scheduled, ad_hoc). Default excludes scheduled.",
    ),
    integration_id: str | None = Query(
        None,
        description="Filter by integration ID (returns runs for tasks linked to this integration)",
    ),
    sort: str = Query(
        "created_at",
        description="Field to sort by (created_at, updated_at, status, duration)",
    ),
    order: str = Query("desc", description="Sort order (asc, desc)"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiListResponse[TaskRunResponse]:
    """
    List task runs with filtering, sorting, and pagination.

    Query Parameters:
    - task_id: Filter by specific task ID
    - workflow_run_id: Filter by workflow run ID
    - status: Filter by execution status (running, completed, failed)
    - run_context: Comma-separated contexts (default: analysis,ad_hoc — excludes scheduled)
    - integration_id: Filter by integration ID
    - sort: Field to sort by (created_at, updated_at, status, duration)
    - order: Sort order (asc, desc)
    - skip: Number of items to skip for pagination
    - limit: Number of items to return (max 100)
    """
    service = TaskRunService()

    # Parse run_context filter
    run_context_list: list[str] | None = None
    if run_context:
        run_context_list = [
            ctx.strip() for ctx in run_context.split(",") if ctx.strip()
        ]

    # Validate sort field
    valid_sort_fields = [
        "created_at",
        "updated_at",
        "status",
        "duration",
        "started_at",
        "completed_at",
    ]
    if sort not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field. Must be one of: {', '.join(valid_sort_fields)}",
        )

    # Validate order
    if order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=400, detail="Invalid order. Must be 'asc' or 'desc'"
        )

    # Get task runs
    task_runs, total = await service.list_task_runs(
        session=session,
        tenant_id=tenant_id,
        task_id=task_id,
        workflow_run_id=workflow_run_id,
        status=status,
        run_context_list=run_context_list,
        integration_id=integration_id,
        sort=sort,
        order=order,
        skip=skip,
        limit=limit,
    )

    # Convert to response models
    task_run_responses = []
    for task_run in task_runs:
        # Skip loading actual input/output data for list view (just show metadata)
        # This avoids storage access issues and improves performance

        response = TaskRunResponse.model_validate(task_run)
        # Note: TaskRunResponse doesn't include actual data, just metadata
        task_run_responses.append(response)

    from analysi.api.pagination import PaginationParams

    pagination = PaginationParams(limit=limit, offset=skip)
    return api_list_response(
        task_run_responses,
        total=total,
        request=request,
        pagination=pagination,
    )


@router.post(
    "/{tenant}/tasks/{task_id}/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[TaskRunInitiated],
    dependencies=[Depends(require_permission("tasks", "execute"))],
    responses={
        202: {
            "description": "Task execution initiated",
            "headers": {
                "Location": {
                    "description": "URL to poll for task run status",
                    "schema": {"type": "string"},
                },
                "Retry-After": {
                    "description": "Suggested delay in seconds before polling",
                    "schema": {"type": "integer"},
                },
            },
        }
    },
)
async def execute_task(
    task_id: UUID,
    execution_data: TaskRunCreate,
    request: Request,
    response: Response,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunInitiated]:
    """
    Execute an existing task asynchronously.

    Returns 202 Accepted with task run ID (trid) and polling information.
    """
    service = TaskRunService()

    # Create task run
    task_run = await service.create_execution(
        session=session,
        tenant_id=tenant_id,
        task_id=task_id,
        cy_script=None,  # Will be loaded from task
        input_data=execution_data.input,
        executor_config=execution_data.executor_config,
    )

    # Update last_used_at field immediately when execution is initiated
    await _update_component_last_used_at_for_task(task_id, tenant_id, session)

    # Flush to ensure the update is written to DB (visible to background task)
    await session.flush()

    logger = get_logger(__name__)
    logger.debug(
        "task_session_flushed", task_run_id=task_run.id, session_id=id(session)
    )

    # Set response headers
    _set_async_headers(response, task_run.id, tenant_id)

    # Commit BEFORE enqueuing ARQ job — worker must see the TaskRun row
    await session.commit()

    # enqueue_or_fail marks the row 'failed' if Redis is down,
    # preventing orphaned 'running' rows.
    from analysi.common.arq_enqueue import enqueue_or_fail
    from analysi.models.task_run import TaskRun

    job_id = await enqueue_or_fail(
        "analysi.jobs.task_run_job.execute_task_run",
        str(task_run.id),
        tenant_id,
        model_class=TaskRun,
        row_id=task_run.id,
    )
    logger.info(
        "task_run_enqueued",
        task_run_id=str(task_run.id),
        job_id=job_id or "duplicate",
    )

    return api_response(
        _build_execution_response(task_run.id, "running"), request=request
    )


@router.post(
    "/{tenant}/tasks/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[TaskRunInitiated],
    dependencies=[Depends(require_permission("tasks", "execute"))],
    responses={
        202: {
            "description": "Ad-hoc task execution initiated",
            "headers": {
                "Location": {"schema": {"type": "string"}},
                "Retry-After": {"schema": {"type": "integer"}},
            },
        }
    },
)
async def execute_ad_hoc_task(
    execution_data: AdHocTaskRunCreate,
    request: Request,
    response: Response,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunInitiated]:
    """
    Execute an ad-hoc Cy script asynchronously.

    No task_id required - executes the provided cy_script directly.
    """
    service = TaskRunService()

    # Create ad-hoc task run
    task_run = await service.create_execution(
        session=session,
        tenant_id=tenant_id,
        task_id=None,  # No task ID for ad-hoc execution
        cy_script=execution_data.cy_script,
        input_data=execution_data.input,
        executor_config=execution_data.executor_config,
    )

    # Flush to ensure the task run is written to DB (visible to background task)
    await session.flush()

    logger = get_logger(__name__)
    logger.debug(
        "adhoc_task_session_flushed", task_run_id=task_run.id, session_id=id(session)
    )

    # Set response headers
    _set_async_headers(response, task_run.id, tenant_id)

    # Commit BEFORE enqueuing ARQ job — worker must see the TaskRun row
    await session.commit()

    from analysi.common.arq_enqueue import enqueue_or_fail
    from analysi.models.task_run import TaskRun

    job_id = await enqueue_or_fail(
        "analysi.jobs.task_run_job.execute_task_run",
        str(task_run.id),
        tenant_id,
        model_class=TaskRun,
        row_id=task_run.id,
    )
    logger.info(
        "adhoc_task_run_enqueued",
        task_run_id=str(task_run.id),
        job_id=job_id or "duplicate",
    )

    return api_response(
        _build_execution_response(task_run.id, "running"), request=request
    )


@router.get("/{tenant}/task-runs/{trid}", response_model=ApiResponse[TaskRunResponse])
async def get_task_run(
    trid: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunResponse]:
    """
    Get full task run details.

    Returns complete execution information including input/output storage.
    """
    service = TaskRunService()

    # Get task run
    task_run = await service.get_task_run(session, tenant_id, trid)

    if not task_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task run {trid} not found"
        )

    # Get input and output data (for future use when we include in response)
    # input_data = await service.retrieve_input_data(task_run)
    # output_data = await service.retrieve_output_data(task_run)

    # Build response with correct field names
    return api_response(
        TaskRunResponse(
            id=task_run.id,
            tenant_id=task_run.tenant_id,
            task_id=task_run.task_id,
            workflow_run_id=task_run.workflow_run_id,
            task_name=task_run.task_name,
            cy_script=task_run.cy_script,
            status=task_run.status,
            duration=task_run.duration,
            started_at=task_run.started_at,
            completed_at=task_run.completed_at,
            input_type=task_run.input_type,
            input_location=task_run.input_location,
            input_content_type=task_run.input_content_type,
            output_type=task_run.output_type,
            output_location=task_run.output_location,
            output_content_type=task_run.output_content_type,
            created_at=task_run.created_at,
            updated_at=task_run.updated_at,
            executor_config=task_run.executor_config,
            execution_context=task_run.execution_context,
        ),
        request=request,
    )


@router.get(
    "/{tenant}/task-runs/{trid}/status",
    response_model=ApiResponse[TaskRunStatusResponse],
)
async def get_task_run_status(
    trid: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunStatusResponse]:
    """
    Get lightweight task run status for polling.

    Returns only status and updated_at for efficient polling.
    """
    service = TaskRunService()

    # Get lightweight status info
    status_info = await service.get_task_run_status(session, tenant_id, trid)

    if not status_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task run {trid} not found"
        )

    return api_response(
        TaskRunStatusResponse(
            trid=trid,
            status=status_info["status"],
            updated_at=status_info["updated_at"],
            duration=status_info.get("duration"),
        ),
        request=request,
    )


@router.get(
    "/{tenant}/task-runs/{trid}/enrichment",
    response_model=ApiResponse[TaskRunEnrichmentResponse],
    summary="Get task run enrichment data",
    description="Extract only the enrichment data added by this task using enrich_alert()",
)
async def get_task_run_enrichment(
    trid: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunEnrichmentResponse]:
    """
    Get the enrichment data produced by a task run.

    When a task uses enrich_alert(), the enrichment is stored under
    output["enrichments"][cy_name]. This endpoint extracts just that data,
    making it easy to see what a specific task contributed.

    Returns:
        TaskRunEnrichmentResponse with the enrichment data if present
    """
    service = TaskRunService()

    # Get task run
    task_run = await service.get_task_run(session, tenant_id, trid)

    if not task_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task run {trid} not found"
        )

    # Get cy_name from execution_context
    cy_name = None
    if task_run.execution_context:
        cy_name = task_run.execution_context.get("cy_name")

    # Retrieve output data
    output_data = await service.retrieve_output_data(task_run)

    # Extract enrichment for this task's cy_name
    enrichment = None
    has_enrichment = False

    if output_data and isinstance(output_data, dict):
        enrichments = output_data.get("enrichments", {})
        if isinstance(enrichments, dict) and cy_name and cy_name in enrichments:
            enrichment = enrichments[cy_name]
            has_enrichment = True

    return api_response(
        TaskRunEnrichmentResponse(
            trid=trid,
            cy_name=cy_name,
            enrichment=enrichment,
            status=task_run.status,
            has_enrichment=has_enrichment,
        ),
        request=request,
    )


@router.get(
    "/{tenant}/task-runs/{trid}/logs",
    response_model=ApiResponse[TaskRunLogsResponse],
    summary="Get task run execution logs",
    description="Retrieve log() output captured during Cy script execution",
)
async def get_task_run_logs(
    trid: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRunLogsResponse]:
    """
    Get the execution logs produced by a task run.

    Cy scripts emit log entries via log(). These are persisted as an
    execution_log artifact after execution completes. This endpoint
    retrieves those entries.

    Returns:
        TaskRunLogsResponse with the log entries if present
    """
    service = TaskRunService()

    # Verify the task run exists
    task_run = await service.get_task_run(session, tenant_id, trid)
    if not task_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task run not found"
        )

    # Look for execution_log artifact (filtered query — avoids loading all task artifacts)
    from analysi.services.artifact_service import ArtifactService

    artifact_service = ArtifactService(session)
    log_artifacts, _ = await artifact_service.list_artifacts(
        tenant_id,
        filters={"task_run_id": trid, "artifact_type": "execution_log"},
        limit=1,
    )

    entries: list[str] = []
    if log_artifacts:
        # get_artifact_content works for both inline and object storage
        content_result = await artifact_service.get_artifact_content(
            tenant_id, log_artifacts[0].id
        )
        if content_result:
            content_bytes, _mime, _fname, _sha = content_result
            try:
                parsed = json.loads(content_bytes)
                entries = parsed.get("entries", [])
            except (ValueError, KeyError):
                pass

    return api_response(
        TaskRunLogsResponse(
            trid=trid,
            status=task_run.status,
            entries=entries,
            has_logs=len(entries) > 0,
        ),
        request=request,
    )


# Helper functions for response headers
def _set_async_headers(response: Response, trid: UUID, tenant_id: str) -> None:
    """Set required headers for async execution responses."""
    response.headers["Location"] = f"/v1/{tenant_id}/task-runs/{trid}"
    response.headers["Retry-After"] = "5"


def _build_execution_response(trid: UUID, status: str = "running") -> TaskRunInitiated:
    """Build standardized execution response."""
    return TaskRunInitiated(
        trid=trid, status=status, message="Task execution initiated"
    )


async def _update_component_last_used_at_for_task(
    task_id: UUID, tenant_id: str, session
) -> None:
    """Update the Component's last_used_at field when a task execution is initiated."""
    from datetime import datetime

    from sqlalchemy import update

    from analysi.models.component import Component

    # task_id is actually the component_id (public task ID)
    # Update Component's last_used_at directly
    stmt = (
        update(Component)
        .where(Component.id == task_id)
        .where(Component.tenant_id == tenant_id)
        .values(last_used_at=datetime.now(UTC))
    )
    await session.execute(stmt)
