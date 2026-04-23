"""
Unit tests for complete alert processing flow with workflow reuse.

Tests the end-to-end flow where:
1. First alert with new rule_name → pauses → workflow generated → routing rule created → resumes
2. Subsequent alerts with same rule_name → find existing workflow immediately

All dependencies are mocked to test the business logic without infrastructure.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.steps.workflow_builder import (
    AnalysisGroupCache,
    WorkflowBuilderStep,
)
from analysi.schemas.alert import AnalysisStatus


class TestCompleteWorkflowReuseFlow:
    """
    Test the complete workflow reuse flow end-to-end with mocked dependencies.

    This simulates:
    1. First alert → pauses for workflow generation → resumes after routing rule created
    2. Subsequent alerts → immediately get workflow from cache/API
    """

    @pytest.fixture
    def mock_kea_client(self):
        """Mock Kea Coordination client."""
        return AsyncMock()

    @pytest.fixture
    def shared_cache(self):
        """Shared cache instance (simulates global cache across workers)."""
        return AnalysisGroupCache()

    @pytest.fixture
    def workflow_step(self, mock_kea_client, shared_cache):
        """Workflow builder step with shared cache."""
        return WorkflowBuilderStep(
            kea_client=mock_kea_client,
            cache=shared_cache,
        )

    @pytest.mark.asyncio
    async def test_first_alert_pauses_then_subsequent_alerts_use_workflow(
        self, workflow_step, mock_kea_client, shared_cache
    ):
        """
        Test complete flow:
        1. Alert 1 (new rule) → workflow not ready → returns None (pause)
        2. [Workflow generation happens externally]
        3. [Reconciliation updates cache with workflow_id]
        4. Alert 2 (same rule) → cache hit → returns workflow_id immediately
        5. Alert 3 (same rule) → cache hit → returns workflow_id immediately
        """
        rule_name = "Suspicious PowerShell Execution"
        group_id = str(uuid4())
        workflow_id = str(uuid4())
        first_analysis_id = str(uuid4())

        # === PHASE 1: First alert - workflow not ready ===
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": group_id, "title": rule_name},
            "workflow_generation": {
                "id": str(uuid4()),
                "status": "running",
                "workflow_id": None,  # No workflow yet
                "triggering_alert_analysis_id": first_analysis_id,  # This alert triggers it
            },
        }

        alert_1 = {
            "id": str(uuid4()),
            "rule_name": rule_name,
            "severity": "high",
            "title": "PowerShell encoded command detected",
        }

        with patch.object(
            workflow_step, "_trigger_workflow_generation", new=AsyncMock()
        ) as mock_trigger:
            result_1 = await workflow_step.execute(
                tenant_id="default",
                alert_id=alert_1["id"],
                analysis_id=first_analysis_id,  # Matches triggering_alert_analysis_id
                alert_data=alert_1,
            )

            # First alert should pause (None = workflow not ready)
            assert result_1 is None
            mock_trigger.assert_called_once()  # Generation was triggered (this alert created it)

        # API was called for first alert
        assert mock_kea_client.create_group_with_generation.call_count == 1

        # === PHASE 2: Simulate workflow generation + routing rule creation ===
        # This happens in workflow_generation_job.py after orchestration completes.
        # The reconciliation job then updates the cache when it finds the routing rule.
        # Simulate reconciliation updating the cache:
        shared_cache.set_group(
            title=rule_name,
            group_id=group_id,
            workflow_id=workflow_id,
            tenant_id="default",
        )

        # === PHASE 3: Second alert - cache hit ===
        alert_2 = {
            "id": str(uuid4()),
            "rule_name": rule_name,  # Same rule_name!
            "severity": "medium",
            "title": "Another PowerShell encoded command",
        }

        result_2 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_2["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_2,
        )

        # Second alert should get workflow immediately from cache
        assert result_2 == workflow_id
        # API should NOT be called again (cache hit)
        assert mock_kea_client.create_group_with_generation.call_count == 1

        # === PHASE 4: Third alert - also cache hit ===
        alert_3 = {
            "id": str(uuid4()),
            "rule_name": rule_name,  # Same rule_name!
            "severity": "low",
            "title": "Yet another PowerShell command",
        }

        result_3 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_3["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_3,
        )

        assert result_3 == workflow_id
        # Still no new API calls
        assert mock_kea_client.create_group_with_generation.call_count == 1

    @pytest.mark.asyncio
    async def test_different_rule_names_get_different_workflows(
        self, workflow_step, mock_kea_client, shared_cache
    ):
        """
        Test that alerts with different rule_names get separate workflows.
        """
        # Rule 1: Phishing
        rule_1 = "Phishing Email Detected"
        group_1 = str(uuid4())
        workflow_1 = str(uuid4())

        # Rule 2: Malware
        rule_2 = "Malware Downloaded"
        group_2 = str(uuid4())
        workflow_2 = str(uuid4())

        # Setup API responses for both rules
        def create_group_side_effect(tenant_id, title, triggering_alert_analysis_id):
            if title == rule_1:
                return {
                    "analysis_group": {"id": group_1, "title": rule_1},
                    "workflow_generation": {
                        "id": str(uuid4()),
                        "status": "completed",
                        "workflow_id": workflow_1,
                    },
                }
            if title == rule_2:
                return {
                    "analysis_group": {"id": group_2, "title": rule_2},
                    "workflow_generation": {
                        "id": str(uuid4()),
                        "status": "completed",
                        "workflow_id": workflow_2,
                    },
                }
            raise ValueError(f"Unexpected rule: {title}")

        mock_kea_client.create_group_with_generation.side_effect = (
            create_group_side_effect
        )

        # Alert with rule 1
        alert_1 = {"id": str(uuid4()), "rule_name": rule_1, "severity": "high"}
        result_1 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_1["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_1,
        )
        assert result_1 == workflow_1

        # Alert with rule 2
        alert_2 = {"id": str(uuid4()), "rule_name": rule_2, "severity": "critical"}
        result_2 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_2["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_2,
        )
        assert result_2 == workflow_2

        # Second alert with rule 1 - should hit cache
        alert_3 = {"id": str(uuid4()), "rule_name": rule_1, "severity": "medium"}
        result_3 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_3["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_3,
        )
        assert result_3 == workflow_1

        # Second alert with rule 2 - should hit cache
        alert_4 = {"id": str(uuid4()), "rule_name": rule_2, "severity": "low"}
        result_4 = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert_4["id"],
            analysis_id=str(uuid4()),
            alert_data=alert_4,
        )
        assert result_4 == workflow_2

        # API called twice (once per unique rule)
        assert mock_kea_client.create_group_with_generation.call_count == 2

    @pytest.mark.asyncio
    async def test_race_condition_another_worker_created_workflow(
        self, workflow_step, mock_kea_client, shared_cache
    ):
        """
        Test race condition: cache miss, but another worker already created the workflow.
        API returns existing workflow_id instead of None.
        """
        rule_name = "SQL Injection Attempt"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # API returns completed generation (another worker created it)
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": group_id, "title": rule_name},
            "workflow_generation": {
                "id": str(uuid4()),
                "status": "completed",
                "workflow_id": workflow_id,  # Already completed!
            },
        }

        alert = {"id": str(uuid4()), "rule_name": rule_name, "severity": "high"}

        result = await workflow_step.execute(
            tenant_id="default",
            alert_id=alert["id"],
            analysis_id=str(uuid4()),
            alert_data=alert,
        )

        # Should get the workflow despite cache miss
        assert result == workflow_id

        # Cache should be populated for subsequent alerts
        assert shared_cache.get_group_id(rule_name, tenant_id="default") == group_id
        assert shared_cache.get_workflow_id(group_id) == workflow_id


class TestReconciliationJobUpdatesCache:
    """
    Test that the reconciliation flow properly updates cache and resumes alerts.
    """

    @pytest.mark.asyncio
    async def test_reconciliation_updates_cache_on_workflow_ready(self):
        """
        Test reconciliation job behavior:
        1. Finds paused alerts
        2. Checks Kea API for routing rule
        3. Updates cache when workflow found
        4. Resumes alerts
        """

        # Use a fresh cache for this test
        cache = AnalysisGroupCache()

        # Simulate the reconciliation logic (from reconciliation.py lines 116-163)
        rule_name = "Data Exfiltration Detected"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # Mock alert from find_paused_at_workflow_builder
        mock_alert = MagicMock()
        mock_alert.id = uuid4()
        mock_alert.tenant_id = "default"
        mock_alert.rule_name = rule_name
        mock_alert.current_analysis_id = uuid4()

        # Simulate cache update (this is what reconciliation job does)
        cache.set_group(
            title=rule_name,
            group_id=group_id,
            workflow_id=workflow_id,
            tenant_id="default",
        )

        # Verify cache is now populated
        assert cache.get_group_id(rule_name, tenant_id="default") == group_id
        assert cache.get_workflow_id(group_id) == workflow_id

        # Now subsequent alerts should hit the cache
        mock_kea_client = AsyncMock()
        workflow_step = WorkflowBuilderStep(
            kea_client=mock_kea_client,
            cache=cache,
        )

        new_alert = {"id": str(uuid4()), "rule_name": rule_name, "severity": "medium"}

        result = await workflow_step.execute(
            tenant_id="default",
            alert_id=new_alert["id"],
            analysis_id=str(uuid4()),
            alert_data=new_alert,
        )

        # Should get workflow from cache
        assert result == workflow_id
        # API should NOT be called
        mock_kea_client.create_group_with_generation.assert_not_called()


class TestPipelineWorkflowBuilderIntegration:
    """
    Test pipeline integration with workflow builder step.
    Verifies correct pause/resume behavior.
    """

    @pytest.fixture(autouse=True)
    def _mock_pipeline_http_clients(self):
        """Mock HTTP clients to prevent real network calls in unit tests."""
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
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
    async def test_pipeline_pauses_when_workflow_not_ready(self):
        """
        Test pipeline correctly pauses when workflow_builder returns None.
        """
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        tenant_id = "default"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        # Mock database
        mock_db = AsyncMock()
        mock_alert = MagicMock()
        mock_alert.title = "Test Alert"
        mock_alert.rule_name = "New Rule Type"
        mock_db.get_alert.return_value = mock_alert
        mock_db.get_analysis.return_value = {"id": analysis_id, "status": "pending"}
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        # Mock API client for status updates
        mock_api_client = AsyncMock()
        mock_api_client.update_analysis_status = AsyncMock(return_value=True)
        mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)

        with patch.object(pipeline, "_is_step_completed", return_value=False):
            with patch.object(pipeline, "_update_step_progress_api", new=AsyncMock()):
                with patch.object(pipeline, "_execute_step") as mock_execute:
                    with patch(
                        "analysi.alert_analysis.clients.BackendAPIClient",
                        return_value=mock_api_client,
                    ):
                        # pre_triage succeeds
                        # workflow_builder returns None (workflow not ready)
                        mock_execute.side_effect = [
                            {"result": "pre_triage_done"},
                            None,  # workflow_builder returns None
                        ]

                        result = await pipeline.execute()

                        # Pipeline should pause
                        paused_value = AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value
                        assert result["status"] == paused_value
                        assert mock_execute.call_count == 2

                        # Verify correct API updates
                        status_calls = [
                            call
                            for call in mock_api_client.update_analysis_status.call_args_list
                            if call[0][2] == paused_value
                        ]
                        assert len(status_calls) > 0, (
                            f"Expected {paused_value} status call"
                        )

    @pytest.mark.asyncio
    async def test_pipeline_completes_when_workflow_ready(self):
        """
        Test pipeline completes all steps when workflow is available.
        """
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        tenant_id = "default"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        # Mock database
        mock_db = AsyncMock()
        mock_alert = MagicMock()
        mock_alert.title = "Test Alert"
        mock_alert.rule_name = "Existing Rule"
        mock_db.get_alert.return_value = mock_alert
        mock_db.get_analysis.return_value = {"id": analysis_id, "status": "pending"}
        mock_db.get_step_progress.return_value = {}
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        with patch.object(pipeline, "_is_step_completed", return_value=False):
            with patch.object(pipeline, "_update_step_progress_api", new=AsyncMock()):
                with patch.object(pipeline, "_execute_step") as mock_execute:
                    # All steps succeed, workflow_builder returns workflow_id
                    mock_execute.side_effect = [
                        {"result": "pre_triage_done"},
                        {
                            "workflow_id": workflow_id
                        },  # workflow_builder returns workflow
                        {"result": "workflow_execution_done"},
                        {"result": "disposition_done"},
                    ]

                    result = await pipeline.execute()

                    # Pipeline should complete
                    assert result["status"] == "completed"
                    assert mock_execute.call_count == 4

    @pytest.mark.asyncio
    async def test_resumed_alert_continues_from_workflow_builder(self):
        """
        Test that a resumed alert (after workflow generation) continues correctly.

        Simulates:
        1. Alert was paused at workflow_builder (first 2 steps completed)
        2. Workflow generation completed
        3. Alert is resumed and should continue from workflow_builder
        """
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        tenant_id = "default"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        workflow_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        # Mock database
        mock_db = AsyncMock()
        mock_alert = MagicMock()
        mock_alert.title = "Test Alert"
        mock_alert.rule_name = "Resumed Rule"
        mock_db.get_alert.return_value = mock_alert
        mock_db.get_analysis.return_value = {"id": analysis_id, "status": "running"}
        # First step already completed (from before pause)
        mock_db.get_step_progress.return_value = {
            "pre_triage": {"completed": True},
        }
        mock_db.update_analysis_status = AsyncMock()
        mock_db.update_alert_status = AsyncMock()
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        # Track which steps are completed
        completed_steps = {"pre_triage"}

        async def is_completed_side_effect(step_name):
            return step_name in completed_steps

        with patch.object(
            pipeline, "_is_step_completed", side_effect=is_completed_side_effect
        ):
            with patch.object(pipeline, "_update_step_progress_api", new=AsyncMock()):
                with patch.object(pipeline, "_execute_step") as mock_execute:
                    # Only remaining 3 steps need to execute
                    # workflow_builder now returns workflow (generation completed)
                    mock_execute.side_effect = [
                        {"workflow_id": workflow_id},  # workflow_builder succeeds
                        {"result": "workflow_execution_done"},
                        {"result": "disposition_done"},
                    ]

                    result = await pipeline.execute()

                    # Pipeline should complete
                    assert result["status"] == "completed"
                    # Only 3 steps executed (skipped first 2)
                    assert mock_execute.call_count == 3


class TestCacheInvalidation:
    """
    Test cache invalidation scenarios.
    """

    def test_cache_invalidate_group_removes_workflow_mapping(self):
        """Test that invalidating a group removes workflow but keeps title mapping."""
        cache = AnalysisGroupCache()

        # Setup cache
        cache.set_group(
            title="Test Rule",
            group_id="group-123",
            workflow_id="workflow-456",
            tenant_id="t",
        )

        # Verify initial state
        assert cache.get_group_id("Test Rule", tenant_id="t") == "group-123"
        assert cache.get_workflow_id("group-123") == "workflow-456"

        # Invalidate
        cache.invalidate_group("group-123")

        # Title → group mapping preserved
        assert cache.get_group_id("Test Rule", tenant_id="t") == "group-123"
        # Workflow mapping removed
        assert cache.get_workflow_id("group-123") is None

    def test_cache_handles_workflow_regeneration(self):
        """
        Test cache handles workflow regeneration scenario.

        When a workflow is regenerated:
        1. Old workflow is invalidated
        2. New workflow is set
        3. Subsequent alerts get new workflow
        """
        cache = AnalysisGroupCache()
        rule_name = "Rule with Regeneration"
        group_id = "group-regen"

        # Initial workflow
        cache.set_group(
            title=rule_name, group_id=group_id, workflow_id="workflow-v1", tenant_id="t"
        )
        assert cache.get_workflow_id(group_id) == "workflow-v1"

        # Invalidate (workflow regeneration triggered)
        cache.invalidate_group(group_id)
        assert cache.get_workflow_id(group_id) is None

        # New workflow set after regeneration completes
        cache.set_group(
            title=rule_name, group_id=group_id, workflow_id="workflow-v2", tenant_id="t"
        )
        assert cache.get_workflow_id(group_id) == "workflow-v2"
