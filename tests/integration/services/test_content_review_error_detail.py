"""Integration tests for structured error fields on content reviews.

Verifies that error_code and error_detail persist correctly through
complete_review and retry_review against real PostgreSQL.
"""

import uuid
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.content_review import ContentReviewStatus
from analysi.schemas.skill import SkillCreate
from analysi.services.content_review import ContentReviewService
from analysi.services.knowledge_module import KnowledgeModuleService


async def _create_test_skill(
    session: AsyncSession, tenant_id: str, suffix: str
) -> UUID:
    km_service = KnowledgeModuleService(session)
    skill = await km_service.create_skill(
        tenant_id,
        SkillCreate(
            name=f"Test Skill {suffix}",
            cy_name=f"test_skill_{suffix}",
            description="Skill for error detail tests",
        ),
    )
    await session.flush()
    return skill.component.id


@pytest.mark.asyncio
@pytest.mark.integration
class TestContentReviewErrorDetail:
    """Integration tests for error_code and error_detail on content reviews."""

    @pytest_asyncio.fixture
    async def setup(self, integration_test_session: AsyncSession):
        suffix = uuid.uuid4().hex[:8]
        tenant_id = f"test-cr-err-{suffix}"
        skill_id = await _create_test_skill(integration_test_session, tenant_id, suffix)
        service = ContentReviewService(integration_test_session)
        # Mock ARQ enqueue — no Redis in test environment
        with patch.object(service, "_enqueue_review_job", new_callable=AsyncMock):
            review = await service.submit_for_review(
                content="# Test content",
                filename="test.md",
                skill_id=skill_id,
                tenant_id=tenant_id,
                pipeline_name="skill_validation",
                trigger_source="test",
            )
        await integration_test_session.commit()
        return {
            "session": integration_test_session,
            "service": service,
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "review_id": review.id,
        }

    async def test_complete_review_stores_error_fields(self, setup):
        """complete_review persists error_code and error_detail to DB."""
        service = setup["service"]
        session = setup["session"]

        await service.complete_review(
            review_id=setup["review_id"],
            pipeline_result={},
            status=ContentReviewStatus.FAILED,
            error_message="Pipeline crashed",
            error_code="pipeline_error",
            error_detail={
                "title": "Review processing failed",
                "hint": "Try again later.",
            },
        )
        await session.commit()

        review = await service.get_review(setup["review_id"], setup["tenant_id"])
        assert review.status == "failed"
        assert review.error_code == "pipeline_error"
        assert review.error_detail["title"] == "Review processing failed"
        assert review.error_detail["hint"] == "Try again later."
        assert review.error_message == "Pipeline crashed"

    async def test_retry_clears_error_fields(self, setup):
        """retry_review clears error_code and error_detail."""
        service = setup["service"]
        session = setup["session"]

        # First, fail it
        await service.complete_review(
            review_id=setup["review_id"],
            pipeline_result={},
            status=ContentReviewStatus.FAILED,
            error_message="Timeout",
            error_code="pipeline_timeout",
            error_detail={"title": "Timed out", "hint": "Retry."},
        )
        await session.commit()

        # Then retry (mock enqueue — no Redis in test environment)
        with patch.object(service, "_enqueue_review_job", new_callable=AsyncMock):
            review = await service.retry_review(setup["review_id"], setup["tenant_id"])
        await session.commit()

        assert review.status == "pending"
        assert review.error_code is None
        assert review.error_detail is None
        assert review.error_message is None

    async def test_error_detail_in_response_schema(self, setup):
        """ContentReviewResponse includes error_code and error_detail."""
        from analysi.schemas.content_review import ContentReviewResponse

        service = setup["service"]
        session = setup["session"]

        await service.complete_review(
            review_id=setup["review_id"],
            pipeline_result={},
            status=ContentReviewStatus.FAILED,
            error_message="Bad content",
            error_code="content_gate_violation",
            error_detail={
                "title": "Content policy violation",
                "hint": "Fix the flagged files.",
                "failures": [{"file": "evil.py", "errors": ["dangerous code"]}],
            },
        )
        await session.commit()

        review = await service.get_review(setup["review_id"], setup["tenant_id"])
        resp = ContentReviewResponse.model_validate(review)
        assert resp.error_code == "content_gate_violation"
        assert resp.error_detail["title"] == "Content policy violation"
        assert len(resp.error_detail["failures"]) == 1

    async def test_complete_without_error_fields_leaves_null(self, setup):
        """Completing a review as approved leaves error fields null."""
        service = setup["service"]
        session = setup["session"]

        await service.complete_review(
            review_id=setup["review_id"],
            pipeline_result={"score": 0.95},
            status=ContentReviewStatus.APPROVED,
        )
        await session.commit()

        review = await service.get_review(setup["review_id"], setup["tenant_id"])
        assert review.status == "approved"
        assert review.error_code is None
        assert review.error_detail is None
