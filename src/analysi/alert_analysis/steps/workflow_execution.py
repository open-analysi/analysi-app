"""Step 4: Workflow Execution implementation.

Executes workflows synchronously in the worker process via direct DB calls.
No REST API round-trip — the worker creates the WorkflowRun record and
drives monitor_execution() directly.  Progress is committed to DB at every
node transition, so the UI sees real-time updates via its read endpoints.
"""

from typing import Any
from uuid import UUID

from analysi.config.logging import get_logger

logger = get_logger(__name__)


class WorkflowExecutionStep:
    """
    Workflow execution step that runs the selected workflow directly
    in the worker process using DB calls (no REST API).

    Progress is visible to the UI because monitor_execution() commits
    to DB at every state transition (node created, running, completed, etc.).
    """

    async def execute(
        self,
        tenant_id: str,
        alert_id: str,
        analysis_id: str,
        workflow_id: str,  # Workflow UUID received from WorkflowBuilderStep
        alert_data: dict | None = None,
        **kwargs,
    ) -> str:
        """
        Execute the selected workflow synchronously in the worker.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID to analyze
            analysis_id: Analysis UUID for tracking
            workflow_id: Workflow UUID to execute (received from WorkflowBuilderStep)
            alert_data: Pre-fetched alert data from pipeline. If provided, avoids
                opening a redundant DB session in _prepare_workflow_input.

        Returns:
            str: Workflow run ID

        Raises:
            WorkflowNotFoundError: If workflow_id references a deleted/stale workflow
                (FK violation). Enables pipeline stale-cache retry.
            WorkflowPausedForHumanInput: If workflow pauses for HITL
                (Project Kalymnos). Pipeline catches and sets PAUSED_HUMAN_REVIEW.
            RuntimeError: If workflow execution ends in FAILED status.
        """
        logger.info(
            "executing_workflow_for_alert", workflow_id=workflow_id, alert_id=alert_id
        )

        # Use pre-fetched alert data from pipeline when available
        if alert_data is not None:
            input_data = alert_data
        else:
            input_data = await self._prepare_workflow_input(tenant_id, alert_id)

        # Import here to avoid circular imports at module level
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        from analysi.common.retry_config import WorkflowNotFoundError
        from analysi.db.session import AsyncSessionLocal
        from analysi.services.workflow_execution import WorkflowExecutor

        # Step 1: Create the WorkflowRun record
        # Catch FK violations on workflow_id and translate to WorkflowNotFoundError
        # so the pipeline's stale-cache retry logic (_execute_workflow_with_retry)
        # can invalidate the cache and request a fresh workflow.
        wf_uuid = UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
        try:
            async with AsyncSessionLocal() as session:
                executor = WorkflowExecutor(session)
                workflow_run_id = await executor.create_workflow_run(
                    tenant_id,
                    wf_uuid,
                    input_data,
                    execution_context={"analysis_id": analysis_id},
                )
                await session.commit()
        except IntegrityError as e:
            # FK violation on workflow_id → stale cached workflow was deleted
            err_msg = str(e.orig) if e.orig else str(e)
            if "workflow" in err_msg.lower() and "foreign key" in err_msg.lower():
                logger.warning(
                    "workflow_fk_violation_stale_cache",
                    workflow_id=workflow_id,
                    error=err_msg,
                )
                raise WorkflowNotFoundError(workflow_id) from e
            raise

        # Step 2: Execute synchronously — monitor_execution commits progress
        # to DB at every node transition, so the UI sees real-time updates.
        await WorkflowExecutor._execute_workflow_synchronously(workflow_run_id)

        # Step 3: Check terminal status — monitor_execution marks failed/paused
        # runs in the DB but returns normally (no exception). We must detect this
        # so the pipeline treats step 3 as failed/paused instead of silently
        # continuing to disposition matching with a non-completed workflow run.
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT status, error_message FROM workflow_runs WHERE id = :id"),
                {"id": str(workflow_run_id)},
            )
            row = result.fetchone()
            if row and row.status == "paused":
                # HITL — Project Kalymnos: workflow paused for human input.
                # Raise so pipeline can set PAUSED_HUMAN_REVIEW and free the worker.
                logger.info(
                    "workflow_paused_for_human_input",
                    workflow_run_id=str(workflow_run_id),
                )
                raise WorkflowPausedForHumanInput(str(workflow_run_id))
            if row and row.status == "failed":
                logger.error(
                    "workflow_execution_failed",
                    workflow_run_id=str(workflow_run_id),
                    error_message=row.error_message,
                )
                raise RuntimeError(f"Workflow execution failed: {row.error_message}")

        logger.info(
            "workflow_execution_completed_runid", workflow_run_id=workflow_run_id
        )
        return str(workflow_run_id)

    async def _prepare_workflow_input(
        self, tenant_id: str, alert_id: str
    ) -> dict[str, Any]:
        """
        Prepare input data for workflow execution.

        Fetches alert data from the database to pass to the workflow.
        """
        from sqlalchemy import select

        from analysi.db import AsyncSessionLocal
        from analysi.models.alert import Alert

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Alert).where(Alert.tenant_id == tenant_id, Alert.id == alert_id)
            )
            alert = result.scalar_one_or_none()

            if not alert:
                raise ValueError(f"Alert not found: {alert_id}")

            # Serialize all alert columns to dict for workflow input
            # This ensures workflows have access to any field they may need
            from sqlalchemy import inspect

            mapper = inspect(Alert)
            result = {}

            for column in mapper.columns:
                key = column.key
                value = getattr(alert, key)

                # Skip internal/relationship fields
                if key in ("current_analysis_id", "analyses"):
                    continue

                # Handle datetime serialization
                if hasattr(value, "isoformat"):
                    result[key] = value.isoformat()
                # Handle UUID serialization
                elif hasattr(value, "hex"):
                    result[key] = str(value)
                else:
                    result[key] = value

            return result
