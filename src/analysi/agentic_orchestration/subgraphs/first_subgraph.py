"""First subgraph: Runbook Generation → Task Proposal (No LangGraph).

This subgraph implements the first two stages of the Kea workflow generation:
- Runbook Generation: Generate runbook from alert
- Task Proposals: Propose tasks from runbook

Uses plain asyncio like second_subgraph_no_langgraph.py for consistency.

- Optional skills_syncer for DB-backed skills (tenant isolation)
- Syncs skills to workspace before execution
- Detects new files created by agent after execution
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from typing_extensions import TypedDict

from analysi.agentic_orchestration.content_policy import ContentPolicy
from analysi.agentic_orchestration.nodes import (
    runbook_generation_node,
    task_proposal_node,
)
from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.workspace import AgentWorkspace
from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer

logger = get_logger(__name__)


class WorkflowGenerationState(TypedDict):
    """State for workflow generation subgraph."""

    alert: dict[str, Any]  # alert
    workspace: Any  # AgentWorkspace object (shared across nodes)
    run_id: str  # Unique run ID (UUID) for workspace isolation
    tenant_id: str  # Tenant ID for multi-tenant isolation
    created_by: str  # User/system that triggered workflow generation
    runbook: str | None
    matching_report: str | None  # JSON from runbook matching
    task_proposals: list[dict[str, Any]] | None
    metrics: list[StageExecutionMetrics]
    error: str | None


async def _detect_and_submit_new_files(
    workspace: AgentWorkspace,
    tenant_id: str,
    session: AsyncSession,
    alert_title: str,
    run_id: str,
) -> None:
    """Detect new files created by agent and submit to Hydra.

    Steps 4-5 of the SDK flow:
    4. Identify newly created resources
    5. Pass new resources through Hydra

    Args:
        workspace: AgentWorkspace with skills_syncer
        tenant_id: Tenant identifier
        session: Database session for Hydra submission
        alert_title: Alert title for source metadata
        run_id: Run ID for source metadata
    """
    from analysi.agentic_orchestration.skills_sync import submit_new_files_to_hydra

    # Step 4: Detect new files
    new_files = workspace.detect_new_files()

    if not new_files:
        logger.info("[FIRST_SUBGRAPH] No new files created by agent")
        return

    logger.info(
        "new_files_detected", count=len(new_files), files=[f.name for f in new_files]
    )

    # Step 5a: Filter through content policy
    policy = ContentPolicy()
    approved, rejected = policy.filter_new_files(new_files)

    if rejected:
        logger.warning(
            "content_policy_blocked_files",
            count=len(rejected),
            reasons=[r["reason"] for r in rejected],
        )

    if not approved:
        logger.info("[FIRST_SUBGRAPH] No files approved for Hydra submission")
        return

    logger.info(
        "files_approved_for_hydra",
        count=len(approved),
        files=[f.name for f in approved],
    )

    # Step 5b: Submit to Hydra extraction pipeline
    try:
        results = await submit_new_files_to_hydra(
            session=session,
            tenant_id=tenant_id,
            skill_name="runbooks-manager",
            approved_files=approved,
            source_metadata={
                "source": "kea_sdk_agent",
                "run_id": run_id,
                "alert_title": alert_title,
            },
        )

        # Log results — status is "pending" (async review), not "applied"
        submitted = [r for r in results if r.get("status") in ("pending", "approved")]
        failed = [r for r in results if r.get("status") in ("rejected", "failed")]

        if submitted:
            logger.info(
                "firstsubgraph_hydra_submitted_files",
                count=len(submitted),
                submitted=submitted,
            )
        if failed:
            logger.warning(
                "firstsubgraph_hydra_rejectedfailed_files",
                failed_count=len(failed),
                failed=failed,
            )

    except Exception as e:
        # Don't fail the workflow if Hydra submission fails
        # The runbook was still generated successfully
        logger.exception("firstsubgraph_hydra_submission_failed", error=str(e))


async def run_first_subgraph(
    alert: dict[str, Any],
    executor: AgentOrchestrationExecutor,
    run_id: str,
    callback: ProgressCallback | None = None,
    tenant_id: str = "default",
    created_by: str = str(SYSTEM_USER_ID),
    skills_syncer: TenantSkillsSyncer | None = None,
    session: AsyncSession | None = None,
) -> WorkflowGenerationState:
    """Run the first subgraph on an alert.

    Executes Runbook Generation and Task Proposals sequentially.
    After agent execution, detects new files and submits approved ones to Hydra.

    Args:
        alert: alert to process
        executor: AgentOrchestrationExecutor for Claude SDK calls
        run_id: Run ID for workspace isolation (typically generation_id from database).
                Workspace paths will contain this ID for troubleshooting and correlation.
        callback: Optional progress callback
        tenant_id: Tenant ID for multi-tenant isolation (default: "default")
        created_by: UUID string of user/system that triggered workflow generation
        skills_syncer: Optional TenantSkillsSyncer for DB-backed skills.
                      When provided, skills are synced to workspace/.claude/skills/
                      before agent execution (enables tenant-isolated skills).
        session: Optional database session for Hydra submission.
                When provided with skills_syncer, new files created by the agent
                are detected, filtered by ContentPolicy, and submitted to Hydra.

    Returns:
        Final workflow generation state with runbook and task_proposals
    """
    # Create workspace ONCE for entire subgraph
    workspace = AgentWorkspace(
        run_id=run_id,
        tenant_id=tenant_id,
        skills_syncer=skills_syncer,
    )

    # Notify callback of workspace creation for early tracking
    if callback:
        await callback.on_workspace_created(workspace_path=str(workspace.work_dir))

    # Sync ALL tenant skills to workspace (DB-backed skills for tenant isolation)
    if skills_syncer:
        try:
            sync_result = await workspace.setup_skills()  # Syncs all tenant skills
            logger.info(
                "skills_synced", count=len(sync_result), skills=list(sync_result.keys())
            )

            # Update executor to use synced skills from workspace
            executor.skills_project_dir = workspace.work_dir
        except Exception as e:
            logger.warning("firstsubgraph_skills_sync_failed", error=str(e))

    # Initialize state
    state: WorkflowGenerationState = {
        "alert": alert,
        "workspace": workspace,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "created_by": created_by,
        "runbook": None,
        "matching_report": None,
        "task_proposals": None,
        "metrics": [],
        "error": None,
    }

    try:
        logger.info(
            "first_subgraph_starting_execution",
            alert_id=alert.get("id"),
            run_id=run_id,
        )

        # Runbook Generation
        logger.info("[FIRST_SUBGRAPH] Runbook Generation")
        runbook_result = await runbook_generation_node(dict(state), executor, callback)

        # Update state with runbook result
        state["runbook"] = runbook_result.get("runbook")
        state["matching_report"] = runbook_result.get("matching_report")
        state["metrics"] = runbook_result.get("metrics", [])

        if runbook_result.get("error"):
            state["error"] = runbook_result["error"]
            logger.error(
                "firstsubgraph_runbook_generation_failed", error=state["error"]
            )
            return state

        logger.info(
            "first_subgraph_runbook_generated",
            runbook_length=len(state["runbook"] or ""),
        )

        # Step 4-5: Detect new files and submit to Hydra
        # Only if skills_syncer and session are provided (enables writeback)
        if skills_syncer and session:
            await _detect_and_submit_new_files(
                workspace=workspace,
                tenant_id=tenant_id,
                session=session,
                alert_title=alert.get("title", "unknown"),
                run_id=run_id,
            )

        # Task Proposals
        logger.info("[FIRST_SUBGRAPH] Task Proposals")
        proposal_result = await task_proposal_node(dict(state), executor, callback)

        # Update state with proposal result
        state["task_proposals"] = proposal_result.get("task_proposals")
        state["metrics"] = proposal_result.get("metrics", state["metrics"])

        if proposal_result.get("error"):
            state["error"] = proposal_result["error"]
            logger.error("firstsubgraph_task_proposal_failed", error=state["error"])
            return state

        # Log completion
        task_proposals = state.get("task_proposals", []) or []
        logger.info(
            "first_subgraph_execution_completed",
            runbook_length=len(state.get("runbook", "") or ""),
            task_proposals=len(task_proposals),
            error=state.get("error"),
        )

        return state

    finally:
        # Cleanup workspace ONCE after all nodes complete
        workspace.cleanup()
