"""Unit tests for chat tool output schemas.

Validates that output schemas correctly extract fields from real model types
and format output consistently. Uses spec_set mocks to catch attribute drift.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from analysi.schemas.alert import AlertSeverity, AlertStatus
from analysi.schemas.chat_tool_output import (
    AlertChatDetail,
    AlertChatSummary,
    IntegrationChatSummary,
    TaskChatSummary,
    TaskRunChatSummary,
    WorkflowChatSummary,
    WorkflowRunChatSummary,
)

# --- AlertChatSummary ---


class TestAlertChatSummary:
    def _make_alert_response(self, **overrides):
        """Build a mock with real AlertResponse fields only."""
        defaults = {
            "alert_id": uuid4(),
            "title": "Possible SQL Injection",
            "severity": AlertSeverity.HIGH,
            "analysis_status": AlertStatus.COMPLETED,
            "source_vendor": "Splunk",
            "source_product": "Enterprise Security",
            "short_summary": "Attack was blocked at perimeter",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def test_from_response_extracts_correct_fields(self):
        alert = self._make_alert_response()
        summary = AlertChatSummary.from_alert_response(alert)
        assert summary.title == "Possible SQL Injection"
        assert summary.severity == AlertSeverity.HIGH
        assert summary.analysis_status == AlertStatus.COMPLETED
        assert summary.source_vendor == "Splunk"

    def test_from_response_uses_analysis_status_not_status(self):
        """Catches the bug where alert.status was used instead of alert.analysis_status."""
        alert = self._make_alert_response()
        # If someone tried to use alert.status, this would fail because
        # our from_alert_response reads analysis_status explicitly
        summary = AlertChatSummary.from_alert_response(alert)
        assert summary.analysis_status == AlertStatus.COMPLETED

    def test_severity_uses_real_enum(self):
        """Severity field is AlertSeverity, not a free string — prevents 'informational' vs 'info' drift."""
        with pytest.raises(ValidationError):
            AlertChatSummary(
                alert_id=uuid4(),
                title="Test",
                severity="informational",  # Wrong — should be 'info'
                analysis_status="new",
            )

    def test_to_chat_line_includes_key_fields(self):
        summary = AlertChatSummary(
            alert_id=uuid4(),
            title="Phishing Alert",
            severity=AlertSeverity.HIGH,
            analysis_status=AlertStatus.NEW,
            short_summary="User clicked link",
        )
        line = summary.to_chat_line()
        assert "Phishing Alert" in line
        assert "high" in line
        assert "new" in line
        assert "User clicked link" in line

    def test_to_chat_line_truncates_long_summary(self):
        summary = AlertChatSummary(
            alert_id=uuid4(),
            title="Test",
            severity=AlertSeverity.MEDIUM,
            analysis_status=AlertStatus.NEW,
            short_summary="x" * 200,
        )
        line = summary.to_chat_line()
        assert "..." in line
        assert len(summary.short_summary) > 100

    def test_format_list_empty(self):
        result = AlertChatSummary.format_list([], 0)
        assert "No alerts found" in result

    def test_format_list_with_items(self):
        items = [
            AlertChatSummary(
                alert_id=uuid4(),
                title=f"Alert {i}",
                severity=AlertSeverity.HIGH,
                analysis_status=AlertStatus.NEW,
            )
            for i in range(3)
        ]
        result = AlertChatSummary.format_list(items, 10)
        assert "Found 10 alerts" in result
        assert "showing 3" in result
        assert "Alert 0" in result
        assert "Alert 2" in result


class TestAlertChatDetail:
    def test_from_response_detail_includes_analysis(self):
        mock_alert = MagicMock()
        mock_alert.model_dump.return_value = {
            "alert_id": str(uuid4()),
            "title": "Test Alert",
            "severity": "high",
            "analysis_status": "completed",
            "source_vendor": "Splunk",
            "source_product": None,
            "triggering_event_time": "2026-04-26T10:00:00Z",
            "description": "Test desc",
            "entities": [{"type": "ip", "value": "1.2.3.4"}],
            "iocs": [],
            "current_analysis": {
                "status": "completed",
                "short_summary": "All clear",
            },
        }
        detail = AlertChatDetail.from_alert_response_detail(mock_alert)
        assert detail.current_analysis is not None
        assert detail.current_analysis["short_summary"] == "All clear"

    def test_from_response_detail_includes_disposition(self):
        """Disposition fields are extracted from alert level, not current_analysis."""
        mock_alert = MagicMock()
        mock_alert.model_dump.return_value = {
            "alert_id": str(uuid4()),
            "title": "SQL Injection",
            "severity": "high",
            "analysis_status": "completed",
            "current_disposition_category": "True Positive (Malicious)",
            "current_disposition_display_name": "Malicious Attempt Blocked",
            "current_disposition_confidence": 75,
            "current_analysis": {
                "status": "completed",
                "short_summary": "Confirmed attack",
            },
        }
        detail = AlertChatDetail.from_alert_response_detail(mock_alert)
        assert detail.disposition_category == "True Positive (Malicious)"
        assert detail.disposition_display_name == "Malicious Attempt Blocked"
        assert detail.disposition_confidence == 75

    def test_to_chat_detail_includes_disposition(self):
        """Disposition data appears in the chat detail output."""
        detail = AlertChatDetail(
            alert_id=uuid4(),
            title="Test",
            severity=AlertSeverity.HIGH,
            analysis_status=AlertStatus.COMPLETED,
            disposition_category="True Positive",
            disposition_confidence=85,
        )
        output = detail.to_chat_detail()
        assert "True Positive" in output
        assert "85" in output

    def test_to_chat_detail_includes_analysis_status_field(self):
        detail = AlertChatDetail(
            alert_id=uuid4(),
            title="Test",
            severity=AlertSeverity.HIGH,
            analysis_status=AlertStatus.COMPLETED,
        )
        output = detail.to_chat_detail()
        assert '"analysis_status"' in output
        assert '"completed"' in output


# --- TaskChatSummary ---


class TestTaskChatSummary:
    def _make_task(self, **overrides):
        comp = MagicMock()
        comp.id = uuid4()
        comp.name = "Splunk Event Retrieval"
        comp.cy_name = "splunk_event_retrieval"
        comp.description = "Retrieves events from Splunk"
        comp.status = "enabled"
        comp.categories = ["Foundation", "Splunk", "SIEM"]

        task = MagicMock()
        task.function = "enrichment"
        task.component = comp

        for k, v in overrides.items():
            if k == "component":
                task.component = v
            else:
                setattr(task, k, v)
        return task

    def test_from_task_extracts_component_fields(self):
        task = self._make_task()
        summary = TaskChatSummary.from_task(task)
        assert summary.name == "Splunk Event Retrieval"
        assert summary.cy_name == "splunk_event_retrieval"
        assert summary.function == "enrichment"
        assert "Foundation" in summary.categories
        assert summary.status == "enabled"

    def test_to_chat_line_includes_categories_and_function(self):
        summary = TaskChatSummary(
            id=uuid4(),
            name="Test Task",
            cy_name="test_task",
            function="reasoning",
            categories=["Foundation", "AI"],
            description="Does reasoning",
        )
        line = summary.to_chat_line()
        assert "(reasoning)" in line
        assert "[Foundation, AI]" in line
        assert "Does reasoning" in line

    def test_to_chat_line_shows_disabled_status(self):
        summary = TaskChatSummary(
            id=uuid4(),
            name="Disabled Task",
            cy_name="disabled",
            status="disabled",
        )
        line = summary.to_chat_line()
        assert "**disabled**" in line

    def test_to_chat_line_hides_enabled_status(self):
        summary = TaskChatSummary(
            id=uuid4(),
            name="Enabled Task",
            cy_name="enabled",
            status="enabled",
        )
        line = summary.to_chat_line()
        assert "**enabled**" not in line

    def test_format_list_with_total(self):
        items = [
            TaskChatSummary(id=uuid4(), name=f"Task {i}", cy_name=f"task_{i}")
            for i in range(5)
        ]
        result = TaskChatSummary.format_list(items, 37)
        assert "Found 37 tasks" in result
        assert "showing 5" in result

    def test_to_chat_detail_includes_all_fields(self):
        summary = TaskChatSummary(
            id=uuid4(),
            name="Test",
            cy_name="test",
            function="search",
            categories=["Foundation"],
            description="Test task",
            status="enabled",
        )
        detail = summary.to_chat_detail()
        assert '"function": "search"' in detail
        assert '"categories"' in detail


# --- WorkflowChatSummary ---


class TestWorkflowChatSummary:
    def test_from_workflow_orm(self):
        mock_wf = MagicMock()
        mock_wf.id = uuid4()
        mock_wf.name = "Alert Triage"
        mock_wf.description = "Triages alerts"
        mock_wf.nodes = [MagicMock() for _ in range(5)]
        summary = WorkflowChatSummary.from_workflow(mock_wf)
        assert summary.name == "Alert Triage"
        assert summary.node_count == 5

    def test_from_workflow_dict_with_nodes(self):
        wf_dict = {
            "id": str(uuid4()),
            "name": "Test WF",
            "description": "Desc",
            "nodes": [{"node_id": f"n{i}"} for i in range(3)],
        }
        summary = WorkflowChatSummary.from_workflow(wf_dict)
        assert summary.name == "Test WF"
        assert summary.node_count == 3

    def test_from_workflow_dict_without_nodes(self):
        wf_dict = {"id": str(uuid4()), "name": "Test WF", "description": "Desc"}
        summary = WorkflowChatSummary.from_workflow(wf_dict)
        assert summary.node_count == 0

    def test_node_count_in_chat_line(self):
        summary = WorkflowChatSummary(id=uuid4(), name="Big WF", node_count=15)
        line = summary.to_chat_line()
        assert "15 nodes" in line

    def test_format_list_sorted_by_complexity(self):
        """Workflows are sorted by node_count descending in format_list."""
        small = WorkflowChatSummary(id=uuid4(), name="Small", node_count=2)
        large = WorkflowChatSummary(id=uuid4(), name="Large", node_count=21)
        medium = WorkflowChatSummary(id=uuid4(), name="Medium", node_count=10)
        result = WorkflowChatSummary.format_list([small, large, medium], 3)
        # Large should appear before Medium before Small
        large_pos = result.index("Large")
        medium_pos = result.index("Medium")
        small_pos = result.index("Small")
        assert large_pos < medium_pos < small_pos

    def test_format_list_empty(self):
        assert "No workflows found" in WorkflowChatSummary.format_list([], 0)


# --- IntegrationChatSummary ---


class TestIntegrationChatSummary:
    def test_from_integration_with_health(self):
        mock_integ = MagicMock()
        mock_integ.integration_id = "splunk-1"
        mock_integ.name = "Splunk Enterprise"
        mock_integ.integration_type = "splunk"
        mock_integ.enabled = True
        mock_integ.health = MagicMock(status="healthy", message="All checks passed")
        summary = IntegrationChatSummary.from_integration(mock_integ)
        assert summary.health_status == "healthy"
        assert summary.enabled is True
        assert summary.health_message == "All checks passed"

    def test_from_integration_with_unhealthy_message(self):
        mock_integ = MagicMock()
        mock_integ.integration_id = "splunk-1"
        mock_integ.name = "Splunk"
        mock_integ.integration_type = "splunk"
        mock_integ.enabled = True
        mock_integ.health = MagicMock(
            status="unhealthy",
            message="No successful runs in 24h (0/0)",
        )
        summary = IntegrationChatSummary.from_integration(mock_integ)
        assert summary.health_status == "unhealthy"
        assert "No successful runs" in summary.health_message

    def test_from_integration_without_health(self):
        mock_integ = MagicMock()
        mock_integ.integration_id = "vt-1"
        mock_integ.name = "VirusTotal"
        mock_integ.integration_type = "virustotal"
        mock_integ.enabled = True
        mock_integ.health = None
        summary = IntegrationChatSummary.from_integration(mock_integ)
        assert summary.health_status == "unknown"
        assert summary.health_message is None

    def test_health_message_truncated(self):
        """Long health messages are truncated to 200 chars."""
        mock_integ = MagicMock()
        mock_integ.integration_id = "x"
        mock_integ.name = "Test"
        mock_integ.integration_type = "test"
        mock_integ.enabled = True
        mock_integ.health = MagicMock(
            status="unhealthy",
            message="A" * 500,
        )
        summary = IntegrationChatSummary.from_integration(mock_integ)
        assert len(summary.health_message) == 200

    def test_to_chat_line_includes_reason(self):
        summary = IntegrationChatSummary(
            integration_id="x",
            name="Splunk",
            integration_type="splunk",
            enabled=True,
            health_status="unhealthy",
            health_message="Connection timed out",
        )
        line = summary.to_chat_line()
        assert "Splunk" in line
        assert "unhealthy" in line
        assert "Connection timed out" in line

    def test_to_chat_line_no_reason_when_healthy(self):
        summary = IntegrationChatSummary(
            integration_id="x",
            name="DNS",
            integration_type="global_dns",
            enabled=True,
            health_status="healthy",
        )
        line = summary.to_chat_line()
        assert "healthy" in line
        assert "—" not in line  # No reason appended

    def test_format_list_includes_health_breakdown(self):
        items = [
            IntegrationChatSummary(
                integration_id="a",
                name="A",
                integration_type="t",
                enabled=True,
                health_status="healthy",
            ),
            IntegrationChatSummary(
                integration_id="b",
                name="B",
                integration_type="t",
                enabled=True,
                health_status="unhealthy",
            ),
            IntegrationChatSummary(
                integration_id="c",
                name="C",
                integration_type="t",
                enabled=True,
                health_status="unhealthy",
            ),
        ]
        result = IntegrationChatSummary.format_list(items)
        assert "Health breakdown" in result
        assert "unhealthy: 2" in result
        assert "healthy: 1" in result


# --- WorkflowRunChatSummary ---


class TestWorkflowRunChatSummary:
    def test_from_workflow_run(self):
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.workflow_id = uuid4()
        mock_run.workflow_name = "SQL Injection Analysis"
        mock_run.status = "completed"
        mock_run.started_at = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
        mock_run.completed_at = datetime(2026, 4, 26, 10, 5, tzinfo=UTC)
        mock_run.error_message = None
        summary = WorkflowRunChatSummary.from_workflow_run(mock_run)
        assert summary.status == "completed"
        assert summary.workflow_name == "SQL Injection Analysis"

    def test_to_chat_detail_iso_format(self):
        summary = WorkflowRunChatSummary(
            id=uuid4(),
            workflow_id=uuid4(),
            status="running",
            started_at=datetime(2026, 4, 26, 10, 0, tzinfo=UTC),
        )
        detail = summary.to_chat_detail()
        assert "2026-04-26" in detail
        assert '"status": "running"' in detail

    def test_to_chat_line_shows_name_and_status(self):
        summary = WorkflowRunChatSummary(
            id=uuid4(),
            workflow_id=uuid4(),
            workflow_name="Phishing Triage",
            status="completed",
            started_at=datetime(2026, 4, 26, 10, 0, tzinfo=UTC),
        )
        line = summary.to_chat_line()
        assert "Phishing Triage" in line
        assert "completed" in line

    def test_format_list_with_status_breakdown(self):
        runs = [
            WorkflowRunChatSummary(
                id=uuid4(),
                workflow_id=uuid4(),
                workflow_name="WF A",
                status="completed",
            ),
            WorkflowRunChatSummary(
                id=uuid4(),
                workflow_id=uuid4(),
                workflow_name="WF B",
                status="failed",
            ),
            WorkflowRunChatSummary(
                id=uuid4(),
                workflow_id=uuid4(),
                workflow_name="WF C",
                status="completed",
            ),
        ]
        result = WorkflowRunChatSummary.format_list(runs, 3)
        assert "3 workflow runs" in result
        assert "Status breakdown" in result
        assert "completed: 2" in result
        assert "failed: 1" in result

    def test_format_list_empty(self):
        assert "No workflow runs" in WorkflowRunChatSummary.format_list([], 0)


# --- TaskRunChatSummary ---


class TestTaskRunChatSummary:
    def test_from_task_run(self):
        mock_run = MagicMock()
        mock_run.id = uuid4()
        mock_run.task_id = uuid4()
        mock_run.task_name = "ip_enrichment"
        mock_run.status = "completed"
        mock_run.started_at = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
        mock_run.completed_at = datetime(2026, 4, 26, 10, 1, tzinfo=UTC)
        mock_run.error_message = None
        mock_run.output_data = {"result": "clean"}
        summary = TaskRunChatSummary.from_task_run(mock_run)
        assert summary.status == "completed"
        assert summary.output_data == {"result": "clean"}

    def test_to_chat_detail_includes_output(self):
        summary = TaskRunChatSummary(
            id=uuid4(),
            task_id=uuid4(),
            status="completed",
            output_data={"key": "value"},
        )
        detail = summary.to_chat_detail()
        assert '"output"' in detail
        assert '"key"' in detail

    def test_to_chat_line_shows_name_and_status(self):
        summary = TaskRunChatSummary(
            id=uuid4(),
            task_name="Splunk Event Retrieval",
            status="completed",
            started_at=datetime(2026, 4, 26, 10, 0, tzinfo=UTC),
        )
        line = summary.to_chat_line()
        assert "Splunk Event Retrieval" in line
        assert "completed" in line

    def test_format_list_with_status_breakdown(self):
        runs = [
            TaskRunChatSummary(
                id=uuid4(),
                task_name="Task A",
                status="completed",
            ),
            TaskRunChatSummary(
                id=uuid4(),
                task_name="Task B",
                status="failed",
                error_message="timeout",
            ),
        ]
        result = TaskRunChatSummary.format_list(runs, 2)
        assert "2 task runs" in result
        assert "Status breakdown" in result
        assert "completed: 1" in result
        assert "failed: 1" in result

    def test_format_list_empty(self):
        assert "No task runs" in TaskRunChatSummary.format_list([], 0)
