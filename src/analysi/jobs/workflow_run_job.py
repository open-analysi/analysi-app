"""ARQ job for workflow execution.

Replaces the ``asyncio.create_task()`` fire-and-forget pattern in
``services/workflow_execution.py`` with a durable ARQ job.  Eliminates the
1-second ``asyncio.sleep`` hack — ARQ naturally dequeues after the API
transaction commits.

The job calls ``WorkflowExecutor._execute_workflow_synchronously()`` which
opens its own DB session and handles idempotency guards internally.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.constants import RunStatus
from analysi.models.workflow_execution import WorkflowRun

logger = get_logger(__name__)


@tracked_job(
    job_type="execute_workflow_run",
    timeout_seconds=3600,
    model_class=WorkflowRun,
    extract_row_id=lambda ctx, workflow_run_id, tenant_id: workflow_run_id,
    # No retry: monitor_execution() would immediately re-detect the failed node
    # and fail again.  Proper workflow resume (reset failed nodes to PENDING)
    # is planned as a Leros + HITL follow-up.
)
async def execute_workflow_run(
    ctx: dict[str, Any],
    workflow_run_id: str,
    tenant_id: str,
) -> dict[str, str]:
    """Execute a workflow run via the existing WorkflowExecutor.

    Args:
        ctx: ARQ context (contains redis pool, worker_id).
        workflow_run_id: UUID string of the WorkflowRun to execute.
        tenant_id: Tenant identifier for context propagation.

    Returns:
        Status dict for ARQ result tracking.
    """
    from analysi.services.workflow_execution import WorkflowExecutor

    # @tracked_job already emits a structured job_started log

    await WorkflowExecutor._execute_workflow_synchronously(UUID(workflow_run_id))

    return {"status": RunStatus.COMPLETED, "workflow_run_id": workflow_run_id}
