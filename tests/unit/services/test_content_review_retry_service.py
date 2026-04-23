"""Unit tests for content review retry — failed → pending re-enqueue."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.models.content_review import ContentReview, ContentReviewStatus
from analysi.services.content_review import (
    ContentReviewService,
    ContentReviewStateError,
)


def _mock_review(status: str = "failed") -> ContentReview:
    review = MagicMock(spec=ContentReview)
    review.id = uuid.uuid4()
    review.tenant_id = "test-tenant"
    review.skill_id = uuid.uuid4()
    review.pipeline_name = "skill_validation"
    review.pipeline_mode = "review"
    review.status = status
    review.error_message = "Pipeline timed out"
    review.pipeline_result = {"error": True}
    review.completed_at = datetime.now(UTC)
    review.actor_user_id = None
    return review


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return ContentReviewService(mock_session)


class TestRetryReview:
    @pytest.mark.asyncio
    async def test_retry_resets_failed_to_pending(self, service):
        """A failed review should be reset to pending."""
        review = _mock_review(status="failed")

        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(service, "_enqueue_review_job", new_callable=AsyncMock),
        ):
            result = await service.retry_review(review.id, "test-tenant")

        assert result.status == ContentReviewStatus.PENDING.value
        assert result.error_message is None
        assert result.pipeline_result is None
        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_retry_enqueues_arq_job(self, service):
        """Retry should re-enqueue the ARQ job."""
        review = _mock_review(status="failed")

        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(
                service, "_enqueue_review_job", new_callable=AsyncMock
            ) as mock_enqueue,
        ):
            await service.retry_review(review.id, "test-tenant")

        mock_enqueue.assert_called_once_with(
            review, "test-tenant", review.pipeline_name, review.actor_user_id
        )

    @pytest.mark.asyncio
    async def test_retry_rejects_non_failed_statuses(self, service):
        """Only failed reviews can be retried."""
        for status in ["pending", "approved", "flagged", "applied", "rejected"]:
            review = _mock_review(status=status)

            with patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ):
                with pytest.raises(ContentReviewStateError, match="Only 'failed'"):
                    await service.retry_review(review.id, "test-tenant")
