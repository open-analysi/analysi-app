"""
Managed Resources Service.

Resolves resource_key (e.g. "alert_ingestion", "health_check") to the
Task + Schedule pair auto-created by the task factory for an integration.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.constants import ManagedResourceKey, TaskConstants
from analysi.models.component import Component
from analysi.models.schedule import Schedule
from analysi.models.task import Task
from analysi.models.task_run import TaskRun

logger = get_logger(__name__)

# Well-known resource keys (health_check has a post-execution hook).
# Custom action tasks can use any string as managed_resource_key.
WELL_KNOWN_RESOURCE_KEYS: frozenset[str] = frozenset(ManagedResourceKey)


@dataclass
class ManagedResource:
    """A Task + Schedule pair auto-created for an integration."""

    resource_key: str
    task_id: UUID
    task_name: str
    schedule_id: UUID | None
    schedule: dict[str, Any] | None  # {type, value, enabled}
    last_run: dict[str, Any] | None  # {status, at, result}
    next_run_at: datetime | None


async def _find_system_task(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    resource_key: str,
) -> Task | None:
    """Find an active system-managed Task by integration_id and managed_resource_key.

    Excludes archived (disabled) tasks left behind by previous integration
    delete/recreate cycles.
    """
    stmt = (
        select(Task)
        .join(Component, Task.component_id == Component.id)
        .where(
            and_(
                Component.tenant_id == tenant_id,
                Component.status != "disabled",
                Task.integration_id == integration_id,
                Task.origin_type == "system",
                Task.managed_resource_key == resource_key,
            )
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _find_schedule_for_task(
    session: AsyncSession,
    tenant_id: str,
    task_id: UUID,
) -> Schedule | None:
    """Find the system-managed Schedule targeting a Task."""
    stmt = select(Schedule).where(
        and_(
            Schedule.tenant_id == tenant_id,
            Schedule.target_type == "task",
            Schedule.target_id == task_id,
            Schedule.origin_type == "system",
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_last_task_run(
    session: AsyncSession,
    tenant_id: str,
    task_id: UUID,
) -> dict[str, Any] | None:
    """Get the most recent TaskRun for a given task."""
    stmt = (
        select(TaskRun)
        .where(
            and_(
                TaskRun.tenant_id == tenant_id,
                TaskRun.task_id == task_id,
            )
        )
        .order_by(desc(TaskRun.created_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        return None

    return {
        "status": run.status,
        "at": run.completed_at.isoformat() if run.completed_at else None,
        "task_run_id": str(run.id),
    }


async def _build_managed_resource(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    resource_key: str,
    task: Task,
) -> ManagedResource:
    """Build a ManagedResource from a Task, looking up schedule and last run."""
    # Load the component for the task name
    await session.refresh(task, ["component"])
    task_id = task.component.id
    task_name = task.component.name

    # Find associated schedule
    schedule = await _find_schedule_for_task(session, tenant_id, task_id)
    schedule_dict = None
    schedule_id = None
    next_run_at = None
    if schedule is not None:
        schedule_id = schedule.id
        schedule_dict = {
            "type": schedule.schedule_type,
            "value": schedule.schedule_value,
            "enabled": schedule.enabled,
        }
        next_run_at = schedule.next_run_at

    # Get last run
    last_run = await _get_last_task_run(session, tenant_id, task_id)

    return ManagedResource(
        resource_key=resource_key,
        task_id=task_id,
        task_name=task_name,
        schedule_id=schedule_id,
        schedule=schedule_dict,
        last_run=last_run,
        next_run_at=next_run_at,
    )


async def resolve_managed_resource(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    resource_key: str,
) -> ManagedResource | None:
    """Resolve a resource_key to its Task + Schedule for an integration.

    Accepts any resource_key — both well-known keys (health_check,
    alert_ingestion) and custom action keys (e.g. sourcetype_discovery).
    Returns None if no matching system Task exists.
    """
    task = await _find_system_task(session, tenant_id, integration_id, resource_key)
    if task is None:
        return None

    return await _build_managed_resource(
        session, tenant_id, integration_id, resource_key, task
    )


async def list_managed_resources(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> dict[str, ManagedResource]:
    """List all managed resources for an integration.

    Queries the DB for all system-managed Tasks linked to this integration
    that have a managed_resource_key set. Supports both well-known keys
    (health_check, alert_ingestion) and custom action keys.
    """
    stmt = (
        select(Task)
        .join(Component, Task.component_id == Component.id)
        .where(
            and_(
                Component.tenant_id == tenant_id,
                Component.status != "disabled",
                Task.integration_id == integration_id,
                Task.origin_type == "system",
                Task.managed_resource_key.isnot(None),
            )
        )
    )
    result = await session.execute(stmt)
    tasks = list(result.scalars().all())

    resources: dict[str, ManagedResource] = {}
    for task in tasks:
        resource_key = task.managed_resource_key
        resource = await _build_managed_resource(
            session, tenant_id, integration_id, resource_key, task
        )
        resources[resource_key] = resource

    return resources


async def trigger_ad_hoc_run(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    resource_key: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger an ad-hoc TaskRun for a managed resource.

    Creates a TaskRun with run_context='ad_hoc' and enqueues it for
    execution on the Alert Analysis worker.

    Returns dict with task_run_id and status.
    Raises ValueError if resource cannot be resolved.
    """
    resource = await resolve_managed_resource(
        session, tenant_id, integration_id, resource_key
    )
    if resource is None:
        raise ValueError(f"Managed resource '{resource_key}' not found")

    # Create the TaskRun
    now = datetime.now(UTC)
    task_run = TaskRun(
        tenant_id=tenant_id,
        task_id=resource.task_id,
        status=TaskConstants.Status.RUNNING,
        run_context="ad_hoc",
        started_at=now,
        executor_config={},
        execution_context={
            "triggered_by": "managed_resources_api",
            "integration_id": integration_id,
            **({"params": params} if params else {}),
        },
    )
    session.add(task_run)
    await session.flush()

    # Enqueue for execution
    try:
        from analysi.common.arq_enqueue import enqueue_or_fail

        await enqueue_or_fail(
            "analysi.jobs.task_run_job.execute_task_run",
            str(task_run.id),
            tenant_id,
            model_class=TaskRun,
            row_id=task_run.id,
        )
        logger.info(
            "managed_resource_ad_hoc_run_enqueued",
            task_run_id=str(task_run.id),
            resource_key=resource_key,
            integration_id=integration_id,
        )
    except Exception:
        logger.exception(
            "managed_resource_ad_hoc_enqueue_failed",
            task_run_id=str(task_run.id),
        )
        # Mark as failed if we can't enqueue
        task_run.status = TaskConstants.Status.FAILED
        await session.flush()

    return {
        "task_run_id": str(task_run.id),
        "status": task_run.status,
        "task_id": str(resource.task_id),
        "resource_key": resource_key,
    }
