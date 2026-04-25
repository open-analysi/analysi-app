"""State machine corner-case tests for ContentReviewService.

Tests every valid and invalid state transition:
  submit → pending/approved(bypass)
  pending → approved/flagged/failed (complete)
  pending → rejected (reject)
  approved/flagged → applied (apply)
  approved/flagged → rejected (reject)
  failed → failed (idempotent via complete)

Blocked transitions:
  applied/rejected → anything (terminal)
  non-pending → approved/flagged (complete, unless target=failed)
  pending/failed → applied (apply)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.content_review import (
    ContentReviewService,
    ContentReviewStateError,
)


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return ContentReviewService(mock_session)


def _mock_review(status: str) -> MagicMock:
    """Create a mock review with a given status."""
    review = MagicMock()
    review.status = status
    review.skill_id = uuid4()
    review.original_filename = "test.md"
    review.original_content = "test content"
    review.transformed_content = None
    return review


class TestCompleteReviewStateGuard:
    """complete_review: pending → approved/flagged/failed only."""

    @pytest.mark.asyncio
    async def test_complete_pending_to_approved(self, service):
        review = _mock_review("pending")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            result = await service.complete_review(
                review_id=uuid4(), pipeline_result={}, status="approved"
            )
        assert result.status == "approved"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_pending_to_flagged(self, service):
        review = _mock_review("pending")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            result = await service.complete_review(
                review_id=uuid4(), pipeline_result={}, status="flagged"
            )
        assert result.status == "flagged"

    @pytest.mark.asyncio
    async def test_complete_pending_to_failed(self, service):
        review = _mock_review("pending")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={},
                status="failed",
                error_message="timeout",
            )
        assert result.status == "failed"
        assert result.error_message == "timeout"

    @pytest.mark.asyncio
    async def test_complete_approved_to_approved_blocked(self, service):
        """Cannot complete an already-approved review to approved."""
        review = _mock_review("approved")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            with pytest.raises(ContentReviewStateError, match="pending"):
                await service.complete_review(
                    review_id=uuid4(), pipeline_result={}, status="approved"
                )

    @pytest.mark.asyncio
    async def test_complete_flagged_to_approved_blocked(self, service):
        """Cannot re-complete a flagged review."""
        review = _mock_review("flagged")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            with pytest.raises(ContentReviewStateError):
                await service.complete_review(
                    review_id=uuid4(), pipeline_result={}, status="approved"
                )

    @pytest.mark.asyncio
    async def test_complete_applied_to_approved_blocked(self, service):
        """Terminal state: applied cannot be re-completed."""
        review = _mock_review("applied")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            with pytest.raises(ContentReviewStateError):
                await service.complete_review(
                    review_id=uuid4(), pipeline_result={}, status="approved"
                )

    @pytest.mark.asyncio
    async def test_complete_rejected_to_approved_blocked(self, service):
        """Terminal state: rejected cannot be re-completed."""
        review = _mock_review("rejected")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            with pytest.raises(ContentReviewStateError):
                await service.complete_review(
                    review_id=uuid4(), pipeline_result={}, status="approved"
                )

    @pytest.mark.asyncio
    async def test_complete_failed_to_failed_idempotent(self, service):
        """Error recovery: marking a failed review as failed again is allowed."""
        review = _mock_review("failed")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={},
                status="failed",
                error_message="retry also failed",
            )
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_complete_approved_to_failed_allowed(self, service):
        """Error recovery: marking an approved review as failed (worker error)."""
        review = _mock_review("approved")
        with patch.object(
            service, "_get_review_by_id", new_callable=AsyncMock, return_value=review
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={},
                status="failed",
                error_message="post-approval error",
            )
        assert result.status == "failed"


class TestApplyReviewStateGuard:
    """apply_review: only from approved/flagged."""

    @pytest.mark.asyncio
    async def test_apply_from_approved(self, service):
        review = _mock_review("approved")
        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=uuid4(),
            ),
        ):
            result = await service.apply_review(uuid4(), tenant_id="t1")
        assert result.status == "applied"
        assert result.applied_at is not None

    @pytest.mark.asyncio
    async def test_apply_from_flagged(self, service):
        """Flagged reviews can be applied (human override)."""
        review = _mock_review("flagged")
        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=review,
            ),
            patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=uuid4(),
            ),
        ):
            result = await service.apply_review(uuid4(), tenant_id="t1")
        assert result.status == "applied"

    @pytest.mark.asyncio
    async def test_apply_from_pending_blocked(self, service):
        review = _mock_review("pending")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError, match="approved.*flagged"):
                await service.apply_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_apply_from_failed_blocked(self, service):
        review = _mock_review("failed")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.apply_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_apply_from_applied_blocked(self, service):
        """Terminal: can't apply twice."""
        review = _mock_review("applied")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.apply_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_apply_from_rejected_blocked(self, service):
        """Terminal: rejected cannot be applied."""
        review = _mock_review("rejected")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.apply_review(uuid4(), tenant_id="t1")


class TestRejectReviewStateGuard:
    """reject_review: from pending/approved/flagged."""

    @pytest.mark.asyncio
    async def test_reject_from_pending(self, service):
        """User cancels before worker finishes."""
        review = _mock_review("pending")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            result = await service.reject_review(
                uuid4(), tenant_id="t1", reason="cancel"
            )
        assert result.status == "rejected"
        assert result.rejection_reason == "cancel"

    @pytest.mark.asyncio
    async def test_reject_from_approved(self, service):
        """User overrides auto-approval."""
        review = _mock_review("approved")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            result = await service.reject_review(uuid4(), tenant_id="t1")
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_reject_from_flagged(self, service):
        review = _mock_review("flagged")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            result = await service.reject_review(
                uuid4(), tenant_id="t1", reason="bad content"
            )
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_reject_from_failed_blocked(self, service):
        """Failed reviews cannot be rejected (stuck state — known gap)."""
        review = _mock_review("failed")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.reject_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_reject_from_applied_blocked(self, service):
        review = _mock_review("applied")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.reject_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_reject_from_rejected_blocked(self, service):
        review = _mock_review("rejected")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.reject_review(uuid4(), tenant_id="t1")

    @pytest.mark.asyncio
    async def test_reject_without_reason(self, service):
        """Reason is optional."""
        review = _mock_review("approved")
        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=review,
        ):
            result = await service.reject_review(uuid4(), tenant_id="t1")
        assert result.rejection_reason is None


class TestBypassEdgeCases:
    """Edge cases for owner bypass path."""

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    @patch.object(
        ContentReviewService,
        "_create_and_link_document",
        new_callable=AsyncMock,
        return_value=uuid4(),
    )
    async def test_owner_bypass_does_not_enqueue(
        self, mock_create_doc, mock_enqueue, mock_get_pipeline, service
    ):
        """Owner bypass auto-applies WITHOUT enqueueing."""
        pipeline = MagicMock()
        pipeline.mode = "review"
        check = MagicMock(side_effect=lambda c, f: [])
        check.__name__ = "mock_check"
        pipeline.content_gates.return_value = [check]
        mock_get_pipeline.return_value = pipeline

        review = await service.submit_for_review(
            content="safe",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="skill_validation",
            trigger_source="test",
            actor_roles=["owner"],
        )

        assert review.status == "applied"
        assert review.bypassed is True
        assert review.completed_at is not None
        mock_enqueue.assert_not_called()
        mock_create_doc.assert_called_once()

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_empty_roles_does_not_bypass(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """No roles = no bypass."""
        pipeline = MagicMock()
        pipeline.mode = "review"
        check = MagicMock(side_effect=lambda c, f: [])
        check.__name__ = "mock_check"
        pipeline.content_gates.return_value = [check]
        mock_get_pipeline.return_value = pipeline

        review = await service.submit_for_review(
            content="safe",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test",
            trigger_source="test",
            actor_roles=[],
        )

        assert review.status == "pending"
        assert review.bypassed is False

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_none_roles_does_not_bypass(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """None roles = no bypass."""
        pipeline = MagicMock()
        pipeline.mode = "review"
        check = MagicMock(side_effect=lambda c, f: [])
        check.__name__ = "mock_check"
        pipeline.content_gates.return_value = [check]
        mock_get_pipeline.return_value = pipeline

        review = await service.submit_for_review(
            content="safe",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test",
            trigger_source="test",
            actor_roles=None,
        )

        assert review.status == "pending"
        assert review.bypassed is False
