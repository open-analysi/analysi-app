"""Unit tests for Enhanced Workflow Builder Step."""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.alert_analysis.steps.workflow_builder import (
    AnalysisGroupCache,
    WorkflowBuilderStep,
)


class TestWorkflowBuilderStepEnhanced:
    """Test enhanced workflow builder with Kea integration."""

    @pytest.fixture
    def mock_kea_client(self):
        """Mock Kea Coordination client."""
        return AsyncMock()

    @pytest.fixture
    def cache(self):
        """Fresh cache instance."""
        return AnalysisGroupCache()

    @pytest.fixture
    def workflow_step(self, mock_kea_client, cache):
        """Workflow builder step with mocked dependencies."""
        return WorkflowBuilderStep(kea_client=mock_kea_client, cache=cache)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_workflow_immediately(
        self, workflow_step, cache, mock_kea_client
    ):
        """Test that cache hit returns workflow without API call."""
        # Arrange: Pre-populate cache (tenant-scoped)
        cache.set_group(
            title="Suspicious Login",
            group_id="group-123",
            workflow_id="workflow-456",
            tenant_id="default",
        )

        alert_data = {"rule_name": "Suspicious Login", "severity": "high"}

        # Act
        result = await workflow_step.execute(
            tenant_id="default",
            alert_id="alert-1",
            analysis_id="analysis-1",
            alert_data=alert_data,
        )

        # Assert
        assert result == "workflow-456"
        # Should NOT call Kea API
        mock_kea_client.create_group_with_generation.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_api_and_caches_result(
        self, workflow_step, cache, mock_kea_client
    ):
        """Test cache miss triggers API call and caches result."""
        # Arrange
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "group-789", "title": "New Alert Type"},
            "workflow_generation": {
                "id": "gen-999",
                "status": "completed",
                "workflow_id": "workflow-abc",
            },
        }

        alert_data = {"rule_name": "New Alert Type", "severity": "critical"}

        # Act
        result = await workflow_step.execute(
            tenant_id="default",
            alert_id="alert-2",
            analysis_id="analysis-2",
            alert_data=alert_data,
        )

        # Assert
        assert result == "workflow-abc"

        # Verify API was called with analysis_id passed through
        mock_kea_client.create_group_with_generation.assert_called_once_with(
            tenant_id="default",
            title="New Alert Type",
            triggering_alert_analysis_id="analysis-2",
        )

        # Verify result cached (tenant-scoped)
        assert cache.get_group_id("New Alert Type", tenant_id="default") == "group-789"
        assert cache.get_workflow_id("group-789") == "workflow-abc"

    @pytest.mark.asyncio
    async def test_new_group_triggers_generation_and_returns_none(
        self, workflow_step, mock_kea_client
    ):
        """Test that new group without workflow triggers generation and signals pause.

        Step returns None to signal pause. Pipeline handles database updates
        (maintains decoupling). Only the triggering alert (whose analysis_id
        matches triggering_alert_analysis_id) should enqueue the workflow
        generation job.
        """
        # Arrange: API returns group with no workflow yet
        # The triggering_alert_analysis_id matches our analysis_id, so we should trigger
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "group-new", "title": "Brand New Rule"},
            "workflow_generation": {
                "id": "gen-new",
                "status": "running",
                "workflow_id": None,  # No workflow yet!
                "triggering_alert_analysis_id": "analysis-3",  # Matches our analysis_id
            },
        }

        alert_data = {"rule_name": "Brand New Rule", "severity": "high"}

        # Mock the workflow generation trigger
        with patch.object(
            workflow_step, "_trigger_workflow_generation", new=AsyncMock()
        ) as mock_trigger:
            # Act
            result = await workflow_step.execute(
                tenant_id="default",
                alert_id="alert-3",
                analysis_id="analysis-3",
                alert_data=alert_data,
            )

            # Assert
            assert (
                result is None
            )  # Signal to pipeline: workflow not ready, pause needed

            # Verify generation was triggered (this alert created the generation)
            mock_trigger.assert_called_once_with(
                tenant_id="default",
                generation_id="gen-new",
                alert_data=alert_data,
            )

    @pytest.mark.asyncio
    async def test_second_alert_skips_generation_trigger(
        self, workflow_step, mock_kea_client
    ):
        """Test that second alert does NOT trigger generation (another alert already did).

        When multiple alerts arrive for the same rule_name, only the first one
        (whose analysis_id matches triggering_alert_analysis_id) should enqueue
        the workflow generation job. Subsequent alerts should just wait.
        """
        # Arrange: API returns existing generation created by another alert
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "group-existing", "title": "Shared Rule"},
            "workflow_generation": {
                "id": "gen-existing",
                "status": "running",
                "workflow_id": None,  # No workflow yet
                "triggering_alert_analysis_id": "analysis-first",  # Different from ours!
            },
        }

        alert_data = {"rule_name": "Shared Rule", "severity": "high"}

        # Mock the workflow generation trigger
        with patch.object(
            workflow_step, "_trigger_workflow_generation", new=AsyncMock()
        ) as mock_trigger:
            # Act: Second alert arrives
            result = await workflow_step.execute(
                tenant_id="default",
                alert_id="alert-second",
                analysis_id="analysis-second",  # Different from triggering_alert_analysis_id
                alert_data=alert_data,
            )

            # Assert
            assert result is None  # Still pauses

            # Verify generation was NOT triggered (another alert already did)
            mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_resumed_alert_after_failed_generation_triggers_new_generation(
        self, workflow_step, mock_kea_client
    ):
        """Test that resumed alert after failed generation creates NEW generation and triggers job.

        Flow:
        1. First alert creates generation (triggers job)
        2. Generation FAILS (is_active=False, no routing rule)
        3. Reconciliation resumes the alert
        4. Resumed alert calls create_group_with_generation again
        5. API returns NEW generation (because old one is inactive)
        6. Resumed alert's analysis_id matches new triggering_alert_analysis_id
        7. Resumed alert triggers a NEW job

        This ensures failed generations can be retried.
        """
        rule_name = "Retry After Failure"
        group_id = "group-retry"
        resumed_analysis_id = "analysis-resumed"

        # API returns NEW generation (old one failed and is_active=False)
        # The NEW generation has triggering_alert_analysis_id = resumed alert's analysis_id
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": group_id, "title": rule_name},
            "workflow_generation": {
                "id": "gen-new-after-failure",
                "status": "running",
                "workflow_id": None,  # No workflow yet
                # NEW generation created for this resumed alert
                "triggering_alert_analysis_id": resumed_analysis_id,
            },
        }

        alert_data = {"rule_name": rule_name, "severity": "high"}

        # Mock the workflow generation trigger
        with patch.object(
            workflow_step, "_trigger_workflow_generation", new=AsyncMock()
        ) as mock_trigger:
            # Act: Resumed alert arrives
            result = await workflow_step.execute(
                tenant_id="default",
                alert_id="alert-resumed",
                analysis_id=resumed_analysis_id,  # Matches new triggering_alert_analysis_id
                alert_data=alert_data,
            )

            # Assert
            assert result is None  # Still needs to pause for new generation

            # Verify NEW generation was triggered (resumed alert owns it)
            mock_trigger.assert_called_once_with(
                tenant_id="default",
                generation_id="gen-new-after-failure",
                alert_data=alert_data,
            )

    @pytest.mark.asyncio
    async def test_race_condition_workflow_exists_after_all(
        self, workflow_step, cache, mock_kea_client
    ):
        """Test race condition: workflow created by another worker before our call."""
        # Arrange: Cache miss, but API returns existing workflow
        # (another worker created it just before us)
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "group-race", "title": "Concurrent Alert"},
            "workflow_generation": {
                "id": "gen-race",
                "status": "completed",
                "workflow_id": "workflow-race",  # Already completed!
            },
        }

        alert_data = {"rule_name": "Concurrent Alert", "severity": "medium"}

        # Act
        result = await workflow_step.execute(
            tenant_id="default",
            alert_id="alert-4",
            analysis_id="analysis-4",
            alert_data=alert_data,
        )

        # Assert
        assert result == "workflow-race"  # Got the workflow!

        # Verify cached
        assert cache.get_workflow_id("group-race") == "workflow-race"

    @pytest.mark.asyncio
    async def test_missing_rule_name_raises_error(self, workflow_step):
        """Test that alert without rule_name raises ValueError."""
        # Arrange
        alert_data = {"severity": "high"}  # Missing rule_name!

        # Act & Assert
        with pytest.raises(ValueError, match="rule_name"):
            await workflow_step.execute(
                tenant_id="default",
                alert_id="alert-5",
                analysis_id="analysis-5",
                alert_data=alert_data,
            )

    @pytest.mark.asyncio
    async def test_api_error_propagates(self, workflow_step, mock_kea_client):
        """Test that API errors are propagated."""
        # Arrange
        mock_kea_client.create_group_with_generation.side_effect = Exception(
            "API unavailable"
        )

        alert_data = {"rule_name": "Test Rule", "severity": "low"}

        # Act & Assert
        with pytest.raises(Exception, match="API unavailable"):
            await workflow_step.execute(
                tenant_id="default",
                alert_id="alert-6",
                analysis_id="analysis-6",
                alert_data=alert_data,
            )

    @pytest.mark.asyncio
    async def test_get_analysis_group_title_extracts_rule_name(self, workflow_step):
        """Test helper method extracts rule_name from alert."""
        # Arrange
        alert_data = {"rule_name": "Malware Detected", "severity": "critical"}

        # Act
        title = await workflow_step._get_analysis_group_title(alert_data)

        # Assert
        assert title == "Malware Detected"

    @pytest.mark.asyncio
    async def test_multiple_alerts_same_group_use_cache(
        self, workflow_step, cache, mock_kea_client
    ):
        """Test that second alert with same rule_name hits cache."""
        # Arrange: First alert populates cache
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "group-shared", "title": "Phishing Email"},
            "workflow_generation": {
                "id": "gen-shared",
                "status": "completed",
                "workflow_id": "workflow-phishing",
            },
        }

        alert_data_1 = {"rule_name": "Phishing Email", "severity": "high"}
        alert_data_2 = {"rule_name": "Phishing Email", "severity": "medium"}

        # Act: First alert
        result1 = await workflow_step.execute(
            tenant_id="default",
            alert_id="alert-7",
            analysis_id="analysis-7",
            alert_data=alert_data_1,
        )

        # Act: Second alert (should hit cache)
        result2 = await workflow_step.execute(
            tenant_id="default",
            alert_id="alert-8",
            analysis_id="analysis-8",
            alert_data=alert_data_2,
        )

        # Assert
        assert result1 == "workflow-phishing"
        assert result2 == "workflow-phishing"

        # API should only be called ONCE (first alert)
        assert mock_kea_client.create_group_with_generation.call_count == 1
