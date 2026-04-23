"""ARQ job for task execution.

Durable ARQ job for task execution.  If the pod restarts,
the job is retried automatically instead of being silently lost.

The job wraps ``TaskExecutionService.execute_and_persist()`` which manages
its own DB sessions internally.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.constants import RunStatus
from analysi.models.task_run import TaskRun

logger = get_logger(__name__)


@tracked_job(
    job_type="execute_task_run",
    timeout_seconds=3600,
    model_class=TaskRun,
    extract_row_id=lambda ctx, task_run_id, tenant_id: task_run_id,
    max_retries=2,
)
async def execute_task_run(
    ctx: dict[str, Any],
    task_run_id: str,
    tenant_id: str,
) -> dict[str, str]:
    """Execute a task run via the existing TaskExecutionService.

    Args:
        ctx: ARQ context (contains redis pool, worker_id).
        task_run_id: UUID string of the TaskRun to execute.
        tenant_id: Tenant identifier for context propagation.

    Returns:
        Status dict for ARQ result tracking.
    """
    from analysi.services.task_execution import TaskExecutionService

    # @tracked_job already emits a structured job_started log

    service = TaskExecutionService()
    await service.execute_and_persist(UUID(task_run_id), tenant_id)

    return {"status": RunStatus.COMPLETED, "task_run_id": task_run_id}
