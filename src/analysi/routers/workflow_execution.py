"""
API routes for workflow execution endpoints.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
from analysi.repositories.workflow_execution import (
    WorkflowNodeInstanceRepository,
    WorkflowRunRepository,
)
from analysi.schemas.task_run import LLMUsageResponse
from analysi.schemas.workflow_execution import (
    NodeInstanceEnvelope,
    WorkflowNodeInstanceResponse,
    WorkflowRunCreate,
    WorkflowRunGraph,
    WorkflowRunInitiated,
    WorkflowRunResponse,
    WorkflowRunStatus,
)
from analysi.services.storage import StorageManager
from analysi.services.workflow_execution import WorkflowExecutionService

logger = get_logger(__name__)

router = APIRouter(
    tags=["workflow-execution"],
    dependencies=[Depends(require_permission("workflows", "read"))],
)


def _llm_usage_from_run(run) -> LLMUsageResponse | None:
    """Extract persisted aggregate LLM usage from execution_context["_llm_usage"]."""
    raw = (run.execution_context or {}).get("_llm_usage")
    if raw and isinstance(raw, dict):
        return LLMUsageResponse(
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            total_tokens=raw.get("total_tokens", 0),
            cost_usd=raw.get("cost_usd"),
        )
    return None


@router.post(
    "/{tenant}/workflows/{workflow_id}/run",
    response_model=ApiResponse[WorkflowRunInitiated],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission("workflows", "execute"))],
    responses={
        202: {
            "description": "Workflow execution initiated",
            "headers": {
                "Location": {
                    "description": "URL to poll for workflow run status",
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
async def start_workflow_execution(
    workflow_id: UUID,
    body: WorkflowRunCreate,
    request: Request,
    response: Response,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRunInitiated]:
    """
    Start asynchronous workflow execution.
    Returns immediately with workflow_run_id for tracking.
    """
    service = WorkflowExecutionService()
    try:
        result = await service.start_workflow(
            session=session,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            input_data=body.input_data,
            execution_context=body.execution_context,
        )

        # Extract workflow_run_id from result
        workflow_run_id = result["workflow_run_id"]

        # Commit BEFORE enqueuing ARQ job — worker must see the WorkflowRun row
        await session.commit()

        # Enqueue durable ARQ job
        from analysi.common.arq_enqueue import enqueue_or_fail
        from analysi.models.workflow_execution import WorkflowRun

        job_id = await enqueue_or_fail(
            "analysi.jobs.workflow_run_job.execute_workflow_run",
            str(workflow_run_id),
            tenant_id,
            model_class=WorkflowRun,
            row_id=workflow_run_id,
        )
        logger.info(
            "workflow_run_enqueued",
            workflow_run_id=str(workflow_run_id),
            job_id=job_id or "duplicate",
        )

        # Set response headers for polling
        response.headers["Location"] = (
            f"/v1/{tenant_id}/workflow-runs/{workflow_run_id}/status"
        )
        response.headers["Retry-After"] = "2"  # Suggest 2 second polling interval

        return api_response(WorkflowRunInitiated(**result), request=request)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="Workflow not found")
        raise HTTPException(
            status_code=400, detail="Invalid workflow execution request"
        )
    except Exception:
        logger.exception("Failed to start workflow execution")
        raise HTTPException(
            status_code=500, detail="Failed to start workflow execution"
        )


@router.get(
    "/{tenant}/workflow-runs",
    response_model=ApiListResponse[WorkflowRunResponse],
)
async def list_workflow_runs(
    request: Request,
    workflow_id: UUID | None = Query(None, description="Filter by workflow ID"),
    status: str | None = Query(
        None, description="Filter by status (running, completed, failed, cancelled)"
    ),
    sort: str = Query(
        "created_at",
        description="Field to sort by (created_at, started_at, completed_at, status)",
    ),
    order: str = Query("desc", description="Sort order (asc, desc)"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiListResponse[WorkflowRunResponse]:
    """
    List workflow runs with filtering, sorting, and pagination.

    Query Parameters:
    - workflow_id: Filter by specific workflow ID
    - status: Filter by execution status (running, completed, failed, cancelled)
    - sort: Field to sort by (created_at, started_at, completed_at, status)
    - order: Sort order (asc, desc)
    - skip: Number of items to skip for pagination
    - limit: Number of items to return (max 100)
    """
    run_repo = WorkflowRunRepository(session)

    # Validate sort field
    valid_sort_fields = ["created_at", "started_at", "completed_at", "status"]
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

    try:
        # Get workflow runs with improved pagination and total count
        workflow_runs, total = await run_repo.list_workflow_runs(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            status=status,
            sort=sort,
            order=order,
            skip=skip,
            limit=limit,
        )

        # Convert to response models (now loading input/output data for each run)
        runs = []
        storage = StorageManager()

        for run in workflow_runs:
            # Load input/output data if available
            input_data = None
            output_data = None

            if run.input_location:
                if run.input_type == "inline":
                    # For inline storage, input_location contains the JSON string directly
                    input_data = json.loads(run.input_location)
                else:
                    # For external storage (S3, etc.), use storage manager
                    input_content = await storage.retrieve(
                        storage_type=run.input_type,
                        location=run.input_location,
                        content_type="application/json",
                    )
                    if isinstance(input_content, str):
                        input_data = json.loads(input_content)
                    else:
                        input_data = input_content

            if run.output_location:
                if run.output_type == "inline":
                    # For inline storage, output_location contains the JSON string directly
                    output_data = json.loads(run.output_location)
                else:
                    # For external storage (S3, etc.), use storage manager
                    output_content = await storage.retrieve(
                        storage_type=run.output_type,
                        location=run.output_location,
                        content_type="application/json",
                    )
                    if isinstance(output_content, str):
                        output_data = json.loads(output_content)
                    else:
                        output_data = output_content

            runs.append(
                WorkflowRunResponse(
                    workflow_run_id=run.id,
                    tenant_id=run.tenant_id,
                    workflow_id=run.workflow_id,
                    workflow_name=run.workflow_name,
                    status=run.status,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    input_data=input_data,
                    output_data=output_data,
                    error_message=run.error_message,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    llm_usage=_llm_usage_from_run(run),
                )
            )

        pagination = PaginationParams(limit=limit, offset=skip)
        return api_list_response(
            runs, total=total, request=request, pagination=pagination
        )

    except Exception:
        logger.exception("Failed to list workflow runs")
        raise HTTPException(status_code=500, detail="Failed to list workflow runs")


@router.get(
    "/{tenant}/workflow-runs/{workflow_run_id}",
    response_model=ApiResponse[WorkflowRunResponse],
)
async def get_workflow_run(
    workflow_run_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRunResponse]:
    """
    Get full workflow run details including input/output.
    """
    service = WorkflowExecutionService()
    storage = StorageManager()

    try:
        workflow_run = await service.get_workflow_run_details(
            session=session,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        # Load input/output data if available
        input_data = None
        output_data = None

        if workflow_run.input_location:
            if workflow_run.input_type == "inline":
                # For inline storage, input_location contains the JSON string directly
                input_data = json.loads(workflow_run.input_location)
            else:
                # For external storage (S3, etc.), use storage manager
                input_content = await storage.retrieve(
                    storage_type=workflow_run.input_type,
                    location=workflow_run.input_location,
                    content_type="application/json",
                )
                if isinstance(input_content, str):
                    input_data = json.loads(input_content)
                else:
                    input_data = input_content

        if workflow_run.output_location:
            if workflow_run.output_type == "inline":
                # For inline storage, output_location contains the JSON string directly
                output_data = json.loads(workflow_run.output_location)
            else:
                # For external storage (S3, etc.), use storage manager
                output_content = await storage.retrieve(
                    storage_type=workflow_run.output_type,
                    location=workflow_run.output_location,
                    content_type="application/json",
                )
                if isinstance(output_content, str):
                    output_data = json.loads(output_content)
                else:
                    output_data = output_content

        return api_response(
            WorkflowRunResponse(
                workflow_run_id=workflow_run.id,
                tenant_id=workflow_run.tenant_id,
                workflow_id=workflow_run.workflow_id,
                workflow_name=workflow_run.workflow_name,
                status=workflow_run.status,
                started_at=workflow_run.started_at,
                completed_at=workflow_run.completed_at,
                input_data=input_data,
                output_data=output_data,
                error_message=workflow_run.error_message,
                created_at=workflow_run.created_at,
                updated_at=workflow_run.updated_at,
                llm_usage=_llm_usage_from_run(workflow_run),
            ),
            request=request,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get workflow run")
        raise HTTPException(status_code=500, detail="Failed to get workflow run")


@router.get(
    "/{tenant}/workflow-runs/{workflow_run_id}/status",
    response_model=ApiResponse[WorkflowRunStatus],
)
async def get_workflow_run_status(
    workflow_run_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRunStatus]:
    """
    Get lightweight workflow run status for polling.
    Optimized for frequent status checks.
    """
    service = WorkflowExecutionService()

    try:
        status_data = await service.get_workflow_run_status(
            session=session,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        if "error" in status_data:
            raise HTTPException(status_code=404, detail=status_data["error"])

        return api_response(
            WorkflowRunStatus(
                workflow_run_id=status_data["workflow_run_id"],
                status=status_data["status"],
                started_at=status_data["started_at"],
                completed_at=status_data["completed_at"],
                updated_at=status_data["updated_at"],
            ),
            request=request,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get workflow run status")
        raise HTTPException(status_code=500, detail="Failed to get workflow run status")


@router.get(
    "/{tenant}/workflow-runs/{workflow_run_id}/graph",
    response_model=ApiResponse[WorkflowRunGraph],
)
async def get_workflow_run_graph(
    workflow_run_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowRunGraph]:
    """
    Get materialized execution graph for visualization.
    Shows complete graph if done, or partial graph with current progress.
    """
    service = WorkflowExecutionService()
    storage = StorageManager()

    try:
        graph_data = await service.get_workflow_run_graph(
            session=session,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        if graph_data is None:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        # Convert nodes to response format
        nodes = []
        for node_data in graph_data["nodes"]:
            # Try to load input/output data for each node
            input_data = None
            output_data = None

            # Get full node instance to access storage info
            node_repo = WorkflowNodeInstanceRepository(session)
            node_instance = await node_repo.get_node_instance(UUID(node_data["id"]))

            if node_instance:
                if node_instance.input_location:
                    input_content = await storage.retrieve(
                        storage_type=node_instance.input_type,
                        location=node_instance.input_location,
                        content_type="application/json",
                    )
                    input_data = json.loads(input_content)

                if node_instance.output_location:
                    output_content = await storage.retrieve(
                        storage_type=node_instance.output_type,
                        location=node_instance.output_location,
                        content_type="application/json",
                    )
                    output_raw = json.loads(output_content)

                    # Convert to envelope format if it's not already
                    if isinstance(output_raw, dict) and "result" in output_raw:
                        output_data = NodeInstanceEnvelope(**output_raw)
                    else:
                        output_data = NodeInstanceEnvelope(
                            node_id=node_data["node_id"], result=output_raw
                        )

            nodes.append(
                WorkflowNodeInstanceResponse(
                    node_instance_id=UUID(node_data["id"]),
                    workflow_run_id=workflow_run_id,
                    node_id=node_data["node_id"],
                    node_uuid=(
                        node_instance.node_uuid
                        if node_instance
                        else UUID(node_data["id"])
                    ),
                    status=node_data["status"],
                    started_at=node_data.get("started_at"),
                    completed_at=node_data.get("completed_at"),
                    input_data=input_data,
                    output_data=output_data,
                    error_message=node_data.get("error_message"),
                    created_at=node_instance.created_at if node_instance else None,
                    updated_at=node_instance.updated_at if node_instance else None,
                )
            )

        # Calculate summary
        summary = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        for node in nodes:
            if node.status in summary:
                summary[node.status] += 1

        return api_response(
            WorkflowRunGraph(
                workflow_run_id=UUID(graph_data["workflow_run_id"]),
                is_complete=graph_data["is_complete"],
                status=graph_data.get("status"),
                snapshot_at=graph_data["snapshot_at"],
                summary=summary,
                nodes=nodes,
                edges=graph_data.get("edges", []),  # Use edge instances from service
            ),
            request=request,
        )

    except Exception:
        logger.exception("Failed to get workflow run graph")
        raise HTTPException(status_code=500, detail="Failed to get workflow run graph")


@router.get(
    "/{tenant}/workflow-runs/{workflow_run_id}/nodes",
    response_model=ApiListResponse[WorkflowNodeInstanceResponse],
)
async def list_node_instances(
    workflow_run_id: UUID,
    request: Request,
    status: str | None = Query(None, description="Filter by node status"),
    parent_instance_id: UUID | None = Query(
        None, description="Filter by parent instance"
    ),
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiListResponse[WorkflowNodeInstanceResponse]:
    """
    List all node instances for a workflow run.
    """
    node_repo = WorkflowNodeInstanceRepository(session)
    storage = StorageManager()

    try:
        # Verify workflow run belongs to tenant
        run_repo = WorkflowRunRepository(session)
        workflow_run = await run_repo.get_workflow_run(tenant_id, workflow_run_id)
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        # Get node instances
        node_instances = await node_repo.list_node_instances(
            workflow_run_id=workflow_run_id,
            status=status,
            parent_instance_id=parent_instance_id,
        )

        # Convert to response format
        nodes = []
        for node_instance in node_instances:
            # Load input/output data
            input_data = None
            output_data = None

            if node_instance.input_location:
                input_content = await storage.retrieve(
                    storage_type=node_instance.input_type,
                    location=node_instance.input_location,
                    content_type="application/json",
                )
                input_data = json.loads(input_content)

            if node_instance.output_location:
                output_content = await storage.retrieve(
                    storage_type=node_instance.output_type,
                    location=node_instance.output_location,
                    content_type="application/json",
                )
                output_raw = json.loads(output_content)

                # Convert to envelope format
                if isinstance(output_raw, dict) and "result" in output_raw:
                    output_data = NodeInstanceEnvelope(**output_raw)
                else:
                    output_data = NodeInstanceEnvelope(
                        node_id=node_instance.node_id, result=output_raw
                    )

            nodes.append(
                WorkflowNodeInstanceResponse(
                    node_instance_id=node_instance.id,
                    workflow_run_id=node_instance.workflow_run_id,
                    node_id=node_instance.node_id,
                    node_uuid=node_instance.node_uuid,
                    status=node_instance.status,
                    parent_instance_id=node_instance.parent_instance_id,
                    loop_context=node_instance.loop_context,
                    started_at=node_instance.started_at,
                    completed_at=node_instance.completed_at,
                    input_data=input_data,
                    output_data=output_data,
                    error_message=node_instance.error_message,
                    created_at=node_instance.created_at,
                    updated_at=node_instance.updated_at,
                )
            )

        return api_list_response(nodes, total=len(nodes), request=request)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list node instances")
        raise HTTPException(status_code=500, detail="Failed to list node instances")


@router.get(
    "/{tenant}/workflow-runs/{workflow_run_id}/nodes/{node_instance_id}",
    response_model=ApiResponse[WorkflowNodeInstanceResponse],
)
async def get_node_instance(
    workflow_run_id: UUID,
    node_instance_id: UUID,
    request: Request,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[WorkflowNodeInstanceResponse]:
    """
    Get specific node instance execution details.
    """
    node_repo = WorkflowNodeInstanceRepository(session)
    run_repo = WorkflowRunRepository(session)
    storage = StorageManager()

    try:
        # Verify workflow run belongs to tenant
        workflow_run = await run_repo.get_workflow_run(tenant_id, workflow_run_id)
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        # Get node instance
        node_instance = await node_repo.get_node_instance(node_instance_id)
        if not node_instance or node_instance.workflow_run_id != workflow_run_id:
            raise HTTPException(status_code=404, detail="Node instance not found")

        # Load input/output data
        input_data = None
        output_data = None

        if node_instance.input_location:
            if node_instance.input_type == "s3":
                input_data = await storage.retrieve_json(node_instance.input_location)
            else:
                input_data = json.loads(node_instance.input_location)

        if node_instance.output_location:
            if node_instance.output_type == "s3":
                output_raw = await storage.retrieve_json(node_instance.output_location)
            else:
                output_raw = json.loads(node_instance.output_location)

            # Convert to envelope format
            if isinstance(output_raw, dict) and "result" in output_raw:
                output_data = NodeInstanceEnvelope(**output_raw)
            else:
                output_data = NodeInstanceEnvelope(
                    node_id=node_instance.node_id, result=output_raw
                )

        return api_response(
            WorkflowNodeInstanceResponse(
                node_instance_id=node_instance.id,
                workflow_run_id=node_instance.workflow_run_id,
                node_id=node_instance.node_id,
                node_uuid=node_instance.node_uuid,
                status=node_instance.status,
                parent_instance_id=node_instance.parent_instance_id,
                loop_context=node_instance.loop_context,
                started_at=node_instance.started_at,
                completed_at=node_instance.completed_at,
                input_data=input_data,
                output_data=output_data,
                error_message=node_instance.error_message,
                created_at=node_instance.created_at,
                updated_at=node_instance.updated_at,
            ),
            request=request,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get node instance")
        raise HTTPException(status_code=500, detail="Failed to get node instance")


@router.post(
    "/{tenant}/workflow-runs/{workflow_run_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("workflows", "execute"))],
)
async def cancel_workflow_run(
    workflow_run_id: UUID,
    tenant_id: str = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """
    Cancel a running workflow execution.
    """
    service = WorkflowExecutionService()

    try:
        success = await service.cancel_workflow_run(
            session=session,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        if not success:
            raise HTTPException(
                status_code=404, detail="Workflow run not found or cannot be cancelled"
            )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to cancel workflow run")
        raise HTTPException(status_code=500, detail="Failed to cancel workflow run")
