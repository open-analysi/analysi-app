"""JobRun status mirroring callbacks.

Updates JobRun status to mirror the final status of the associated
TaskRun or WorkflowRun. Called from execution post-hooks.
"""

from datetime import datetime
from uuid import UUID

from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.repositories.job_run_repository import JobRunRepository

logger = get_logger(__name__)


async def update_job_run_status(
    tenant_id: str,
    job_run_id: UUID,
    job_run_created_at: datetime,
    status: str,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> bool:
    """Update a JobRun's status to mirror its target run.

    Uses a dedicated session (fire-and-forget) so failures here
    don't affect the caller's session state.

    Args:
        tenant_id: Tenant identifier.
        job_run_id: JobRun ID to update.
        job_run_created_at: JobRun created_at (for partition pruning).
        status: New status (running, completed, failed).
        started_at: When execution started.
        completed_at: When execution completed.

    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        async with AsyncSessionLocal() as session:
            repo = JobRunRepository(session)
            result = repo.update_status(
                tenant_id=tenant_id,
                job_run_id=job_run_id,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                created_at=job_run_created_at,
            )
            # update_status is async
            updated = await result
            await session.commit()

            if updated is None:
                logger.warning(
                    "job_run_status_update_not_found",
                    job_run_id=str(job_run_id),
                    status=status,
                )
                return False

            logger.debug(
                "job_run_status_updated",
                job_run_id=str(job_run_id),
                status=status,
            )
            return True

    except Exception as exc:
        logger.error(
            "job_run_status_update_failed",
            job_run_id=str(job_run_id),
            error=str(exc),
        )
        return False
