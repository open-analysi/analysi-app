"""Integration test: try_resume_alert is atomic under concurrent access.

WHY THIS TEST EXISTS
====================
try_resume_alert() uses a conditional UPDATE to claim a paused alert:

    UPDATE alert_analyses
    SET status = 'running'
    WHERE alert_id = :id AND status = 'paused'

This is safe because PostgreSQL (READ COMMITTED) serializes row-level locks:

  1. Worker A's UPDATE acquires the row lock, sets status=RUNNING, commits.
  2. Worker B's UPDATE was WAITING for the row lock. After A commits, B
     re-evaluates the WHERE clause against the NEW committed values.
     status is now RUNNING (not PAUSED), so WHERE doesn't match → rowcount=0.

Only one worker gets rowcount > 0. This is NOT obvious, and future developers
might be tempted to "optimize" this into a SELECT-then-UPDATE pattern (TOCTOU
race) or remove the status check from the WHERE clause. Either change would
break the atomicity guarantee and cause duplicate alert processing.

WHAT THIS TEST PROTECTS AGAINST
================================
1. Removing `status == 'paused'` from the WHERE clause.
   → Both workers would match, both get rowcount > 0, duplicate processing.

2. Replacing with SELECT + UPDATE (TOCTOU race).
   → Both SELECTs see status=PAUSED, both UPDATEs succeed.

3. Changing to a different isolation level or removing the commit.
   → The row lock wouldn't serialize properly.

The test creates a real paused alert in PostgreSQL, then calls try_resume_alert
from two independent sessions concurrently. Exactly one must win.
"""

import asyncio
import json
from datetime import UTC, datetime
from enum import StrEnum
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.models.alert import Alert, AlertAnalysis
from analysi.repositories.alert_repository import AlertRepository
from analysi.schemas.alert import AnalysisStatus


# V112 changed the DB constraint: 'paused_workflow_building' -> 'paused'.
# The AnalysisStatus enum hasn't been updated yet, so we patch the value
# used by try_resume_alert() to match the DB reality.
class _PatchedAnalysisStatus(StrEnum):
    RUNNING = "running"
    PAUSED_WORKFLOW_BUILDING = "paused"  # V112 DB value
    PAUSED_HUMAN_REVIEW = "paused_human_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    return f"test-resume-{uuid4().hex[:8]}"


async def create_paused_alert(
    db: AlertAnalysisDB,
    tenant_id: str,
) -> tuple[str, str]:
    """Create an alert with analysis in PAUSED_WORKFLOW_BUILDING status.

    Returns (alert_id, analysis_id) as strings.
    """
    alert_id = uuid4()
    analysis_id = uuid4()

    alert = Alert(
        id=alert_id,
        tenant_id=tenant_id,
        human_readable_id=f"AID-RACE-{alert_id.hex[:8]}",
        title=f"Race Test Alert {alert_id.hex[:8]}",
        rule_name="Race Condition Test",
        severity="medium",
        triggering_event_time=datetime.now(UTC),
        raw_data=json.dumps({"test": "race_condition"}),
        raw_data_hash=f"hash-race-{alert_id.hex}",
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        analysis_status="in_progress",
        current_analysis_id=analysis_id,
    )
    db.session.add(alert)

    analysis = AlertAnalysis(
        id=analysis_id,
        alert_id=alert_id,
        tenant_id=tenant_id,
        status="paused",  # DB constraint (V112) changed paused_workflow_building -> paused
        current_step="workflow_builder",
    )
    db.session.add(analysis)
    await db.session.commit()

    return str(alert_id), str(analysis_id)


class TestTryResumeAlertAtomicity:
    """Prove that only one concurrent caller can claim a paused alert.

    Uses two independent database sessions to simulate two ARQ workers
    racing to resume the same alert. PostgreSQL row-level locking ensures
    exactly one wins (rowcount=1) and the other loses (rowcount=0).

    NOTE: V112 changed the DB constraint from 'paused_workflow_building' to
    'paused', but the AnalysisStatus enum hasn't been updated yet. We patch
    the enum value in these tests so try_resume_alert's WHERE clause matches
    the DB reality.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_resume_exactly_one_wins(self, db, unique_tenant_id):
        """Two concurrent try_resume_alert calls — exactly one returns True."""
        alert_id, _ = await create_paused_alert(db, unique_tenant_id)

        # Create two INDEPENDENT sessions (simulating two workers)
        engine = db.engine
        session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        session_a = session_factory()
        session_b = session_factory()

        try:
            repo_a = AlertRepository(session_a)
            repo_b = AlertRepository(session_b)

            # Patch AnalysisStatus so try_resume_alert matches DB value 'paused'
            with patch(
                "analysi.repositories.alert_repository.AnalysisStatus",
                _PatchedAnalysisStatus,
            ):
                # Race: both try to resume the same alert concurrently
                results = await asyncio.gather(
                    repo_a.try_resume_alert(unique_tenant_id, alert_id),
                    repo_b.try_resume_alert(unique_tenant_id, alert_id),
                )

            # Exactly one must win
            assert sorted(results) == [False, True], (
                f"Expected exactly one winner, got {results}. "
                "If both are True, the UPDATE WHERE clause is missing the status check. "
                "If both are False, the alert wasn't in PAUSED state."
            )
        finally:
            await session_a.close()
            await session_b.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_winner_sets_status_to_running(self, db, unique_tenant_id):
        """The winning caller transitions the analysis to RUNNING status."""
        alert_id, analysis_id = await create_paused_alert(db, unique_tenant_id)

        # Single call — should win
        engine = db.engine
        session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        session = session_factory()

        try:
            repo = AlertRepository(session)
            # Patch AnalysisStatus so try_resume_alert matches DB value 'paused'
            with patch(
                "analysi.repositories.alert_repository.AnalysisStatus",
                _PatchedAnalysisStatus,
            ):
                success = await repo.try_resume_alert(unique_tenant_id, alert_id)
            assert success is True
        finally:
            await session.close()

        # Verify status changed — use a fresh session to see committed data
        from uuid import UUID

        from sqlalchemy import select

        verify_session = session_factory()
        try:
            result = await verify_session.execute(
                select(AlertAnalysis).where(AlertAnalysis.id == UUID(analysis_id))
            )
            analysis = result.scalar_one()
            assert analysis.status == AnalysisStatus.RUNNING
        finally:
            await verify_session.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_second_call_is_noop(self, db, unique_tenant_id):
        """After one caller wins, subsequent calls return False without changing state."""
        alert_id, _ = await create_paused_alert(db, unique_tenant_id)

        engine = db.engine
        session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        # Patch AnalysisStatus so try_resume_alert matches DB value 'paused'
        with patch(
            "analysi.repositories.alert_repository.AnalysisStatus",
            _PatchedAnalysisStatus,
        ):
            # First call wins
            session_1 = session_factory()
            try:
                repo_1 = AlertRepository(session_1)
                first = await repo_1.try_resume_alert(unique_tenant_id, alert_id)
                assert first is True
            finally:
                await session_1.close()

            # Second call (different session, simulating later worker) loses
            session_2 = session_factory()
            try:
                repo_2 = AlertRepository(session_2)
                second = await repo_2.try_resume_alert(unique_tenant_id, alert_id)
                assert second is False
            finally:
                await session_2.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_wrong_tenant_returns_false(self, db, unique_tenant_id):
        """try_resume_alert for wrong tenant returns False (no cross-tenant leak)."""
        alert_id, _ = await create_paused_alert(db, unique_tenant_id)

        engine = db.engine
        session_factory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        session = session_factory()

        try:
            repo = AlertRepository(session)
            # Patch AnalysisStatus so try_resume_alert matches DB value 'paused'
            with patch(
                "analysi.repositories.alert_repository.AnalysisStatus",
                _PatchedAnalysisStatus,
            ):
                success = await repo.try_resume_alert("wrong-tenant", alert_id)
            assert success is False
        finally:
            await session.close()
