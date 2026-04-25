"""Orchestrator for full alert → Workflow pipeline.

This module provides two orchestration approaches:

1. run_full_orchestration() - Legacy approach using subgraphs directly
2. run_orchestration_with_stages() - New pluggable stages approach

The pluggable stages approach enables:
- Test mode: Skip expensive AI calls, clone default workflow
- Production mode: Full agent-based workflow generation
- Future: Mix and match stage implementations

- Optional skills_syncer for DB-backed skills (tenant isolation)
- Syncs skills to workspace before agent execution
- Routes agent-created files through extraction pipeline

Usage:
    from analysi.agentic_orchestration import (
        run_full_orchestration,
        create_executor,
    )

    executor = create_executor(
        tenant_id=tenant_id,
        oauth_token=oauth_token,
    )

    result = await run_full_orchestration(
        alert=alert,
        executor=executor,
        tenant_id=tenant_id,
    )

    workflow_id = result["workflow_id"]

For detailed specification, see:
    docs/specs/AutomatedWorkflowBuilder.md
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.stages.base import SDK_METRICS_KEY, StageStrategy
from analysi.agentic_orchestration.subgraphs import (
    run_first_subgraph,
    run_second_subgraph,
)
from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.alert import AlertBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer

logger = get_logger(__name__)


async def run_full_orchestration(
    alert: AlertBase,
    executor: AgentOrchestrationExecutor,
    tenant_id: str,
    run_id: str,
    created_by: str = str(SYSTEM_USER_ID),
    progress_callback: ProgressCallback | None = None,
    max_tasks_to_build: int | None = None,
    skills_syncer: TenantSkillsSyncer | None = None,
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Execute complete workflow generation pipeline.

    Connects both subgraphs sequentially:
    1. First subgraph: Alert → Runbook → Task Proposals
    2. Second subgraph: Task Building (parallel) → Workflow Assembly

    Args:
        alert: alert in Pydantic format
        executor: Agent orchestration executor with MCP access
        tenant_id: Tenant identifier for MCP operations
        run_id: Run ID for workspace isolation (typically generation_id from database).
                Workspace paths will contain this ID for troubleshooting and correlation
                with DB records.
        created_by: UUID string of user/system that triggered workflow generation
        progress_callback: Optional callback for stage progress tracking
        max_tasks_to_build: Optional limit on parallel task building (for cost control during testing)
        skills_syncer: Optional TenantSkillsSyncer for DB-backed skills.
                      When provided, skills are synced to workspace/.claude/skills/
                      before agent execution (enables tenant-isolated skills).
        session: Optional database session for Hydra submission.
                When provided with skills_syncer, new files created by the agent
                are submitted to the Hydra extraction pipeline.

    Returns:
        {
            "workflow_id": str | None,
            "workspace_path": str | None,
            "workflow_composition": list[str],
            "tasks_built": list[dict],
            "runbook": str,
            "metrics": list[StageExecutionMetrics],
            "error": str | None
        }

    Example:
        >>> result = await run_full_orchestration(
        ...     alert, executor, "tenant-1", run_id="550e8400-e29b-41d4-a716-446655440000"
        ... )
        >>> print(result["workflow_id"])
        "550e8400-e29b-41d4-a716-446655440000"
    """
    # Convert AlertBase to dict for subgraph consumption
    alert_dict = alert.model_dump(mode="json")

    logger.info(
        "orchestrator_starting_full_workflow_generation",
        alert_title=alert.title,
        run_id=run_id,
    )

    # Stage 1-2: First subgraph (Runbook → Task Proposals)
    first_result = await run_first_subgraph(
        alert_dict,
        executor,
        run_id,
        callback=progress_callback,
        tenant_id=tenant_id,
        created_by=created_by,
        skills_syncer=skills_syncer,
        session=session,
    )

    # Log first subgraph completion
    task_proposals = first_result.get("task_proposals") or []
    logger.info(
        "orchestrator_first_subgraph_completed",
        task_proposals_count=len(task_proposals),
    )

    # Count proposals by designation
    designation_counts: dict[str, int] = {}
    for proposal in task_proposals:
        designation = proposal.get("designation", "unknown")
        designation_counts[designation] = designation_counts.get(designation, 0) + 1

    logger.info(
        "orchestrator_proposals_by_designation", designations=designation_counts
    )

    # Check for errors in first subgraph
    if first_result.get("error"):
        logger.error(
            "orchestrator_first_subgraph_failed",
            error=first_result.get("error"),
        )
        return {
            "workflow_id": None,
            "workspace_path": None,
            "workflow_composition": [],
            "tasks_built": [],
            "runbook": first_result.get("runbook", ""),
            "metrics": first_result.get("metrics", []),
            "error": first_result["error"],
        }

    # Stage 3-4: Second subgraph (Task Building → Workflow Assembly)
    # Use same run_id for workspace correlation
    logger.info(
        "orchestrator_starting_second_subgraph",
        proposals_count=len(task_proposals),
    )

    second_result = await run_second_subgraph(
        task_proposals=first_result.get("task_proposals") or [],
        runbook=first_result.get("runbook") or "",
        alert=alert_dict,
        executor=executor,
        run_id=run_id,
        callback=progress_callback,
        tenant_id=tenant_id,
        created_by=created_by,
        max_tasks_to_build=max_tasks_to_build,
    )

    # Aggregate metrics from both subgraphs
    all_metrics = first_result.get("metrics", []) + second_result.get("metrics", [])

    # Log final result
    tasks_built = second_result.get("tasks_built", [])
    workflow_id = second_result.get("workflow_id")
    workflow_composition = second_result.get("workflow_composition", [])

    logger.info(
        "orchestrator_completed",
        tasks_built_count=len(tasks_built),
        workflow_id=workflow_id,
        workflow_composition_steps=len(workflow_composition),
    )

    if workflow_id:
        logger.info("orchestrator_success_workflow_created", workflow_id=workflow_id)
    else:
        logger.warning(
            "orchestrator_no_workflow_created",
            tasks_built_count=len(tasks_built),
            error=second_result.get("workflow_error"),
        )

    # Return combined results
    return {
        "workflow_id": second_result.get("workflow_id"),
        "workspace_path": second_result.get("workspace_path"),
        "workflow_composition": second_result.get("workflow_composition", []),
        "tasks_built": second_result.get("tasks_built", []),
        "runbook": first_result["runbook"],
        "metrics": all_metrics,
        "error": second_result.get("workflow_error"),
    }


async def run_orchestration_with_stages(
    stages: list[StageStrategy],
    initial_state: dict[str, Any],
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run workflow generation with pluggable stages.

    This is the framework function that handles:
    - Timing measurement (duration_ms)
    - Callback invocations (on_stage_start, on_stage_complete)
    - Metrics aggregation
    - Error handling

    Stages just do their work and return state updates. The framework
    wraps each stage with timing and callback logic.

    Args:
        stages: Ordered list of stage strategies to execute
        initial_state: Initial state containing alert, tenant_id, run_id
        callback: Optional progress callback for status updates

    Returns:
        Final state with all stage outputs and aggregated metrics
    """
    # Validate required state keys
    for key in ("tenant_id", "run_id", "alert"):
        if key not in initial_state:
            raise ValueError(f"initial_state missing required key: '{key}'")

    state = initial_state.copy()
    all_metrics: list[StageExecutionMetrics] = []

    logger.info("orchestrator_starting", stage_count=len(stages))

    for stage in stages:
        stage_name = stage.stage.value

        # Framework: timing starts
        start_time = time.perf_counter()

        # Framework: notify stage start
        if callback:
            await callback.on_stage_start(stage.stage, {"stage": stage_name})

        try:
            # Stage: just does the work, returns state updates
            logger.info("orchestrator_executing_stage", stage_name=stage_name)
            state_update = await stage.execute(state)

            # Framework: timing ends
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Framework: extract SDK metrics if present, or create empty
            sdk_metrics = state_update.pop(SDK_METRICS_KEY, None)
            if sdk_metrics:
                # Agent stage - use SDK metrics, but ensure duration is framework-measured
                metrics = sdk_metrics
                # Only override if SDK didn't measure (e.g., for consistency)
                if metrics.duration_ms == 0:
                    metrics.duration_ms = duration_ms
            else:
                # Non-agent stage (e.g., dummy, clone) - framework creates empty metrics
                metrics = StageExecutionMetrics(
                    duration_ms=duration_ms,
                    duration_api_ms=0,
                    num_turns=0,
                    total_cost_usd=0.0,
                    usage={},
                    tool_calls=[],
                )

            # Framework: notify stage complete
            if callback:
                await callback.on_stage_complete(stage.stage, state_update, metrics)

            # Apply state updates
            state.update(state_update)
            all_metrics.append(metrics)

            logger.info(
                "orchestrator_stage_completed",
                stage_name=stage_name,
                duration_ms=duration_ms,
            )

            # Check for errors - stop if stage failed
            if state.get("error"):
                logger.error(
                    "orchestrator_stage_failed",
                    stage_name=stage_name,
                    error=state["error"],
                )
                break

        except Exception as e:
            # Framework: error handling with partial metrics
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            partial_metrics = StageExecutionMetrics(
                duration_ms=duration_ms,
                duration_api_ms=0,
                num_turns=0,
                total_cost_usd=0.0,
                usage={},
                tool_calls=[],
            )
            if callback:
                await callback.on_stage_error(stage.stage, e, partial_metrics)

            logger.exception(
                "orchestrator_stage_raised_exception", stage_name=stage_name
            )
            state["error"] = str(e)
            all_metrics.append(partial_metrics)
            break

    state["metrics"] = all_metrics

    # Log final result
    workflow_id = state.get("workflow_id")
    if workflow_id:
        logger.info("orchestrator_success_workflow_created", workflow_id=workflow_id)
    else:
        logger.warning(
            "orchestrator_no_workflow_created",
            error=state.get("error"),
        )

    return state
