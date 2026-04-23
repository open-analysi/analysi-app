"""Integration tests for content review reconciliation — stuck review recovery.

Verifies that reconcile_stuck_content_reviews finds pending reviews older
than the timeout threshold and marks them as failed.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.alert_analysis.jobs.content_review import (
    reconcile_stuck_content_reviews,
)
from analysi.models.content_review import ContentReview, ContentReviewStatus
from analysi.schemas.skill import SkillCreate
from analysi.services.knowledge_module import KnowledgeModuleService


async def _create_test_skill(session: AsyncSession, tenant_id: str, suffix: str):
    km_service = KnowledgeModuleService(session)
    skill = await km_service.create_skill(
        tenant_id,
        SkillCreate(
            name=f"Test Skill {suffix}",
            cy_name=f"test_skill_{suffix}",
            description="Skill for reconciliation tests",
        ),
    )
    await session.flush()
    return skill.component.id


def _make_review(
    tenant_id: str,
    skill_id,
    status: str = "pending",
    created_minutes_ago: int = 0,
) -> ContentReview:
    ts = datetime.now(UTC) - timedelta(minutes=created_minutes_ago)
    return ContentReview(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        skill_id=skill_id,
        pipeline_name="skill_validation",
        pipeline_mode="review",
        trigger_source="test",
        original_filename="test.md",
        original_content="# Test",
        content_gates_passed=True,
        status=status,
        created_at=ts,
        updated_at=ts,
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestReconcileStuckContentReviews:
    @pytest_asyncio.fixture
    async def setup(self, integration_test_session: AsyncSession):
        suffix = uuid.uuid4().hex[:8]
        tenant_id = f"test-reconcile-{suffix}"
        skill_id = await _create_test_skill(integration_test_session, tenant_id, suffix)
        await integration_test_session.commit()
        return {
            "session": integration_test_session,
            "tenant_id": tenant_id,
            "skill_id": skill_id,
        }

    async def test_marks_old_pending_reviews_as_failed(self, setup):
        """Reviews pending longer than threshold are marked failed."""
        session = setup["session"]
        review = _make_review(
            setup["tenant_id"],
            setup["skill_id"],
            status="pending",
            created_minutes_ago=30,  # Well past 20-min threshold
        )
        session.add(review)
        await session.commit()

        marked = await reconcile_stuck_content_reviews()

        assert marked >= 1

        await session.refresh(review)
        assert review.status == ContentReviewStatus.FAILED.value
        assert "stuck in pending" in review.error_message

    async def test_ignores_recent_pending_reviews(self, setup):
        """Reviews created recently should NOT be marked failed."""
        session = setup["session"]
        review = _make_review(
            setup["tenant_id"],
            setup["skill_id"],
            status="pending",
            created_minutes_ago=5,  # Recent — should be left alone
        )
        session.add(review)
        await session.commit()

        await reconcile_stuck_content_reviews()

        await session.refresh(review)
        assert review.status == ContentReviewStatus.PENDING.value

    async def test_ignores_non_pending_reviews(self, setup):
        """Reviews in approved/flagged/applied/failed states are untouched."""
        session = setup["session"]

        for status in ["approved", "flagged", "applied", "failed"]:
            review = _make_review(
                setup["tenant_id"],
                setup["skill_id"],
                status=status,
                created_minutes_ago=60,  # Old but not pending
            )
            session.add(review)

        await session.commit()

        marked = await reconcile_stuck_content_reviews()
        assert marked == 0
