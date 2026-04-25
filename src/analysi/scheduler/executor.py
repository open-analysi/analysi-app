"""Generic schedule executor.

ARQ cron function that polls the ``schedules`` table using direct DB access
(FOR UPDATE SKIP LOCKED), creates JobRun + TaskRun/WorkflowRun in a single
transaction, enqueues execution to the Alert Analysis worker, and advances
``next_run_at``.

Each schedule is processed in its **own session/transaction** so that the
FOR UPDATE lock is held only for that single row.  This prevents the
mid-loop commit from releasing locks on unprocessed schedules (which would
allow a concurrent worker to double-fire them).

Runs on the Integrations worker (DB 5). Task/Workflow execution happens
on the Alert Analysis worker (DB 0) with a 3600s timeout.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from analysi.common.arq_enqueue import enqueue_arq_job
from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.repositories.job_run_repository import JobRunRepository
from analysi.repositories.schedule_repository import ScheduleRepository
from analysi.scheduler.interval import compute_next_run_at
from analysi.services.task_run import TaskRunService
from analysi.services.workflow_execution import WorkflowExecutionService

logger = get_logger(__name__)

# Safety limit: max schedules to process per cron invocation.
MAX_SCHEDULES_PER_CYCLE = 100


async def execute_due_schedules(ctx: dict[str, Any]) -> dict[str, Any]:
    """Main scheduler cron: process all due schedules.

    Fetches one due schedule at a time, each in its own transaction,
    so FOR UPDATE SKIP LOCKED holds only the row currently being
    processed.  Failed schedules are tracked and excluded from
    subsequent queries within the same cycle.

    Args:
        ctx: ARQ context with Redis connection.

    Returns:
        Summary dict with processed/skipped/error counts.
    """
    processed = 0
    errors = 0
    failed_ids: set[UUID] = set()

    for _ in range(MAX_SCHEDULES_PER_CYCLE):
        try:
            result = await _fetch_and_process_one(failed_ids)
        except _NoDueSchedules:
            break
        except Exception as exc:
            # Session-level failure (DB connectivity, etc.)
            if isinstance(exc, OSError) or "connection" in str(exc).lower():
                logger.warning(
                    "schedule_executor_db_unavailable",
                    error=str(exc),
                )
            else:
                logger.error(
                    "schedule_executor_failed",
                    error=str(exc),
                    exc_info=True,
                )
            break

        if result["status"] == "processed":
            processed += 1
        else:
            errors += 1
            failed_ids.add(result["schedule_id"])

    total_due = processed + errors
    if total_due > 0:
        logger.info(
            "schedule_executor_completed",
            processed=processed,
            errors=errors,
        )
    else:
        logger.debug("schedule_executor_no_due_schedules")

    return {
        "processed": processed,
        "errors": errors,
        "total_due": total_due,
    }


class _NoDueSchedules(Exception):
    """Sentinel: no more due schedules to process."""


async def _fetch_and_process_one(
    failed_ids: set[UUID],
) -> dict[str, Any]:
    """Fetch exactly one due schedule, process it, and commit — all in one transaction.

    Raises:
        _NoDueSchedules: When get_due_schedules returns empty.

    Returns:
        Dict with ``status`` ("processed" | "error") and ``schedule_id``.
    """
    async with AsyncSessionLocal() as session:
        sched_repo = ScheduleRepository(session)
        due = await sched_repo.get_due_schedules(
            limit=1,
            exclude_ids=failed_ids or None,
        )

        if not due:
            raise _NoDueSchedules

        schedule = due[0]

        try:
            result = await _process_single_schedule(session, schedule)
            return result
        except Exception as exc:
            logger.error(
                "schedule_processing_failed",
                schedule_id=str(schedule.id),
                tenant_id=schedule.tenant_id,
                error=str(exc),
            )
            # Session discards uncommitted changes on context-exit.
            # Explicit rollback so the connection returns clean to the pool.
            await session.rollback()
            return {
                "status": "error",
                "schedule_id": schedule.id,
            }


async def _process_single_schedule(session, schedule) -> dict[str, Any]:
    """Process a single due schedule within a transaction.

    Creates JobRun + target run, updates next_run_at, commits,
    then enqueues the execution job.

    Args:
        session: Active database session.
        schedule: Schedule model instance (locked via FOR UPDATE SKIP LOCKED).

    Returns:
        Dict with status and created IDs.
    """
    now = datetime.now(UTC)

    # Compute next_run_at — if unparseable, skip this schedule
    new_next_run_at = compute_next_run_at(
        schedule.schedule_type, schedule.schedule_value, from_time=now
    )
    if new_next_run_at is None:
        raise ValueError(
            f"Cannot parse interval '{schedule.schedule_value}' "
            f"for schedule {schedule.id}"
        )

    # Create JobRun
    jr_repo = JobRunRepository(session)
    job_run = await jr_repo.create(
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.id,
        target_type=schedule.target_type,
        target_id=schedule.target_id,
        integration_id=schedule.integration_id,
        status="pending",
    )

    # Create the target run based on target_type
    enqueue_function: str
    enqueue_args: tuple[Any, ...]

    if schedule.target_type == "task":
        task_run_service = TaskRunService()
        task_run = await task_run_service.create_execution(
            session=session,
            tenant_id=schedule.tenant_id,
            task_id=schedule.target_id,
            cy_script=None,  # Loaded from the task
            input_data=schedule.params,
            execution_context={
                "run_context": "scheduled",
                "schedule_id": str(schedule.id),
                "job_run_id": str(job_run.id),
                # Propagate integration_id so Cy functions like ingest_alerts()
                # are available during execution (gated on this field).
                **(
                    {"integration_id": schedule.integration_id}
                    if schedule.integration_id
                    else {}
                ),
            },
        )
        # Set run_context on the TaskRun directly
        task_run.run_context = "scheduled"
        await session.flush()

        # Update JobRun with task_run reference
        job_run.task_run_id = task_run.id
        await session.flush()

        enqueue_function = "analysi.jobs.task_run_job.execute_task_run"
        enqueue_args = (str(task_run.id), schedule.tenant_id)

    elif schedule.target_type == "workflow":
        wf_service = WorkflowExecutionService()
        wf_result = await wf_service.start_workflow(
            session=session,
            tenant_id=schedule.tenant_id,
            workflow_id=schedule.target_id,
            input_data=schedule.params,
            execution_context={
                "run_context": "scheduled",
                "schedule_id": str(schedule.id),
                "job_run_id": str(job_run.id),
            },
        )
        workflow_run_id = wf_result["workflow_run_id"]
        job_run.workflow_run_id = workflow_run_id
        await session.flush()

        enqueue_function = "analysi.jobs.workflow_run_job.execute_workflow_run"
        enqueue_args = (str(workflow_run_id), schedule.tenant_id)

    else:
        raise ValueError(f"Unknown target_type: {schedule.target_type}")

    # Update schedule timing
    sched_repo = ScheduleRepository(session)
    await sched_repo.update_next_run_at(schedule.id, new_next_run_at, last_run_at=now)

    # Commit the transaction (JobRun + TaskRun/WorkflowRun + schedule update)
    await session.commit()

    # Enqueue execution to Alert Analysis worker (AFTER commit).
    # If enqueue fails, revert next_run_at so the schedule retries next cycle.
    try:
        await enqueue_arq_job(enqueue_function, *enqueue_args)
    except Exception:
        logger.error(
            "schedule_enqueue_failed",
            schedule_id=str(schedule.id),
            target_type=schedule.target_type,
            exc_info=True,
        )
        # Revert schedule so it fires again on the next poll cycle
        await sched_repo.update_next_run_at(schedule.id, now, last_run_at=now)
        await session.commit()
        raise

    logger.info(
        "schedule_fired",
        schedule_id=str(schedule.id),
        target_type=schedule.target_type,
        target_id=str(schedule.target_id),
        job_run_id=str(job_run.id),
        next_run_at=str(new_next_run_at),
    )

    return {
        "status": "processed",
        "schedule_id": schedule.id,
        "job_run_id": str(job_run.id),
    }
