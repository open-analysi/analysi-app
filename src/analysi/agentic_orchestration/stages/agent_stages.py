"""Agent-based stages for workflow generation.

These stages wrap the existing node functions and subgraph logic.

SDK Skills Integration (Hydra Phases 6-8):
When skills_syncer and session are provided, the AgentRunbookStage implements
the 6-step flow for tenant-isolated, DB-backed skills:
1. Create workspace
2. Sync skills from DB to workspace filesystem
3. Run agent with isolated skills
4. Detect new files created by agent
5. Submit approved files to Hydra pipeline
6. Cleanup
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from analysi.agentic_orchestration.content_policy import ContentPolicy
from analysi.agentic_orchestration.nodes import runbook_generation_node
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.skills_sync import submit_new_files_to_hydra
from analysi.agentic_orchestration.stages.base import SDK_METRICS_KEY
from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer
    from analysi.agentic_orchestration.task_generation_client import (
        TaskGenerationApiClient,
    )

logger = get_logger(__name__)


class AgentRunbookStage:
    """Production stage 1: Agent-based runbook generation.

    Supports optional skills_syncer for tenant-isolated DB-backed skills:
    - When provided, skills are synced to workspace before agent execution
    - After execution, new files are detected and submitted to Hydra
    """

    stage = WorkflowGenerationStage.RUNBOOK_GENERATION

    def __init__(
        self,
        executor: AgentOrchestrationExecutor,
        skills_syncer: TenantSkillsSyncer | None = None,
        session: AsyncSession | None = None,
    ):
        self.executor = executor
        self.skills_syncer = skills_syncer
        self.session = session

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute runbook generation using the runbook-match-agent.

        When skills_syncer is provided, implements the 6-step SDK flow:
        1. Create workspace
        2. Sync skills from DB to workspace
        3. Run agent with isolated skills
        4. Detect new files
        5. Submit approved files to Hydra
        6. Cleanup
        """
        run_id = state["run_id"]
        tenant_id = state["tenant_id"]

        # Create workspace for this stage (pass skills_syncer for tenant isolation)
        workspace = AgentWorkspace(
            run_id=f"{run_id}-runbook",
            tenant_id=tenant_id,
            skills_syncer=self.skills_syncer,
        )

        try:
            # Step 2: Sync ALL tenant skills to workspace (if syncer provided)
            if self.skills_syncer:
                await workspace.setup_skills()  # Syncs all tenant skills
                self.executor.skills_project_dir = workspace.work_dir

            # Build state for node (expects workspace object)
            node_state = {
                "alert": state["alert"],
                "workspace": workspace,
                "run_id": run_id,
                "tenant_id": tenant_id,
            }

            # Step 3: Execute node (pass None for callback - framework handles callbacks)
            result = await runbook_generation_node(node_state, self.executor, None)

            # Step 4: Detect new files created by agent
            if self.skills_syncer and self.session:
                await self._detect_and_submit_new_files(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    alert_title=state.get("alert", {}).get("title", ""),
                    run_id=run_id,
                )

            # Extract SDK metrics if present
            state_update = {
                "runbook": result.get("runbook"),
                "matching_report": result.get("matching_report"),
            }

            # Extract metrics for framework
            metrics = result.get("metrics", [])
            if metrics:
                # Node returns list of metrics, take the first one
                state_update[SDK_METRICS_KEY] = (
                    metrics[0] if isinstance(metrics, list) and metrics else metrics
                )

            # Propagate errors
            if result.get("error"):
                state_update["error"] = result["error"]

            return state_update

        finally:
            # Step 6: Cleanup
            workspace.cleanup()

    async def _detect_and_submit_new_files(
        self,
        workspace: AgentWorkspace,
        tenant_id: str,
        alert_title: str,
        run_id: str,
    ) -> None:
        """Detect new files created by agent and submit to Hydra.

        Steps 4-5 of the SDK flow:
        - Detect new/modified files via manifest diff
        - Filter through ContentPolicy
        - Submit approved files to Hydra pipeline
        """
        # Detect new files (uses baseline manifest from sync_skills)
        new_files = workspace.detect_new_files()
        if not new_files:
            logger.debug("[AgentRunbookStage] No new files detected in workspace")
            return

        logger.info(
            "agentrunbookstage_detected_new_files", new_files_count=len(new_files)
        )

        # Apply content policy
        policy = ContentPolicy()
        approved, rejected = policy.filter_new_files(new_files)

        if rejected:
            logger.warning(
                "agent_runbook_stage_blocked_files",
                blocked_count=len(rejected),
                rejected=rejected,
            )

        if approved:
            # Submit to Hydra pipeline
            assert (
                self.session is not None
            )  # Checked by caller (self.session guard above)
            results = await submit_new_files_to_hydra(
                session=self.session,
                tenant_id=tenant_id,
                skill_name="runbooks-manager",
                approved_files=approved,
                source_metadata={
                    "source": "kea_sdk_agent",
                    "run_id": run_id,
                    "alert_title": alert_title,
                    "stage": "runbook_generation",
                },
            )
            logger.info(
                "agent_runbook_stage_submitted_to_hydra",
                approved_count=len(approved),
                results=results,
            )


class AgentTaskProposalStage:
    """Production stage 2: Agent-based task proposals."""

    stage = WorkflowGenerationStage.TASK_PROPOSALS

    def __init__(self, executor: AgentOrchestrationExecutor):
        self.executor = executor

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute task proposal using the runbook-to-task-proposals agent."""
        from analysi.agentic_orchestration.nodes import task_proposal_node

        # Early exit if previous stage failed
        if state.get("error"):
            return {"task_proposals": None}

        run_id = state["run_id"]
        tenant_id = state["tenant_id"]

        # Create workspace for this stage
        workspace = AgentWorkspace(
            run_id=f"{run_id}-proposals",
            tenant_id=tenant_id,
        )

        try:
            # Build state for node
            node_state = {
                "alert": state["alert"],
                "runbook": state["runbook"],
                "workspace": workspace,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "metrics": [],  # Node expects this for accumulation
            }

            # Execute node (pass None for callback - framework handles callbacks)
            result = await task_proposal_node(node_state, self.executor, None)

            state_update = {
                "task_proposals": result.get("task_proposals"),
            }

            # Extract metrics for framework
            metrics = result.get("metrics", [])
            if metrics:
                # Node accumulates metrics, take the last one (this stage's)
                state_update[SDK_METRICS_KEY] = (
                    metrics[-1] if isinstance(metrics, list) and metrics else metrics
                )

            if result.get("error"):
                state_update["error"] = result["error"]

            return state_update

        finally:
            workspace.cleanup()


class AgentTaskBuildingStage:
    """Production stage 3: Agent-based parallel task building."""

    stage = WorkflowGenerationStage.TASK_BUILDING

    def __init__(
        self,
        executor: AgentOrchestrationExecutor,
        max_tasks_to_build: int | None = None,
        task_generation_client: TaskGenerationApiClient | None = None,
    ):
        self.executor = executor
        self.max_tasks_to_build = max_tasks_to_build
        self.task_generation_client = task_generation_client

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute parallel task building."""
        from analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph import (
            run_parallel_task_building,
        )

        # Early exit if previous stage failed
        if state.get("error"):
            return {"tasks_built": []}

        task_proposals = state.get("task_proposals", [])
        if not task_proposals:
            return {"tasks_built": []}

        run_id = state["run_id"]
        tenant_id = state["tenant_id"]
        created_by = state.get("created_by", str(SYSTEM_USER_ID))

        # Handle both dict and AlertBase objects for alert
        alert = state.get("alert", {})
        if hasattr(alert, "model_dump"):
            alert = alert.model_dump(mode="json")

        # Run parallel task building (creates its own workspaces per task)
        # Pass None for callback - framework handles stage-level callbacks
        tasks_built, metrics = await run_parallel_task_building(
            task_proposals=task_proposals,
            alert=alert,
            runbook=state.get("runbook", ""),
            run_id=run_id,
            tenant_id=tenant_id,
            created_by=created_by,
            executor=self.executor,
            callback=None,  # Framework handles callbacks
            max_tasks_to_build=self.max_tasks_to_build,
            task_generation_client=self.task_generation_client,
        )

        state_update: dict[str, Any] = {
            "tasks_built": tasks_built,
        }

        # Aggregate metrics into a summary metric
        if metrics:
            state_update[SDK_METRICS_KEY] = _aggregate_metrics(metrics)

        return state_update


class AgentWorkflowAssemblyStage:
    """Production stage 4: Agent-based workflow assembly."""

    stage = WorkflowGenerationStage.WORKFLOW_ASSEMBLY

    def __init__(self, executor: AgentOrchestrationExecutor):
        self.executor = executor

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute workflow assembly using the workflow-builder agent."""
        from analysi.agentic_orchestration.nodes import workflow_assembly_node

        # Early exit if previous stage failed
        if state.get("error"):
            return {
                "workflow_id": None,
                "workflow_composition": [],
                "workflow_error": state.get("error"),
            }

        run_id = state["run_id"]
        tenant_id = state["tenant_id"]

        # Create workspace for this stage
        workspace = AgentWorkspace(
            run_id=f"{run_id}-assembly",
            tenant_id=tenant_id,
        )

        try:
            # Handle both dict and AlertBase objects for alert
            alert = state.get("alert", {})
            if hasattr(alert, "model_dump"):
                alert = alert.model_dump(mode="json")

            # Build state for node
            node_state = {
                "alert": alert,
                "runbook": state.get("runbook", ""),
                "task_proposals": state.get("task_proposals", []),
                "tasks_built": state.get("tasks_built", []),
                "workspace": workspace,
                "run_id": run_id,
                "tenant_id": tenant_id,
            }

            # Execute node (pass None for callback - framework handles callbacks)
            result = await workflow_assembly_node(node_state, self.executor, None)

            state_update = {
                "workflow_id": result.get("workflow_id"),
                "workflow_composition": result.get("workflow_composition", []),
                "workflow_error": result.get("workflow_error"),
            }

            # Extract metrics for framework
            metrics = result.get("metrics", [])
            if metrics:
                state_update[SDK_METRICS_KEY] = (
                    metrics[0] if isinstance(metrics, list) and metrics else metrics
                )

            return state_update

        finally:
            workspace.cleanup()


def _aggregate_metrics(
    metrics_list: list[StageExecutionMetrics],
) -> StageExecutionMetrics:
    """Aggregate multiple metrics into a single summary metric."""
    if not metrics_list:
        return StageExecutionMetrics(
            duration_ms=0,
            duration_api_ms=0,
            num_turns=0,
            total_cost_usd=0.0,
            usage={},
            tool_calls=[],
        )

    total_duration_ms = sum(m.duration_ms for m in metrics_list)
    total_duration_api_ms = sum(m.duration_api_ms for m in metrics_list)
    total_num_turns = sum(m.num_turns for m in metrics_list)
    total_cost_usd = sum(m.total_cost_usd for m in metrics_list)

    # Aggregate token usage
    total_input_tokens = sum(m.usage.get("total_input_tokens", 0) for m in metrics_list)
    total_output_tokens = sum(
        m.usage.get("total_output_tokens", 0) for m in metrics_list
    )

    # Combine all tool calls
    all_tool_calls = []
    for m in metrics_list:
        all_tool_calls.extend(m.tool_calls)

    return StageExecutionMetrics(
        duration_ms=total_duration_ms,
        duration_api_ms=total_duration_api_ms,
        num_turns=total_num_turns,
        total_cost_usd=total_cost_usd,
        usage={
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
        },
        tool_calls=all_tool_calls,
    )
