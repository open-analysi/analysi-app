"""Action tools for product chatbot.

These tools mutate state (run workflows, tasks, create alerts). Each uses a
two-phase confirmation pattern:

1. First call: tool returns a confirmation message describing the action.
   The LLM relays this to the user and asks "Should I proceed?"
2. Second call (after user says "yes"): tool detects matching pending_action
   and executes.

The pending action is persisted in conversation.metadata["pending_action"]
so it survives across user turns.
"""

from dataclasses import asdict, dataclass
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.services.chat_ku_tools import cap_tool_result

logger = get_logger(__name__)


@dataclass
class PendingAction:
    """An action awaiting user confirmation."""

    tool_name: str
    description: str  # Human-readable summary
    kwargs: dict[str, Any]  # Arguments to replay

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingAction":
        return cls(
            tool_name=data["tool_name"],
            description=data["description"],
            kwargs=data["kwargs"],
        )


def check_confirmation(
    pending: PendingAction | None,
    tool_name: str,
    kwargs: dict[str, Any],
) -> bool:
    """Check if a pending action matches the current call (confirmation)."""
    if pending is None:
        return False
    return pending.tool_name == tool_name and pending.kwargs == kwargs


def build_confirmation_message(action_description: str) -> str:
    """Build a structured confirmation request message for the LLM."""
    return (
        f"⚠️ **Action requires confirmation**\n\n"
        f"{action_description}\n\n"
        f"Please confirm with the user before proceeding. "
        f"If they agree, call this tool again with the same arguments."
    )


# --- Action implementations ---


async def run_workflow_impl(
    session: AsyncSession,
    tenant_id: str,
    workflow_id: str,
    input_data: dict[str, Any] | None = None,
) -> str:
    """Execute a workflow. Returns the workflow run ID for tracking."""
    from analysi.services.workflow import WorkflowService
    from analysi.services.workflow_execution import WorkflowExecutor

    try:
        wf_uuid = UUID(workflow_id)
    except ValueError:
        return f"Invalid workflow ID format: '{workflow_id}'. Expected a UUID."

    # Verify workflow exists first
    wf_service = WorkflowService(session)
    workflow = await wf_service.get_workflow(tenant_id, wf_uuid)
    if not workflow:
        return f"Workflow '{workflow_id}' not found."

    executor = WorkflowExecutor(session)
    workflow_run_id = await executor.execute_workflow(
        tenant_id=tenant_id,
        workflow_id=wf_uuid,
        input_data=input_data or {},
    )
    await session.flush()

    result = (
        f"✅ Workflow **{workflow.name}** started successfully.\n\n"
        f"- Workflow Run ID: `{workflow_run_id}`\n"
        f"- Status: running\n\n"
        f"Use `get_workflow_run` with this ID to check progress."
    )
    return cap_tool_result(result)


async def run_task_impl(
    session: AsyncSession,
    tenant_id: str,
    task_identifier: str,
    input_data: dict[str, Any] | None = None,
) -> str:
    """Execute a task. Returns the task run ID for tracking."""
    from analysi.services.task import TaskService

    service = TaskService(session)

    # Resolve task by UUID or cy_name
    task = None
    try:
        task_uuid = UUID(task_identifier)
        task = await service.get_task(task_uuid, tenant_id)
    except ValueError:
        task = await service.get_task_by_cy_name(task_identifier, tenant_id)

    if not task:
        return f"Task '{task_identifier}' not found."

    # Execute via the task execution endpoint pattern
    from analysi.services.task_execution import DefaultTaskExecutor

    executor = DefaultTaskExecutor(session)
    task_run = await executor.create_and_execute(
        task=task,
        tenant_id=tenant_id,
        input_data=input_data or {},
    )
    await session.flush()

    result = (
        f"✅ Task **{task.component.name}** started successfully.\n\n"
        f"- Task Run ID: `{task_run.id}`\n"
        f"- Status: {task_run.status}\n\n"
        f"Use `get_task_run` with this ID to check progress."
    )
    return cap_tool_result(result)


async def analyze_alert_impl(
    session: AsyncSession,
    tenant_id: str,
    alert_id: str,
) -> str:
    """Trigger alert analysis by dispatching a control event."""
    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        return f"Invalid alert ID format: '{alert_id}'. Expected a UUID."

    # Verify alert exists
    from analysi.services.chat_tools import _make_alert_service

    alert_service = _make_alert_service(session)
    alert = await alert_service.get_alert(tenant_id, alert_uuid, include_analysis=False)
    if not alert:
        return f"Alert '{alert_id}' not found."

    # Dispatch control event for analysis
    from analysi.repositories.control_event_repository import (
        ControlEventRepository,
    )

    event_repo = ControlEventRepository(session)
    await event_repo.insert(
        tenant_id=tenant_id,
        channel="alert:analyze",
        payload={"alert_id": str(alert_uuid)},
    )
    await session.flush()

    result = (
        f"✅ Analysis triggered for alert **{alert.title}** ({alert_id}).\n\n"
        f"The alert will be picked up by the analysis pipeline shortly."
    )
    return cap_tool_result(result)


async def create_alert_impl(
    session: AsyncSession,
    tenant_id: str,
    title: str,
    severity: str = "medium",
    description: str | None = None,
    source_vendor: str = "chatbot",
    source_product: str = "analysi-chatbot",
) -> str:
    """Create a new alert."""
    import json
    from datetime import datetime

    from analysi.schemas.alert import AlertCreate
    from analysi.services.chat_tools import _make_alert_service

    service = _make_alert_service(session)

    # raw_data must be valid JSON (alert_service hashes it for deduplication
    # and downstream OCSF normalizers / exports parse it). Building it as
    # an f-string silently produces invalid JSON for any title containing a
    # double-quote, backslash, newline, control char, or itself JSON-shaped
    # text. ``json.dumps`` is the only safe encoder.
    raw_data = json.dumps(
        {"title": title, "severity": severity, "source": "chatbot"}
    )

    create_data = AlertCreate(
        title=title,
        severity=severity,
        description=description,
        source_vendor=source_vendor,
        source_product=source_product,
        triggering_event_time=datetime.now(UTC),
        raw_data=raw_data,
    )

    alert = await service.create_alert(tenant_id, create_data)
    await session.flush()

    result = (
        f"✅ Alert created successfully.\n\n"
        f"- Alert ID: `{alert.alert_id}`\n"
        f"- Title: {title}\n"
        f"- Severity: {severity}\n"
    )
    return cap_tool_result(result)
