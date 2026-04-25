"""
Unit tests for Alert Analysis Pipeline Steps.
Tests each of the 4 steps in isolation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.alert_analysis.steps import (
    PreTriageStep,
    WorkflowBuilderStep,
    WorkflowExecutionStep,
)
from analysi.alert_analysis.steps.final_disposition_update import (
    FinalDispositionUpdateStep as DispositionMatchingStep,
)


@pytest.mark.asyncio
class TestPreTriageStep:
    """Test the Pre-Triage step (Step 1)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.step = PreTriageStep()
        self.tenant_id = "test-tenant"
        self.alert_id = "alert-123"
        self.analysis_id = "analysis-456"

    @pytest.mark.asyncio
    async def test_execute_returns_placeholder(self):
        """Test that execute returns placeholder data."""
        # Act
        result = await self.step.execute(
            self.tenant_id, self.alert_id, self.analysis_id
        )

        # Assert
        assert result is not None
        assert "priority" in result
        assert result["priority"] == "high"
        assert result["category"] == "malware"
        assert result["requires_immediate_action"] is True
        assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_execute_with_missing_data(self):
        """Test execute with missing alert data."""
        # Act - should still return placeholder
        result = await self.step.execute(
            self.tenant_id,
            None,
            self.analysis_id,  # Missing alert_id
        )

        # Assert - still returns placeholder
        assert result is not None
        assert result["priority"] == "high"
        assert result["category"] == "malware"

    @pytest.mark.asyncio
    async def test_execute_with_null_context(self):
        """Test execute with null context."""
        # Act
        result = await self.step.execute(
            self.tenant_id, self.alert_id, self.analysis_id, extra_context=None
        )

        # Assert
        assert result is not None
        assert result["priority"] == "high"
        assert result["category"] == "malware"


@pytest.mark.asyncio
class TestWorkflowBuilderStep:
    """
    Test the Workflow Builder step (Step 2).

    NOTE: Comprehensive tests for enhanced version in test_workflow_builder_step.py
    These tests verify basic initialization with mocked dependencies.
    """

    def setup_method(self):
        """Set up test fixtures with mocked dependencies."""
        from unittest.mock import AsyncMock

        mock_kea_client = AsyncMock()
        self.step = WorkflowBuilderStep(
            kea_client=mock_kea_client,
        )
        self.tenant_id = "test-tenant"
        self.alert_id = "alert-123"
        self.analysis_id = "analysis-456"

    @pytest.mark.asyncio
    async def test_execute_selects_workflow(self):
        """Test that execute returns workflow ID when cached."""
        # Arrange: Pre-populate cache
        self.step.cache.set_group(
            title="Test Rule",
            group_id="group-1",
            workflow_id="workflow-1",
            tenant_id=self.tenant_id,
        )
        alert_data = {"rule_name": "Test Rule"}

        # Act
        result = await self.step.execute(
            self.tenant_id, self.alert_id, self.analysis_id, alert_data=alert_data
        )

        # Assert
        assert result == "workflow-1"

    @pytest.mark.asyncio
    async def test_execute_with_unknown_alert_type(self):
        """Test workflow selection handles missing rule_name."""
        # Arrange: Alert missing rule_name
        alert_data = {"severity": "high"}  # Missing rule_name

        # Act & Assert
        with pytest.raises(ValueError, match="rule_name"):
            await self.step.execute(
                self.tenant_id, self.alert_id, self.analysis_id, alert_data=alert_data
            )

    @pytest.mark.asyncio
    async def test_get_alert_type_stub(self):
        """Test the _get_analysis_group_title helper method."""
        # Arrange
        alert_data = {"rule_name": "Test Alert Type"}

        # Act
        title = await self.step._get_analysis_group_title(alert_data)

        # Assert
        assert title == "Test Alert Type"  # Returns rule_name


@pytest.mark.asyncio
class TestWorkflowExecutionStep:
    """Test the Workflow Execution step (Step 4).

    WorkflowExecutionStep executes workflows directly via DB calls
    (no REST API). Tests mock WorkflowExecutor service methods.
    """

    def setup_method(self):
        """Set up test fixtures."""
        from uuid import uuid4

        self.step = WorkflowExecutionStep()
        self.tenant_id = "test-tenant"
        self.alert_id = "alert-123"
        self.analysis_id = "analysis-456"
        self.workflow_id = str(uuid4())
        self.workflow_run_id = uuid4()

    def _mock_execution_context(self):
        """Create patch context for direct DB execution."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Set up post-execution status check to return "completed"
        mock_status_row = MagicMock()
        mock_status_row.status = "completed"
        mock_status_row.error_message = None
        mock_status_result = MagicMock()
        mock_status_result.fetchone = MagicMock(return_value=mock_status_row)
        mock_session.execute = AsyncMock(return_value=mock_status_result)

        return (
            mock_session,
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
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        )

    @pytest.mark.asyncio
    async def test_execute_workflow_success(self):
        """Test successful workflow execution via direct service call."""
        self.step._prepare_workflow_input = AsyncMock(return_value={"test": "data"})
        _, p_session, p_init, p_create, p_exec = self._mock_execution_context()

        with p_session, p_init, p_create as mock_create, p_exec as mock_exec:
            result = await self.step.execute(
                self.tenant_id,
                self.alert_id,
                self.analysis_id,
                self.workflow_id,
            )

        assert result == str(self.workflow_run_id)
        mock_create.assert_called_once()
        mock_exec.assert_called_once_with(self.workflow_run_id)

    @pytest.mark.asyncio
    async def test_execute_workflow_error_propagates(self):
        """Test workflow execution failure propagates the error."""
        self.step._prepare_workflow_input = AsyncMock(return_value={"test": "data"})
        _, p_session, p_init, p_create, _ = self._mock_execution_context()

        with (
            p_session,
            p_init,
            p_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Workflow node failed"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Workflow node failed"):
                await self.step.execute(
                    self.tenant_id,
                    self.alert_id,
                    self.analysis_id,
                    self.workflow_id,
                )

    @pytest.mark.asyncio
    async def test_execute_uses_direct_db_not_rest(self):
        """Verify execution uses WorkflowExecutor service, not REST API."""
        from analysi.alert_analysis.steps import workflow_execution as mod

        assert not hasattr(mod, "BackendAPIClient"), (
            "WorkflowExecutionStep should not import BackendAPIClient"
        )


@pytest.mark.asyncio
class TestDispositionMatchingStep:
    """Test the Disposition Matching step (Step 5)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.step = DispositionMatchingStep()
        # Mock the API client to prevent network calls
        self.step.api_client = MagicMock()
        self.step.api_client.get_artifacts_by_workflow_run = AsyncMock(return_value=[])
        self.step.api_client.get_dispositions = AsyncMock(
            return_value=[
                {
                    "disposition_id": "disp-1",
                    "display_name": "Suspicious Activity",
                    "category": "Undetermined",
                    "subcategory": "",
                }
            ]
        )
        # Mock the database update
        self.step._complete_analysis = AsyncMock()
        self.tenant_id = "test-tenant"
        self.alert_id = "alert-123"
        self.analysis_id = "analysis-456"
        self.workflow_run_id = "run-123"

    @pytest.mark.asyncio
    async def test_execute_matches_disposition(self):
        """Test successful disposition matching."""
        # Setup mock artifacts with disposition
        self.step.api_client.get_artifacts_by_workflow_run = AsyncMock(
            return_value=[{"name": "Disposition", "content": "suspicious activity"}]
        )

        # Act
        result = await self.step.execute(
            self.tenant_id, self.alert_id, self.analysis_id, self.workflow_run_id
        )

        # Assert
        assert result is not None
        assert "disposition_id" in result
        assert "confidence" in result
        # Should match to "Suspicious Activity"
        assert result["disposition_id"] == "disp-1"
        assert result["confidence"] == 75

    @pytest.mark.asyncio
    async def test_execute_with_no_artifacts_completes_without_disposition(self):
        """Missing Disposition artifact should complete with warning, not crash."""
        self.step.api_client.get_artifacts_by_workflow_run = AsyncMock(return_value=[])
        self.step.api_client.get_dispositions = AsyncMock(return_value=[])

        with patch.object(self.step, "_complete_analysis", new=AsyncMock()):
            result = await self.step.execute(
                self.tenant_id, self.alert_id, self.analysis_id, self.workflow_run_id
            )

        assert result["status"] == "completed"
        assert result["disposition_id"] is None
        assert "warning" in result

    @pytest.mark.asyncio
    async def test_execute_with_artifacts(self):
        """Test disposition matching with workflow artifacts."""
        self.step.api_client.get_artifacts_by_workflow_run = AsyncMock(
            return_value=[
                {"name": "Analysis", "content": "test-data"},
                {
                    "name": "Disposition",
                    "content": "confirmed compromise",
                },
            ]
        )

        # Add a true positive disposition
        self.step.api_client.get_dispositions = AsyncMock(
            return_value=[
                {
                    "disposition_id": "disp-1",
                    "display_name": "Suspicious Activity",
                    "category": "Undetermined",
                    "subcategory": "",
                },
                {
                    "disposition_id": "disp-2",
                    "display_name": "Confirmed Compromise",
                    "category": "True Positive (Malicious)",
                    "subcategory": "Confirmed Compromise",
                },
            ]
        )

        result = await self.step.execute(
            self.tenant_id, self.alert_id, self.analysis_id, self.workflow_run_id
        )

        assert result is not None
        # "confirmed compromise" exactly matches "Confirmed Compromise" display_name
        assert result["disposition_id"] == "disp-2"
        assert result["disposition_name"] == "Confirmed Compromise"
