"""Runbook generation node for workflow generation."""

import os
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
RUNBOOK_AGENT_NAME = "runbook-match-agent.md"

# Feature flag environment variable
LANGGRAPH_FEATURE_FLAG = "ANALYSI_USE_LANGGRAPH_PHASE1"


def _use_langgraph() -> bool:
    """Check if LangGraph implementation should be used.

    Returns:
        True if ANALYSI_USE_LANGGRAPH_PHASE1 env var is set to "true" (case-insensitive).
    """
    value = os.environ.get(LANGGRAPH_FEATURE_FLAG, "").strip().lower()
    return value == "true"


async def runbook_generation_node(
    state: dict[str, Any],
    executor: AgentOrchestrationExecutor | None = None,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Generate runbook for alert using runbook-match-agent.

    Args:
        state: Current workflow state containing alert
        executor: AgentOrchestrationExecutor for Claude SDK calls (not needed for LangGraph)
        callback: Optional progress callback

    Returns:
        State update with runbook, matching_report, and metrics

    Raises:
        RuntimeError: If agent execution fails or expected outputs are missing
    """
    # Check feature flag for LangGraph dispatch
    if _use_langgraph():
        from analysi.agentic_orchestration.nodes.runbook_generation_langgraph import (
            runbook_generation_node_langgraph,
        )

        logger.info(
            "[RUNBOOK_GENERATION] Using LangGraph implementation (feature flag enabled)"
        )
        # runbook_generation_node_langgraph handles its own exceptions and returns
        # {error: ...} on failure, no need for another try/except here
        return await runbook_generation_node_langgraph(state, callback)

    # SDK implementation (default)
    logger.info("[RUNBOOK_GENERATION] Using SDK implementation")

    # Get alert identifier for logging (use source_event_id or title)
    alert = state["alert"]
    alert_identifier = (
        alert.get("source_event_id") or alert.get("title", "unknown")[:50]
    )

    if callback:
        await callback.on_stage_start(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            {"alert_identifier": alert_identifier},
        )

    # Use workspace from state (created at subgraph level)
    workspace = state["workspace"]

    logger.info(
        "runbookgeneration_starting_for_alert", alert_identifier=alert_identifier
    )

    try:
        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=get_agent_path(RUNBOOK_AGENT_NAME),
            context={"alert": state["alert"]},
            expected_outputs=["matching-report.json", "matched-runbook.md"],
            stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
            callback=callback,
        )

        runbook = outputs.get("matched-runbook.md")
        matching_report = outputs.get("matching-report.json")

        # Validate critical outputs exist
        if runbook is None:
            raise RuntimeError(
                f"Runbook generation failed: expected 'matched-runbook.md' not found in {workspace.work_dir}"
            )

        if callback:
            await callback.on_stage_complete(
                WorkflowGenerationStage.RUNBOOK_GENERATION,
                runbook,
                metrics,
            )

        logger.info(
            "runbook_generation_success",
            runbook_chars=len(runbook),
        )

        return {
            "runbook": runbook,
            "matching_report": matching_report,
            "metrics": [metrics],
        }
    except FileNotFoundError:
        # Let configuration errors propagate immediately (fail fast)
        # Missing agent files are deployment errors, not runtime errors
        raise
    except Exception as e:
        # Update state with error for runtime errors
        # This allows the orchestrator to capture the error in state
        error_msg = f"Runbook generation failed: {e!s}"
        logger.error("runbookgeneration_error", error_msg=error_msg)

        # Notify callback of stage error
        if callback:
            await callback.on_stage_error(
                WorkflowGenerationStage.RUNBOOK_GENERATION,
                e,
                None,  # No partial metrics available in SDK path
            )

        return {
            "runbook": None,
            "matching_report": None,
            "metrics": state.get("metrics", []),
            "error": error_msg,
        }
