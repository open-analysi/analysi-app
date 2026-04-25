"""
Integration tests for Alert Analysis Pipeline.
Tests actual pipeline execution with real components.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.pipeline import AlertAnalysisPipeline


def create_mock_api_client():
    """Create a mock BackendAPIClient for testing."""
    mock_client = AsyncMock()
    mock_client.update_analysis_status = AsyncMock(return_value=True)
    mock_client.update_alert_analysis_status = AsyncMock(return_value=True)
    return mock_client


@pytest.mark.integration
@pytest.mark.asyncio
class TestAlertAnalysisPipelineIntegration:
    """Integration tests for the alert analysis pipeline."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tenant_id = "test-tenant"
        self.alert_id = str(uuid4())
        self.analysis_id = str(uuid4())
        self.pipeline = AlertAnalysisPipeline(
            tenant_id=self.tenant_id,
            alert_id=self.alert_id,
            analysis_id=self.analysis_id,
        )

    @pytest.mark.asyncio
    async def test_pipeline_with_no_alert(self):
        """Test pipeline completes with mocked alert data."""
        # Mock alert data for workflow builder step
        mock_alert_data = MagicMock()
        mock_alert_data.title = "Test Alert"
        mock_alert_data.rule_name = "test_rule"

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = mock_alert_data
        mock_db.update_analysis_status = AsyncMock()
        mock_db.get_step_progress.return_value = {}
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        # Mock BackendAPIClient for status updates (REST API only, no DB fallback)
        mock_api_client = create_mock_api_client()

        # Mock the steps to prevent network and database calls
        for step_name, step in self.pipeline.steps.items():
            # Mock WorkflowBuilderStep to avoid HTTP calls
            if step_name == "workflow_builder":
                step.execute = AsyncMock(return_value="test-workflow")
            if hasattr(step, "api_client"):
                step.api_client = MagicMock()
                step.api_client.get_workflow_by_name = AsyncMock(
                    return_value="workflow-123"
                )
                step.api_client.execute_workflow = AsyncMock(return_value="run-123")
                step.api_client.get_workflow_status = AsyncMock(
                    return_value="completed"
                )
                step.api_client.get_artifacts_by_workflow_run = AsyncMock(
                    return_value=[
                        {
                            "name": "Disposition",
                            "content": "Undetermined / Suspicious Activity",
                        }
                    ]
                )
                step.api_client.get_dispositions = AsyncMock(
                    return_value=[
                        {
                            "disposition_id": "disp-1",
                            "display_name": "Suspicious Activity",
                            "category": "Undetermined",
                            "subcategory": "",
                        }
                    ]
                )
            if hasattr(step, "_complete_analysis"):
                step._complete_analysis = AsyncMock()
            # Mock WorkflowExecutionStep — now uses direct DB calls, not REST
            if step_name == "workflow_execution":
                step.execute = AsyncMock(return_value="run-123")

        # Act - With mocked steps, API client, and alert data, pipeline completes
        with patch(
            "analysi.alert_analysis.clients.BackendAPIClient",
            return_value=mock_api_client,
        ):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                result = await self.pipeline.execute()

        # Assert - Pipeline completes with mocked alert data
        assert result["status"] == "completed"
