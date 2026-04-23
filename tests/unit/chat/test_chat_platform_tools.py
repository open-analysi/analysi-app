"""Unit tests for chat platform tools.

Tests read-only tools, action tools with confirmation, admin role gating,
and meta tools. Uses mocked services to avoid database dependency.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.chat_action_tools import (
    PendingAction,
    build_confirmation_message,
    check_confirmation,
)
from analysi.services.chat_meta_tools import (
    get_page_context_impl,
    suggest_next_steps_impl,
)
from analysi.services.chat_tools import (
    get_alert_impl,
    get_task_impl,
    get_workflow_impl,
    list_integrations_impl,
    list_tasks_impl,
    list_workflows_impl,
    search_alerts_impl,
    search_audit_trail_impl,
)

# --- Fixtures ---


@pytest.fixture
def mock_session():
    """Mock async DB session."""
    return AsyncMock()


@pytest.fixture
def tenant_id():
    return f"test-tenant-{uuid4().hex[:8]}"


# --- PendingAction and confirmation logic ---


class TestPendingAction:
    """Tests for the two-phase confirmation pattern."""

    def test_to_dict_round_trip(self):
        """PendingAction serializes and deserializes correctly."""
        action = PendingAction(
            tool_name="run_workflow",
            description="Execute workflow abc",
            kwargs={"workflow_id": "abc-123"},
        )
        data = action.to_dict()
        restored = PendingAction.from_dict(data)
        assert restored.tool_name == "run_workflow"
        assert restored.kwargs == {"workflow_id": "abc-123"}

    def test_check_confirmation_matches(self):
        """Confirmation check succeeds when tool_name and kwargs match."""
        pending = PendingAction(
            tool_name="run_task",
            description="Execute task foo",
            kwargs={"task_identifier": "foo", "input_data": None},
        )
        assert check_confirmation(
            pending, "run_task", {"task_identifier": "foo", "input_data": None}
        )

    def test_check_confirmation_wrong_tool(self):
        """Confirmation check fails when tool_name differs."""
        pending = PendingAction(
            tool_name="run_task",
            description="Execute task",
            kwargs={"task_identifier": "foo"},
        )
        assert not check_confirmation(
            pending, "run_workflow", {"task_identifier": "foo"}
        )

    def test_check_confirmation_wrong_kwargs(self):
        """Confirmation check fails when kwargs differ."""
        pending = PendingAction(
            tool_name="run_task",
            description="Execute task",
            kwargs={"task_identifier": "foo"},
        )
        assert not check_confirmation(pending, "run_task", {"task_identifier": "bar"})

    def test_check_confirmation_none_pending(self):
        """Confirmation check returns False when nothing is pending."""
        assert not check_confirmation(None, "run_task", {"task_identifier": "foo"})

    def test_build_confirmation_message_structure(self):
        """Confirmation message contains the action description."""
        msg = build_confirmation_message("Execute workflow phishing-triage")
        assert "Action requires confirmation" in msg
        assert "phishing-triage" in msg
        assert "confirm" in msg.lower()


# --- Read-only tool tests ---


class TestGetAlert:
    """Tests for get_alert tool."""

    @pytest.mark.asyncio
    async def test_returns_alert_summary(self, mock_session, tenant_id):
        """Returns formatted alert with key fields."""
        alert_id = str(uuid4())
        mock_alert = MagicMock()
        mock_alert.model_dump.return_value = {
            "alert_id": alert_id,
            "title": "Suspicious Login",
            "severity": "high",
            "analysis_status": "new",
            "source_vendor": "Splunk",
            "source_product": "ES",
            "triggering_event_time": "2026-03-19T10:00:00Z",
            "description": "Multiple failed logins",
            "entities": [],
            "iocs": [],
            "current_analysis": None,
        }

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.get_alert = AsyncMock(return_value=mock_alert)
            result = await get_alert_impl(mock_session, tenant_id, alert_id)

        assert "Suspicious Login" in result
        assert "high" in result
        assert alert_id in result

    @pytest.mark.asyncio
    async def test_alert_not_found(self, mock_session, tenant_id):
        """Returns not-found message for missing alert."""
        alert_id = str(uuid4())
        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.get_alert = AsyncMock(return_value=None)
            result = await get_alert_impl(mock_session, tenant_id, alert_id)

        assert "not found" in result

    @pytest.mark.asyncio
    async def test_invalid_uuid(self, mock_session, tenant_id):
        """Returns error for invalid UUID format."""
        result = await get_alert_impl(mock_session, tenant_id, "not-a-uuid")
        assert "Invalid alert ID" in result


class TestSearchAlerts:
    """Tests for search_alerts tool."""

    @pytest.mark.asyncio
    async def test_returns_filtered_results(self, mock_session, tenant_id):
        """Returns formatted list of matching alerts."""
        mock_alert = MagicMock()
        mock_alert.alert_id = uuid4()
        mock_alert.title = "Phishing Attempt"
        mock_alert.severity = "high"
        mock_alert.analysis_status = "new"
        mock_alert.source_vendor = "Splunk"
        mock_alert.source_product = "ES"
        mock_alert.short_summary = "User clicked malicious link"

        mock_list = MagicMock()
        mock_list.alerts = [mock_alert]
        mock_list.total = 1

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.list_alerts = AsyncMock(return_value=mock_list)
            result = await search_alerts_impl(mock_session, tenant_id, severity="high")

        assert "Phishing Attempt" in result
        assert "high" in result

    @pytest.mark.asyncio
    async def test_no_results(self, mock_session, tenant_id):
        """Returns informative message when no alerts match."""
        mock_list = MagicMock()
        mock_list.alerts = []

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.list_alerts = AsyncMock(return_value=mock_list)
            result = await search_alerts_impl(
                mock_session, tenant_id, severity="critical"
            )

        assert "No alerts found" in result

    @pytest.mark.asyncio
    async def test_ioc_filter_passes_through(self, mock_session, tenant_id):
        """IOC filter is passed to the service layer for searching by IOC value."""
        mock_alert = MagicMock()
        mock_alert.alert_id = uuid4()
        mock_alert.title = "SQL Injection Detected"
        mock_alert.severity = "high"
        mock_alert.analysis_status = "completed"
        mock_alert.source_vendor = "Splunk"
        mock_alert.source_product = "ES"
        mock_alert.short_summary = "Attack from 167.99.169.17"

        mock_list = MagicMock()
        mock_list.alerts = [mock_alert]
        mock_list.total = 1

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.list_alerts = AsyncMock(return_value=mock_list)
            result = await search_alerts_impl(
                mock_session, tenant_id, ioc_filter="167.99.169.17"
            )

        assert "SQL Injection Detected" in result
        # Verify ioc_filter was passed through to the service
        call_kwargs = MockService.return_value.list_alerts.call_args
        filters = call_kwargs.kwargs.get("filters", call_kwargs[1].get("filters", {}))
        assert filters.get("ioc_filter") == "167.99.169.17"


class TestListWorkflows:
    """Tests for list_workflows tool."""

    @pytest.mark.asyncio
    async def test_returns_workflow_list(self, mock_session, tenant_id):
        """Returns formatted list of workflows."""
        mock_wf = MagicMock()
        mock_wf.id = uuid4()
        mock_wf.name = "Phishing Triage"
        mock_wf.description = "Automated phishing investigation"

        with patch("analysi.services.workflow.WorkflowService") as MockService:
            MockService.return_value.list_workflows = AsyncMock(
                return_value=([mock_wf], {"total": 1, "skip": 0, "limit": 20})
            )
            result = await list_workflows_impl(mock_session, tenant_id)

        assert "Phishing Triage" in result
        assert "1 workflows" in result


class TestGetWorkflow:
    """Tests for get_workflow tool."""

    @pytest.mark.asyncio
    async def test_returns_workflow_details(self, mock_session, tenant_id):
        """Returns formatted workflow definition."""
        wf_id = str(uuid4())
        mock_workflow = {"name": "Test WF", "nodes": [], "edges": []}

        with patch("analysi.services.workflow.WorkflowService") as MockService:
            MockService.return_value.get_workflow = AsyncMock(
                return_value=mock_workflow
            )
            result = await get_workflow_impl(mock_session, tenant_id, wf_id)

        assert "Test WF" in result


class TestListTasks:
    """Tests for list_tasks tool."""

    @pytest.mark.asyncio
    async def test_returns_task_list(self, mock_session, tenant_id):
        """Returns formatted list of tasks."""
        comp = MagicMock()
        comp.id = uuid4()
        comp.name = "IP Enrichment"
        comp.cy_name = "ip_enrichment"
        comp.description = "Enrich IP addresses"
        comp.status = "enabled"
        comp.categories = ["enrichment"]
        mock_task = MagicMock()
        mock_task.component = comp
        mock_task.function = "enrichment"

        with patch("analysi.services.task.TaskService") as MockService:
            MockService.return_value.list_tasks = AsyncMock(
                return_value=([mock_task], {"total": 1, "skip": 0, "limit": 20})
            )
            result = await list_tasks_impl(mock_session, tenant_id)

        assert "IP Enrichment" in result
        assert "ip_enrichment" in result


class TestGetTask:
    """Tests for get_task tool."""

    @pytest.mark.asyncio
    async def test_get_by_cy_name(self, mock_session, tenant_id):
        """Falls back to cy_name lookup when UUID parse fails."""
        mock_task = MagicMock()
        mock_task.component.id = uuid4()
        mock_task.component.name = "IP Enrichment"
        mock_task.component.cy_name = "ip_enrichment"
        mock_task.component.description = "Enrich IPs"
        mock_task.component.status = "enabled"
        mock_task.component.categories = ["enrichment"]
        mock_task.function = "enrichment"
        mock_task.scope = "per_alert"

        with patch("analysi.services.task.TaskService") as MockService:
            MockService.return_value.get_task = AsyncMock(side_effect=ValueError)
            MockService.return_value.get_task_by_cy_name = AsyncMock(
                return_value=mock_task
            )
            result = await get_task_impl(mock_session, tenant_id, "ip_enrichment")

        assert "IP Enrichment" in result


class TestListIntegrations:
    """Tests for list_integrations tool."""

    @pytest.mark.asyncio
    async def test_returns_integration_list(self, mock_session, tenant_id):
        """Returns formatted list with health status."""
        mock_integ = MagicMock()
        mock_integ.integration_id = "splunk-es-1"
        mock_integ.name = "Splunk ES"
        mock_integ.integration_type = "splunk"
        mock_integ.enabled = True
        mock_integ.health = MagicMock()
        mock_integ.health.status = "healthy"
        mock_integ.health.message = "All checks passed"

        with patch(
            "analysi.services.integration_service.IntegrationService"
        ) as MockService:
            MockService.return_value.list_integrations = AsyncMock(
                return_value=[mock_integ]
            )
            result = await list_integrations_impl(mock_session, tenant_id)

        assert "Splunk ES" in result
        assert "healthy" in result


# --- Run listing tools ---


class TestListWorkflowRuns:
    """Tests for list_workflow_runs tool."""

    @pytest.mark.asyncio
    async def test_returns_workflow_runs(self, mock_session, tenant_id):
        """Returns formatted list of recent workflow runs."""
        from analysi.services.chat_tools import list_workflow_runs_impl

        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.workflow_id = uuid4()
        mock_run.workflow_name = "SQL Injection Analysis"
        mock_run.status = "completed"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.error_message = None

        with patch(
            "analysi.repositories.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            MockRepo.return_value.list_workflow_runs = AsyncMock(
                return_value=([mock_run], 1)
            )
            result = await list_workflow_runs_impl(mock_session, tenant_id)

        assert "SQL Injection Analysis" in result
        assert "completed" in result

    @pytest.mark.asyncio
    async def test_no_runs_found(self, mock_session, tenant_id):
        """Returns informative message when no runs exist."""
        from analysi.services.chat_tools import list_workflow_runs_impl

        with patch(
            "analysi.repositories.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            MockRepo.return_value.list_workflow_runs = AsyncMock(return_value=([], 0))
            result = await list_workflow_runs_impl(mock_session, tenant_id)

        assert "No workflow runs" in result


class TestListTaskRuns:
    """Tests for list_task_runs tool."""

    @pytest.mark.asyncio
    async def test_returns_task_runs(self, mock_session, tenant_id):
        """Returns formatted list of recent task runs."""
        from analysi.services.chat_tools import list_task_runs_impl

        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.task_id = uuid4()
        mock_run.task_name = "VirusTotal IP Check"
        mock_run.status = "completed"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.error_message = None
        mock_run.output_data = None

        with patch("analysi.services.task_run.TaskRunService") as MockService:
            MockService.return_value.list_task_runs = AsyncMock(
                return_value=([mock_run], 1)
            )
            result = await list_task_runs_impl(mock_session, tenant_id)

        assert "VirusTotal IP Check" in result
        assert "completed" in result


# --- Audit trail with role gating ---


class TestSearchAuditTrail:
    """Tests for search_audit_trail tool."""

    @pytest.mark.asyncio
    async def test_returns_audit_events(self, mock_session, tenant_id):
        """Returns formatted audit trail events."""
        mock_event = MagicMock()
        mock_event.created_at = MagicMock()
        mock_event.created_at.isoformat.return_value = "2026-03-19T10:00:00Z"
        mock_event.action = "task.create"
        mock_event.resource_type = "task"
        mock_event.resource_id = "abc-123"
        mock_event.actor_type = "user"

        with patch(
            "analysi.services.activity_audit_service.ActivityAuditService"
        ) as MockService:
            MockService.return_value.list_activities = AsyncMock(
                return_value=([mock_event], 1)
            )
            result = await search_audit_trail_impl(
                mock_session, tenant_id, action="task.create"
            )

        assert "task.create" in result
        assert "1 audit events" in result


# --- Meta tools ---


class TestGetPageContext:
    """Tests for get_page_context meta tool."""

    def test_with_context(self):
        """Returns structured page info."""
        result = get_page_context_impl({"route": "/alerts", "entity_type": "alerts"})
        assert "route" in result
        assert "/alerts" in result

    def test_without_context(self):
        """Returns informative message when no context."""
        result = get_page_context_impl(None)
        assert "No page context" in result


class TestSuggestNextSteps:
    """Tests for suggest_next_steps meta tool."""

    def test_alerts_page_suggestions(self):
        """Returns alert-specific suggestions for alerts page."""
        result = suggest_next_steps_impl({"route": "/alerts"})
        # Assert page-specific content (not in dashboard defaults)
        assert "high-severity" in result.lower()

    def test_workflows_page_suggestions(self):
        """Returns workflow-specific suggestions."""
        result = suggest_next_steps_impl({"route": "/workflows"})
        # Assert page-specific content (not in dashboard defaults)
        assert (
            "how do i create a new workflow" in result.lower()
            or "complexity" in result.lower()
        )

    def test_default_suggestions(self):
        """Returns default suggestions for unknown page."""
        result = suggest_next_steps_impl(None)
        assert "things you can ask" in result.lower()

    def test_detail_page_detection(self):
        """Detects detail pages from route pattern."""
        result = suggest_next_steps_impl({"route": "/alerts/abc-123"})
        assert "alert" in result.lower()

    def test_page_type_takes_precedence(self):
        """entity_type field takes precedence over route parsing."""
        result = suggest_next_steps_impl({"route": "/whatever", "entity_type": "admin"})
        assert "audit" in result.lower()


# --- Action tool tests ---


class TestCreateAlertImpl:
    """Tests for create_alert action tool."""

    @pytest.mark.asyncio
    async def test_creates_alert_with_defaults(self, mock_session, tenant_id):
        """Creates alert with auto-populated triggering_event_time and raw_alert.

        Uses a real AlertResponse (not MagicMock) to catch field name mismatches
        like .id vs .alert_id — MagicMock silently allows nonexistent attributes.
        """
        from datetime import UTC, datetime

        from analysi.schemas.alert import AlertResponse

        fake_id = uuid4()
        mock_alert = AlertResponse(
            alert_id=fake_id,
            tenant_id=tenant_id,
            human_readable_id="AID-TEST-1",
            title="Test Phishing Alert",
            severity="high",
            triggering_event_time=datetime.now(UTC),
            analysis_status="new",
            raw_data_hash="abc123",
            ingested_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            raw_alert="{}",
        )

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.create_alert = AsyncMock(return_value=mock_alert)

            from analysi.services.chat_action_tools import create_alert_impl

            result = await create_alert_impl(
                mock_session,
                tenant_id,
                title="Test Phishing Alert",
                severity="high",
                description="Exec targeting phishing campaign",
            )

        assert "Alert created successfully" in result
        assert "Test Phishing Alert" in result
        assert str(fake_id) in result, "Result should contain the alert_id"

        # Verify create_alert was called with proper schema
        call_args = MockService.return_value.create_alert.call_args
        alert_create = call_args[0][1]  # second positional arg
        assert alert_create.title == "Test Phishing Alert"
        assert alert_create.triggering_event_time is not None
        assert alert_create.raw_alert is not None

    @pytest.mark.asyncio
    async def test_creates_alert_without_description(self, mock_session, tenant_id):
        """Creates alert when optional description is omitted."""
        from datetime import UTC, datetime

        from analysi.schemas.alert import AlertResponse

        mock_alert = AlertResponse(
            alert_id=uuid4(),
            tenant_id=tenant_id,
            human_readable_id="AID-TEST-2",
            title="Quick Alert",
            severity="medium",
            triggering_event_time=datetime.now(UTC),
            analysis_status="new",
            raw_data_hash="def456",
            ingested_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            raw_alert="{}",
        )

        with patch("analysi.services.alert_service.AlertService") as MockService:
            MockService.return_value.create_alert = AsyncMock(return_value=mock_alert)

            from analysi.services.chat_action_tools import create_alert_impl

            result = await create_alert_impl(
                mock_session,
                tenant_id,
                title="Quick Alert",
            )

        assert "Alert created successfully" in result
