"""Read-only platform tools for product chatbot.

Provides read-only access to alerts, workflows, tasks, integrations, and
execution history via Pydantic AI tool calls. All results are capped and
scanned for injection.

Architecture:
  - Tools call service layer directly (same process, same DB session)
  - Results are capped at MAX_TOOL_RESULT_TOKENS to prevent context bloat
  - Injection patterns in results are flagged (tenant data is untrusted)
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.schemas.chat_tool_output import (
    AlertChatDetail,
    AlertChatSummary,
    IntegrationChatSummary,
    TaskChatSummary,
    TaskRunChatSummary,
    WorkflowChatSummary,
    WorkflowRunChatSummary,
)
from analysi.services.chat_ku_tools import cap_tool_result, sanitize_tool_result

logger = get_logger(__name__)


# --- Service factory helpers (avoid repeating repo construction) ---


def _make_alert_service(session: AsyncSession):
    """Build AlertService with all required repositories."""
    from analysi.repositories.alert_repository import (
        AlertAnalysisRepository,
        AlertRepository,
        DispositionRepository,
    )
    from analysi.services.alert_service import AlertService

    return AlertService(
        AlertRepository(session),
        AlertAnalysisRepository(session),
        DispositionRepository(session),
        session,
    )


def _make_integration_service(session: AsyncSession):
    """Build IntegrationService with required repositories."""
    from analysi.repositories.integration_repository import IntegrationRepository
    from analysi.services.integration_service import IntegrationService

    return IntegrationService(
        integration_repo=IntegrationRepository(session),
    )


def _format_dict(data: Any, indent: int = 2) -> str:
    """JSON-serialize a dict/list for tool output, handling UUIDs and datetimes."""
    return json.dumps(data, indent=indent, default=str)


# --- Alert tools ---


async def get_alert_impl(
    session: AsyncSession,
    tenant_id: str,
    alert_id: str,
) -> str:
    """Fetch alert details by ID."""
    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        return f"Invalid alert ID format: '{alert_id}'. Expected a UUID."

    service = _make_alert_service(session)

    alert = await service.get_alert(tenant_id, alert_uuid, include_analysis=True)
    if not alert:
        return f"Alert '{alert_id}' not found."

    detail = AlertChatDetail.from_alert_response_detail(alert)
    result = detail.to_chat_detail()
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"alert '{alert_id}'")


async def search_alerts_impl(
    session: AsyncSession,
    tenant_id: str,
    severity: str | None = None,
    status: str | None = None,
    source_vendor: str | None = None,
    title_filter: str | None = None,
    ioc_filter: str | None = None,
    limit: int = 10,
) -> str:
    """Search/filter alerts by severity, status, source, title, or IOC value."""
    service = _make_alert_service(session)
    filters: dict[str, Any] = {}
    if severity:
        # Repo expects a list for IN clause
        filters["severity"] = [severity] if isinstance(severity, str) else severity
    if status:
        filters["status"] = status
    if source_vendor:
        filters["source_vendor"] = source_vendor
    if title_filter:
        filters["title_filter"] = title_filter
    if ioc_filter:
        filters["ioc_filter"] = ioc_filter

    alert_list = await service.list_alerts(
        tenant_id=tenant_id,
        filters=filters,
        limit=min(limit, 20),
        include_short_summary=True,
    )

    if not alert_list.alerts:
        filter_desc = ", ".join(f"{k}={v}" for k, v in filters.items()) or "none"
        return f"No alerts found matching filters: {filter_desc}."

    summaries = [
        AlertChatSummary.from_alert_response(alert) for alert in alert_list.alerts
    ]
    result = AlertChatSummary.format_list(summaries, alert_list.total)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "alert search")


# --- Workflow tools ---


async def get_workflow_impl(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str,
) -> str:
    """Fetch workflow definition by ID."""
    from analysi.services.workflow import WorkflowService

    service = WorkflowService(session)

    try:
        wf_uuid = UUID(workflow_id)
    except ValueError:
        return f"Invalid workflow ID format: '{workflow_id}'. Expected a UUID."

    workflow = await service.get_workflow(tenant_id, wf_uuid, slim=True)
    if not workflow:
        return f"Workflow '{workflow_id}' not found."

    result = f"# Workflow\n\n{_format_dict(workflow)}"
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"workflow '{workflow_id}'")


async def list_workflows_impl(
    session: AsyncSession,
    tenant_id: str,
    name_filter: str | None = None,
    limit: int = 20,
) -> str:
    """List available workflows with optional name filter."""
    from analysi.services.workflow import WorkflowService

    service = WorkflowService(session)
    workflows, meta = await service.list_workflows(
        tenant_id=tenant_id,
        limit=min(limit, 50),
        name_filter=name_filter,
    )

    if not workflows:
        return "No workflows found."

    summaries = [WorkflowChatSummary.from_workflow(wf) for wf in workflows]
    result = WorkflowChatSummary.format_list(summaries, meta["total"])
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "workflow list")


# --- Task tools ---


async def get_task_impl(
    session: AsyncSession,
    tenant_id: str,
    task_identifier: str,
) -> str:
    """Fetch task details by ID or cy_name."""
    from analysi.services.task import TaskService

    service = TaskService(session)

    # Try UUID first, then cy_name
    task = None
    try:
        task_uuid = UUID(task_identifier)
        task = await service.get_task(task_uuid, tenant_id)
    except ValueError:
        task = await service.get_task_by_cy_name(task_identifier, tenant_id)

    if not task:
        return f"Task '{task_identifier}' not found."

    summary = TaskChatSummary.from_task(task)
    result = summary.to_chat_detail()
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"task '{task_identifier}'")


async def list_tasks_impl(
    session: AsyncSession,
    tenant_id: str,
    function: str | None = None,
    name_filter: str | None = None,
    categories: list[str] | None = None,
    limit: int = 50,
) -> str:
    """List available tasks with optional filters."""
    from analysi.services.task import TaskService

    service = TaskService(session)
    tasks, meta = await service.list_tasks(
        tenant_id=tenant_id,
        limit=min(limit, 50),
        function=function,
        name_filter=name_filter,
        categories=categories,
    )

    if not tasks:
        return "No tasks found."

    summaries = [TaskChatSummary.from_task(task) for task in tasks]
    result = TaskChatSummary.format_list(summaries, meta["total"])
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "task list")


# --- Integration tools ---


async def get_integration_health_impl(
    session: AsyncSession,
    tenant_id: str,
    integration_id: str,
) -> str:
    """Fetch integration details and health status."""
    service = _make_integration_service(session)
    integration = await service.get_integration(tenant_id, integration_id)

    if not integration:
        return f"Integration '{integration_id}' not found."

    summary = IntegrationChatSummary.from_integration(integration)
    result = summary.to_chat_detail()
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"integration '{integration_id}'")


async def list_integrations_impl(
    session: AsyncSession,
    tenant_id: str,
) -> str:
    """List all configured integrations with health status."""
    service = _make_integration_service(session)
    integrations = await service.list_integrations(tenant_id)

    if not integrations:
        return "No integrations configured."

    summaries = [IntegrationChatSummary.from_integration(i) for i in integrations]
    result = IntegrationChatSummary.format_list(summaries)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "integration list")


# --- Execution result tools ---


async def get_workflow_run_impl(
    session: AsyncSession,
    tenant_id: str,
    workflow_run_id: str,
) -> str:
    """Fetch workflow run details including node statuses."""
    from analysi.services.workflow_execution import WorkflowExecutionService

    try:
        run_uuid = UUID(workflow_run_id)
    except ValueError:
        return f"Invalid workflow run ID format: '{workflow_run_id}'. Expected a UUID."

    service = WorkflowExecutionService()
    run = await service.get_workflow_run_details(session, tenant_id, run_uuid)

    if not run:
        return f"Workflow run '{workflow_run_id}' not found."

    summary = WorkflowRunChatSummary.from_workflow_run(run)
    result = summary.to_chat_detail()
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"workflow run '{workflow_run_id}'")


async def get_task_run_impl(
    session: AsyncSession,
    tenant_id: str,
    task_run_id: str,
) -> str:
    """Fetch task run details including output."""
    from analysi.services.task_run import TaskRunService

    try:
        run_uuid = UUID(task_run_id)
    except ValueError:
        return f"Invalid task run ID format: '{task_run_id}'. Expected a UUID."

    service = TaskRunService()
    task_run = await service.get_task_run(session, tenant_id, run_uuid)

    if not task_run:
        return f"Task run '{task_run_id}' not found."

    summary = TaskRunChatSummary.from_task_run(task_run)
    result = summary.to_chat_detail()
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"task run '{task_run_id}'")


# --- Run listing tools ---


async def list_workflow_runs_impl(
    session: AsyncSession,
    tenant_id: str,
    status: str | None = None,
    limit: int = 10,
) -> str:
    """List recent workflow runs with optional status filter."""
    from analysi.repositories.workflow_execution import WorkflowRunRepository

    repo = WorkflowRunRepository(session)
    runs, total = await repo.list_workflow_runs(
        tenant_id=tenant_id,
        status=status,
        limit=min(limit, 20),
    )

    if not runs:
        filter_desc = f" (status={status})" if status else ""
        return f"No workflow runs found{filter_desc}."

    summaries = [WorkflowRunChatSummary.from_workflow_run(r) for r in runs]
    result = WorkflowRunChatSummary.format_list(summaries, total)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "workflow run list")


async def list_task_runs_impl(
    session: AsyncSession,
    tenant_id: str,
    status: str | None = None,
    workflow_run_id: str | None = None,
    limit: int = 10,
) -> str:
    """List recent task runs with optional status or workflow run filter."""
    from analysi.services.task_run import TaskRunService

    service = TaskRunService()

    wf_run_uuid = None
    if workflow_run_id:
        try:
            wf_run_uuid = UUID(workflow_run_id)
        except ValueError:
            return f"Invalid workflow run ID format: '{workflow_run_id}'."

    runs, total = await service.list_task_runs(
        session,
        tenant_id=tenant_id,
        status=status,
        workflow_run_id=wf_run_uuid,
        limit=min(limit, 20),
    )

    if not runs:
        filter_desc = f" (status={status})" if status else ""
        return f"No task runs found{filter_desc}."

    summaries = [TaskRunChatSummary.from_task_run(r) for r in runs]
    result = TaskRunChatSummary.format_list(summaries, total)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "task run list")


# --- Audit trail tool ---


async def search_audit_trail_impl(
    session: AsyncSession,
    tenant_id: str,
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 20,
) -> str:
    """Search the activity audit trail. Admin-only (caller must gate)."""
    from analysi.repositories.activity_audit_repository import (
        ActivityAuditRepository,
    )
    from analysi.services.activity_audit_service import ActivityAuditService

    service = ActivityAuditService(ActivityAuditRepository(session))
    events, total = await service.list_activities(
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        limit=min(limit, 50),
    )

    if not events:
        filter_desc = (
            ", ".join(
                f"{k}={v}"
                for k, v in {"action": action, "resource_type": resource_type}.items()
                if v
            )
            or "none"
        )
        return f"No audit events found matching filters: {filter_desc}."

    lines = [f"Found {total} audit events (showing {len(events)}):\n"]
    for event in events:
        ts = event.created_at.isoformat() if event.created_at else "?"
        lines.append(
            f"- [{ts}] **{event.action}** on {event.resource_type}"
            f" ({event.resource_id}) by {event.actor_type}"
        )

    result = "\n".join(lines)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "audit trail search")


# --- Platform summary tool ---


async def get_platform_summary_impl(
    session: AsyncSession,
    tenant_id: str,
) -> str:
    """Get a combined summary of alerts and integrations in one call.

    Designed for 'briefing' / 'overview' / 'status' type questions
    where the user wants a snapshot of the whole platform.
    """
    sections: list[str] = ["# Platform Summary\n"]

    # --- Alerts ---
    try:
        alert_service = _make_alert_service(session)
        alert_list = await alert_service.list_alerts(
            tenant_id=tenant_id,
            filters={},
            limit=10,
            include_short_summary=True,
        )
        if alert_list.alerts:
            summaries = [
                AlertChatSummary.from_alert_response(a) for a in alert_list.alerts
            ]
            sections.append(f"## Alerts ({alert_list.total} total)\n")
            sections.extend(s.to_chat_line() for s in summaries)
        else:
            sections.append("## Alerts\nNo alerts in the system.\n")
    except Exception as exc:
        logger.warning("chat_summary_alerts_error", error=str(exc)[:200])
        sections.append("## Alerts\nUnable to fetch alerts.\n")

    sections.append("")  # blank line

    # --- Integrations ---
    try:
        integ_service = _make_integration_service(session)
        integrations = await integ_service.list_integrations(tenant_id)
        if integrations:
            integ_summaries = [
                IntegrationChatSummary.from_integration(i) for i in integrations
            ]
            healthy = [s.name for s in integ_summaries if s.health_status == "healthy"]
            degraded = [
                s.name for s in integ_summaries if s.health_status == "degraded"
            ]
            unhealthy = [
                s.name
                for s in integ_summaries
                if s.health_status not in ("healthy", "degraded")
            ]

            sections.append(f"## Integrations ({len(integrations)} total)\n")
            if unhealthy:
                sections.append(
                    f"**Unhealthy ({len(unhealthy)})**: {', '.join(unhealthy)}"
                )
            if degraded:
                sections.append(
                    f"**Degraded ({len(degraded)})**: {', '.join(degraded)}"
                )
            if healthy:
                sections.append(f"**Healthy ({len(healthy)})**: {', '.join(healthy)}")
        else:
            sections.append("## Integrations\nNo integrations configured.\n")
    except Exception as exc:
        logger.warning("chat_summary_integrations_error", error=str(exc)[:200])
        sections.append("## Integrations\nUnable to fetch integrations.\n")

    result = "\n".join(sections)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "platform summary")
