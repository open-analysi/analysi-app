"""
Tests for pipeline resilience fixes:
1. Cross-tenant cache isolation
2. alert_data passthrough to WorkflowExecutionStep
3. tenant_id as explicit parameter in _complete_analysis
4. Status update failure doesn't lose completed analysis
5. Reconciliation API call deduplication
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
from analysi.alert_analysis.steps.final_disposition_update import (
    FinalDispositionUpdateStep,
)
from analysi.alert_analysis.steps.workflow_builder import AnalysisGroupCache
from analysi.alert_analysis.steps.workflow_execution import WorkflowExecutionStep
from analysi.common.stuck_detection import StuckDetectionResult


def _stub_stuck_result() -> StuckDetectionResult:
    """Create a zero-count StuckDetectionResult for test patching."""
    return StuckDetectionResult(
        counts={
            "stuck_running_alerts": 0,
            "stuck_generations": 0,
            "stuck_content_reviews": 0,
        },
    )


def create_mock_api_client():
    """Create a mock BackendAPIClient for testing."""
    mock_client = AsyncMock()
    mock_client.update_analysis_status = AsyncMock(return_value=True)
    return mock_client


# ── Fix 1: Cross-tenant cache isolation ──────────────────────────────────────


class TestCrossTenantCacheIsolation:
    """Verify that cache entries are scoped per tenant."""

    def test_same_rule_name_different_tenants_returns_different_groups(self):
        """Two tenants with identical rule_name must get independent group_ids."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Suspicious Login",
            group_id="group-alpha",
            workflow_id="wf-alpha",
            tenant_id="tenant-alpha",
        )
        cache.set_group(
            title="Suspicious Login",
            group_id="group-beta",
            workflow_id="wf-beta",
            tenant_id="tenant-beta",
        )

        # Each tenant sees only their own entry
        assert (
            cache.get_group_id("Suspicious Login", tenant_id="tenant-alpha")
            == "group-alpha"
        )
        assert (
            cache.get_group_id("Suspicious Login", tenant_id="tenant-beta")
            == "group-beta"
        )

        # Workflows are independent (group_id is globally unique)
        assert cache.get_workflow_id("group-alpha") == "wf-alpha"
        assert cache.get_workflow_id("group-beta") == "wf-beta"

    def test_tenant_a_entry_invisible_to_tenant_b(self):
        """A cache entry for one tenant must not be visible to another."""
        cache = AnalysisGroupCache()

        cache.set_group(
            title="Malware Alert",
            group_id="g-1",
            workflow_id="wf-1",
            tenant_id="acme-corp",
        )

        # Different tenant — should be a miss
        assert cache.get_group_id("Malware Alert", tenant_id="evil-corp") is None

    @pytest.mark.asyncio
    async def test_workflow_builder_uses_tenant_scoped_cache(self):
        """WorkflowBuilderStep cache lookups are tenant-scoped."""
        from analysi.alert_analysis.steps.workflow_builder import WorkflowBuilderStep

        cache = AnalysisGroupCache()
        mock_kea_client = AsyncMock()

        step = WorkflowBuilderStep(
            kea_client=mock_kea_client,
            cache=cache,
        )

        # Populate cache for tenant-alpha only
        cache.set_group(
            title="Same Rule",
            group_id="g-alpha",
            workflow_id="wf-alpha",
            tenant_id="tenant-alpha",
        )

        # tenant-alpha: cache hit
        result = await step.execute(
            tenant_id="tenant-alpha",
            alert_id="alert-1",
            analysis_id="analysis-1",
            alert_data={"rule_name": "Same Rule"},
        )
        assert result == "wf-alpha"
        mock_kea_client.create_group_with_generation.assert_not_called()

        # tenant-beta: cache miss — must call API
        mock_kea_client.create_group_with_generation.return_value = {
            "analysis_group": {"id": "g-beta", "title": "Same Rule"},
            "workflow_generation": {
                "id": "gen-1",
                "status": "completed",
                "workflow_id": "wf-beta",
            },
        }

        result = await step.execute(
            tenant_id="tenant-beta",
            alert_id="alert-2",
            analysis_id="analysis-2",
            alert_data={"rule_name": "Same Rule"},
        )
        assert result == "wf-beta"
        mock_kea_client.create_group_with_generation.assert_called_once()


# ── Fix 2: alert_data passthrough avoids redundant DB session ────────────────


class TestAlertDataPassthrough:
    """Verify WorkflowExecutionStep uses pre-fetched alert_data."""

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
    async def test_execute_uses_alert_data_when_provided(self):
        """When alert_data is passed, _prepare_workflow_input is NOT called."""
        from uuid import uuid4

        step = WorkflowExecutionStep()
        step._prepare_workflow_input = AsyncMock()

        alert_data = {"alert_id": "abc", "severity": "high", "title": "Test"}
        workflow_id = str(uuid4())
        run_id = uuid4()

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
            result = await step.execute(
                tenant_id="t1",
                alert_id="abc",
                analysis_id="a1",
                workflow_id=workflow_id,
                alert_data=alert_data,
            )

        assert result == str(run_id)
        # Should NOT open a new DB session for alert data
        step._prepare_workflow_input.assert_not_called()
        # Should pass alert_data as input to workflow
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][2] == alert_data  # input_data is 3rd positional arg

    @pytest.mark.asyncio
    async def test_execute_falls_back_to_prepare_when_no_alert_data(self):
        """When alert_data is None, _prepare_workflow_input is called (backward compat)."""
        from uuid import uuid4

        step = WorkflowExecutionStep()
        step._prepare_workflow_input = AsyncMock(
            return_value={"alert_id": "xyz", "severity": "low"}
        )

        workflow_id = str(uuid4())
        run_id = uuid4()

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
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            result = await step.execute(
                tenant_id="t1",
                alert_id="xyz",
                analysis_id="a2",
                workflow_id=workflow_id,
                # alert_data NOT provided
            )

        assert result == str(run_id)
        step._prepare_workflow_input.assert_called_once_with("t1", "xyz")

    @pytest.mark.asyncio
    async def test_pipeline_passes_alert_data_to_workflow_execution(self):
        """Pipeline passes alert_data through to WorkflowExecutionStep."""
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        mock_db = AsyncMock()
        alert_data = {"alert_id": alert_id, "rule_name": "Test Rule"}
        mock_db.get_alert.return_value = alert_data
        mock_db.get_step_progress.return_value = {}
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        mock_api_client = create_mock_api_client()

        # Track what kwargs _execute_step receives for workflow_execution
        execute_step_calls = []

        async def spy_execute_step(step_name, **kwargs):
            execute_step_calls.append((step_name, kwargs))
            if step_name == "workflow_builder":
                return "wf-123"  # workflow ready
            if step_name == "workflow_execution":
                return "run-789"  # workflow run id
            if step_name == "final_disposition_update":
                return {"status": "completed"}
            return {"result": "ok"}

        with (
            patch.object(pipeline, "_is_step_completed", return_value=False),
            patch.object(pipeline, "_execute_step", side_effect=spy_execute_step),
            patch(
                "analysi.alert_analysis.clients.BackendAPIClient",
                return_value=mock_api_client,
            ),
        ):
            await pipeline.execute()

        # Find the workflow_execution call
        wf_exec_calls = [
            (name, kw)
            for name, kw in execute_step_calls
            if name == "workflow_execution"
        ]
        assert len(wf_exec_calls) == 1
        _, kwargs = wf_exec_calls[0]
        assert kwargs["alert_data"] == alert_data


# ── Fix 3: tenant_id as explicit parameter ───────────────────────────────────


class TestTenantIdExplicitParameter:
    """Verify _complete_analysis receives tenant_id as parameter, not getattr."""

    @pytest.mark.asyncio
    async def test_complete_analysis_uses_explicit_tenant_id(self):
        """_complete_analysis must use the tenant_id parameter, not instance attr."""
        step = FinalDispositionUpdateStep(tenant_id="constructor-default")

        with patch(
            "analysi.alert_analysis.steps.final_disposition_update.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.put.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await step._complete_analysis(
                tenant_id="explicit-tenant",
                analysis_id="a-123",
                disposition_id="d-456",
                confidence=80,
                short_summary="Summary",
                long_summary="Long",
                workflow_run_id="run-789",
            )

            # Verify the API call used the explicit tenant_id
            call_args = mock_client.put.call_args
            assert "/v1/explicit-tenant/analyses/a-123/complete" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_execute_passes_tenant_id_to_complete_analysis(self):
        """The execute() method must pass tenant_id to _complete_analysis."""
        step = FinalDispositionUpdateStep(tenant_id="init-default")
        step.api_client = AsyncMock()
        step.api_client.get_dispositions.return_value = [
            {
                "disposition_id": "d-1",
                "display_name": "True Positive",
                "category": "True Positive (TP)",
                "subcategory": "Confirmed",
            }
        ]

        # Mock artifact retrieval
        step._get_workflow_artifacts = AsyncMock(
            return_value=[
                {"name": "Disposition", "content": "True Positive - 85% confidence"},
                {"name": "Alert Summary", "content": "Summary text"},
                {"name": "Detailed Analysis", "content": "Long analysis text"},
            ]
        )

        # Spy on _complete_analysis
        complete_calls = []

        async def spy_complete(*args, **kwargs):
            complete_calls.append(kwargs)

        step._complete_analysis = spy_complete

        await step.execute(
            tenant_id="runtime-tenant",
            alert_id="alert-1",
            analysis_id="analysis-1",
            workflow_run_id="run-1",
        )

        assert len(complete_calls) == 1
        assert complete_calls[0]["tenant_id"] == "runtime-tenant"


# ── Fix 4: Status update failure resilience ──────────────────────────────────


@pytest.mark.asyncio
class TestStatusUpdateResilience:
    """Verify pipeline doesn't mark analysis as failed when final status update fails."""

    @pytest.mark.asyncio
    async def test_pipeline_returns_completed_when_final_status_update_fails(self):
        """If _update_status('completed') fails, pipeline should still return completed."""
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": alert_id, "rule_name": "R"}
        mock_db.get_step_progress.return_value = {}
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        # Track _update_status calls
        status_calls = []

        async def mock_update_status(status, error=None):
            status_calls.append(status)
            if status == "completed":
                raise ConnectionError("API temporarily unavailable")

        with (
            patch.object(pipeline, "_is_step_completed", return_value=False),
            patch.object(pipeline, "_execute_step") as mock_execute,
            patch.object(pipeline, "_update_status", side_effect=mock_update_status),
        ):
            mock_execute.side_effect = [
                {"pre_triage": "ok"},  # Step 1
                "wf-123",  # Step 2: workflow_id
                "run-456",  # Step 3: workflow_run_id
                {"disposition": "done"},  # Step 4
            ]

            result = await pipeline.execute()

        # Pipeline should return completed even though status update failed
        assert result["status"] == "completed"
        assert result["workflow_run_id"] == "run-456"

        # Should have attempted both "running" and "completed" status updates
        assert "running" in status_calls
        assert "completed" in status_calls

        # Should NOT have called _update_status("failed")
        assert "failed" not in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_still_fails_on_step_error(self):
        """Step failures should still propagate (fix only protects final status update)."""
        tenant_id = "test-tenant"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())

        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
        )

        mock_db = AsyncMock()
        mock_db.get_alert.return_value = {"alert_id": alert_id}
        mock_db.get_step_progress.return_value = {}
        pipeline.db = mock_db

        mock_api_client = create_mock_api_client()

        with (
            patch.object(pipeline, "_is_step_completed", return_value=False),
            patch.object(
                pipeline, "_execute_step", side_effect=ValueError("Step 1 failed")
            ),
            patch(
                "analysi.alert_analysis.clients.BackendAPIClient",
                return_value=mock_api_client,
            ),
        ):
            with pytest.raises(ValueError, match="Step 1 failed"):
                await pipeline.execute()


# ── Fix 5: Reconciliation deduplication ──────────────────────────────────────


@pytest.mark.asyncio
class TestReconciliationDeduplication:
    """Verify reconciliation deduplicates Kea API calls for same rule_name."""

    @pytest.mark.asyncio
    async def test_same_rule_name_alerts_trigger_single_api_call(self):
        """N alerts with same rule_name should trigger only 1 Kea API call."""
        from analysi.alert_analysis.jobs.reconciliation import reconcile_paused_alerts

        # Create 3 mock alerts with same rule_name
        alerts = []
        for _ in range(3):
            alert = MagicMock()
            alert.id = uuid4()
            alert.tenant_id = "shared-tenant"
            alert.rule_name = "Suspicious Login Detected"
            alert.current_analysis_id = uuid4()
            alerts.append(alert)

        # Create context with mocked dependencies
        with (
            patch(
                "analysi.alert_analysis.jobs.reconciliation.create_pool"
            ) as mock_create_pool,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.AlertAnalysisDB"
            ) as mock_db_class,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.AlertRepository"
            ) as mock_alert_repo_class,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.AlertAnalysisRepository"
            ) as mock_analysis_repo_class,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.WorkflowGenerationRepository"
            ) as mock_gen_repo_class,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.KeaCoordinationClient"
            ) as mock_kea_class,
            patch(
                "analysi.common.stuck_detection.run_all_stuck_detection",
                new_callable=AsyncMock,
                return_value=_stub_stuck_result(),
            ),
            patch(
                "analysi.alert_analysis.jobs.reconciliation.sync_mismatched_alert_statuses",
                return_value=0,
            ),
            patch(
                "analysi.alert_analysis.jobs.reconciliation.cleanup_orphaned_workspaces",
                return_value=0,
            ),
            patch(
                "analysi.alert_analysis.jobs.reconciliation.detect_orphaned_analyses",
                return_value=0,
            ),
            patch(
                "analysi.alert_analysis.jobs.reconciliation.maintain_partitions",
                return_value={},
            ),
            patch(
                "analysi.alert_analysis.jobs.reconciliation.get_global_cache"
            ) as mock_get_cache,
        ):
            # Setup mocks
            mock_cache = MagicMock()
            mock_get_cache.return_value = mock_cache

            mock_redis = AsyncMock()
            mock_redis.zcard = AsyncMock(return_value=0)
            mock_redis.keys = AsyncMock(return_value=[])
            mock_redis.enqueue_job = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_create_pool.return_value = mock_redis

            mock_db = AsyncMock()
            mock_db.initialize = AsyncMock()
            mock_db.session = AsyncMock()
            mock_db.close = AsyncMock()
            mock_db_class.return_value = mock_db

            mock_alert_repo = AsyncMock()
            mock_alert_repo.find_paused_at_workflow_builder.return_value = alerts
            mock_alert_repo.try_resume_alert.return_value = True
            mock_alert_repo_class.return_value = mock_alert_repo

            mock_analysis_repo = AsyncMock()
            mock_analysis_repo.find_paused_for_human_review.return_value = []
            mock_analysis_repo_class.return_value = mock_analysis_repo

            mock_gen_repo = AsyncMock()
            mock_gen_repo.count_running.return_value = 0
            mock_gen_repo_class.return_value = mock_gen_repo

            mock_kea_client = AsyncMock()
            mock_kea_client.get_active_workflow.return_value = {
                "routing_rule": {
                    "analysis_group_id": "group-1",
                    "workflow_id": "wf-1",
                },
            }
            mock_kea_class.return_value = mock_kea_client

            result = await reconcile_paused_alerts({})

        # Key assertion: Kea API called only ONCE for 3 alerts with same rule_name
        assert mock_kea_client.get_active_workflow.call_count == 1

        # All 3 alerts should have been resumed
        assert result["resumed_count"] == 3
