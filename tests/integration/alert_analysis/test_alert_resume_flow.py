"""Integration tests for alert resume flow after workflow generation.

Tests the complete flow:
1. Alert pauses at workflow_builder step
2. Workflow generation completes (success or failure)
3. Alert resumes and continues processing

These tests verify:
- Reconciliation job resumes alerts when workflows are ready
- Reconciliation job resumes alerts even when workflow generation FAILS
- Alerts are resumed immediately after workflow generation (push-based)
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.alert_analysis.jobs.reconciliation import reconcile_paused_alerts
from analysi.models.alert import Alert, AlertAnalysis
from analysi.repositories.alert_repository import AlertRepository
from analysi.repositories.kea_coordination_repository import (
    AlertRoutingRuleRepository,
    AnalysisGroupRepository,
    WorkflowGenerationRepository,
)
from analysi.schemas.alert import AnalysisStatus


@pytest.fixture
async def db():
    """Create AlertAnalysisDB instance for integration tests."""
    db_instance = AlertAnalysisDB()
    await db_instance.initialize()
    try:
        yield db_instance
    finally:
        await db_instance.close()


@pytest.fixture
def unique_tenant_id():
    """Generate unique tenant ID for test isolation."""
    return f"test-tenant-{uuid4().hex[:8]}"


@pytest.fixture
def unique_rule_name():
    """Generate unique rule name for test isolation."""
    return f"Test Rule {uuid4().hex[:8]}"


async def create_paused_alert(
    db: AlertAnalysisDB,
    tenant_id: str,
    rule_name: str,
) -> tuple[Alert, AlertAnalysis]:
    """Create an alert paused at workflow_builder step."""
    alert_id = uuid4()
    analysis_id = uuid4()

    # Create alert with required fields
    # Note: Alert.analysis_status has check constraint (new, in_progress, completed, failed, cancelled)
    # The paused_workflow_building status is only on AlertAnalysis, not Alert
    alert = Alert(
        id=alert_id,
        tenant_id=tenant_id,
        human_readable_id=f"AID-TEST-{alert_id.hex[:8]}",
        title=f"Test Alert {alert_id.hex[:8]}",
        rule_name=rule_name,
        severity="medium",
        triggering_event_time=datetime.now(UTC),
        raw_data=json.dumps({"test": "data"}),
        raw_data_hash=f"hash-{alert_id.hex}",
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status="in_progress",  # Alert uses simplified statuses
        current_analysis_id=analysis_id,
    )
    db.session.add(alert)

    # Create analysis in paused_workflow_building status
    analysis = AlertAnalysis(
        id=analysis_id,
        alert_id=alert_id,
        tenant_id=tenant_id,
        status=AnalysisStatus.PAUSED_WORKFLOW_BUILDING,
        current_step="workflow_builder",
    )
    db.session.add(analysis)

    await db.session.commit()
    return alert, analysis


class TestReconciliationResumesAlertsOnSuccess:
    """Test reconciliation resumes alerts when workflow generation succeeds."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reconciliation_resumes_alert_when_routing_rule_exists(
        self, db, unique_tenant_id, unique_rule_name
    ):
        """
        When workflow generation succeeds and creates a routing rule,
        reconciliation should resume paused alerts.
        """
        # Arrange: Create paused alert
        alert, analysis = await create_paused_alert(
            db, unique_tenant_id, unique_rule_name
        )

        # Create analysis group and successful workflow generation
        group_repo = AnalysisGroupRepository(db.session)
        generation_repo = WorkflowGenerationRepository(db.session)
        routing_repo = AlertRoutingRuleRepository(db.session)

        group = await group_repo.create(
            tenant_id=unique_tenant_id, title=unique_rule_name
        )

        workflow_id = uuid4()
        generation = await generation_repo.create(
            tenant_id=unique_tenant_id,
            analysis_group_id=group.id,
        )
        await generation_repo.update_with_results(
            tenant_id=unique_tenant_id,
            generation_id=generation.id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results={"workflow_composition": ["task1"]},
        )

        # Create routing rule (indicates successful workflow)
        await routing_repo.create(
            tenant_id=unique_tenant_id,
            analysis_group_id=group.id,
            workflow_id=workflow_id,
        )
        await db.session.commit()

        # Act: Run reconciliation with mocked Redis and Kea client
        with (
            patch(
                "analysi.alert_analysis.jobs.reconciliation.create_pool"
            ) as mock_pool,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.KeaCoordinationClient"
            ) as mock_kea_class,
        ):
            # Setup Redis mock
            mock_redis = AsyncMock()
            mock_redis.zcard.return_value = 0
            mock_redis.keys.return_value = []
            mock_redis.enqueue_job = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_pool.return_value = mock_redis

            # Setup Kea client mock - return routing rule (successful generation)
            mock_kea_client = AsyncMock()
            mock_kea_client.get_active_workflow.return_value = {
                "routing_rule": {
                    "analysis_group_id": str(group.id),
                    "workflow_id": str(workflow_id),
                },
            }
            mock_kea_class.return_value = mock_kea_client

            result = await reconcile_paused_alerts({})

        # Assert: Alert should be resumed
        assert result["resumed_count"] >= 1
        mock_redis.enqueue_job.assert_called()


class TestReconciliationResumesAlertsOnFailure:
    """Test reconciliation resumes alerts even when workflow generation fails."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reconciliation_resumes_alert_when_generation_failed(
        self, db, unique_tenant_id, unique_rule_name
    ):
        """
        BUG TEST: When workflow generation FAILS (no routing rule),
        reconciliation should still resume paused alerts so they can retry.

        Current behavior: Alerts stay stuck forever because reconciliation
        only checks for routing_rule existence.

        Expected behavior: Alerts should be resumed to re-trigger workflow
        generation or handle the error gracefully.
        """
        # Arrange: Create paused alert
        alert, analysis = await create_paused_alert(
            db, unique_tenant_id, unique_rule_name
        )

        # Create analysis group and FAILED workflow generation
        group_repo = AnalysisGroupRepository(db.session)
        generation_repo = WorkflowGenerationRepository(db.session)

        group = await group_repo.create(
            tenant_id=unique_tenant_id, title=unique_rule_name
        )

        generation = await generation_repo.create(
            tenant_id=unique_tenant_id,
            analysis_group_id=group.id,
        )
        # Mark as failed - NO routing rule created!
        await generation_repo.update_with_results(
            tenant_id=unique_tenant_id,
            generation_id=generation.id,
            workflow_id=None,  # No workflow created
            status="failed",
            orchestration_results={
                "error": {
                    "message": "Workflow generation timed out",
                    "type": "timeout",
                }
            },
        )
        await db.session.commit()

        # Act: Run reconciliation with mocked Redis and Kea client
        with (
            patch(
                "analysi.alert_analysis.jobs.reconciliation.create_pool"
            ) as mock_pool,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.KeaCoordinationClient"
            ) as mock_kea_class,
        ):
            # Setup Redis mock
            mock_redis = AsyncMock()
            mock_redis.zcard.return_value = 0
            mock_redis.keys.return_value = []
            mock_redis.enqueue_job = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_pool.return_value = mock_redis

            # Setup Kea client mock - return no routing_rule (failed generation)
            mock_kea_client = AsyncMock()
            mock_kea_client.get_active_workflow.return_value = {
                "routing_rule": None,  # No routing rule because generation failed
                "generation": {
                    "id": str(generation.id),
                    "status": "failed",  # But generation is terminal
                },
            }
            mock_kea_class.return_value = mock_kea_client

            result = await reconcile_paused_alerts({})

        # Assert: Alert should be resumed even though generation failed
        # This test should FAIL with current implementation (the bug)
        assert result["resumed_count"] >= 1, (
            "Alert should be resumed even when workflow generation failed. "
            "Current implementation only resumes when routing_rule exists."
        )
        mock_redis.enqueue_job.assert_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_alerts_resumed_when_generation_failed(
        self, db, unique_tenant_id, unique_rule_name
    ):
        """
        When workflow generation fails, ALL paused alerts for that rule_name
        should be resumed, not just the triggering one.
        """
        # Arrange: Create multiple paused alerts with same rule_name
        alert1, analysis1 = await create_paused_alert(
            db, unique_tenant_id, unique_rule_name
        )
        alert2, analysis2 = await create_paused_alert(
            db, unique_tenant_id, unique_rule_name
        )
        alert3, analysis3 = await create_paused_alert(
            db, unique_tenant_id, unique_rule_name
        )

        # Create analysis group and FAILED workflow generation
        group_repo = AnalysisGroupRepository(db.session)
        generation_repo = WorkflowGenerationRepository(db.session)

        group = await group_repo.create(
            tenant_id=unique_tenant_id, title=unique_rule_name
        )

        generation = await generation_repo.create(
            tenant_id=unique_tenant_id,
            analysis_group_id=group.id,
        )
        await generation_repo.update_with_results(
            tenant_id=unique_tenant_id,
            generation_id=generation.id,
            workflow_id=None,
            status="failed",
            orchestration_results={"error": {"message": "Test failure"}},
        )
        await db.session.commit()

        # Act: Run reconciliation with mocked Redis and Kea client
        with (
            patch(
                "analysi.alert_analysis.jobs.reconciliation.create_pool"
            ) as mock_pool,
            patch(
                "analysi.alert_analysis.jobs.reconciliation.KeaCoordinationClient"
            ) as mock_kea_class,
        ):
            # Setup Redis mock
            mock_redis = AsyncMock()
            mock_redis.zcard.return_value = 0
            mock_redis.keys.return_value = []
            mock_redis.enqueue_job = AsyncMock()
            mock_redis.aclose = AsyncMock()
            mock_pool.return_value = mock_redis

            # Setup Kea client mock - return no routing_rule (failed generation)
            mock_kea_client = AsyncMock()
            mock_kea_client.get_active_workflow.return_value = {
                "routing_rule": None,
                "generation": {"id": str(generation.id), "status": "failed"},
            }
            mock_kea_class.return_value = mock_kea_client

            result = await reconcile_paused_alerts({})

        # Assert: All 3 alerts should be resumed
        assert result["resumed_count"] >= 3, (
            f"Expected 3 alerts to be resumed, got {result['resumed_count']}. "
            "All paused alerts should resume when generation fails."
        )


class TestCurrentStepWorkflowExecutionFix:
    """
    Tests for the fix where paused alerts have current_step='workflow_execution'.

    Bug: The pipeline advances current_step to 'workflow_execution' BEFORE checking
    if it needs to pause. So alerts end up with:
    - status = 'paused_workflow_building'
    - current_step = 'workflow_execution' (not 'workflow_builder')

    The old query looked for current_step='workflow_builder' which never matched.
    The fix removes the current_step check - status alone is sufficient.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_find_paused_alerts_with_workflow_execution_step(
        self, db, unique_tenant_id
    ):
        """
        Verify that paused alerts are found even when current_step='workflow_execution'.
        This is the realistic scenario from the actual pipeline.
        """
        alert_id = uuid4()
        analysis_id = uuid4()
        rule_name = f"Test Rule {uuid4().hex[:8]}"

        # Create alert
        alert = Alert(
            id=alert_id,
            tenant_id=unique_tenant_id,
            human_readable_id=f"AID-TEST-{alert_id.hex[:8]}",
            title=f"Test Alert {alert_id.hex[:8]}",
            rule_name=rule_name,
            severity="medium",
            triggering_event_time=datetime.now(UTC),
            raw_data=json.dumps({"test": "data"}),
            raw_data_hash=f"hash-{alert_id.hex}",
            raw_data_hash_algorithm="SHA-256",
            finding_info={},
            ocsf_metadata={},
            severity_id=4,
            status_id=1,
            analysis_status="in_progress",
            current_analysis_id=analysis_id,
        )
        db.session.add(alert)

        # Create analysis with the REALISTIC state: paused but current_step advanced
        analysis = AlertAnalysis(
            id=analysis_id,
            alert_id=alert_id,
            tenant_id=unique_tenant_id,
            status=AnalysisStatus.PAUSED_WORKFLOW_BUILDING,
            current_step="workflow_execution",  # This is the realistic state!
        )
        db.session.add(analysis)
        await db.session.commit()

        # Act: Query for paused alerts
        alert_repo = AlertRepository(db.session)
        paused_alerts = await alert_repo.find_paused_at_workflow_builder()

        # Assert: Should find the alert despite current_step='workflow_execution'
        assert len(paused_alerts) >= 1, (
            "Alert with status='paused_workflow_building' and current_step='workflow_execution' "
            "should be found. This was the bug - old query required current_step='workflow_builder'."
        )

        found_alert_ids = [str(a.id) for a in paused_alerts]
        assert str(alert_id) in found_alert_ids

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_active_workflow_endpoint_accepts_title(self, db, unique_tenant_id):
        """
        Verify the new /analysis-groups/active-workflow?title=xxx endpoint works.
        This replaces the old /{group_id}/active-workflow that required UUID.
        """
        from httpx import ASGITransport, AsyncClient

        from analysi.main import app

        rule_name = f"Test Rule {uuid4().hex[:8]}"

        # Create analysis group
        group_repo = AnalysisGroupRepository(db.session)
        await group_repo.create(tenant_id=unique_tenant_id, title=rule_name)
        await db.session.commit()

        # Act: Query active workflow by title (not UUID)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                f"/v1/{unique_tenant_id}/analysis-groups/active-workflow",
                params={"title": rule_name},
            )

        # Assert: Should succeed (200) and return empty workflow (no routing rule yet)
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()["data"]
        assert data["routing_rule"] is None  # No workflow yet
        assert data["generation"] is None  # No generation yet


# NOTE: Push-based resume tests are commented out until the feature is implemented.
# The _resume_paused_alerts function doesn't exist yet.
# Uncomment these tests after implementing the push-based resume in workflow_generation_job.py

# class TestImmediateResumeAfterGeneration:
#     """Test that alerts are resumed immediately after workflow generation completes."""
#
#     @pytest.mark.integration
#     @pytest.mark.asyncio
#     async def test_workflow_generation_job_resumes_alerts_on_success(...):
#         """When workflow generation job completes successfully,
#         it should immediately resume paused alerts (push-based)."""
#         pass
#
#     @pytest.mark.integration
#     @pytest.mark.asyncio
#     async def test_workflow_generation_job_resumes_alerts_on_failure(...):
#         """When workflow generation job FAILS,
#         it should still immediately resume paused alerts."""
#         pass
