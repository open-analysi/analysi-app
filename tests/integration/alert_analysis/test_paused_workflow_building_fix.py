"""
Integration tests for reconciliation fixes applied 2026-02-24.

Three bugs were fixed in reconciliation.py:

Bug 1 (kwarg): mark_failed() was called with error= instead of error_message=,
               and str(analysis.id) instead of UUID.

Bug 2 (missing arg): mark_stuck_alert_failed() was called without analysis_id.

Bug 3 (wrong status filter): In the max-retries-exceeded path, mark_stuck_alert_failed()
       checks AlertAnalysis.status == RUNNING, but the analysis is in
       paused_workflow_building. So rowcount=0, the update is a no-op, and
       Alert.analysis_status is never set to 'failed' — the alert stays stuck forever.

       Fixed by replacing mark_stuck_alert_failed() with db.update_alert_status(),
       which updates Alert.analysis_status unconditionally and calls commit().
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.models.alert import Alert, AlertAnalysis
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
)
from analysi.schemas.alert import AlertStatus, AnalysisStatus

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """AlertAnalysisDB for integration tests."""
    db_instance = AlertAnalysisDB()
    await db_instance.initialize()
    try:
        yield db_instance
    finally:
        await db_instance.close()


async def _create_paused_alert(
    db, *, retry_count: int = 0
) -> tuple[Alert, AlertAnalysis, str]:
    """Create an alert + analysis in the paused_workflow_building state."""
    tenant_id = f"test-paused-fix-{uuid4().hex[:8]}"

    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Test Paused Alert",
        triggering_event_time=datetime.now(UTC),
        severity="high",
        rule_name="Test Rule",
        raw_data=json.dumps({"test": "data"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=AlertStatus.IN_PROGRESS.value,
        ingested_at=datetime.now(UTC),
    )
    db.session.add(alert)
    await db.session.flush()

    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status="paused",  # DB constraint (V112) changed paused_workflow_building -> paused
        started_at=datetime.now(UTC),
        workflow_gen_retry_count=retry_count,
        workflow_gen_last_failure_at=datetime.now(UTC) - timedelta(hours=1)
        if retry_count
        else None,
        created_at=datetime.now(UTC),
    )
    db.session.add(analysis)
    alert.current_analysis_id = analysis.id
    await db.session.commit()

    return alert, analysis, tenant_id


# ---------------------------------------------------------------------------
# Bug 3 regression: old approach silently fails for paused_workflow_building
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_stuck_alert_failed_is_no_op_for_paused_workflow_building(db):
    """
    Regression: mark_stuck_alert_failed() filters on status == RUNNING.
    For paused_workflow_building analyses it returns False (rowcount=0)
    and Alert.analysis_status is left unchanged.

    This is WHY the fix was needed — we document it as a test so the
    behaviour can never silently regress.
    """
    alert, analysis, tenant_id = await _create_paused_alert(db)

    alert_repo = AlertRepository(db.session)
    result = await alert_repo.mark_stuck_alert_failed(
        tenant_id=tenant_id,
        alert_id=str(alert.id),
        analysis_id=str(analysis.id),
        error="max retries exceeded",
    )

    # Returns False because filter on status==RUNNING never matches
    assert result is False

    # Refresh from DB: both statuses must be unchanged
    await db.session.refresh(alert)
    await db.session.refresh(analysis)
    assert alert.analysis_status == AlertStatus.IN_PROGRESS.value
    assert analysis.status == "paused"  # V112: paused_workflow_building -> paused


# ---------------------------------------------------------------------------
# Bug 1 regression: mark_failed() called with correct kwarg + UUID type
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_failed_accepts_uuid_and_error_message_kwarg(db):
    """
    Bug 1 fix: mark_failed() requires analysis_id as UUID (not str) and
    the kwarg is error_message=, not error=.

    Previously the call site used str(analysis.id) and error= which caused
    a TypeError at runtime. This test verifies the correct signature.
    """
    alert, analysis, tenant_id = await _create_paused_alert(db)

    analysis_repo = AlertAnalysisRepository(db.session)

    # Must not raise TypeError
    result = await analysis_repo.mark_failed(
        analysis_id=analysis.id,  # UUID, not str
        error_message="max retries exceeded",  # kwarg name is error_message
        tenant_id=tenant_id,
    )
    await db.session.commit()

    assert result is True

    await db.session.refresh(analysis)
    assert analysis.status == AnalysisStatus.FAILED.value
    assert "max retries exceeded" in analysis.error_message


# ---------------------------------------------------------------------------
# Bug 3 fix: update_alert_status commits the full transaction
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_alert_status_commits_both_analysis_and_alert(db):
    """
    Bug 3 fix: calling analysis_repo.mark_failed() then db.update_alert_status()
    persists both changes to the database.

    mark_failed() only flushes (does not commit). update_alert_status() commits,
    which persists the entire transaction — including the flushed analysis change.
    """
    alert, analysis, tenant_id = await _create_paused_alert(db)

    analysis_repo = AlertAnalysisRepository(db.session)

    # Step 1: mark analysis failed (flush only, no commit)
    await analysis_repo.mark_failed(
        analysis_id=analysis.id,
        error_message="Workflow generation failed after max retries",
        tenant_id=tenant_id,
    )

    # Step 2: update alert status and COMMIT (also commits the flushed analysis change)
    await db.update_alert_status(str(alert.id), "failed")

    # Open a fresh session to verify changes are truly persisted
    fresh_db = AlertAnalysisDB()
    await fresh_db.initialize()
    try:
        fresh_analysis_repo = AlertAnalysisRepository(fresh_db.session)
        fresh_alert_repo = AlertRepository(fresh_db.session)

        fresh_analysis = await fresh_analysis_repo.get_by_alert_id(
            tenant_id=tenant_id,
            alert_id=analysis.alert_id,
        )
        fresh_alerts = await fresh_alert_repo.find_paused_at_workflow_builder()
        paused_ids = {str(a.id) for a in fresh_alerts}

        assert fresh_analysis is not None
        assert fresh_analysis.status == AnalysisStatus.FAILED.value
        assert "max retries" in fresh_analysis.error_message

        # Alert should NOT appear in paused list (it's now failed)
        assert str(alert.id) not in paused_ids
    finally:
        await fresh_db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_failed_alone_does_not_persist_without_commit(db):
    """
    Root cause documentation: mark_failed() uses flush() not commit().

    If the session ends without commit(), the analysis status change is
    rolled back. This is why relying on mark_failed() alone was insufficient.
    """
    alert, analysis, tenant_id = await _create_paused_alert(db)

    analysis_repo = AlertAnalysisRepository(db.session)

    # Capture values before rollback (ORM objects are expired after rollback)
    analysis_alert_id = analysis.alert_id

    # Call mark_failed but do NOT commit
    await analysis_repo.mark_failed(
        analysis_id=analysis.id,
        error_message="should not persist",
        tenant_id=tenant_id,
    )

    # Rollback instead of committing
    await db.session.rollback()

    # Fresh read: analysis should still be paused_workflow_building
    fresh_analysis = await analysis_repo.get_by_alert_id(
        tenant_id=tenant_id,
        alert_id=analysis_alert_id,
    )
    assert fresh_analysis is not None
    assert fresh_analysis.status == "paused"  # V112: paused_workflow_building -> paused


# ---------------------------------------------------------------------------
# End-to-end: simulate the max-retries path in reconcile_paused_alerts
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_max_retries_path_marks_both_statuses_failed(db):
    """
    Simulate the exact code path executed by reconcile_paused_alerts when
    max retries are exceeded for a paused_workflow_building alert.

    This is the core regression test: the old code called mark_stuck_alert_failed()
    (no-op for paused_workflow_building), so Alert.analysis_status stayed 'in_progress'
    and the alert looped forever.

    The fix calls db.update_alert_status() which updates and commits both changes.
    """
    max_retries = AlertAnalysisConfig.MAX_WORKFLOW_GEN_RETRIES
    alert, analysis, tenant_id = await _create_paused_alert(db, retry_count=max_retries)

    analysis_repo = AlertAnalysisRepository(db.session)

    # Reproduce exactly what reconcile_paused_alerts now does:
    from analysi.alert_analysis.jobs.reconciliation import (
        should_retry_workflow_generation,
    )

    should_retry, reason = should_retry_workflow_generation(analysis)
    assert should_retry is False
    assert "Max retries" in reason

    # The fix: mark_failed (flush) + update_alert_status (commit)
    await analysis_repo.mark_failed(
        analysis_id=analysis.id,
        error_message=f"Workflow generation failed after max retries: {reason}",
        tenant_id=tenant_id,
    )
    await db.update_alert_status(str(alert.id), "failed")

    # Verify via fresh DB read that both are persisted
    fresh_db = AlertAnalysisDB()
    await fresh_db.initialize()
    try:
        fresh_analysis_repo = AlertAnalysisRepository(fresh_db.session)
        fresh_alert_repo = AlertRepository(fresh_db.session)

        fresh_analysis = await fresh_analysis_repo.get_by_alert_id(
            tenant_id=tenant_id,
            alert_id=analysis.alert_id,
        )

        # Find the alert directly
        from sqlalchemy import select

        from analysi.models.alert import Alert as AlertModel

        result = await fresh_db.session.execute(
            select(AlertModel).where(AlertModel.id == alert.id)
        )
        fresh_alert = result.scalar_one_or_none()

        assert fresh_analysis is not None
        assert fresh_analysis.status == AnalysisStatus.FAILED.value, (
            f"Expected FAILED, got {fresh_analysis.status}"
        )

        assert fresh_alert is not None
        assert fresh_alert.analysis_status == AlertStatus.FAILED.value, (
            f"Expected FAILED, got {fresh_alert.analysis_status}"
        )

        # Alert must NOT appear in the paused-waiting list anymore
        paused = await fresh_alert_repo.find_paused_at_workflow_builder()
        paused_ids = {str(a.id) for a in paused}
        assert str(alert.id) not in paused_ids, (
            "Alert still appears in paused list after being marked failed"
        )
    finally:
        await fresh_db.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_alert_status_does_not_affect_other_alerts(db):
    """
    update_alert_status() scopes update by alert_id — other alerts are untouched.
    """
    # Create two independent paused alerts
    alert1, analysis1, tenant1 = await _create_paused_alert(db)
    alert2, analysis2, tenant2 = await _create_paused_alert(db)

    analysis_repo = AlertAnalysisRepository(db.session)

    # Only fail alert1
    await analysis_repo.mark_failed(
        analysis_id=analysis1.id,
        error_message="max retries",
        tenant_id=tenant1,
    )
    await db.update_alert_status(str(alert1.id), "failed")

    # Verify alert2 is unaffected
    await db.session.refresh(alert2)
    await db.session.refresh(analysis2)
    assert alert2.analysis_status == AlertStatus.IN_PROGRESS.value
    assert analysis2.status == "paused"  # V112: paused_workflow_building -> paused
