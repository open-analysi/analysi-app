"""
Unit tests for Alert Analysis Pipeline.
Tests 5-step pipeline orchestration and idempotency.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
from analysi.common.retry_config import WorkflowNotFoundError
from analysi.schemas.alert import AnalysisStatus


def create_mock_api_client():
    """Create a mock BackendAPIClient for testing."""
    mock_client = AsyncMock()
    mock_client.update_analysis_status = AsyncMock(return_value=True)
    mock_client.update_alert_analysis_status = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture(autouse=True)
def _mock_pipeline_http_clients():
    """Mock HTTP clients to prevent real network calls in unit tests.

    Pipeline._update_status() creates BackendAPIClient internally.
    Pipeline._update_step_progress_api() uses InternalAsyncClient directly.
    Both must be mocked to prevent connection errors without containers.
    """
    mock_api_client = create_mock_api_client()
    with (
        patch(
            "analysi.alert_analysis.clients.BackendAPIClient",
            return_value=mock_api_client,
        ),
        patch(
            "analysi.alert_analysis.pipeline.InternalAsyncClient",
        ) as mock_internal,
    ):
        mock_ctx = AsyncMock()
        mock_internal.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_internal.return_value.__aexit__ = AsyncMock(return_value=False)
        yield


@pytest.mark.asyncio
class TestAlertAnalysisPipeline:
    """Test the 5-step alert analysis pipeline."""

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
    async def test_pipeline_initialization(self):
        """Test pipeline initializes with correct parameters."""
        assert self.pipeline.tenant_id == self.tenant_id
        assert self.pipeline.alert_id == self.alert_id
        assert self.pipeline.analysis_id == self.analysis_id
        assert self.pipeline.db is None  # DB not initialized yet

    @pytest.mark.asyncio
    async def test_complete_pipeline_execution(self):
        """Test complete 5-step pipeline execution."""
        # Arrange
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {
            "alert_id": self.alert_id,
            "title": "Test Alert",
        }
        mock_db.get_analysis.return_value = {
            "id": self.analysis_id,
            "status": "pending",
        }
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()

        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        # Mock step execution
        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                with patch(
                    "analysi.alert_analysis.clients.BackendAPIClient",
                    return_value=mock_api_client,
                ):
                    mock_execute.return_value = {"result": "step_output"}

                    # Act
                    result = await self.pipeline.execute()

                    # Assert
                    assert result is not None
                    assert mock_execute.call_count == 4  # All 4 steps executed
                    mock_api_client.update_analysis_status.assert_called()

    @pytest.mark.asyncio
    async def test_idempotent_execution(self):
        """Test pipeline skips already completed steps."""
        # Arrange
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_analysis.return_value = {
            "id": self.analysis_id,
            "status": "running",
        }
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()

        self.pipeline.db = mock_db

        # Mock some steps as completed
        completed_steps = ["pre_triage"]

        async def is_completed_side_effect(step_name):
            return step_name in completed_steps

        with patch.object(
            self.pipeline, "_is_step_completed", side_effect=is_completed_side_effect
        ):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                mock_execute.return_value = {"result": "step_output"}

                # Act
                await self.pipeline.execute()

                # Assert - only 3 steps should be executed (4 - 1 completed)
                assert mock_execute.call_count == 3

    @pytest.mark.asyncio
    async def test_pipeline_failure_handling(self):
        """Test pipeline handles step failures correctly."""
        # Arrange
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_analysis.return_value = {
            "id": self.analysis_id,
            "status": "pending",
        }
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()

        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                with patch(
                    "analysi.alert_analysis.clients.BackendAPIClient",
                    return_value=mock_api_client,
                ):
                    # Fail on step 2
                    mock_execute.side_effect = [
                        {"result": "step1"},
                        Exception("Step 2 failed"),
                        {"result": "step3"},
                        {"result": "step4"},
                    ]

                    # Act & Assert
                    with pytest.raises(Exception) as exc_info:
                        await self.pipeline.execute()

                    assert str(exc_info.value) == "Step 2 failed"
                    assert mock_execute.call_count == 2  # Stopped at step 2
                    # Check that failed status was set via API with error message
                    status_calls = [
                        call
                        for call in mock_api_client.update_analysis_status.call_args_list
                        if call[0][2] == "failed"
                        and "Step 2 failed" in call[1].get("error", "")
                    ]
                    assert len(status_calls) > 0, (
                        "Expected 'failed' status call with error message"
                    )

    @pytest.mark.asyncio
    async def test_step_progress_tracking(self):
        """Test that step progress is tracked correctly."""
        # This test validates the _update_step_progress method
        mock_db = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        self.pipeline.db = mock_db

        # Mock the API call to avoid retry delays
        with patch.object(
            self.pipeline, "_update_step_progress_api", new_callable=AsyncMock
        ):
            # Act - use correct signature with status parameter
            await self.pipeline._update_step_progress("pre_triage", "completed")

            # Assert - API method should be called
            self.pipeline._update_step_progress_api.assert_called_once_with(
                "pre_triage", True, None
            )

    @pytest.mark.asyncio
    async def test_current_step_update(self):
        """Test that current step is updated during execution."""
        mock_db = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        # Act
        await self.pipeline._update_current_step("workflow_execution")

        # Assert
        mock_db.update_current_step.assert_called_once_with(
            self.analysis_id, "workflow_execution"
        )

    @pytest.mark.asyncio
    async def test_status_update(self):
        """Test that analysis status is updated correctly via API."""
        mock_db = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        # Act
        with patch(
            "analysi.alert_analysis.clients.BackendAPIClient",
            return_value=mock_api_client,
        ):
            await self.pipeline._update_status("completed")

        # Assert - API client should be called
        mock_api_client.update_analysis_status.assert_called_once_with(
            self.pipeline.tenant_id, self.pipeline.analysis_id, "completed", error=None
        )

    @pytest.mark.asyncio
    async def test_step_result_retrieval(self):
        """Test retrieving stored step results."""
        expected_result = {"output": "test_data"}

        mock_db = AsyncMock()
        mock_db.get_step_progress = AsyncMock(
            return_value={"pre_triage": {"completed": True, "result": expected_result}}
        )
        self.pipeline.db = mock_db

        # Act - use correct signature with field parameter
        result = await self.pipeline._get_step_result("pre_triage", "output")

        # Assert
        assert result == "test_data"
        mock_db.get_step_progress.assert_called_once_with(self.analysis_id)

    @pytest.mark.asyncio
    async def test_step_initialization(self):
        """Test that all steps are properly initialized."""
        # The steps are initialized in __init__, not during execute
        assert "pre_triage" in self.pipeline.steps
        assert "workflow_builder" in self.pipeline.steps
        assert "workflow_execution" in self.pipeline.steps
        assert "final_disposition_update" in self.pipeline.steps

        # Steps should be actual instances, not mocks
        from analysi.alert_analysis.steps import (
            DispositionMatchingStep,
            PreTriageStep,
            WorkflowBuilderStep,
            WorkflowExecutionStep,
        )

        assert isinstance(self.pipeline.steps["pre_triage"], PreTriageStep)
        assert isinstance(self.pipeline.steps["workflow_builder"], WorkflowBuilderStep)
        assert isinstance(
            self.pipeline.steps["workflow_execution"], WorkflowExecutionStep
        )
        assert isinstance(
            self.pipeline.steps["final_disposition_update"], DispositionMatchingStep
        )

    @pytest.mark.asyncio
    async def test_pipeline_with_no_alert(self):
        """Test pipeline completes with mocked alert data."""
        # Mock alert data for workflow builder step
        from unittest.mock import MagicMock

        mock_alert_data = MagicMock()
        mock_alert_data.title = "Test Alert"
        mock_alert_data.rule_name = "test_rule"

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = mock_alert_data
        mock_db.update_analysis_status = AsyncMock()
        mock_db.get_step_progress.return_value = {}
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        mock_db.get_analysis.return_value = {
            "id": self.analysis_id,
            "status": "pending",
        }
        self.pipeline.db = mock_db

        # Replace ALL step instances with mocks to avoid any real network calls
        mock_steps = {}
        for step_name in [
            "pre_triage",
            "workflow_builder",
            "workflow_execution",
            "final_disposition_update",
        ]:
            mock_step = AsyncMock()
            mock_step.execute = AsyncMock(
                return_value={"status": "success", "result": f"{step_name}_result"}
            )
            mock_steps[step_name] = mock_step

        self.pipeline.steps = mock_steps

        # Mock internal methods AND the API call method to prevent HTTP calls
        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                # Act - With fully mocked steps and alert data, pipeline completes
                result = await self.pipeline.execute()

                # Assert - Pipeline completes with mocked alert data
                assert result["status"] == "completed"
                # Verify all 5 steps were executed
                for _step_name, mock_step in self.pipeline.steps.items():
                    mock_step.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_with_no_analysis(self):
        """Test pipeline fails gracefully when analysis doesn't exist."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_analysis.return_value = None
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # The pipeline doesn't explicitly check for missing analysis
        # It will proceed with execution
        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                mock_execute.return_value = {"result": "test"}

                # Act - should still execute
                result = await self.pipeline.execute()

                # Assert - pipeline runs anyway
                assert result is not None

    @pytest.mark.asyncio
    async def test_pipeline_pauses_when_workflow_not_ready(self):
        """Test pipeline pauses when workflow generation is in progress.

        Verifies API status updates maintain decoupling.
        Pipeline should update status via API when workflow_builder returns None."""
        # Arrange
        from unittest.mock import MagicMock

        mock_alert_data = MagicMock()
        mock_alert_data.title = "Test Alert"
        mock_alert_data.rule_name = "test_rule"

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = mock_alert_data
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.get_step_progress.return_value = {}
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        # Mock the workflow_builder step to return None (workflow not ready)
        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        # First step succeeds, workflow_builder returns None
                        mock_execute.side_effect = [
                            {"result": "pre_triage_done"},
                            None,  # workflow_builder returns None (workflow not ready)
                        ]

                        # Act
                        result = await self.pipeline.execute()

                        # Assert - Pipeline paused, not completed
                        assert (
                            result["status"]
                            == AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value
                        )
                        assert "message" in result
                        assert "paused_at" in result
                        # Only 2 steps executed (pre_triage, workflow_builder)
                        assert mock_execute.call_count == 2

                        # Verify API status updates (decoupling maintained)
                        # Pipeline should update AlertAnalysis.status to paused via API
                        paused_value = AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value
                        status_calls = [
                            call
                            for call in mock_api_client.update_analysis_status.call_args_list
                            if call[0][2] == paused_value
                        ]
                        assert len(status_calls) > 0, (
                            f"Expected {paused_value} status call"
                        )

    @pytest.mark.asyncio
    async def test_dual_status_fields_design_decision(self):
        """Document the design: Alert.analysis_status vs AlertAnalysis.status.

        IMPORTANT DESIGN DECISION:
        - Alert.analysis_status: User-facing simplified status
          Values: 'new', 'in_progress', 'completed', 'failed', 'cancelled'
          Purpose: Display in UI, simple state for users

        - AlertAnalysis.status: Internal pipeline status
          Values: 'running', 'paused_workflow_building', 'completed', 'failed', 'cancelled'
          Purpose: Track internal pipeline state, reconciliation queries

        When workflow generation is in progress:
        - Alert.analysis_status = 'in_progress' (user sees "analyzing")
        - AlertAnalysis.status = 'paused_workflow_building' (reconciliation can find it)

        The reconciliation job queries AlertAnalysis.status, NOT Alert.analysis_status.
        This is why Alert.analysis_status must NOT be set to 'paused_workflow_building'.
        """
        # The allowed values for each table
        alert_allowed_statuses = {
            "new",
            "in_progress",
            "completed",
            "failed",
            "cancelled",
        }
        analysis_allowed_statuses = {
            "running",
            "paused",  # simplified from paused_workflow_building
            "completed",
            "failed",
            "cancelled",
        }

        # paused is ONLY allowed in AlertAnalysis, not Alert
        assert "paused" not in alert_allowed_statuses
        assert "paused" in analysis_allowed_statuses

        # Verify AnalysisStatus enum has PAUSED_WORKFLOW_BUILDING member with "paused" value
        assert hasattr(AnalysisStatus, "PAUSED_WORKFLOW_BUILDING")
        assert AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value == "paused"


@pytest.mark.asyncio
class TestPipelineWorkflowIdPropagation:
    """Test that workflow_id is passed from step 3 (workflow_execution) to step 4 (final_disposition_update).

    Bug: The pipeline passed workflow_run_id to step 4 but not workflow_id,
    leaving alert_analysis.workflow_id NULL after completion.
    """

    def setup_method(self):
        self.tenant_id = "test-tenant"
        self.alert_id = str(uuid4())
        self.analysis_id = str(uuid4())
        self.pipeline = AlertAnalysisPipeline(
            tenant_id=self.tenant_id,
            alert_id=self.alert_id,
            analysis_id=self.analysis_id,
        )

    @pytest.mark.asyncio
    async def test_pipeline_passes_workflow_id_to_step4(self):
        """Step 4 should receive both workflow_id and workflow_run_id."""
        workflow_id = str(uuid4())
        workflow_run_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id, "title": "Test"}
        mock_db.get_step_progress.return_value = {}
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        # Track what kwargs step 4 receives
        step4_kwargs = {}

        async def tracking_execute_step(step_name, **kwargs):
            if step_name == "final_disposition_update":
                step4_kwargs.update(kwargs)
            # Return appropriate values for each step
            if step_name == "pre_triage":
                return {"priority": "high"}
            if step_name == "workflow_builder":
                return workflow_id
            if step_name == "workflow_execution":
                return workflow_run_id
            if step_name == "final_disposition_update":
                return {"status": "completed"}
            return None

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_execute_step", side_effect=tracking_execute_step
            ):
                with patch.object(
                    self.pipeline, "_update_status", new_callable=AsyncMock
                ):
                    with patch.object(
                        self.pipeline,
                        "_execute_workflow_with_retry",
                        return_value=workflow_run_id,
                    ):
                        await self.pipeline.execute()

        assert "workflow_id" in step4_kwargs, (
            "Pipeline must pass workflow_id to final_disposition_update step"
        )
        assert step4_kwargs["workflow_id"] == workflow_id


@pytest.mark.asyncio
class TestPipelineAlertNotFound:
    """Test corner cases when alert data is missing or invalid."""

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
    async def test_alert_not_found_raises_value_error(self):
        """Test pipeline raises ValueError when alert doesn't exist in DB."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = None  # Alert not found
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        # First two steps succeed
                        mock_execute.side_effect = [
                            {"result": "pre_triage"},
                            {"result": "context"},
                        ]

                        with pytest.raises(ValueError) as exc_info:
                            await self.pipeline.execute()

                        assert f"Alert {self.alert_id} not found" in str(exc_info.value)
                        # Should have updated status to failed via API
                        status_calls = [
                            call
                            for call in mock_api_client.update_analysis_status.call_args_list
                            if call[0][2] == "failed"
                        ]
                        assert len(status_calls) > 0, "Expected 'failed' status call"

    @pytest.mark.asyncio
    async def test_alert_not_found_with_empty_dict(self):
        """Test pipeline handles empty alert dict (falsy) correctly.

        In Python, empty dict {} is falsy, so `if not alert_data` is True.
        This should also raise ValueError, same as None.
        """
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {}  # Empty dict is also falsy
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    # First two steps succeed
                    mock_execute.side_effect = [
                        {"result": "pre_triage"},
                        {"result": "context"},
                    ]

                    # Empty dict is falsy, so ValueError is raised
                    with pytest.raises(ValueError) as exc_info:
                        await self.pipeline.execute()

                    assert f"Alert {self.alert_id} not found" in str(exc_info.value)


@pytest.mark.asyncio
class TestPipelineStepResumption:
    """Test pipeline resumption from various completed states."""

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
    async def test_resume_from_workflow_builder_with_existing_workflow(self):
        """Test resuming when workflow_builder already completed with a workflow ID."""
        workflow_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
            "workflow_builder": {
                "completed": True,
                "result": {"selected_workflow": workflow_id},
            },
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        async def is_completed_side_effect(step_name):
            return step_name in ["pre_triage", "workflow_builder"]

        with patch.object(
            self.pipeline, "_is_step_completed", side_effect=is_completed_side_effect
        ):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    workflow_run_id = str(uuid4())
                    mock_execute.side_effect = [
                        workflow_run_id,  # workflow_execution
                        {"disposition": "benign"},  # final_disposition_update
                    ]

                    result = await self.pipeline.execute()

                    # Only 2 steps executed (workflow_execution, final_disposition_update)
                    assert mock_execute.call_count == 2
                    assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_resume_from_workflow_execution_with_existing_run_id(self):
        """Test resuming when workflow_execution already completed."""
        workflow_id = str(uuid4())
        workflow_run_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
            "workflow_builder": {
                "completed": True,
                "result": {"selected_workflow": workflow_id},
            },
            "workflow_execution": {
                "completed": True,
                "result": {"workflow_run_id": workflow_run_id},
            },
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        async def is_completed_side_effect(step_name):
            return step_name in ["pre_triage", "workflow_builder", "workflow_execution"]

        with patch.object(
            self.pipeline, "_is_step_completed", side_effect=is_completed_side_effect
        ):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    mock_execute.return_value = {"disposition": "benign"}

                    result = await self.pipeline.execute()

                    # Only 1 step executed (final_disposition_update)
                    assert mock_execute.call_count == 1
                    assert result["status"] == "completed"
                    assert result["workflow_run_id"] == workflow_run_id

    @pytest.mark.asyncio
    async def test_resume_all_steps_completed(self):
        """Test pipeline completes immediately when all steps already done."""
        workflow_run_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
            "workflow_builder": {
                "completed": True,
                "result": {"selected_workflow": "wf-123"},
            },
            "workflow_execution": {
                "completed": True,
                "result": {"workflow_run_id": workflow_run_id},
            },
            "final_disposition_update": {"completed": True},
        }
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # All steps completed
        with patch.object(self.pipeline, "_is_step_completed", return_value=True):
            with patch.object(self.pipeline, "_execute_step") as mock_execute:
                result = await self.pipeline.execute()

                # No steps should be executed
                mock_execute.assert_not_called()
                assert result["status"] == "completed"


@pytest.mark.asyncio
class TestPipelineIsStepCompletedEdgeCases:
    """Test _is_step_completed edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_is_step_completed_no_db(self):
        """Test _is_step_completed returns False when db is None."""
        self.pipeline.db = None
        result = await self.pipeline._is_step_completed("pre_triage")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_step_completed_db_exception(self):
        """Test _is_step_completed handles database exceptions gracefully."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.side_effect = Exception("DB connection failed")
        self.pipeline.db = mock_db

        # Should not raise, returns False
        result = await self.pipeline._is_step_completed("pre_triage")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_step_completed_step_not_in_progress(self):
        """Test _is_step_completed when step not yet tracked."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True}
            # workflow_builder not in dict
        }
        self.pipeline.db = mock_db

        result = await self.pipeline._is_step_completed("workflow_builder")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_step_completed_missing_completed_flag(self):
        """Test _is_step_completed when 'completed' key is missing."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"status": "started"}  # No 'completed' key
        }
        self.pipeline.db = mock_db

        result = await self.pipeline._is_step_completed("pre_triage")
        assert result is False


@pytest.mark.asyncio
class TestPipelineGetStepResultEdgeCases:
    """Test _get_step_result edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_get_step_result_no_db(self):
        """Test _get_step_result returns None when db is None."""
        self.pipeline.db = None
        result = await self.pipeline._get_step_result(
            "workflow_builder", "selected_workflow"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_step_result_db_exception(self):
        """Test _get_step_result handles database exceptions gracefully."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.side_effect = Exception("DB read failed")
        self.pipeline.db = mock_db

        result = await self.pipeline._get_step_result(
            "workflow_builder", "selected_workflow"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_step_result_step_not_in_progress(self):
        """Test _get_step_result when step not in progress dict."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {"pre_triage": {"completed": True}}
        self.pipeline.db = mock_db

        result = await self.pipeline._get_step_result(
            "workflow_builder", "selected_workflow"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_step_result_non_dict_result(self):
        """Test _get_step_result when result is not a dict (returns raw value)."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {
            "workflow_builder": {"completed": True, "result": "workflow-123"}
        }
        self.pipeline.db = mock_db

        result = await self.pipeline._get_step_result("workflow_builder", "anything")
        # When result is not a dict, returns the raw value
        assert result == "workflow-123"

    @pytest.mark.asyncio
    async def test_get_step_result_missing_result_key(self):
        """Test _get_step_result when result key doesn't exist in dict."""
        mock_db = AsyncMock()
        mock_db.get_step_progress.return_value = {
            "workflow_builder": {"completed": True, "result": {"other_key": "value"}}
        }
        self.pipeline.db = mock_db

        result = await self.pipeline._get_step_result(
            "workflow_builder", "selected_workflow"
        )
        assert result is None


@pytest.mark.asyncio
class TestPipelineUpdateStatusEdgeCases:
    """Test _update_status edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_update_status_no_db(self):
        """Test _update_status does nothing when db is None."""
        self.pipeline.db = None
        # Should not raise
        await self.pipeline._update_status("completed")

    @pytest.mark.asyncio
    async def test_update_status_with_error(self):
        """Test _update_status passes error message correctly via API."""
        mock_db = AsyncMock()
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        with patch(
            "analysi.alert_analysis.clients.BackendAPIClient",
            return_value=mock_api_client,
        ):
            await self.pipeline._update_status("failed", error="Something went wrong")

        # Assert - API client should be called with error
        mock_api_client.update_analysis_status.assert_called_once_with(
            self.pipeline.tenant_id,
            self.pipeline.analysis_id,
            "failed",
            error="Something went wrong",
        )


@pytest.mark.asyncio
class TestPipelineUpdateCurrentStepEdgeCases:
    """Test _update_current_step edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_update_current_step_none_step_name(self):
        """Test _update_current_step does nothing when step_name is None."""
        mock_db = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        self.pipeline.db = mock_db

        await self.pipeline._update_current_step(None)

        mock_db.update_current_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_current_step_no_db(self):
        """Test _update_current_step does nothing when db is None."""
        self.pipeline.db = None
        # Should not raise
        await self.pipeline._update_current_step("workflow_execution")


@pytest.mark.asyncio
class TestPipelineUpdateStepProgressEdgeCases:
    """Test _update_step_progress edge cases - REST API only, no DB fallback."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_update_step_progress_api_failure_raises_exception(self):
        """Test _update_step_progress raises exception when API fails (no DB fallback)."""
        mock_db = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        self.pipeline.db = mock_db

        with patch.object(
            self.pipeline,
            "_update_step_progress_api",
            side_effect=Exception("API unavailable"),
        ):
            # Should raise - no DB fallback
            with pytest.raises(Exception) as exc_info:
                await self.pipeline._update_step_progress(
                    "pre_triage", "completed", result={"data": "test"}
                )

            assert str(exc_info.value) == "API unavailable"
            # DB should NOT be called - no fallback
            mock_db.update_step_progress.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_step_progress_api_failure_no_db_raises(self):
        """Test _update_step_progress raises exception when API fails even without DB."""
        self.pipeline.db = None

        with patch.object(
            self.pipeline,
            "_update_step_progress_api",
            side_effect=Exception("API unavailable"),
        ):
            # Should raise - no fallback regardless of DB state
            with pytest.raises(Exception) as exc_info:
                await self.pipeline._update_step_progress("pre_triage", "completed")

            assert str(exc_info.value) == "API unavailable"

    @pytest.mark.asyncio
    async def test_update_step_progress_with_error(self):
        """Test _update_step_progress passes error correctly."""
        with patch.object(self.pipeline, "_update_step_progress_api") as mock_api:
            await self.pipeline._update_step_progress(
                "pre_triage", "failed", error="Step execution failed"
            )

            mock_api.assert_called_once_with(
                "pre_triage", False, "Step execution failed"
            )


class TestPipelineGetNextStep:
    """Test _get_next_step edge cases (sync tests - no asyncio marker needed)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    def test_get_next_step_first_step(self):
        """Test _get_next_step returns correct next step from first."""
        assert self.pipeline._get_next_step("pre_triage") == "workflow_builder"

    def test_get_next_step_middle_step(self):
        """Test _get_next_step returns correct next step from middle."""
        assert self.pipeline._get_next_step("workflow_builder") == "workflow_execution"

    def test_get_next_step_last_step(self):
        """Test _get_next_step returns None for last step."""
        assert self.pipeline._get_next_step("final_disposition_update") is None

    def test_get_next_step_invalid_step(self):
        """Test _get_next_step returns None for invalid step name."""
        assert self.pipeline._get_next_step("nonexistent_step") is None

    def test_get_next_step_all_transitions(self):
        """Test all valid step transitions."""
        expected_transitions = [
            ("pre_triage", "workflow_builder"),
            ("workflow_builder", "workflow_execution"),
            ("workflow_execution", "final_disposition_update"),
            ("final_disposition_update", None),
        ]

        for current, expected_next in expected_transitions:
            assert self.pipeline._get_next_step(current) == expected_next


@pytest.mark.asyncio
class TestPipelineExecuteStepEdgeCases:
    """Test _execute_step edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_execute_step_marks_failed_on_exception(self):
        """Test _execute_step marks step as failed when step raises exception."""
        mock_db = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        self.pipeline.db = mock_db

        # Mock step that raises
        mock_step = AsyncMock()
        mock_step.execute.side_effect = RuntimeError("Step crashed")
        self.pipeline.steps["pre_triage"] = mock_step

        with patch.object(self.pipeline, "_update_step_progress_api", new=AsyncMock()):
            with pytest.raises(RuntimeError):
                await self.pipeline._execute_step("pre_triage")

    @pytest.mark.asyncio
    async def test_execute_step_passes_kwargs_to_step(self):
        """Test _execute_step passes kwargs correctly to step.execute()."""
        mock_db = AsyncMock()
        self.pipeline.db = mock_db

        mock_step = AsyncMock()
        mock_step.execute.return_value = {"result": "success"}
        self.pipeline.steps["workflow_builder"] = mock_step

        with patch.object(self.pipeline, "_update_step_progress_api", new=AsyncMock()):
            with patch.object(self.pipeline, "_update_current_step", new=AsyncMock()):
                await self.pipeline._execute_step(
                    "workflow_builder",
                    alert_data={"title": "Test"},
                    extra_param="value",
                )

                mock_step.execute.assert_called_once_with(
                    tenant_id=self.pipeline.tenant_id,
                    alert_id=self.pipeline.alert_id,
                    analysis_id=self.pipeline.analysis_id,
                    alert_data={"title": "Test"},
                    extra_param="value",
                )


@pytest.mark.asyncio
class TestPipelineMultipleFailures:
    """Test pipeline behavior with multiple failure scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = AlertAnalysisPipeline(
            tenant_id="test-tenant",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_first_step_fails(self):
        """Test pipeline handles failure at first step correctly."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.pipeline.alert_id}
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    mock_execute.side_effect = Exception("First step failed")

                    with pytest.raises(Exception) as exc_info:
                        await self.pipeline.execute()

                    assert str(exc_info.value) == "First step failed"
                    assert mock_execute.call_count == 1

    @pytest.mark.asyncio
    async def test_last_step_fails(self):
        """Step 4 failure should fail the pipeline — no silent fallback disposition."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.pipeline.alert_id}
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        self.pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        mock_execute.side_effect = [
                            {"result": "step1"},
                            "workflow-123",  # workflow_builder returns ID
                            "run-456",  # workflow_execution
                            Exception("Final step failed"),
                        ]

                        with pytest.raises(Exception, match="Final step failed"):
                            await self.pipeline.execute()

    @pytest.mark.asyncio
    async def test_api_failure_causes_pipeline_failure(self):
        """Test pipeline fails when API calls fail (no DB fallback)."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.pipeline.alert_id}
        mock_db.get_step_progress.return_value = {}
        self.pipeline.db = mock_db

        # Mock API client to fail on status update
        mock_api_client = create_mock_api_client()
        mock_api_client.update_analysis_status.side_effect = Exception(
            "API unavailable"
        )

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch(
                "analysi.alert_analysis.clients.BackendAPIClient",
                return_value=mock_api_client,
            ):
                # Pipeline should fail because API status update fails
                with pytest.raises(Exception) as exc_info:
                    await self.pipeline.execute()

                assert str(exc_info.value) == "API unavailable"


@pytest.mark.asyncio
class TestPipelineWorkflowNotFoundRetry:
    """Test pipeline retry logic when workflow is not found (stale cache)."""

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
    async def test_retry_on_workflow_not_found(self):
        """Test pipeline retries with cache invalidation when workflow not found."""
        stale_workflow_id = str(uuid4())
        fresh_workflow_id = str(uuid4())
        workflow_run_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {
            "alert_id": self.alert_id,
            "title": "Test Alert",
        }
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        mock_db.clear_step_completion = AsyncMock()
        self.pipeline.db = mock_db

        # Track call count for workflow_builder
        workflow_builder_calls = []

        async def mock_execute_step(step_name, **kwargs):
            if step_name == "pre_triage":
                return {"result": "done"}
            if step_name == "workflow_builder":
                workflow_builder_calls.append(kwargs)
                # First call returns stale ID, second call returns fresh ID
                if len(workflow_builder_calls) == 1:
                    return stale_workflow_id
                return fresh_workflow_id
            if step_name == "workflow_execution":
                workflow_id = kwargs.get("workflow_id")
                if workflow_id == stale_workflow_id:
                    raise WorkflowNotFoundError(workflow_id)
                return workflow_run_id
            if step_name == "final_disposition_update":
                return {"disposition": "benign"}
            return None

        # Mock the workflow_builder step's invalidate_cache method
        mock_invalidate = AsyncMock()
        self.pipeline.steps["workflow_builder"].invalidate_cache = mock_invalidate

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(
                    self.pipeline, "_execute_step", side_effect=mock_execute_step
                ):
                    result = await self.pipeline.execute()

        # Assert
        assert result["status"] == "completed"
        # workflow_builder should be called twice (once stale, once fresh)
        assert len(workflow_builder_calls) == 2
        # Cache should be invalidated
        mock_invalidate.assert_called_once()
        # Step completion should be cleared for retry
        mock_db.clear_step_completion.assert_called_with(
            self.analysis_id, "workflow_builder"
        )

    @pytest.mark.asyncio
    async def test_retry_fails_if_workflow_still_not_found(self):
        """Test pipeline fails if workflow still not found after retry."""
        stale_workflow_id = str(uuid4())
        another_stale_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {
            "alert_id": self.alert_id,
            "title": "Test Alert",
        }
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        mock_db.clear_step_completion = AsyncMock()
        self.pipeline.db = mock_db

        workflow_builder_calls = []

        async def mock_execute_step(step_name, **kwargs):
            if step_name == "pre_triage":
                return {"result": "done"}
            if step_name == "workflow_builder":
                workflow_builder_calls.append(kwargs)
                if len(workflow_builder_calls) == 1:
                    return stale_workflow_id
                return another_stale_id
            if step_name == "workflow_execution":
                workflow_id = kwargs.get("workflow_id")
                # Both workflow IDs are stale
                raise WorkflowNotFoundError(workflow_id)
            if step_name == "final_disposition_update":
                return {"disposition": "benign"}
            return None

        mock_invalidate = AsyncMock()
        self.pipeline.steps["workflow_builder"].invalidate_cache = mock_invalidate

        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(
                    self.pipeline, "_execute_step", side_effect=mock_execute_step
                ):
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        with pytest.raises(WorkflowNotFoundError):
                            await self.pipeline.execute()

        # Should have tried once, then retried once
        assert len(workflow_builder_calls) == 2

    @pytest.mark.asyncio
    async def test_retry_handles_workflow_generation_triggered(self):
        """Test pipeline pauses when retry triggers new workflow generation."""
        stale_workflow_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {
            "alert_id": self.alert_id,
            "title": "Test Alert",
        }
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        mock_db.clear_step_completion = AsyncMock()
        self.pipeline.db = mock_db

        workflow_builder_calls = []

        async def mock_execute_step(step_name, **kwargs):
            if step_name == "pre_triage":
                return {"result": "done"}
            if step_name == "workflow_builder":
                workflow_builder_calls.append(kwargs)
                if len(workflow_builder_calls) == 1:
                    return stale_workflow_id
                # Second call triggers new workflow generation (returns None)
                return None
            if step_name == "workflow_execution":
                raise WorkflowNotFoundError(stale_workflow_id)
            if step_name == "final_disposition_update":
                return {"disposition": "benign"}
            return None

        mock_invalidate = AsyncMock()
        self.pipeline.steps["workflow_builder"].invalidate_cache = mock_invalidate

        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(
                    self.pipeline, "_execute_step", side_effect=mock_execute_step
                ):
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        # Pipeline should pause (return None) when workflow generation is triggered
                        await self.pipeline.execute()

        # Workflow builder should have been called twice (initial + retry)
        assert len(workflow_builder_calls) == 2
        # Cache should have been invalidated
        mock_invalidate.assert_called_once()


@pytest.mark.asyncio
class TestPipelineStep4Failure:
    """Step 4 failure should fail the pipeline — no silent fallback.

    The disposition must come from the actual analysis (workflow tasks),
    not from an arbitrary fallback code path.
    """

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
    async def test_step4_failure_fails_the_pipeline(self):
        """Steps 1-3 succeed, Step 4 raises. Pipeline should fail (not silently complete)."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_step_progress.return_value = {}
        self.pipeline.db = mock_db

        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        mock_execute.side_effect = [
                            {"result": "pre_triage_done"},
                            "workflow-123",
                            str(uuid4()),
                            Exception("Disposition API down"),
                        ]

                        with pytest.raises(Exception, match="Disposition API down"):
                            await self.pipeline.execute()

    @pytest.mark.asyncio
    async def test_step4_failure_marks_analysis_as_failed(self):
        """When Step 4 fails, analysis status should be 'failed', not 'completed'."""
        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": self.alert_id}
        mock_db.get_step_progress.return_value = {}
        self.pipeline.db = mock_db

        mock_api_client = create_mock_api_client()

        with patch.object(self.pipeline, "_is_step_completed", return_value=False):
            with patch.object(
                self.pipeline, "_update_step_progress_api", new=AsyncMock()
            ):
                with patch.object(self.pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        mock_execute.side_effect = [
                            {"result": "pre_triage_done"},
                            "workflow-123",
                            str(uuid4()),
                            Exception("Disposition API down"),
                        ]

                        with pytest.raises(Exception, match="Disposition API down"):
                            await self.pipeline.execute()

                        # Should have called update_analysis_status with "failed"
                        failed_calls = [
                            call
                            for call in mock_api_client.update_analysis_status.call_args_list
                            if call[0][2] == "failed"
                        ]
                        assert len(failed_calls) > 0, (
                            "Analysis should be marked 'failed' when Step 4 fails. "
                            f"Status calls: {mock_api_client.update_analysis_status.call_args_list}"
                        )


@pytest.mark.unit
class TestWorkflowNotFoundError:
    """Test WorkflowNotFoundError exception."""

    def test_exception_stores_workflow_id(self):
        """Test exception stores workflow_id correctly."""
        workflow_id = "test-workflow-123"
        error = WorkflowNotFoundError(workflow_id)

        assert error.workflow_id == workflow_id
        assert "test-workflow-123" in str(error)

    def test_exception_with_custom_message(self):
        """Test exception with custom message."""
        workflow_id = "test-workflow-123"
        custom_msg = "Custom error message"
        error = WorkflowNotFoundError(workflow_id, message=custom_msg)

        assert error.workflow_id == workflow_id
        assert str(error) == custom_msg

    def test_exception_default_message(self):
        """Test exception default message format."""
        workflow_id = "abc-123"
        error = WorkflowNotFoundError(workflow_id)

        assert str(error) == f"Workflow {workflow_id} not found"


@pytest.mark.unit
class TestAnalysisGroupCacheInvalidation:
    """Test AnalysisGroupCache invalidation."""

    def test_cache_clear(self):
        """Test cache.clear() removes all entries."""
        from analysi.alert_analysis.steps.workflow_builder import AnalysisGroupCache

        cache = AnalysisGroupCache()

        # Add some entries (tenant-scoped)
        cache.set_group("title1", "group-1", "workflow-1", tenant_id="t")
        cache.set_group("title2", "group-2", "workflow-2", tenant_id="t")

        # Verify entries exist
        assert cache.get_group_id("title1", tenant_id="t") == "group-1"
        assert cache.get_workflow_id("group-1") == "workflow-1"

        # Clear the cache
        cache.clear()

        # Verify entries are gone
        assert cache.get_group_id("title1", tenant_id="t") is None
        assert cache.get_workflow_id("group-1") is None
        assert cache.get_group_id("title2", tenant_id="t") is None
        assert cache.get_workflow_id("group-2") is None

    def test_workflow_builder_step_invalidate_cache(self):
        """Test WorkflowBuilderStep.invalidate_cache() clears the cache."""
        from analysi.alert_analysis.steps.workflow_builder import (
            AnalysisGroupCache,
            WorkflowBuilderStep,
        )

        cache = AnalysisGroupCache()
        cache.set_group("test-title", "group-1", "workflow-1", tenant_id="t")

        # Create step with this cache
        step = WorkflowBuilderStep(
            kea_client=AsyncMock(),
            cache=cache,
        )

        # Verify cache has entries
        assert cache.get_workflow_id("group-1") == "workflow-1"

        # Invalidate via step
        step.invalidate_cache()

        # Verify cache is cleared
        assert cache.get_workflow_id("group-1") is None
