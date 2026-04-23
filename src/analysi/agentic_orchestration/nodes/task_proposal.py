"""Task proposal node for workflow generation."""

from typing import Any

from analysi.agentic_orchestration.config import get_agent_path
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Agent name (resolved via config at runtime)
TASK_PROPOSAL_AGENT_NAME = "runbook-to-task-proposals.md"


async def task_proposal_node(
    state: dict[str, Any],
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Propose tasks from runbook using runbook-to-task-proposals agent.

    Args:
        state: Current workflow state containing alert and runbook
        executor: AgentOrchestrationExecutor for Claude SDK calls
        callback: Optional progress callback

    Returns:
        State update with task proposals and metrics

    Raises:
        RuntimeError: If agent execution fails or expected outputs are missing
    """
    # Early exit if previous stage failed
    if state.get("error"):
        return {"task_proposals": None, "metrics": state.get("metrics", [])}

    # Get alert identifier for logging
    alert = state["alert"]
    alert_identifier = (
        alert.get("source_event_id") or alert.get("title", "unknown")[:50]
    )

    if callback:
        await callback.on_stage_start(
            WorkflowGenerationStage.TASK_PROPOSALS,
            {"alert_identifier": alert_identifier},
        )

    # Use workspace from state (created at subgraph level)
    workspace = state["workspace"]

    logger.info("taskproposal_starting_for_alert", alert_identifier=alert_identifier)

    try:
        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=get_agent_path(TASK_PROPOSAL_AGENT_NAME),
            context={
                "alert": state["alert"],
                "runbook": state["runbook"],
            },
            expected_outputs=["task-proposals.json"],
            stage=WorkflowGenerationStage.TASK_PROPOSALS,
            callback=callback,
        )

        # Parse structured output
        task_proposals_json = outputs.get("task-proposals.json")

        # Validate critical outputs exist
        if task_proposals_json is None:
            raise RuntimeError(
                f"Task proposal failed: expected 'task-proposals.json' not found in {workspace.work_dir}"
            )

        task_proposals = parse_task_proposals(task_proposals_json)

        if callback:
            await callback.on_stage_complete(
                WorkflowGenerationStage.TASK_PROPOSALS,
                task_proposals_json,
                metrics,
            )

        # Count proposals by designation
        designation_counts: dict[str, int] = {}
        for proposal in task_proposals:
            designation = proposal.get("designation", "unknown")
            designation_counts[designation] = designation_counts.get(designation, 0) + 1

        logger.info(
            "task_proposal_success",
            proposals_count=len(task_proposals),
            designation_counts=designation_counts,
        )

        return {
            "task_proposals": task_proposals,
            "metrics": state["metrics"] + [metrics],
        }
    except FileNotFoundError:
        # Let configuration errors propagate immediately (fail fast)
        # Missing agent files are deployment errors, not runtime errors
        raise
    except Exception as e:
        # Update state with error for runtime errors
        error_msg = f"Task proposal failed: {e!s}"
        logger.error("taskproposal_error", error_msg=error_msg)
        return {
            "task_proposals": None,
            "metrics": state.get("metrics", []),
            "error": error_msg,
        }


def parse_task_proposals(llm_output: str | None) -> list[dict[str, Any]]:
    """Parse LLM output into structured task proposals.

    Args:
        llm_output: Raw LLM output containing task proposals (JSON string)

    Returns:
        List of parsed task proposal dictionaries
    """
    if not llm_output:
        return []

    import json

    try:
        data = json.loads(llm_output)
        # Handle both list and object with 'proposals' key
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "proposals" in data:
            return data["proposals"]
        return []
    except json.JSONDecodeError:
        return []
