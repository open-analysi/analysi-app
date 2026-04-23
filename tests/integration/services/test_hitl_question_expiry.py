"""
Integration test for HITL question expiry through real asyncpg → PostgreSQL.

Exercises the code path that failed in production: HITLQuestionRepository
queries against the partitioned hitl_questions table via asyncpg prepared
statements. Covers find_expired(), mark_expired(), find_pending_by_analysis_id(),
and the reconciliation function mark_expired_hitl_paused_analyses().

Regression test for hitl_question_expiry_check_failed.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from analysi.constants import HITLQuestionConstants
from analysi.models.hitl_question import HITLQuestion
from analysi.repositories.hitl_repository import HITLQuestionRepository


def _make_question(
    tenant_id: str,
    *,
    status: str = "pending",
    timeout_offset_hours: float = -1,
    analysis_id: uuid.UUID | None = None,
) -> HITLQuestion:
    """Build a HITLQuestion with sensible defaults for expiry tests."""
    now = datetime.now(UTC)
    return HITLQuestion(
        id=uuid.uuid4(),
        created_at=now - timedelta(hours=2),
        tenant_id=tenant_id,
        question_ref=f"ref-{uuid.uuid4().hex[:8]}",
        channel=f"C-{uuid.uuid4().hex[:8]}",
        question_text="Block this IP?",
        options=[{"value": "Block"}, {"value": "Ignore"}],
        status=status,
        timeout_at=now + timedelta(hours=timeout_offset_hours),
        task_run_id=uuid.uuid4(),
        analysis_id=analysis_id,
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.kind_ci
class TestHITLQuestionExpiryDB:
    """Exercises HITLQuestionRepository queries through real asyncpg.

    These tests would have caught the hitl_question_expiry_check_failed
    error: StrEnum parameters in prepared statements and prepared statement
    cache invalidation on the partitioned hitl_questions table.
    """

    async def test_find_expired_returns_timed_out_questions(
        self, integration_test_session
    ):
        """find_expired() retrieves pending questions past their timeout_at."""
        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"

        expired_q = _make_question(tenant_id, timeout_offset_hours=-1)
        not_expired_q = _make_question(tenant_id, timeout_offset_hours=+2)
        already_answered_q = _make_question(
            tenant_id, status="answered", timeout_offset_hours=-1
        )

        db.add_all([expired_q, not_expired_q, already_answered_q])
        await db.commit()

        repo = HITLQuestionRepository(db)
        expired = await repo.find_expired()

        expired_ids = {q.id for q in expired}
        assert expired_q.id in expired_ids
        assert not_expired_q.id not in expired_ids
        assert already_answered_q.id not in expired_ids

    async def test_find_expired_returns_empty_when_none(self, integration_test_session):
        """find_expired() returns [] when no expired questions exist."""
        repo = HITLQuestionRepository(integration_test_session)
        expired = await repo.find_expired()
        assert expired == [] or all(q.timeout_at < datetime.now(UTC) for q in expired)

    async def test_mark_expired_transitions_pending_to_expired(
        self, integration_test_session
    ):
        """mark_expired() atomically transitions pending → expired."""
        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"

        question = _make_question(tenant_id, timeout_offset_hours=-1)
        db.add(question)
        await db.commit()

        repo = HITLQuestionRepository(db)
        result = repo.mark_expired(question.id)
        success = await result
        await db.commit()

        assert success is True

        # Verify via fresh query
        reloaded = await repo.get_by_id(question.id)
        assert reloaded is not None
        assert reloaded.status == HITLQuestionConstants.Status.EXPIRED

    async def test_mark_expired_ignores_already_answered(
        self, integration_test_session
    ):
        """mark_expired() returns False for non-pending questions."""
        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"

        question = _make_question(tenant_id, status="answered", timeout_offset_hours=-1)
        db.add(question)
        await db.commit()

        repo = HITLQuestionRepository(db)
        success = await repo.mark_expired(question.id)
        assert success is False

    async def test_find_pending_by_analysis_id(self, integration_test_session):
        """find_pending_by_analysis_id() matches on analysis_id + status=pending."""
        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"
        analysis_id = uuid.uuid4()

        pending_q = _make_question(tenant_id, analysis_id=analysis_id)
        expired_q = _make_question(tenant_id, status="expired", analysis_id=analysis_id)
        other_analysis_q = _make_question(tenant_id, analysis_id=uuid.uuid4())

        db.add_all([pending_q, expired_q, other_analysis_q])
        await db.commit()

        repo = HITLQuestionRepository(db)
        found = await repo.find_pending_by_analysis_id(analysis_id)

        assert found is not None
        assert found.id == pending_q.id

    async def test_record_answer_transitions_pending_to_answered(
        self, integration_test_session
    ):
        """record_answer() atomically sets status, answer, answered_by, answered_at."""
        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"

        question = _make_question(tenant_id)
        db.add(question)
        await db.commit()

        repo = HITLQuestionRepository(db)
        success = await repo.record_answer(question.id, "Block", "U-analyst-1")
        await db.commit()

        assert success is True

        reloaded = await repo.get_by_id(question.id)
        assert reloaded.status == HITLQuestionConstants.Status.ANSWERED
        assert reloaded.answer == "Block"
        assert reloaded.answered_by == "U-analyst-1"
        assert reloaded.answered_at is not None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.kind_ci
class TestHITLReconciliationExpiry:
    """Test mark_expired_hitl_paused_analyses() against real PostgreSQL.

    Exercises the full reconciliation code path that calls find_expired()
    and mark_expired() through the repository layer.
    """

    async def test_reconciliation_expires_timed_out_question_and_analysis(
        self, integration_test_session
    ):
        """Full path: expired question → analysis marked failed → alert updated."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )
        from analysi.repositories.alert_repository import (
            AlertAnalysisRepository,
            AlertRepository,
        )

        db = integration_test_session
        tenant_id = f"test-hitl-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        paused_at = now - timedelta(hours=30)

        from analysi.models.alert import Alert, AlertAnalysis

        # Alert stays in_progress (valid per CHECK constraint).
        # The paused_human_review status lives on AlertAnalysis, not Alert.
        alert = Alert(
            tenant_id=tenant_id,
            human_readable_id=f"HITL-{uuid.uuid4().hex[:6]}",
            title="Test HITL alert",
            triggering_event_time=now,
            severity="high",
            raw_data='{"test": true}',
            raw_data_hash=f"hash-{uuid.uuid4().hex[:8]}",
            raw_data_hash_algorithm="SHA-256",
            finding_info={},
            ocsf_metadata={},
            severity_id=4,
            status_id=1,
            analysis_status="in_progress",
        )
        db.add(alert)
        await db.flush()

        # AlertAnalysis is paused_human_review (no CHECK constraint on this table)
        analysis = AlertAnalysis(
            tenant_id=tenant_id,
            alert_id=alert.id,
            status="paused_human_review",
            created_at=paused_at,
            updated_at=paused_at,
        )
        db.add(analysis)
        await db.flush()

        question = _make_question(
            tenant_id,
            timeout_offset_hours=-2,
            analysis_id=analysis.id,
        )
        db.add(question)
        await db.commit()

        # Save IDs before reconciliation commits (which detaches objects)
        question_id = question.id

        # Run the reconciliation function
        analysis_repo = AlertAnalysisRepository(db)
        alert_repo = AlertRepository(db)
        hitl_repo = HITLQuestionRepository(db)

        count = await mark_expired_hitl_paused_analyses(
            analysis_repo,
            alert_repo,
            timeout_hours=24,
            hitl_repo=hitl_repo,
        )

        # The question was expired AND the analysis was paused > 24h
        assert count >= 1

        # Verify question was marked expired
        db.expire_all()
        reloaded_q = await hitl_repo.get_by_id(question_id)
        assert reloaded_q.status == "expired"
