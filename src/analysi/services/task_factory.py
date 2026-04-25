"""
Task Factory — auto-creates Tasks and Schedules for integrations.

Python functions that generate real, editable Tasks when an integration is
configured. NOT a template system — the output is a plain Task with
origin_type="system" and integration_id set.

Factory functions:
  - create_alert_ingestion_task(): Cy script with pull_alerts -> alerts_to_ocsf -> ingest_alerts
  - create_health_check_task(): Cy script with health_check()
  - create_default_schedule(): Schedule row targeting a Task
  - process_health_check_result(): Post-execution hook for health status
"""

from datetime import UTC, datetime
from textwrap import dedent
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.constants import IntegrationHealthStatus, ManagedResourceKey, TaskConstants
from analysi.models.component import Component
from analysi.models.schedule import Schedule
from analysi.models.task import Task
from analysi.repositories.schedule_repository import ScheduleRepository
from analysi.repositories.task import TaskRepository
from analysi.scheduler.interval import compute_next_run_at

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Script generation (pure functions)
# ---------------------------------------------------------------------------


def generate_alert_ingestion_script(integration_type: str) -> str:
    """Generate Cy script for alert ingestion.

    The script reads the last checkpoint, pulls alerts, normalizes to OCSF,
    persists via ingest_alerts(), and updates the checkpoint on success.

    Args:
        integration_type: Integration type identifier (e.g. "splunk").

    Returns:
        Cy script string.
    """
    return dedent(f"""\
        start_time = get_checkpoint("last_pull") ?? default_lookback()
        end_time = now()

        pull_result = app::{integration_type}::pull_alerts(start_time, end_time)
        raw_alerts = pull_result["alerts"]

        ocsf_result = app::{integration_type}::alerts_to_ocsf(raw_alerts=raw_alerts)
        ocsf_alerts = ocsf_result["normalized_alerts"]

        result = ingest_alerts(ocsf_alerts)

        set_checkpoint("last_pull", end_time)
        return result
    """).strip()


def generate_action_script(integration_type: str, cy_name: str) -> str:
    """Generate Cy script for a generic scheduled action.

    Produces a one-liner that calls the action and returns its result.
    Suitable for self-contained actions like sourcetype_discovery that
    handle their own side effects (e.g. writing to Knowledge Units).

    Args:
        integration_type: Integration type identifier (e.g. "splunk").
        cy_name: The action's Cy-callable name (e.g. "sourcetype_discovery").

    Returns:
        Cy script string.
    """
    return f"return app::{integration_type}::{cy_name}()"


def generate_health_check_script(integration_type: str) -> str:
    """Generate Cy script for health check.

    Args:
        integration_type: Integration type identifier (e.g. "splunk").

    Returns:
        Cy script string.
    """
    return f"return app::{integration_type}::health_check()"


# ---------------------------------------------------------------------------
# Task creation (DB operations via TaskRepository)
# ---------------------------------------------------------------------------


async def _create_system_task(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    integration_type: str,
    *,
    name: str,
    description: str,
    script: str,
    function: str,
    scope: str,
    managed_resource_key: str,
    categories: list[str] | None = None,
) -> Task:
    """Shared helper: create a system-managed Task linked to an integration."""
    task_data = {
        "tenant_id": tenant_id,
        "name": name,
        "description": description,
        "script": script,
        "function": function,
        "scope": scope,
        "managed_resource_key": managed_resource_key,
        "categories": categories or [],
        "mode": "saved",
        "app": integration_type,
        "integration_id": integration_id,
        "origin_type": "system",
        "system_only": False,
        "visible": True,
    }

    repo = TaskRepository(session)
    return await repo.create(task_data)


async def create_alert_ingestion_task(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    integration_type: str,
) -> Task:
    """Create an alert ingestion Task for an AlertSource integration.

    Generates a Cy script that calls pull_alerts -> alerts_to_ocsf -> ingest_alerts
    with checkpoint management. The Task is marked origin_type="system" and linked
    to the integration via integration_id.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID (e.g. "splunk-prod").
        integration_type: Integration type from manifest (e.g. "splunk").

    Returns:
        The created Task with component loaded.
    """
    task = await _create_system_task(
        session,
        tenant_id,
        integration_id,
        integration_type,
        name=f"Alert Ingestion for {integration_id}",
        description=(
            f"Auto-created alert ingestion task for {integration_id}. "
            "Pulls alerts, normalizes to OCSF, and persists via ingest_alerts()."
        ),
        script=generate_alert_ingestion_script(integration_type),
        function="data_conversion",
        scope="input",
        managed_resource_key=ManagedResourceKey.ALERT_INGESTION,
        categories=["alert_ingestion", "integration", "scheduled"],
    )

    logger.info(
        "created_alert_ingestion_task",
        tenant_id=tenant_id,
        integration_id=integration_id,
        integration_type=integration_type,
        task_component_id=str(task.component.id),
    )

    return task


async def create_health_check_task(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    integration_type: str,
) -> Task:
    """Create a health check Task for an integration.

    Generates a Cy script that calls health_check() and returns the result.
    The Task is marked origin_type="system" and linked to the integration.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID.
        integration_type: Integration type from manifest.

    Returns:
        The created Task with component loaded.
    """
    task = await _create_system_task(
        session,
        tenant_id,
        integration_id,
        integration_type,
        name=f"Health Check for {integration_id}",
        description=(
            f"Auto-created health check task for {integration_id}. "
            "Returns {{healthy: true/false}} to indicate integration status."
        ),
        script=generate_health_check_script(integration_type),
        function="extraction",
        scope="processing",
        managed_resource_key=ManagedResourceKey.HEALTH_CHECK,
        categories=["health_monitoring", "integration", "scheduled"],
    )

    logger.info(
        "created_health_check_task",
        tenant_id=tenant_id,
        integration_id=integration_id,
        integration_type=integration_type,
        task_component_id=str(task.component.id),
    )

    return task


async def create_action_task(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
    integration_type: str,
    *,
    action_id: str,
    action_name: str,
    cy_name: str,
    categories: list[str] | None = None,
) -> Task:
    """Create a generic scheduled Task for an integration action.

    For self-contained actions (e.g. sourcetype_discovery) that handle their
    own side effects. The generated Cy script simply calls the action and
    returns its result.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID.
        integration_type: Integration type from manifest.
        action_id: Action identifier, used as managed_resource_key.
        action_name: Human-readable action name for the task title.
        cy_name: Cy-callable tool name.
        categories: Optional action categories from the manifest.

    Returns:
        The created Task with component loaded.
    """
    base_categories = list(categories) if categories else []
    base_categories.extend(["integration", "scheduled"])

    task = await _create_system_task(
        session,
        tenant_id,
        integration_id,
        integration_type,
        name=f"{action_name} for {integration_id}",
        description=(f"Auto-created {action_name.lower()} task for {integration_id}."),
        script=generate_action_script(integration_type, cy_name),
        function="extraction",
        scope="processing",
        managed_resource_key=action_id,
        categories=base_categories,
    )

    logger.info(
        "created_action_task",
        tenant_id=tenant_id,
        integration_id=integration_id,
        integration_type=integration_type,
        action_id=action_id,
        task_component_id=str(task.component.id),
    )

    return task


# ---------------------------------------------------------------------------
# Schedule creation
# ---------------------------------------------------------------------------


async def create_default_schedule(
    session: AsyncSession,
    tenant_id: str,
    task_id: UUID,
    *,
    schedule_value: str = "5m",
    integration_id: str | None = None,
) -> Schedule:
    """Create a disabled system-managed Schedule for a Task.

    The schedule starts disabled -- the admin enables the integration
    (after configuring credentials) to activate it.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        task_id: Target Task's component_id.
        schedule_value: Interval string (default "5m").
        integration_id: Optional integration link for cascade operations.

    Returns:
        The created Schedule.
    """
    repo = ScheduleRepository(session)
    schedule = await repo.create(
        tenant_id=tenant_id,
        target_type="task",
        target_id=task_id,
        schedule_type="every",
        schedule_value=schedule_value,
        enabled=False,
        origin_type="system",
        integration_id=integration_id,
    )

    logger.info(
        "created_default_schedule",
        tenant_id=tenant_id,
        task_id=str(task_id),
        schedule_id=str(schedule.id),
        schedule_value=schedule_value,
        integration_id=integration_id,
    )

    return schedule


# ---------------------------------------------------------------------------
# Lifecycle cascades
# ---------------------------------------------------------------------------


async def cascade_enable_schedules(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> int:
    """Enable all system-managed schedules for an integration and compute next_run_at.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID.

    Returns:
        Number of schedules enabled.
    """
    # Find currently disabled system-managed schedules for this integration.
    # Only enable schedules that have a valid target (target_id references
    # an existing Task/Workflow component_id). This prevents re-enabling
    # stale schedules from a previously deleted integration with the same ID.
    from analysi.models.component import Component

    stmt = (
        select(Schedule)
        .join(Component, Schedule.target_id == Component.id)
        .where(
            and_(
                Schedule.tenant_id == tenant_id,
                Schedule.integration_id == integration_id,
                Schedule.origin_type == "system",
                Schedule.enabled.is_(False),
                Component.status != "disabled",
            )
        )
    )
    result = await session.execute(stmt)
    schedules = list(result.scalars().all())

    count = 0
    now = datetime.now(UTC)
    for schedule in schedules:
        schedule.enabled = True
        next_run = compute_next_run_at(
            schedule.schedule_type, schedule.schedule_value, from_time=now
        )
        schedule.next_run_at = next_run
        count += 1

    await session.flush()

    if count > 0:
        logger.info(
            "cascade_enabled_schedules",
            tenant_id=tenant_id,
            integration_id=integration_id,
            count=count,
        )

    return count


async def cascade_disable_schedules(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> int:
    """Disable all system-managed schedules for an integration.

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID.

    Returns:
        Number of schedules disabled.
    """
    stmt = (
        update(Schedule)
        .where(
            and_(
                Schedule.tenant_id == tenant_id,
                Schedule.integration_id == integration_id,
                Schedule.origin_type == "system",
            )
        )
        .values(enabled=False, next_run_at=None)
    )
    result = await session.execute(stmt)
    await session.flush()

    count = result.rowcount
    if count > 0:
        logger.info(
            "cascade_disabled_schedules",
            tenant_id=tenant_id,
            integration_id=integration_id,
            count=count,
        )

    return count


async def cleanup_integration_tasks(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> dict[str, int]:
    """Archive Tasks and disable Schedules for a deleted integration.

    Disables system-managed schedules and sets Task components to
    status="disabled" (soft-delete / archive).

    Args:
        session: Database session.
        tenant_id: Tenant identifier.
        integration_id: Integration instance ID.

    Returns:
        {"schedules_disabled": int, "tasks_archived": int}
    """
    # 1. Disable all system-managed schedules
    schedules_disabled = await cascade_disable_schedules(
        session, tenant_id, integration_id
    )

    # 2. Archive Tasks linked to this integration by disabling their components
    task_stmt = (
        select(Task)
        .join(Component, Task.component_id == Component.id)
        .where(
            and_(
                Component.tenant_id == tenant_id,
                Task.integration_id == integration_id,
                Task.origin_type == "system",
            )
        )
    )
    result = await session.execute(task_stmt)
    tasks = list(result.scalars().all())

    tasks_archived = 0
    for task in tasks:
        # Load component to update status
        await session.refresh(task, ["component"])
        if task.component.status != "disabled":
            task.component.status = "disabled"
            tasks_archived += 1

    await session.flush()

    if schedules_disabled > 0 or tasks_archived > 0:
        logger.info(
            "cleanup_integration_tasks",
            tenant_id=tenant_id,
            integration_id=integration_id,
            schedules_disabled=schedules_disabled,
            tasks_archived=tasks_archived,
        )

    return {
        "schedules_disabled": schedules_disabled,
        "tasks_archived": tasks_archived,
    }


# ---------------------------------------------------------------------------
# Health check result processing
# ---------------------------------------------------------------------------


def process_health_check_result(
    task_run_status: str,
    task_run_result: dict[str, Any] | None,
) -> str:
    """Determine integration health status from a health check TaskRun.

    | TaskRun Status | result.healthy | Health    |
    |----------------|----------------|-----------|
    | completed      | true           | healthy   |
    | completed      | false          | unhealthy |
    | failed         | n/a            | unknown   |

    Args:
        task_run_status: TaskRun status string.
        task_run_result: TaskRun result dict (may contain "healthy" key).

    Returns:
        One of "healthy", "unhealthy", "unknown".
    """
    if task_run_status != TaskConstants.Status.COMPLETED:
        return IntegrationHealthStatus.UNKNOWN

    if task_run_result is None:
        return IntegrationHealthStatus.UNHEALTHY

    if task_run_result.get("healthy") is True:
        return IntegrationHealthStatus.HEALTHY

    return IntegrationHealthStatus.UNHEALTHY
