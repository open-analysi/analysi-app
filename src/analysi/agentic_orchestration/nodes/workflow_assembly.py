"""Workflow assembly node for workflow generation.

This node gathers task cy_names from existing proposals and newly built tasks,
then assembles them into a validated workflow using the workflow-builder agent.

The agent uses MCP tools from the workflow-builder skill to:
1. Call compose_workflow() to create and validate the workflow
2. Optionally test the workflow with the alert data
3. Write the result (workflow_id or error) to workflow-result.json
"""

import json
import re
from typing import Any

from analysi.agentic_orchestration.config import get_agent_path
from analysi.agentic_orchestration.logging_context import get_stage_logger
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Agent name (resolved via config at runtime)
WORKFLOW_BUILDER_AGENT_NAME = "workflow-builder.md"


async def generate_unique_workflow_name(tenant_id: str, rule_name: str) -> str:
    """Generate a unique workflow name based on the alert rule name.

    Format: "{Rule Name} Analysis Workflow" (or "{Rule Name} Analysis Workflow 2" if exists)

    Args:
        tenant_id: Tenant ID to scope the uniqueness check
        rule_name: The alert's rule_name to base the workflow name on

    Returns:
        A unique workflow name
    """
    from sqlalchemy import select

    from analysi.db import AsyncSessionLocal
    from analysi.models.workflow import Workflow

    # Create base name: "Rule Name Analysis Workflow"
    # Title case the rule name for readability
    base_name = f"{rule_name} Analysis Workflow"

    # Query existing workflows with similar names
    async with AsyncSessionLocal() as session:
        # Find all workflows that start with our base name
        result = await session.execute(
            select(Workflow.name).where(
                Workflow.tenant_id == tenant_id,
                Workflow.name.like(f"{base_name}%"),
            )
        )
        existing_names = {row[0] for row in result.fetchall()}

    # If base name doesn't exist, use it
    if base_name not in existing_names:
        return base_name

    # Find the next available number
    # Extract numbers from existing names like "Rule Name Analysis Workflow 2"
    max_num = 1
    pattern = re.compile(rf"^{re.escape(base_name)}(?: (\d+))?$")

    for name in existing_names:
        match = pattern.match(name)
        if match:
            num_str = match.group(1)
            max_num = max(max_num, int(num_str)) if num_str else max(max_num, 1)

    # Return next available name
    return f"{base_name} {max_num + 1}"


class WorkflowAssemblyResult:
    """Result from workflow assembly."""

    def __init__(
        self,
        success: bool,
        workflow_id: str | None = None,
        composition: list[str] | None = None,
        error: str | None = None,
    ):
        self.success = success
        self.workflow_id = workflow_id
        self.composition = composition or []
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for state serialization."""
        return {
            "success": self.success,
            "workflow_id": self.workflow_id,
            "composition": self.composition,
            "error": self.error,
        }


async def workflow_assembly_node(
    state: dict[str, Any],
    executor: AgentOrchestrationExecutor,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Assemble tasks into validated workflow.

    Gathers cy_names from existing task proposals and newly built tasks,
    then uses the workflow-builder agent to compose them into a workflow.

    Args:
        state: Current workflow state containing task_proposals, tasks_built
        executor: AgentOrchestrationExecutor for Claude SDK calls
        callback: Optional progress callback

    Returns:
        State update with workflow_id, workflow_composition, and metrics
    """
    # Create contextual logger (no task_id for workflow assembly - it's a fan-in node)
    ctx_logger = get_stage_logger(WorkflowGenerationStage.WORKFLOW_ASSEMBLY)

    # Early exit if previous stage failed
    if state.get("error"):
        ctx_logger.info("Skipping workflow assembly due to previous error")
        return {
            "workflow_id": None,
            "workflow_composition": [],
            "workflow_error": None,
            # Don't return tasks_built or metrics - they're already accumulated by reducer
        }

    # Gather all cy_names from existing proposals and built tasks
    proposals = state.get("task_proposals", [])
    tasks_built = state.get("tasks_built", [])
    cy_names = gather_all_cy_names(proposals, tasks_built)

    # Log task building summary for observability
    total_proposals = len(
        [p for p in proposals if p.get("designation") in ("new", "modification")]
    )
    successful_builds = len([t for t in tasks_built if t.get("success")])
    failed_builds = len([t for t in tasks_built if not t.get("success")])

    if failed_builds > 0:
        failed_names = [
            t.get("proposal_name", "unknown")
            for t in tasks_built
            if not t.get("success")
        ]
        ctx_logger.warning(
            "task_building_partial_failures",
            successful_builds=successful_builds,
            total_proposals=total_proposals,
            failed_tasks=failed_names,
        )

    # Check if we have any tasks to compose
    if not cy_names:
        ctx_logger.error(
            "no_tasks_available_for_workflow_assembly",
            total_proposals=total_proposals,
        )
        return {
            "workflow_id": None,
            "workflow_composition": [],
            "workflow_error": "No tasks available for workflow assembly - all task builds failed",
            # Don't return tasks_built or metrics - they're already accumulated by reducer
        }

    ctx_logger.info(
        "assembling_workflow",
        num_tasks=len(cy_names),
        tasks=cy_names,
        newly_built=successful_builds,
        existing=len(gather_cy_names_from_existing(proposals)),
    )

    # Get alert identifier for logging
    alert_for_logging = state.get("alert", {})
    alert_identifier = (
        alert_for_logging.get("source_event_id")
        or alert_for_logging.get("title", "unknown")[:50]
    )

    if callback:
        await callback.on_stage_start(
            WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
            {
                "alert_identifier": alert_identifier,
                "num_tasks": len(cy_names),
            },
        )

    # Use workspace from state (created at subgraph level)
    workspace = state["workspace"]

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
        # Prepare context for the agent
        alert = state.get("alert", {})
        tenant_id = state["tenant_id"]
        rule_name = alert.get("rule_name", "Unknown Rule")

        # Generate unique workflow name: "{Rule Name} Analysis Workflow"
        # Appends number if name already exists (e.g., "SQL Injection Analysis Workflow 2")
        workflow_name = await generate_unique_workflow_name(tenant_id, rule_name)
        ctx_logger.info("workflow_name_generated", workflow_name=workflow_name)

        # Provide information about newly built tasks
        tasks_built = state.get("tasks_built", [])
        newly_built_cy_names = [
            t["cy_name"] for t in tasks_built if t.get("success") and t.get("cy_name")
        ]

        context = {
            "tasks": cy_names,
            "alert": alert,
            "runbook": state.get("runbook", ""),
            "workflow_name": workflow_name,
            "newly_built_tasks": newly_built_cy_names,
            "task_build_summary": f"{len(newly_built_cy_names)} tasks were just built and tested in the previous stage",
        }

        outputs, metrics = await workspace.run_agent(
            executor=executor,
            agent_prompt_path=get_agent_path(WORKFLOW_BUILDER_AGENT_NAME),
            context=context,
            expected_outputs=["workflow-result.json"],
            stage=WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
            callback=callback,
        )

        # Parse agent output
        workflow_result_json = outputs.get("workflow-result.json")

        if workflow_result_json is None:
            ctx_logger.warning("Agent did not produce workflow-result.json")
            if callback:
                await callback.on_stage_complete(
                    WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
                    {"error": "Missing output"},
                    metrics,
                )
            return {
                "workflow_id": None,
                "workflow_composition": cy_names,
                "workflow_error": "Agent did not produce workflow-result.json",
                # Don't return tasks_built - already accumulated by reducer
                # Add metrics for this stage only (reducer will accumulate)
                "metrics": [metrics],
            }

        parsed_result = parse_workflow_result(workflow_result_json)

        workflow_id = parsed_result.get("workflow_id")
        composition = parsed_result.get("composition", cy_names)
        error = parsed_result.get("error")

        # Distinguish between creation failure and test failure
        # If workflow_id exists, the workflow was created successfully
        # Test failures shouldn't invalidate a successfully created workflow
        if error and not workflow_id:
            # True creation failure - no workflow was created
            ctx_logger.warning("workflow_creation_failed", error=error)
            if callback:
                await callback.on_stage_complete(
                    WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
                    {"error": error},
                    metrics,
                )
            return {
                "workflow_id": None,
                "workflow_composition": composition,
                "workflow_error": error,
                # Don't return tasks_built - already accumulated by reducer
                # Add metrics for this stage only (reducer will accumulate)
                "metrics": [metrics],
            }
        if error and workflow_id:
            # Workflow created but test failed - still return the workflow_id
            # The workflow is valid, it just failed during testing (e.g., integration not configured)
            ctx_logger.warning(
                "workflow_created_but_test_failed",
                workflow_id=workflow_id,
                error=error,
            )

        ctx_logger.info("workflow_assembled", workflow_id=workflow_id)

        if callback:
            await callback.on_stage_complete(
                WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
                {"workflow_id": workflow_id, "composition": composition},
                metrics,
            )

        return {
            "workflow_id": workflow_id,
            "workflow_composition": composition,
            "workflow_error": None,
            # Don't return tasks_built - already accumulated by reducer
            # Add metrics for this stage only (reducer will accumulate)
            "metrics": [metrics],
        }

    except FileNotFoundError:
        # Let configuration errors propagate immediately (fail fast)
        # Missing agent files are deployment errors, not runtime errors
        raise
    except Exception as e:
        ctx_logger.exception("Error during workflow assembly")
        return {
            "workflow_id": None,
            "workflow_composition": cy_names,
            "workflow_error": str(e),
            # Don't return tasks_built - already accumulated by reducer
            # Add metrics for this stage only (reducer will accumulate)
            "metrics": [default_metrics],
        }


def gather_cy_names_from_existing(
    proposals: list[dict[str, Any]] | None,
) -> list[str]:
    """Extract cy_names from existing task proposals.

    Args:
        proposals: List of task proposals

    Returns:
        List of cy_names from proposals with designation="existing"
    """
    if not proposals:
        return []

    return [
        p["cy_name"]
        for p in proposals
        if p.get("designation") == "existing" and p.get("cy_name")
    ]


def gather_cy_names_from_built(
    tasks_built: list[dict[str, Any]] | None,
) -> list[str]:
    """Extract cy_names from successfully built tasks.

    Args:
        tasks_built: List of task building results

    Returns:
        List of cy_names from successful builds
    """
    if not tasks_built:
        return []

    return [t["cy_name"] for t in tasks_built if t.get("success") and t.get("cy_name")]


def gather_all_cy_names(
    proposals: list[dict[str, Any]] | None,
    tasks_built: list[dict[str, Any]] | None,
) -> list[str]:
    """Gather all cy_names from existing proposals and built tasks.

    Args:
        proposals: List of task proposals
        tasks_built: List of task building results

    Returns:
        Combined list of cy_names maintaining proposal order
    """
    # Existing tasks first (they were pre-existing)
    existing = gather_cy_names_from_existing(proposals)

    # Then newly built tasks
    built = gather_cy_names_from_built(tasks_built)

    return existing + built


def parse_workflow_result(output_json: str | None) -> dict[str, Any]:
    """Parse agent output JSON into workflow result.

    Args:
        output_json: JSON string from agent's workflow-result.json

    Returns:
        Parsed workflow result dictionary
    """
    if not output_json:
        return {"error": "Empty output"}

    try:
        return json.loads(output_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e!s}"}
