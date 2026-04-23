"""Second subgraph: Parallel Task Building → Workflow Assembly (No LangGraph).

This subgraph implements the final two stages of the Kea workflow generation:
- Task Building: Parallel task building using asyncio.gather()
- Workflow Assembly: Workflow assembly (fresh execution after clean break)

KEY INSIGHT: We don't use LangGraph to avoid SDK cancel scope errors corrupting state.
Instead, we use plain asyncio and query the database for results.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from analysi.agentic_orchestration.nodes import (
    task_building_node,
    workflow_assembly_node,
)
from analysi.agentic_orchestration.nodes.task_building import (
    filter_proposals_for_building,
)
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID

if TYPE_CHECKING:
    from analysi.agentic_orchestration.task_generation_client import (
        TaskGenerationApiClient,
    )

logger = get_logger(__name__)


async def _build_single_task_with_recovery(
    proposal: dict[str, Any],
    alert: dict[str, Any],
    runbook: str,
    run_id: str,
    tenant_id: str,
    created_by: str,
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None,
    task_index: int,
    task_generation_client: TaskGenerationApiClient | None = None,
    task_generation_id: str | None = None,
) -> tuple[dict[str, Any], list[StageExecutionMetrics]]:
    """Build a single task, ignoring SDK cleanup errors.

    This wrapper allows SDK cleanup errors to occur without affecting
    the result. We rely on the database as the source of truth.

    Args:
        proposal: Task proposal to build
        alert: alert context
        runbook: Runbook content
        run_id: Run ID for workspace isolation
        tenant_id: Tenant ID
        created_by: User who triggered generation
        executor: SDK executor
        callback: Progress callback
        task_index: Index of this task (for workspace naming)
        task_generation_client: Optional client for tracking progress via REST API
        task_generation_id: Optional run ID for tracking this specific task build

    Returns:
        Tuple of (task_result, metrics_list)
    """
    proposal_name = proposal.get("name", "unknown")

    # Create progress callback if tracking enabled
    progress_callback = None
    if task_generation_client and task_generation_id:
        # Import here to avoid circular imports
        from analysi.agentic_orchestration.task_generation_client import (
            TaskGenerationProgressCallback,
        )

        await task_generation_client.mark_in_progress(task_generation_id)
        await task_generation_client.append_progress(
            task_generation_id,
            [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "message": f"Starting task building for '{proposal_name}'",
                    "level": "info",
                    "details": {},
                }
            ],
        )
        # Create callback to push tool calls to database
        progress_callback = TaskGenerationProgressCallback(
            client=task_generation_client,
            run_id=task_generation_id,
        )

    # Create isolated workspace for this task
    sub_workspace = AgentWorkspace(
        run_id=f"{run_id}-task-{task_index}",
        tenant_id=tenant_id,
    )

    state = {
        "workspace": sub_workspace,
        "proposal": proposal,
        "alert": alert,
        "runbook": runbook,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "created_by": created_by,
    }

    try:
        # Execute task building node with progress callback
        result = await task_building_node(state, executor, progress_callback)

        # Result is {"tasks_built": [single_result], "metrics": [metrics]}
        # Extract the single result and metrics
        tasks_built = result.get("tasks_built", [])
        metrics = result.get("metrics", [])

        if tasks_built:
            task_result = tasks_built[0]
            # Update tracking with result
            if task_generation_client and task_generation_id:
                if task_result.get("success"):
                    await task_generation_client.mark_completed(
                        task_generation_id,
                        task_id=task_result.get("task_id", ""),
                        cy_name=task_result.get("cy_name", ""),
                        recovered=task_result.get("recovered", False),
                    )
                else:
                    await task_generation_client.mark_failed(
                        task_generation_id,
                        error=task_result.get("error", "Unknown error"),
                        error_type="TaskBuildingError",
                    )
            return task_result, metrics
        error = "task_building_node returned empty tasks_built"
        if task_generation_client and task_generation_id:
            await task_generation_client.mark_failed(
                task_generation_id,
                error=error,
                error_type="EmptyResultError",
            )
        return {
            "proposal_name": proposal_name,
            "designation": proposal.get("designation", "new"),
            "success": False,
            "task_id": None,
            "cy_name": None,
            "error": error,
        }, metrics

    except Exception as e:
        # Log the error but don't let it stop other tasks
        logger.exception(
            "task_building_failed",
            proposal_name=proposal_name,
            error=str(e),
        )
        error = f"Exception during task building: {e!s}"
        if task_generation_client and task_generation_id:
            await task_generation_client.mark_failed(
                task_generation_id,
                error=error,
                error_type=type(e).__name__,
            )
        return {
            "proposal_name": proposal_name,
            "designation": proposal.get("designation", "new"),
            "success": False,
            "task_id": None,
            "cy_name": None,
            "error": error,
        }, []
    except BaseException as e:
        # CRITICAL: CancelledError is a BaseException in Python 3.8+
        # This can happen during SDK cleanup when running parallel queries.
        # The task may have actually completed successfully - check the database!
        logger.warning(
            "base_exception_during_task_building",
            exception_type=type(e).__name__,
            proposal_name=proposal_name,
        )

        # Import here to avoid circular imports
        from analysi.agentic_orchestration.nodes.task_building import (
            _check_task_exists,
        )

        try:
            existing_task = await _check_task_exists(tenant_id, proposal_name)
            if existing_task:
                logger.info(
                    "task_recovered_after_exception",
                    exception_type=type(e).__name__,
                    cy_name=existing_task.get("cy_name"),
                    task_id=existing_task.get("id"),
                )
                if task_generation_client and task_generation_id:
                    await task_generation_client.mark_completed(
                        task_generation_id,
                        task_id=existing_task.get("id", ""),
                        cy_name=existing_task.get("cy_name", ""),
                        recovered=True,
                    )
                return {
                    "proposal_name": proposal_name,
                    "designation": proposal.get("designation", "new"),
                    "success": True,
                    "task_id": existing_task.get("id"),
                    "cy_name": existing_task.get("cy_name"),
                    "recovered": True,
                    "error": None,
                }, []
        except Exception as recovery_err:
            logger.warning("recovery_check_failed", error=str(recovery_err))

        # Task doesn't exist - genuine failure
        error = f"{type(e).__name__} during task building: {e!s}"
        if task_generation_client and task_generation_id:
            await task_generation_client.mark_failed(
                task_generation_id,
                error=error,
                error_type=type(e).__name__,
            )
        return {
            "proposal_name": proposal_name,
            "designation": proposal.get("designation", "new"),
            "success": False,
            "task_id": None,
            "cy_name": None,
            "error": error,
        }, []


async def run_parallel_task_building(
    task_proposals: list[dict[str, Any]],
    alert: dict[str, Any],
    runbook: str,
    run_id: str,
    tenant_id: str,
    created_by: str,
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None = None,
    max_tasks_to_build: int | None = None,
    task_generation_client: TaskGenerationApiClient | None = None,
) -> tuple[list[dict[str, Any]], list[StageExecutionMetrics]]:
    """Run task building in parallel using asyncio.gather().

    This function builds all tasks in parallel, ignoring SDK cleanup errors.
    The recovery logic in task_building_node will check the database to see
    if tasks were created despite cleanup failures.

    Args:
        task_proposals: Proposals from the Task Proposals stage
        alert: alert
        runbook: Runbook content
        run_id: Run ID for workspace isolation
        tenant_id: Tenant ID
        created_by: User who triggered generation
        executor: SDK executor
        callback: Progress callback
        max_tasks_to_build: Optional limit on parallel tasks (cost control)
        task_generation_client: Optional client for tracking progress via REST API

    Returns:
        Tuple of (tasks_built, metrics)
    """
    # Filter proposals to those needing building
    proposals_to_build = filter_proposals_for_building(
        task_proposals,
        max_tasks=max_tasks_to_build,
    )

    logger.info(
        "parallel_task_building_proposal_counts",
        total_proposals=len(task_proposals),
        proposals_to_build=len(proposals_to_build),
    )

    if max_tasks_to_build is not None:
        logger.info(
            "paralleltaskbuilding_maxtaskstobuild_limit",
            max_tasks_to_build=max_tasks_to_build,
        )

    if not proposals_to_build:
        logger.info("parallel_task_building_no_tasks_to_build")
        return [], []

    # Notify callback of task building start
    if callback:
        await callback.on_stage_start(
            WorkflowGenerationStage.TASK_BUILDING,
            {
                "alert_id": alert.get("id"),
                "tasks_count": len(proposals_to_build),
            },
        )

    # Create TaskGeneration records for each proposal (if tracking enabled)
    task_generation_ids: list[str | None] = []
    if task_generation_client:
        logger.info(
            "parallel_task_building_creating_tracking_records",
            count=len(proposals_to_build),
        )
        for idx, proposal in enumerate(proposals_to_build):
            try:
                run_record_id = await task_generation_client.create_run(
                    input_context={
                        "proposal": proposal,
                        "alert": alert,
                        "runbook": runbook,
                    },
                    created_by=str(SYSTEM_USER_ID),
                )
                task_generation_ids.append(run_record_id)
            except Exception as e:
                logger.warning(
                    "failed_to_create_task_generation",
                    proposal_index=idx,
                    error=str(e),
                )
                task_generation_ids.append(None)
    else:
        # No tracking - fill with None
        task_generation_ids = [None] * len(proposals_to_build)

    # Build all tasks in parallel using asyncio.gather()
    logger.info(
        "paralleltaskbuilding_starting_parallel_tasks",
        proposals_to_build_count=len(proposals_to_build),
    )

    # NOTE: Don't pass callback to individual task builds - they run in parallel
    # and would cause multiple on_stage_complete calls. We call it once after gather().
    tasks = [
        _build_single_task_with_recovery(
            proposal=proposal,
            alert=alert,
            runbook=runbook,
            run_id=run_id,
            tenant_id=tenant_id,
            created_by=created_by,
            executor=executor,
            callback=None,  # Don't pass callback to parallel tasks
            task_index=idx,
            task_generation_client=task_generation_client,
            task_generation_id=task_generation_ids[idx],
        )
        for idx, proposal in enumerate(proposals_to_build)
    ]

    # Execute all tasks in parallel
    # Use return_exceptions=True to catch any exceptions without stopping other tasks
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results and collect metrics
    tasks_built = []
    all_metrics = []

    for idx, result in enumerate(results):
        proposal_name = proposals_to_build[idx].get("name", "unknown")
        proposal_designation = proposals_to_build[idx].get("designation", "new")

        # Note: CancelledError is a BaseException, not Exception, in Python 3.8+
        # We need to check BaseException to catch CancelledError from asyncio.gather
        if isinstance(result, BaseException):
            # Exception returned by asyncio.gather(return_exceptions=True)
            exc_type = type(result).__name__
            logger.error(
                "unexpected_exception_for_task",
                proposal_name=proposal_name,
                exc_type=exc_type,
                result=result,
            )
            tasks_built.append(
                {
                    "proposal_name": proposal_name,
                    "designation": proposal_designation,
                    "success": False,
                    "task_id": None,
                    "cy_name": None,
                    "error": f"Unexpected {exc_type}: {result!s}",
                }
            )
            # No metrics for unexpected exceptions
        elif isinstance(result, tuple) and len(result) == 2:
            # Expected result: tuple of (task_result, metrics_list)
            task_result, metrics_list = result
            tasks_built.append(task_result)
            all_metrics.extend(metrics_list)
        else:
            # Defensive: unexpected result type - should never happen
            logger.error(
                "unexpected_result_type_for_task",
                proposal_name=proposal_name,
                result_type=type(result).__name__,
                result=repr(result),
            )
            tasks_built.append(
                {
                    "proposal_name": proposal_name,
                    "designation": proposal_designation,
                    "success": False,
                    "task_id": None,
                    "cy_name": None,
                    "error": f"Unexpected result type: {type(result).__name__}",
                }
            )

    successful_count = sum(1 for t in tasks_built if t.get("success"))
    logger.info(
        "parallel_task_building_completed",
        successful_count=successful_count,
        total_count=len(tasks_built),
    )

    # Notify callback that task building stage is complete (called ONCE after gather)
    if callback:
        # Aggregate metrics for the completion callback
        aggregated_metrics = StageExecutionMetrics(
            duration_ms=sum(m.duration_ms for m in all_metrics) if all_metrics else 0,
            duration_api_ms=sum(m.duration_api_ms for m in all_metrics)
            if all_metrics
            else 0,
            num_turns=sum(m.num_turns for m in all_metrics) if all_metrics else 0,
            total_cost_usd=sum(m.total_cost_usd for m in all_metrics)
            if all_metrics
            else 0.0,
            usage={
                "total_input_tokens": sum(
                    m.usage.get("total_input_tokens", 0) for m in all_metrics
                ),
                "total_output_tokens": sum(
                    m.usage.get("total_output_tokens", 0) for m in all_metrics
                ),
            },
            tool_calls=[tc for m in all_metrics for tc in m.tool_calls],
        )
        await callback.on_stage_complete(
            WorkflowGenerationStage.TASK_BUILDING,
            {
                "tasks_count": len(tasks_built),
                "successful": successful_count,
                "failed": len(tasks_built) - successful_count,
            },
            aggregated_metrics,
        )

    return tasks_built, all_metrics


async def run_workflow_assembly_independent(
    task_proposals: list[dict[str, Any]],
    tasks_built: list[dict[str, Any]],
    alert: dict[str, Any],
    runbook: str,
    run_id: str,
    tenant_id: str,
    created_by: str,
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run workflow assembly as independent execution.

    This starts a fresh execution context with no SDK state carried over
    from Task Building. This avoids cancel scope errors from Task Building
    affecting Workflow Assembly.

    Args:
        task_proposals: Original proposals from the Task Proposals stage
        tasks_built: Results from parallel Task Building
        alert: alert
        runbook: Runbook content
        run_id: Run ID (reused for correlation)
        tenant_id: Tenant ID
        created_by: User who triggered generation
        executor: SDK executor (fresh instance)
        callback: Progress callback

    Returns:
        Dict with workflow_id, workflow_composition, workflow_error, metrics
    """
    logger.info("workflow_assembly_starting_phase4")

    # Create fresh workspace for workflow assembly
    workspace = AgentWorkspace(run_id=f"{run_id}-workflow", tenant_id=tenant_id)

    try:
        # Prepare state for workflow assembly
        state = {
            "workspace": workspace,
            "task_proposals": task_proposals,
            "tasks_built": tasks_built,
            "alert": alert,
            "runbook": runbook,
            "run_id": run_id,
            "tenant_id": tenant_id,
            "created_by": created_by,
        }

        # Execute workflow assembly
        result = await workflow_assembly_node(state, executor, callback)

        return {
            "workflow_id": result.get("workflow_id"),
            "workflow_composition": result.get("workflow_composition", []),
            "workflow_error": result.get("workflow_error"),
            "workspace_path": str(workspace.work_dir),
            "metrics": result.get("metrics", []),
        }

    except Exception as e:
        logger.exception("workflow_assembly_failed", error=str(e))
        return {
            "workflow_id": None,
            "workflow_composition": [],
            "workflow_error": f"Workflow assembly exception: {e!s}",
            "workspace_path": str(workspace.work_dir),
            "metrics": [],
        }
    finally:
        # Cleanup workspace
        workspace.cleanup()


async def run_second_subgraph(
    task_proposals: list[dict[str, Any]],
    runbook: str,
    alert: dict[str, Any],
    executor: AgentOrchestrationExecutor,
    run_id: str,
    callback: ProgressCallback | None = None,
    tenant_id: str = "default",
    created_by: str = str(SYSTEM_USER_ID),
    max_tasks_to_build: int | None = None,
    task_generation_client: TaskGenerationApiClient | None = None,
) -> dict[str, Any]:
    """Run the second subgraph without LangGraph.

    Task Building: Parallel task building using asyncio.gather()
    Workflow Assembly: Workflow assembly (fresh execution after clean break)

    Args:
        task_proposals: Task proposals from first subgraph
        runbook: Runbook content from first subgraph
        alert: alert to process
        executor: AgentOrchestrationExecutor for Claude SDK calls
        run_id: Run ID from first subgraph (reused for workspace correlation)
        callback: Optional progress callback
        tenant_id: Tenant ID for multi-tenant isolation
        created_by: User/system that triggered workflow generation
        max_tasks_to_build: Optional limit on parallel task building (cost control)
        task_generation_client: Optional client for tracking task building via REST API

    Returns:
        Dict with workflow_id, tasks_built, workflow_composition, metrics, etc.
    """
    logger.info(
        "second_subgraph_starting",
        proposal_count=len(task_proposals),
    )

    # ===================================================================
    # PHASE 3: PARALLEL TASK BUILDING
    # ===================================================================
    tasks_built, metrics = await run_parallel_task_building(
        task_proposals=task_proposals,
        alert=alert,
        runbook=runbook,
        run_id=run_id,
        tenant_id=tenant_id,
        created_by=created_by,
        executor=executor,
        callback=callback,
        max_tasks_to_build=max_tasks_to_build,
        task_generation_client=task_generation_client,
    )

    logger.info("second_subgraph_phase3_complete", tasks_built=len(tasks_built))

    # ===================================================================
    # CLEAN BREAK: No SDK state carried over
    # ===================================================================

    # ===================================================================
    # PHASE 4: WORKFLOW ASSEMBLY (FRESH EXECUTION)
    # ===================================================================
    assembly_result = await run_workflow_assembly_independent(
        task_proposals=task_proposals,
        tasks_built=tasks_built,
        alert=alert,
        runbook=runbook,
        run_id=run_id,
        tenant_id=tenant_id,
        created_by=created_by,
        executor=executor,
        callback=callback,
    )

    logger.info(
        "second_subgraph_phase4_complete",
        workflow_id=assembly_result.get("workflow_id"),
    )

    # Combine Task Building + Workflow Assembly metrics
    all_metrics = metrics + assembly_result.get("metrics", [])

    # Combine results
    return {
        "tasks_built": tasks_built,
        "workflow_id": assembly_result.get("workflow_id"),
        "workflow_composition": assembly_result.get("workflow_composition", []),
        "workflow_error": assembly_result.get("workflow_error"),
        "workspace_path": assembly_result.get("workspace_path"),
        "metrics": all_metrics,
        "run_id": run_id,
        "tenant_id": tenant_id,
    }
