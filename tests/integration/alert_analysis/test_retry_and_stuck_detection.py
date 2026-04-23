"""Integration tests for retry loop prevention and stuck alert detection."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.alert_analysis.jobs.reconciliation import (
    mark_stuck_running_alerts_as_failed,
    should_retry_workflow_generation,
)
from analysi.models.alert import Alert, AlertAnalysis
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
)
from analysi.schemas.alert import AlertStatus, AnalysisStatus


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
async def setup_alert_with_analysis(db) -> tuple[Alert, AlertAnalysis, str]:
    """Create a test alert with analysis for retry testing."""
    tenant_id = f"test-retry-{uuid4().hex[:8]}"

    # Create alert directly
    # Alert.analysis_status uses AlertStatus: new, in_progress, completed, failed, cancelled
    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Test Alert for Retry",
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
        analysis_status=AlertStatus.IN_PROGRESS.value,  # Alert-level status
        ingested_at=datetime.now(UTC),
    )
    db.session.add(alert)
    await db.session.flush()

    # Create analysis
    # AlertAnalysis.status uses AnalysisStatus: running, paused_workflow_building, etc.
    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status="paused",  # DB constraint (V112) changed paused_workflow_building -> paused
        started_at=datetime.now(UTC),
        workflow_gen_retry_count=0,
        workflow_gen_last_failure_at=None,
        created_at=datetime.now(UTC),
    )
    db.session.add(analysis)

    # Link alert to analysis
    alert.current_analysis_id = analysis.id
    await db.session.commit()

    return alert, analysis, tenant_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_should_retry_allows_first_attempt(setup_alert_with_analysis):
    """Test that should_retry_workflow_generation allows first attempt."""
    _, analysis, _ = setup_alert_with_analysis

    # First attempt should be allowed
    should_retry, reason = should_retry_workflow_generation(analysis)

    assert should_retry is True
    assert "OK" in reason
    assert "retry 1/" in reason


@pytest.mark.integration
@pytest.mark.asyncio
async def test_increment_retry_count_persists_to_db(db, setup_alert_with_analysis):
    """Test that incrementing retry count is persisted to database."""
    _, analysis, tenant_id = setup_alert_with_analysis

    analysis_repo = AlertAnalysisRepository(db.session)

    # Increment retry count
    await analysis_repo.increment_workflow_gen_retry_count(
        analysis_id=str(analysis.id),
    )
    await db.session.commit()

    # Fetch fresh from database
    fresh_analysis = await analysis_repo.get_by_alert_id(
        tenant_id=tenant_id,
        alert_id=str(analysis.alert_id),
    )

    assert fresh_analysis is not None
    assert fresh_analysis.workflow_gen_retry_count == 1
    assert fresh_analysis.workflow_gen_last_failure_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_failed_persists_to_db(db, setup_alert_with_analysis):
    """Test that marking analysis as failed is persisted to database."""
    _, analysis, tenant_id = setup_alert_with_analysis

    analysis_repo = AlertAnalysisRepository(db.session)

    # Mark as failed (pass UUID directly, not string)
    result = await analysis_repo.mark_failed(
        analysis_id=analysis.id,
        error_message="Test error message",
        tenant_id=tenant_id,
    )
    await db.session.commit()

    # Verify update succeeded
    assert result is True

    # Fetch fresh from database
    fresh_analysis = await analysis_repo.get_by_alert_id(
        tenant_id=tenant_id,
        alert_id=analysis.alert_id,
    )

    assert fresh_analysis is not None
    assert fresh_analysis.status == AnalysisStatus.FAILED.value
    assert "Test error message" in fresh_analysis.error_message


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stuck_alert_detection_finds_old_running_alerts(db):
    """Test that stuck alert detection finds alerts running for too long."""
    tenant_id = f"test-stuck-{uuid4().hex[:8]}"

    # Create an alert that's been running for a long time (simulated via updated_at)
    old_time = datetime.now(UTC) - timedelta(minutes=90)  # 90 minutes ago

    # Alert.analysis_status uses AlertStatus values
    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Stuck Test Alert",
        triggering_event_time=old_time,
        severity="medium",
        rule_name="Stuck Test Rule",
        raw_data=json.dumps({"test": "stuck"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=AlertStatus.IN_PROGRESS.value,  # Alert-level status
        ingested_at=old_time,
    )
    db.session.add(alert)
    await db.session.flush()

    # Create analysis with old updated_at (simulating stuck state)
    # AlertAnalysis.status uses AnalysisStatus values
    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status=AnalysisStatus.RUNNING.value,  # Stuck in running (analysis-level)
        started_at=old_time,
        created_at=old_time,
    )
    # Manually set updated_at to simulate stuck state
    analysis.updated_at = old_time
    db.session.add(analysis)

    alert.current_analysis_id = analysis.id
    await db.session.commit()

    # Force updated_at to be old (SQLAlchemy may override on commit)
    from sqlalchemy import text

    await db.session.execute(
        text("""
            UPDATE alert_analyses
            SET updated_at = :old_time
            WHERE id = :analysis_id AND created_at = :created_at
        """),
        {"old_time": old_time, "analysis_id": str(analysis.id), "created_at": old_time},
    )
    await db.session.commit()

    # Find stuck alerts
    alert_repo = AlertRepository(db.session)
    stuck_results = await alert_repo.find_stuck_running_alerts(
        stuck_threshold_minutes=60
    )

    # Should find the stuck alert
    assert len(stuck_results) >= 1
    found_ids = [str(a.id) for a, _ in stuck_results]
    assert str(alert.id) in found_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stuck_alert_detection_ignores_recent_alerts(db):
    """Test that stuck alert detection ignores recently updated alerts."""
    tenant_id = f"test-recent-{uuid4().hex[:8]}"
    recent_time = datetime.now(UTC) - timedelta(minutes=5)  # Only 5 minutes ago

    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Recent Test Alert",
        triggering_event_time=recent_time,
        severity="low",
        rule_name="Recent Test Rule",
        raw_data=json.dumps({"test": "recent"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=AlertStatus.IN_PROGRESS.value,  # Alert-level status
        ingested_at=recent_time,
    )
    db.session.add(alert)
    await db.session.flush()

    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status=AnalysisStatus.RUNNING.value,  # Analysis-level status
        started_at=recent_time,
        created_at=recent_time,
    )
    db.session.add(analysis)

    alert.current_analysis_id = analysis.id
    await db.session.commit()

    # Find stuck alerts with 60 min threshold
    alert_repo = AlertRepository(db.session)
    stuck_results = await alert_repo.find_stuck_running_alerts(
        stuck_threshold_minutes=60
    )

    # Recent alert should NOT be found (it's only 5 minutes old)
    found_ids = [str(a.id) for a, _ in stuck_results]
    assert str(alert.id) not in found_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_stuck_alert_failed_updates_both_alert_and_analysis(db):
    """Test that marking stuck alert as failed updates both alert and analysis status."""
    tenant_id = f"test-mark-failed-{uuid4().hex[:8]}"
    old_time = datetime.now(UTC) - timedelta(minutes=90)

    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Mark Failed Test Alert",
        triggering_event_time=old_time,
        severity="high",
        rule_name="Mark Failed Test Rule",
        raw_data=json.dumps({"test": "mark_failed"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=AlertStatus.IN_PROGRESS.value,  # Alert-level status
        ingested_at=old_time,
    )
    db.session.add(alert)
    await db.session.flush()

    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status=AnalysisStatus.RUNNING.value,  # Analysis-level status
        started_at=old_time,
        created_at=old_time,
    )
    db.session.add(analysis)

    alert.current_analysis_id = analysis.id
    await db.session.commit()

    # Mark as failed
    alert_repo = AlertRepository(db.session)
    success = await alert_repo.mark_stuck_alert_failed(
        tenant_id=tenant_id,
        alert_id=str(alert.id),
        analysis_id=str(analysis.id),
        error="Test timeout error",
    )

    assert success is True

    # Refresh from database
    await db.session.refresh(alert)
    await db.session.refresh(analysis)

    # Both should be marked as failed
    assert alert.analysis_status == AlertStatus.FAILED.value
    assert analysis.status == AnalysisStatus.FAILED.value
    assert "Test timeout error" in analysis.error_message


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_stuck_detection_marks_alerts_as_failed(db):
    """Integration test for full stuck detection flow via mark_stuck_running_alerts_as_failed."""
    tenant_id = f"test-full-stuck-{uuid4().hex[:8]}"
    old_time = datetime.now(UTC) - timedelta(minutes=90)

    alert = Alert(
        id=uuid4(),
        tenant_id=tenant_id,
        human_readable_id=f"AID-{uuid4().hex[:6]}",
        title="Full Stuck Detection Test",
        triggering_event_time=old_time,
        severity="critical",
        rule_name="Full Stuck Test Rule",
        raw_data=json.dumps({"test": "full_stuck"}),
        raw_data_hash=uuid4().hex,
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status=AlertStatus.IN_PROGRESS.value,  # Alert-level status
        ingested_at=old_time,
    )
    db.session.add(alert)
    await db.session.flush()

    analysis = AlertAnalysis(
        id=uuid4(),
        alert_id=alert.id,
        tenant_id=tenant_id,
        status=AnalysisStatus.RUNNING.value,  # Analysis-level status
        started_at=old_time,
        created_at=old_time,
    )
    db.session.add(analysis)

    alert.current_analysis_id = analysis.id
    await db.session.commit()

    # Force old updated_at
    from sqlalchemy import text

    await db.session.execute(
        text("""
            UPDATE alert_analyses
            SET updated_at = :old_time
            WHERE id = :analysis_id AND created_at = :created_at
        """),
        {"old_time": old_time, "analysis_id": str(analysis.id), "created_at": old_time},
    )
    await db.session.commit()

    # Run the full stuck detection function
    alert_repo = AlertRepository(db.session)
    failed_count = await mark_stuck_running_alerts_as_failed(alert_repo)

    # Should mark at least our test alert as failed
    assert failed_count >= 1

    # Refresh and verify
    await db.session.refresh(analysis)
    assert analysis.status == AnalysisStatus.FAILED.value
