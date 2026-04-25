"""LangGraph-based runbook generation node.

Drop-in replacement for runbook_generation_node() when feature flag is enabled.
Uses the LangGraph Runbook Matching implementation instead of Claude Agent SDK.
"""

import json
from typing import Any

from analysi.agentic_orchestration.langgraph.config import (
    create_langgraph_llm,
    get_db_skills_store,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.graph import run_phase1
from analysi.agentic_orchestration.langgraph.metrics import LangGraphMetricsCollector
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    WorkflowGenerationStage,
)
from analysi.config.logging import get_logger

logger = get_logger(__name__)


async def runbook_generation_node_langgraph(
    state: dict[str, Any],
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Generate runbook using LangGraph Runbook Matching implementation.

    Drop-in replacement for runbook_generation_node() when feature flag enabled.
    Returns same output structure: {runbook, matching_report, metrics}.

    Args:
        state: Current workflow state containing alert.
        callback: Optional progress callback for stage notifications.

    Returns:
        State update with runbook, matching_report (JSON string), and metrics list.
        On error, returns {runbook: None, matching_report: None, error: str}.
    """
    alert = state["alert"]
    alert_identifier = (
        alert.get("source_event_id") or alert.get("title", "unknown")[:50]
    )

    # Start metrics collection
    # NOTE: Currently only duration is tracked. Token counting requires deeper
    # integration with SubStep executor to capture LLM response metadata.
    # See TODO in langgraph/metrics.py for future enhancement.
    metrics_collector = LangGraphMetricsCollector()
    metrics_collector.start()

    # Notify callback of stage start
    if callback:
        await callback.on_stage_start(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            {"alert_identifier": alert_identifier},
        )

    try:
        # Get dependencies
        llm = create_langgraph_llm()
        store = get_db_skills_store(state["tenant_id"])

        logger.info(
            "runbookgenerationlanggraph_starting_for_alert",
            alert_identifier=alert_identifier,
        )

        # Run Runbook Matching graph
        # Note: repository_path is empty since we use DB-based store (skills are DB-only)
        result = await run_phase1(
            alert=alert,
            llm=llm,
            store=store,
            repository_path="",  # Not used when store is provided
        )

        runbook = result.get("runbook")
        matching_report = result.get("matching_report", {})

        # Log decision
        decision = matching_report.get("decision", "unknown")
        if decision == "matched":
            logger.info("[RUNBOOK_GENERATION_LANGGRAPH] Matched existing runbook")
        elif decision == "composed":
            logger.info("[RUNBOOK_GENERATION_LANGGRAPH] Composed new runbook")
        else:
            logger.info("runbookgenerationlanggraph_decision", decision=decision)

        # Convert matching_report to JSON string (SDK contract)
        # Use "is not None" to handle empty dicts correctly ({} is falsy but valid)
        matching_report_json = (
            json.dumps(matching_report) if matching_report is not None else None
        )

        # Collect metrics
        stage_metrics = metrics_collector.to_stage_metrics()

        # Notify callback of stage completion
        if callback:
            await callback.on_stage_complete(
                WorkflowGenerationStage.RUNBOOK_GENERATION,
                runbook,
                stage_metrics,
            )

        logger.info(
            "runbook_generation_langgraph_success",
            runbook_chars=len(runbook) if runbook else 0,
        )

        return {
            "runbook": runbook,
            "matching_report": matching_report_json,
            "metrics": [stage_metrics],
        }

    except Exception as e:
        error_msg = f"LangGraph runbook generation failed: {e!s}"
        logger.error("runbookgenerationlanggraph_error", error_msg=error_msg)

        # Notify callback of stage error
        if callback:
            partial_metrics = metrics_collector.to_stage_metrics()
            await callback.on_stage_error(
                WorkflowGenerationStage.RUNBOOK_GENERATION,
                e,
                partial_metrics,
            )

        return {
            "runbook": None,
            "matching_report": None,
            "metrics": state.get("metrics", []),
            "error": error_msg,
        }
