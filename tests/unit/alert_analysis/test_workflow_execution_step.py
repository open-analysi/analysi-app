"""
Unit tests for Workflow Execution Step.

Tests the WorkflowExecutionStep which executes workflows directly
in the worker process via DB calls (no REST API).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from analysi.alert_analysis.steps.workflow_execution import WorkflowExecutionStep


@pytest.mark.asyncio
class TestWorkflowExecutionStep:
    """Test the Workflow Execution step."""

    def setup_method(self):
        """Set up test fixtures."""
        self.step = WorkflowExecutionStep()
        self.tenant_id = "test-tenant"
        self.alert_id = "550e8400-e29b-41d4-a716-446655440000"
        self.analysis_id = "analysis-456"
        self.workflow_name = "Alert Analysis Workflow"
        self.workflow_id = "3e65cccd-608a-41a5-887d-c591335a45f2"
        self.workflow_run_id = uuid4()

    @patch("analysi.db.AsyncSessionLocal")
    @pytest.mark.asyncio
    async def test_prepare_workflow_input_success(self, mock_session_local):
        """Test preparing workflow input from alert data."""
        # Arrange
        mock_alert = MagicMock()
        mock_alert.id = UUID(self.alert_id)
        mock_alert.human_readable_id = "AID-1"
        mock_alert.title = "Suspicious Activity Detected"
        mock_alert.severity = "high"
        mock_alert.severity_id = 4
        mock_alert.source_vendor = "Microsoft"
        mock_alert.source_product = "Azure AD"
        mock_alert.rule_name = "multiple_failed_logins"
        mock_alert.triggering_event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_alert.raw_data = '{"event_count": 5}'
        mock_alert.raw_data_hash = "abc123"
        mock_alert.raw_data_hash_algorithm = "SHA-256"
        mock_alert.source_event_id = None
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        mock_alert.evidences = None
        mock_alert.observables = [{"type": "ip", "value": "192.168.1.100"}]
        mock_alert.osint = None
        mock_alert.actor = {"user": {"name": "alice@corp.example"}}
        mock_alert.device = None
        mock_alert.cloud = None
        mock_alert.vulnerabilities = None
        mock_alert.unmapped = None
        mock_alert.disposition_id = None
        mock_alert.verdict_id = None
        mock_alert.action_id = None
        mock_alert.status_id = 1
        mock_alert.confidence_id = None
        mock_alert.risk_level_id = None
        mock_alert.ocsf_time = None
        mock_alert.detected_at = None
        mock_alert.ingested_at = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.current_analysis_id = None
        mock_alert.analysis_status = "new"
        mock_alert.current_disposition_category = None
        mock_alert.current_disposition_subcategory = None
        mock_alert.current_disposition_display_name = None
        mock_alert.current_disposition_confidence = None
        mock_alert.created_at = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.updated_at = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.tenant_id = self.tenant_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Act
        result = await self.step._prepare_workflow_input(self.tenant_id, self.alert_id)

        # Assert
        assert result["id"] == self.alert_id
        assert result["human_readable_id"] == "AID-1"
        assert result["title"] == "Suspicious Activity Detected"
        assert result["severity"] == "high"
        assert result["observables"] == [{"type": "ip", "value": "192.168.1.100"}]
        assert result["triggering_event_time"] == "2024-01-15T10:30:00+00:00"

    @patch("analysi.db.AsyncSessionLocal")
    @pytest.mark.asyncio
    async def test_prepare_workflow_input_alert_not_found(self, mock_session_local):
        """Test preparing workflow input when alert not found."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await self.step._prepare_workflow_input(self.tenant_id, self.alert_id)

        assert f"Alert not found: {self.alert_id}" in str(exc_info.value)

    @staticmethod
    def _setup_status_check(mock_session, status="completed"):
        """Configure mock session for post-execution status check."""
        mock_status_row = MagicMock()
        mock_status_row.status = status
        mock_status_row.error_message = None
        mock_status_result = MagicMock()
        mock_status_result.fetchone = MagicMock(return_value=mock_status_row)
        mock_session.execute = AsyncMock(return_value=mock_status_result)

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful workflow execution via direct service call."""
        # Arrange
        self.step._prepare_workflow_input = AsyncMock(
            return_value={"alert_id": self.alert_id, "severity": "high"}
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=self.workflow_run_id,
            ) as mock_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ) as mock_exec_sync,
        ):
            result = await self.step.execute(
                self.tenant_id, self.alert_id, self.analysis_id, self.workflow_id
            )

        # Assert
        assert result == str(self.workflow_run_id)
        mock_create.assert_called_once()
        mock_exec_sync.assert_called_once_with(self.workflow_run_id)

    @pytest.mark.asyncio
    async def test_execute_no_rest_api_used(self):
        """Verify WorkflowExecutionStep does not import or use BackendAPIClient."""
        from analysi.alert_analysis.steps import workflow_execution as mod

        # The module should NOT import BackendAPIClient
        assert not hasattr(mod, "BackendAPIClient"), (
            "WorkflowExecutionStep should not import BackendAPIClient"
        )

    @pytest.mark.asyncio
    async def test_execute_should_accept_workflow_id_directly(self):
        """WorkflowExecutionStep accepts workflow_id as a UUID string directly."""
        workflow_uuid = "3e65cccd-608a-41a5-887d-c591335a45f2"
        run_id = uuid4()

        self.step._prepare_workflow_input = AsyncMock(
            return_value={"alert_id": self.alert_id, "severity": "high"}
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ) as mock_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            result = await self.step.execute(
                self.tenant_id,
                self.alert_id,
                self.analysis_id,
                workflow_id=workflow_uuid,
            )

        assert result == str(run_id)
        # UUID string should be converted to UUID object for create_workflow_run
        call_args = mock_create.call_args
        assert call_args[0][1] == UUID(workflow_uuid)

    @patch("analysi.db.AsyncSessionLocal")
    @pytest.mark.asyncio
    async def test_prepare_workflow_input_null_fields(self, mock_session_local):
        """Test preparing workflow input with null optional fields."""
        # Arrange
        mock_alert = MagicMock()
        mock_alert.id = UUID(self.alert_id)
        mock_alert.tenant_id = self.tenant_id
        mock_alert.human_readable_id = "AID-2"
        mock_alert.title = "Test Alert"
        mock_alert.severity = "low"
        mock_alert.severity_id = 2
        mock_alert.source_vendor = None
        mock_alert.source_product = None
        mock_alert.rule_name = None
        mock_alert.source_event_id = None
        mock_alert.triggering_event_time = None
        mock_alert.raw_data = None
        mock_alert.raw_data_hash = ""
        mock_alert.raw_data_hash_algorithm = "SHA-256"
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        mock_alert.evidences = None
        mock_alert.observables = None
        mock_alert.osint = None
        mock_alert.actor = None
        mock_alert.device = None
        mock_alert.cloud = None
        mock_alert.vulnerabilities = None
        mock_alert.unmapped = None
        mock_alert.disposition_id = None
        mock_alert.verdict_id = None
        mock_alert.action_id = None
        mock_alert.status_id = 1
        mock_alert.confidence_id = None
        mock_alert.risk_level_id = None
        mock_alert.ocsf_time = None
        mock_alert.detected_at = None
        mock_alert.ingested_at = None
        mock_alert.current_analysis_id = None
        mock_alert.analysis_status = "new"
        mock_alert.current_disposition_category = None
        mock_alert.current_disposition_subcategory = None
        mock_alert.current_disposition_display_name = None
        mock_alert.current_disposition_confidence = None
        mock_alert.created_at = None
        mock_alert.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Act
        result = await self.step._prepare_workflow_input(self.tenant_id, self.alert_id)

        # Assert
        assert result["id"] == self.alert_id
        assert result["human_readable_id"] == "AID-2"
        assert result["title"] == "Test Alert"
        assert result["severity"] == "low"
        assert result["source_vendor"] is None
        assert result["triggering_event_time"] is None
        assert result["raw_data"] is None

    @patch("analysi.db.AsyncSessionLocal")
    @pytest.mark.asyncio
    async def test_prepare_workflow_input_includes_all_alert_fields(
        self, mock_session_local
    ):
        """Test that _prepare_workflow_input serializes ALL alert columns.

        This test ensures we don't miss any fields that workflows may require.
        Uses OCSF schema fields (Project Skaros).
        """
        # Arrange - create mock alert with ALL expected OCSF fields
        mock_alert = MagicMock()
        mock_alert.id = UUID(self.alert_id)
        mock_alert.tenant_id = self.tenant_id
        mock_alert.human_readable_id = "AID-TEST"
        mock_alert.title = "Test Alert"
        mock_alert.triggering_event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_alert.source_vendor = "Splunk"
        mock_alert.source_product = "Enterprise Security"
        mock_alert.rule_name = "Test Rule"
        mock_alert.severity = "high"
        mock_alert.severity_id = 4
        mock_alert.source_event_id = "evt-123"
        mock_alert.finding_info = {"title": "Test Finding", "uid": "F-001"}
        mock_alert.ocsf_metadata = {"product": {"name": "ES"}}
        mock_alert.evidences = [{"data": "evidence1"}]
        mock_alert.observables = [{"type": "ip", "value": "192.168.1.100"}]
        mock_alert.osint = [{"source": "OTX"}]
        mock_alert.actor = {"user": {"name": "alice@corp.example"}}
        mock_alert.device = {"hostname": "workstation-1"}
        mock_alert.cloud = {"provider": "aws"}
        mock_alert.vulnerabilities = [{"cve_uid": "CVE-2024-0001"}]
        mock_alert.unmapped = {"custom_field": "value"}
        mock_alert.disposition_id = 1
        mock_alert.verdict_id = 2
        mock_alert.action_id = 1
        mock_alert.status_id = 1
        mock_alert.confidence_id = 3
        mock_alert.risk_level_id = 4
        mock_alert.ocsf_time = 1705312200000
        mock_alert.raw_data_hash = "abc123"
        mock_alert.raw_data_hash_algorithm = "SHA-256"
        mock_alert.detected_at = datetime(2024, 1, 15, 10, 29, 0, tzinfo=UTC)
        mock_alert.ingested_at = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.raw_data = '{"raw": "data"}'
        mock_alert.current_analysis_id = UUID("00000000-0000-0000-0000-000000000000")
        mock_alert.analysis_status = "in_progress"
        mock_alert.current_disposition_category = None
        mock_alert.current_disposition_subcategory = None
        mock_alert.current_disposition_display_name = None
        mock_alert.current_disposition_confidence = None
        mock_alert.created_at = datetime(2024, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.updated_at = datetime(2024, 1, 15, 10, 32, 0, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Act
        result = await self.step._prepare_workflow_input(self.tenant_id, self.alert_id)

        # Assert - verify OCSF JSONB fields are included
        assert "finding_info" in result, "finding_info must be included"
        assert result["finding_info"] == {"title": "Test Finding", "uid": "F-001"}

        assert "observables" in result, "observables must be included"
        assert result["observables"] == [{"type": "ip", "value": "192.168.1.100"}]

        assert "actor" in result, "actor must be included"
        assert result["actor"] == {"user": {"name": "alice@corp.example"}}

        assert "device" in result, "device must be included"
        assert result["device"] == {"hostname": "workstation-1"}

        assert "cloud" in result, "cloud must be included"
        assert result["cloud"] == {"provider": "aws"}

        # Assert - verify datetime serialization
        assert result["triggering_event_time"] == "2024-01-15T10:30:00+00:00"
        assert result["detected_at"] == "2024-01-15T10:29:00+00:00"

        # Assert - verify UUID serialization
        assert result["id"] == self.alert_id

        # Assert - internal fields should be excluded
        assert "current_analysis_id" not in result, (
            "current_analysis_id should be excluded"
        )

    @patch("analysi.db.AsyncSessionLocal")
    @pytest.mark.asyncio
    async def test_prepare_workflow_input_handles_none_jsonb_fields(
        self, mock_session_local
    ):
        """Test that _prepare_workflow_input handles None JSONB fields gracefully."""
        # Arrange
        mock_alert = MagicMock()
        mock_alert.id = UUID(self.alert_id)
        mock_alert.tenant_id = self.tenant_id
        mock_alert.human_readable_id = "AID-NONE"
        mock_alert.title = "Alert with None fields"
        mock_alert.triggering_event_time = datetime(2024, 1, 15, tzinfo=UTC)
        mock_alert.source_vendor = None
        mock_alert.source_product = None
        mock_alert.rule_name = None
        mock_alert.severity = "low"
        mock_alert.severity_id = 2
        mock_alert.source_event_id = None
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        mock_alert.evidences = None  # JSONB can be None
        mock_alert.observables = None
        mock_alert.osint = None
        mock_alert.actor = None
        mock_alert.device = None
        mock_alert.cloud = None
        mock_alert.vulnerabilities = None
        mock_alert.unmapped = None
        mock_alert.disposition_id = None
        mock_alert.verdict_id = None
        mock_alert.action_id = None
        mock_alert.status_id = 1
        mock_alert.confidence_id = None
        mock_alert.risk_level_id = None
        mock_alert.ocsf_time = None
        mock_alert.detected_at = None
        mock_alert.ingested_at = datetime(2024, 1, 15, tzinfo=UTC)
        mock_alert.raw_data = "{}"
        mock_alert.raw_data_hash = "hash123"
        mock_alert.raw_data_hash_algorithm = "SHA-256"
        mock_alert.current_analysis_id = None
        mock_alert.analysis_status = "new"
        mock_alert.current_disposition_category = None
        mock_alert.current_disposition_subcategory = None
        mock_alert.current_disposition_display_name = None
        mock_alert.current_disposition_confidence = None
        mock_alert.created_at = datetime(2024, 1, 15, tzinfo=UTC)
        mock_alert.updated_at = datetime(2024, 1, 15, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Act
        result = await self.step._prepare_workflow_input(self.tenant_id, self.alert_id)

        # Assert - None values should be preserved for OCSF JSONB fields
        assert result["observables"] is None
        assert result["actor"] is None
        assert result["device"] is None
        assert result["cloud"] is None

        # Should not raise any errors
