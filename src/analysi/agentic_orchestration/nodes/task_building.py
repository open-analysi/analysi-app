"""Task building node for workflow generation.

This node builds a SINGLE task from a proposal using the cybersec-task-builder agent.
It is designed to be called in parallel via asyncio.gather().

The second_subgraph spawns multiple instances of this node (one per task proposal
that needs building - designation="new" or "modification").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from analysi.agentic_orchestration.config import get_agent_path
from analysi.config.logging import get_logger

if TYPE_CHECKING:
    from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.agentic_orchestration.logging_context import (
    extract_task_id_from_run_id,
    get_stage_logger,
)
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.models.auth import SYSTEM_USER_ID

logger = get_logger(__name__)

# Agent name (resolved via config at runtime)
TASK_BUILDER_AGENT_NAME = "cybersec-task-builder.md"


async def run_task_builder_agent(
    workspace: AgentWorkspace,
    executor: AgentOrchestrationExecutor,
    context: dict[str, Any],
    callback: ProgressCallback | None = None,
) -> tuple[dict[str, str | None], StageExecutionMetrics]:
    """Run the cybersec-task-builder agent via workspace.

    Shared function used by both:
    - task_building_node() for Kea workflow generation
    - execute_task_build() for standalone task generation API

    Args:
        workspace: AgentWorkspace for file capture and isolation
        executor: AgentOrchestrationExecutor for Claude SDK calls
        context: Agent context dict (proposal, alert, runbook, task_metadata)
        callback: Optional progress callback

    Returns:
        Tuple of (outputs dict, metrics)
    """
    outputs, metrics = await workspace.run_agent(
        executor=executor,
        agent_prompt_path=get_agent_path(TASK_BUILDER_AGENT_NAME),
        context=context,
        expected_outputs=[],  # No file outputs expected - agent uses MCP
        stage=WorkflowGenerationStage.TASK_BUILDING,
        callback=callback,
    )
    return outputs, metrics


async def _check_task_exists(
    tenant_id: str,
    task_identifier: str,
    api_base_url: str | None = None,
) -> dict[str, Any] | None:
    """Check if a task already exists using REST API.

    Searches in order:
    1. Exact cy_name match (task_identifier used as-is)
    2. Exact name match via fuzzy search
    3. Derived cy_name match (generate cy_name from task_identifier as if it were
       a display name — handles cases where the agent renames the task slightly
       but the normalized cy_name is the same)

    Args:
        tenant_id: Tenant ID for API call
        task_identifier: Task cy_name or name to check
        api_base_url: Base URL for API (default: from AlertAnalysisConfig.API_BASE_URL)

    Returns:
        Task dict if exists, None if not found
    """
    from analysi.repositories.component import generate_cy_name

    if api_base_url is None:
        api_base_url = AlertAnalysisConfig.API_BASE_URL
    from analysi.common.internal_auth import internal_auth_headers
    from analysi.common.internal_client import InternalAsyncClient

    try:
        async with InternalAsyncClient(headers=internal_auth_headers()) as client:
            # 1. Try searching by cy_name first (exact match)
            response = await client.get(
                f"{api_base_url}/v1/{tenant_id}/tasks",
                params={"cy_name": task_identifier, "limit": 1},
                timeout=10.0,
            )

            if response.status_code == 200:
                tasks = response.json()
                if tasks and len(tasks) > 0:
                    logger.info(
                        "task_found_by_cy_name",
                        task_identifier=task_identifier,
                        task_id=tasks[0].get("id"),
                        task_name=tasks[0].get("name"),
                    )
                    return tasks[0]

            # 2. Try searching by exact name match
            response = await client.get(
                f"{api_base_url}/v1/{tenant_id}/tasks",
                params={"q": task_identifier, "limit": 1},
                timeout=10.0,
            )

            if response.status_code == 200:
                tasks = response.json()
                if tasks and len(tasks) > 0:
                    task = tasks[0]
                    # Verify exact match (q does fuzzy search)
                    if task.get("name") == task_identifier:
                        logger.info(
                            "task_found_by_exact_name",
                            task_identifier=task_identifier,
                            task_id=task.get("id"),
                        )
                        return task
                    logger.info(
                        "task_name_near_miss",
                        searched_for=task_identifier,
                        fuzzy_result_name=task.get("name"),
                        fuzzy_result_id=task.get("id"),
                    )

            # 3. Derive cy_name from identifier and search by that.
            # Handles agent renaming: "SharePoint JWT Auth" vs "SharePoint: JWT Auth"
            # both normalize to the same cy_name.
            derived_cy_name = generate_cy_name(task_identifier, "task")
            if derived_cy_name != task_identifier:
                response = await client.get(
                    f"{api_base_url}/v1/{tenant_id}/tasks",
                    params={"cy_name": derived_cy_name, "limit": 1},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    tasks = response.json()
                    if tasks and len(tasks) > 0:
                        logger.info(
                            "task_found_by_derived_cy_name",
                            task_identifier=task_identifier,
                            derived_cy_name=derived_cy_name,
                            task_id=tasks[0].get("id"),
                            task_name=tasks[0].get("name"),
                        )
                        return tasks[0]

            logger.info(
                "task_not_found",
                task_identifier=task_identifier,
                derived_cy_name=derived_cy_name,
            )

        return None
    except Exception as e:
        logger.warning(
            "task_check_for_failed_with_error",
            task_identifier=task_identifier,
            error=str(e),
        )
        return None


async def _verify_task_created(
    tenant_id: str,
    cy_name: str,
    api_base_url: str | None = None,
) -> dict[str, Any] | None:
    """Verify a task was created by checking if it exists.

    Args:
        tenant_id: Tenant ID for API call
        cy_name: Expected cy_name of created task
        api_base_url: Base URL for API (default: from AlertAnalysisConfig.API_BASE_URL)

    Returns:
        Task dict if exists, None if not found
    """
    return await _check_task_exists(tenant_id, cy_name, api_base_url)


async def task_building_node(
    state: dict[str, Any],
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build a SINGLE task from a proposal using cybersec-task-builder agent.

    This node is designed to be invoked in parallel via asyncio.gather().
    Each instance receives a single proposal to build.

    Flow:
    1. Pre-flight check: Does task already exist?
    2. Agent execution: Run cybersec-task-builder
    3. Post-flight check: Was task created successfully?

    Args:
        state: State containing a single proposal, alert, runbook, run_id, tenant_id
            - proposal: The task proposal to build (required)
            - alert: alert context
            - runbook: Runbook content
            - run_id: Unique run ID for workspace isolation
            - tenant_id: Tenant ID for multi-tenant isolation
        executor: AgentOrchestrationExecutor for Claude SDK calls
        callback: Optional progress callback

    Returns:
        State update with tasks_built (list with single result) for reducer aggregation
    """
    proposal = state.get("proposal")

    if not proposal:
        # This is a programming error - parallel task invocation is broken
        raise ValueError(
            "task_building_node called without proposal in state. "
            "This indicates a bug in the parallel task setup. "
            "Each parallel task node MUST receive a proposal."
        )

    proposal_name = proposal.get("name", "unknown")
    designation = proposal.get("designation", "new")
    expected_cy_name = proposal.get("cy_name")  # May be None for "new" tasks
    tenant_id = state["tenant_id"]

    # Use workspace from state (created in second_subgraph for each parallel task)
    workspace = state["workspace"]

    # Create contextual logger with stage and task ID from workspace run_id
    task_id = extract_task_id_from_run_id(workspace.run_id)
    ctx_logger = get_stage_logger(WorkflowGenerationStage.TASK_BUILDING, task_id)

    ctx_logger.info(
        "building_task", proposal_name=proposal_name, designation=designation
    )

    # Default metrics for error cases
    default_metrics = StageExecutionMetrics(
        duration_ms=0,
        duration_api_ms=0,
        num_turns=0,
        total_cost_usd=0.0,
        usage={},
        tool_calls=[],
    )

    try:
        # ===================================================================
        # PRE-FLIGHT CHECK: Does task already exist via REST API?
        # ===================================================================

        # Check by name first (primary identifier)
        existing_by_name = await _check_task_exists(tenant_id, proposal_name)

        # Check by cy_name if provided (for modification/existing tasks)
        existing_by_cy_name = None
        if expected_cy_name:
            existing_by_cy_name = await _check_task_exists(tenant_id, expected_cy_name)

        if existing_by_name or existing_by_cy_name:
            # Task already exists - skip generation
            existing_task = existing_by_name or existing_by_cy_name
            assert existing_task is not None  # Guaranteed by the if condition
            ctx_logger.warning(
                "task_already_exists_skipping",
                proposal_name=proposal_name,
                existing_cy_name=existing_task.get("cy_name"),
                existing_id=existing_task.get("id"),
                designation=designation,
            )

            result = {
                "proposal_name": proposal_name,
                "designation": designation,
                "success": True,  # Success - task exists
                "task_id": existing_task.get("id"),
                "cy_name": existing_task.get("cy_name"),
                "error": None,
                "skipped": True,  # Flag indicating we skipped generation
                "skip_reason": "Task already exists in system",
            }

            if callback:
                await callback.on_stage_complete(
                    WorkflowGenerationStage.TASK_BUILDING,
                    {
                        "task_id": result["task_id"],
                        "cy_name": result["cy_name"],
                        "skipped": True,
                    },
                    default_metrics,
                )

            return_value = {"tasks_built": [result], "metrics": [default_metrics]}
            ctx_logger.info(
                "task_building_existing_task_return",
                tasks_built=return_value["tasks_built"],
            )
            return return_value

        # ===================================================================
        # AGENT EXECUTION: Build the task
        # ===================================================================

        # Prepare enhanced context with explicit metadata
        agent_context = {
            "proposal": proposal,
            "alert": state.get("alert", {}),
            "runbook": state.get("runbook", ""),
            # Explicit task metadata for MCP create_task
            "task_metadata": {
                "name": proposal.get("name"),  # Explicit name from proposal
                "created_by": state.get("created_by", str(SYSTEM_USER_ID)),
                "tenant_id": state.get("tenant_id", "default"),
                "source": "runbook-workflow",
                "rule_name": state.get("alert", {}).get("rule_name"),
            },
        }

        outputs, metrics = await run_task_builder_agent(
            workspace=workspace,
            executor=executor,
            context=agent_context,
            callback=callback,
        )

        # ===================================================================
        # POST-FLIGHT CHECK: Verify task was created via REST API
        # ===================================================================

        # Try to find the created task by name (agent should have created it)
        created_task = await _check_task_exists(tenant_id, proposal_name)

        if not created_task:
            # Task creation failed - agent didn't create the task
            error_msg = (
                f"Agent execution completed but task '{proposal_name}' was not found in system. "
                f"Agent may have failed to call create_task MCP tool or task creation failed. "
                f"Check agent workspace for details: {workspace.work_dir}"
            )
            ctx_logger.error(
                "task_not_created_after_agent_execution",
                proposal_name=proposal_name,
                work_dir=str(workspace.work_dir),
            )

            result = {
                "proposal_name": proposal_name,
                "designation": designation,
                "success": False,
                "task_id": None,
                "cy_name": None,
                "error": error_msg,
            }

            if callback:
                await callback.on_stage_complete(
                    WorkflowGenerationStage.TASK_BUILDING,
                    {"error": result["error"]},
                    metrics,
                )

            return_value = {"tasks_built": [result], "metrics": [metrics]}
            ctx_logger.info(
                "task_building_not_created_return",
                tasks_built=return_value["tasks_built"],
            )
            return return_value

        # Success - task was created
        result = {
            "proposal_name": proposal_name,
            "designation": designation,
            "success": True,
            "task_id": created_task.get("id"),
            "cy_name": created_task.get("cy_name"),
            "error": None,
        }

        ctx_logger.info(
            "task_built_successfully",
            cy_name=result["cy_name"],
            task_id=result["task_id"],
        )

        if callback:
            await callback.on_stage_complete(
                WorkflowGenerationStage.TASK_BUILDING,
                {"task_id": result["task_id"], "cy_name": result["cy_name"]},
                metrics,
            )

        return_value = {"tasks_built": [result], "metrics": [metrics]}
        ctx_logger.info(
            "task_building_success_return",
            tasks_built=return_value["tasks_built"],
        )
        return return_value

    except FileNotFoundError:
        # Let configuration errors propagate immediately (fail fast)
        # Missing agent files are deployment errors, not runtime errors
        raise
    except BaseException as e:
        # CRITICAL: Catch BaseException to handle CancelledError from SDK cleanup
        # CancelledError is a BaseException in Python 3.8+, not Exception
        ctx_logger.exception(
            "agent_execution_failed", proposal_name=proposal_name, error=str(e)
        )

        # ===================================================================
        # RECOVERY: Check if task was created before agent crashed
        # ===================================================================
        # Agent might have successfully called create_task() MCP tool before
        # the SDK cancel scope exception occurred. Check if task exists.

        try:
            ctx_logger.info(
                "task_building_attempting_recovery",
                proposal_name=proposal_name,
            )
            existing_task = await _check_task_exists(tenant_id, proposal_name)

            if existing_task:
                # Success! Task was created before crash
                ctx_logger.info(
                    "task_building_recovered",
                    cy_name=existing_task["cy_name"],
                    task_id=existing_task["id"],
                )
                result = {
                    "proposal_name": proposal_name,
                    "designation": designation,
                    "success": True,
                    "task_id": existing_task.get("id"),
                    "cy_name": existing_task.get("cy_name"),
                    "recovered": True,  # Flag for observability
                    "error": None,
                }
                return_value = {"tasks_built": [result], "metrics": [default_metrics]}
                ctx_logger.info(
                    "task_building_recovered_return",
                    tasks_built=return_value["tasks_built"],
                )
                return return_value
        except Exception as recovery_error:
            ctx_logger.warning(
                "task_building_recovery_check_failed",
                proposal_name=proposal_name,
                error=str(recovery_error),
            )

        # Task doesn't exist - genuine failure
        ctx_logger.error(
            "task_building_agent_failed_before_creation",
            proposal_name=proposal_name,
        )
        result = {
            "proposal_name": proposal_name,
            "designation": designation,
            "success": False,
            "task_id": None,
            "cy_name": None,
            "error": str(e),
        }
        return_value = {"tasks_built": [result], "metrics": [default_metrics]}
        ctx_logger.info(
            "task_building_exception_return",
            tasks_built=return_value["tasks_built"],
        )
        return return_value
    finally:
        # Cleanup sub-workspace for this parallel task
        # (Sequential nodes share workspace, but parallel tasks get their own)
        workspace.cleanup()


def filter_proposals_for_building(
    proposals: list[dict[str, Any]] | None,
    max_tasks: int | None = None,
) -> list[dict[str, Any]]:
    """Filter task proposals to only those needing building.

    Args:
        proposals: List of task proposals from first subgraph
        max_tasks: Optional limit on number of tasks to build (for cost control during testing)

    Returns:
        Filtered list containing only proposals with designation "new" or "modification",
        limited to max_tasks if specified
    """
    if not proposals:
        return []

    filtered = [p for p in proposals if p.get("designation") in ("new", "modification")]

    # Apply limit if specified
    if max_tasks is not None and max_tasks > 0:
        return filtered[:max_tasks]

    return filtered
