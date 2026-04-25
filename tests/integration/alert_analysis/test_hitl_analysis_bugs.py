"""
Integration tests for bugs discovered during HITL workflow testing.

1. Reconciliation sync_mismatched must only check CURRENT analysis (not old ones)
2. Step 4 fallback (no disposition) must still store workflow_run_id on analysis
3. complete_analysis API must accept disposition_id=None and still link workflow
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from analysi.models.alert import Alert, AlertAnalysis
from analysi.repositories.alert_repository import AlertRepository

TENANT_ID = f"hitl-bugs-{uuid.uuid4().hex[:8]}"


async def _create_alert(session, *, analysis_status="in_progress"):
    """Create a minimal Alert."""
    alert_id = uuid.uuid4()
    now = datetime.now(UTC)
    alert = Alert(
        id=alert_id,
        tenant_id=TENANT_ID,
        human_readable_id=f"BUG-{uuid.uuid4().hex[:8]}",
        title="Bug Test Alert",
        severity="high",
        analysis_status=analysis_status,
        rule_name="test-rule",
        triggering_event_time=now - timedelta(minutes=10),
        raw_data='{"test": true}',
        raw_data_hash=f"hash-{uuid.uuid4().hex[:8]}",
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        created_at=now - timedelta(minutes=5),
        updated_at=now,
    )
    session.add(alert)
    await session.flush()
    return alert


async def _create_analysis(session, alert_id, *, status="running"):
    """Create an AlertAnalysis linked to an alert."""
    now = datetime.now(UTC)
    analysis = AlertAnalysis(
        id=uuid.uuid4(),
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        status=status,
        started_at=now - timedelta(minutes=4),
        created_at=now - timedelta(minutes=4),
        updated_at=now,
    )
    session.add(analysis)
    await session.flush()
    return analysis


# ---------------------------------------------------------------------------
# 1. Reconciliation only checks CURRENT analysis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestMismatchedStatusOnlyChecksCurrent:
    """find_mismatched_alert_statuses must join on current_analysis_id,
    not alert_id. Otherwise, old failed analyses cause re-analysis to
    be synced back to 'failed'."""

    async def test_old_failed_analysis_does_not_cause_mismatch(
        self, integration_test_session
    ):
        """Alert with in_progress current analysis and old failed analysis
        should NOT be detected as mismatched."""
        session = integration_test_session

        # Create alert
        alert = await _create_alert(session, analysis_status="in_progress")

        # Create OLD failed analysis
        old_analysis = await _create_analysis(session, alert.id, status="failed")

        # Create CURRENT running analysis
        current_analysis = await _create_analysis(session, alert.id, status="running")

        # Point alert to current analysis
        alert.current_analysis_id = current_analysis.id
        await session.commit()

        # Find mismatched — should NOT find this alert
        repo = AlertRepository(session)
        mismatched = await repo.find_mismatched_alert_statuses(tenant_id=TENANT_ID)

        alert_ids_in_mismatch = {a.alert_id for a, _ in mismatched}
        assert alert.id not in alert_ids_in_mismatch, (
            f"Alert with running current analysis should NOT be in mismatch list. "
            f"Old failed analysis {old_analysis.id} was incorrectly matched."
        )

    async def test_current_failed_analysis_is_detected_as_mismatch(
        self, integration_test_session
    ):
        """Alert with in_progress status but current analysis is failed
        SHOULD be detected as mismatched (legitimate sync needed)."""
        session = integration_test_session

        alert = await _create_alert(session, analysis_status="in_progress")

        # Current analysis is failed — this IS a real mismatch
        failed_analysis = await _create_analysis(session, alert.id, status="failed")
        alert.current_analysis_id = failed_analysis.id
        await session.commit()

        repo = AlertRepository(session)
        mismatched = await repo.find_mismatched_alert_statuses(tenant_id=TENANT_ID)

        alert_ids_in_mismatch = {a.alert_id for a, _ in mismatched}
        assert alert.id in alert_ids_in_mismatch, (
            "Alert with failed current analysis should be detected as mismatched"
        )


# ---------------------------------------------------------------------------
# 2. Step 4 fallback passes workflow_run_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestStep4FallbackPassesWorkflowRunId:
    """When step 4 completes without a disposition (fallback path),
    workflow_run_id must still be passed to _complete_analysis."""

    async def test_fallback_includes_workflow_run_id(self):
        """The fallback ValueError handler passes workflow_run_id."""
        from unittest.mock import AsyncMock, patch

        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        step = FinalDispositionUpdateStep()
        wf_run_id = str(uuid.uuid4())
        wf_id = str(uuid.uuid4())

        # No artifacts → no disposition → fallback path
        step.api_client.get_artifacts_by_workflow_run = AsyncMock(return_value=[])
        step.api_client.get_dispositions = AsyncMock(return_value=[])

        with patch.object(step, "_complete_analysis", new=AsyncMock()) as mock_complete:
            result = await step.execute(
                tenant_id="t1",
                alert_id=str(uuid.uuid4()),
                analysis_id=str(uuid.uuid4()),
                workflow_run_id=wf_run_id,
                workflow_id=wf_id,
            )

        # Verify workflow_run_id was passed to _complete_analysis
        mock_complete.assert_awaited_once()
        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["workflow_run_id"] == wf_run_id
        assert call_kwargs["workflow_id"] == wf_id
        assert call_kwargs["disposition_id"] is None
        assert result["status"] == "completed"
        assert result["warning"] is not None


# ---------------------------------------------------------------------------
# 3. complete_analysis API stores workflow_run_id without disposition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompleteAnalysisWithoutDisposition:
    """The /analyses/{id}/complete endpoint must store workflow_run_id
    even when disposition_id is None."""

    async def test_workflow_run_id_stored_without_disposition(
        self, integration_test_session
    ):
        """complete_analysis with disposition_id=None still stores workflow_run_id."""
        from collections.abc import AsyncGenerator

        from httpx import ASGITransport, AsyncClient

        from analysi.db.session import get_db
        from analysi.main import app

        session = integration_test_session

        # Create alert + analysis
        alert = await _create_alert(session)
        analysis = await _create_analysis(session, alert.id, status="running")
        alert.current_analysis_id = analysis.id
        await session.commit()

        wf_run_id = uuid.uuid4()

        # Override DB dependency
        async def override_get_db() -> AsyncGenerator:
            yield session

        app.dependency_overrides[get_db] = override_get_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.put(
                    f"/v1/{TENANT_ID}/analyses/{analysis.id}/complete",
                    json={
                        "confidence": 0,
                        "short_summary": "",
                        "long_summary": "",
                        "workflow_run_id": str(wf_run_id),
                    },
                )
                assert response.status_code == 200, response.text
        finally:
            app.dependency_overrides.clear()

        # Verify workflow_run_id was stored — use a raw text query
        # to avoid greenlet issues with the shared test session.
        from sqlalchemy import text

        result = await session.execute(
            text(
                "SELECT status, workflow_run_id, disposition_id "
                "FROM alert_analyses WHERE id = :id"
            ),
            {"id": str(analysis.id)},
        )
        row = result.one()
        assert row.status == "completed"
        assert str(row.workflow_run_id) == str(wf_run_id)
        assert row.disposition_id is None
