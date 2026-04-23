"""Unit tests for ContentReviewService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.content_review import (
    ContentReviewGateError,
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


def _make_mock_pipeline(name="test_pipeline", mode="review", gates_pass=True):
    """Create a mock pipeline that passes or fails content gates."""
    pipeline = MagicMock()
    pipeline.name = name
    pipeline.mode = mode

    if gates_pass:
        check = MagicMock(side_effect=lambda content, filename: [])
        check.__name__ = "mock_check"
    else:
        check = MagicMock(side_effect=lambda content, filename: ["error found"])
        check.__name__ = "mock_check"

    pipeline.content_gates.return_value = [check]
    return pipeline


class TestSubmitForReview:
    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_submit_runs_content_gates(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """Content gates are called with content and filename."""
        pipeline = _make_mock_pipeline(gates_pass=True)
        mock_get_pipeline.return_value = pipeline

        await service.submit_for_review(
            content="test content",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test_pipeline",
            trigger_source="ku_create",
        )

        pipeline.content_gates.assert_called_once()

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    async def test_submit_rejects_on_gate_failure(self, mock_get_pipeline, service):
        """Raises ContentReviewGateError when content gates fail."""
        pipeline = _make_mock_pipeline(gates_pass=False)
        mock_get_pipeline.return_value = pipeline

        with pytest.raises(ContentReviewGateError):
            await service.submit_for_review(
                content="bad content",
                filename="test.md",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name="test_pipeline",
                trigger_source="ku_create",
            )

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_submit_creates_pending_record(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """Creates a record with status=pending for non-owner roles."""
        pipeline = _make_mock_pipeline(gates_pass=True)
        mock_get_pipeline.return_value = pipeline

        review = await service.submit_for_review(
            content="test content",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test_pipeline",
            trigger_source="ku_create",
            actor_roles=["analyst"],
        )

        assert review.status == "pending"
        assert review.bypassed is False
        service.session.add.assert_called_once()

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_submit_enqueues_arq_job(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """Enqueue is called with review_id after record creation."""
        pipeline = _make_mock_pipeline(gates_pass=True)
        mock_get_pipeline.return_value = pipeline

        await service.submit_for_review(
            content="test content",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test_pipeline",
            trigger_source="ku_create",
            actor_roles=["admin"],
        )

        mock_enqueue.assert_called_once()


class TestCompleteReview:
    @pytest.mark.asyncio
    async def test_complete_sets_approved(self, service):
        """Status set to approved when pipeline passes."""
        mock_review = MagicMock()
        mock_review.status = "pending"

        with patch.object(
            service,
            "_get_review_by_id",
            new_callable=AsyncMock,
            return_value=mock_review,
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={"relevance": True},
                status="approved",
                summary="Looks good",
            )

        assert result.status == "approved"
        assert result.summary == "Looks good"

    @pytest.mark.asyncio
    async def test_complete_sets_flagged(self, service):
        """Status set to flagged when pipeline flags issues."""
        mock_review = MagicMock()
        mock_review.status = "pending"

        with patch.object(
            service,
            "_get_review_by_id",
            new_callable=AsyncMock,
            return_value=mock_review,
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={"safe": False},
                status="flagged",
                summary="Safety concerns found",
            )

        assert result.status == "flagged"

    @pytest.mark.asyncio
    async def test_complete_sets_failed(self, service):
        """Status set to failed on pipeline error."""
        mock_review = MagicMock()
        mock_review.status = "pending"

        with patch.object(
            service,
            "_get_review_by_id",
            new_callable=AsyncMock,
            return_value=mock_review,
        ):
            result = await service.complete_review(
                review_id=uuid4(),
                pipeline_result={},
                status="failed",
                error_message="LLM timeout",
            )

        assert result.status == "failed"
        assert result.error_message == "LLM timeout"


class TestApplyReview:
    @pytest.mark.asyncio
    async def test_apply_sets_applied(self, service):
        """Status transitions to applied, creates document."""
        mock_review = MagicMock()
        mock_review.status = "approved"
        mock_review.skill_id = uuid4()
        mock_review.original_filename = "test.md"
        mock_review.transformed_content = None
        mock_review.original_content = "test content"

        doc_id = uuid4()
        with (
            patch.object(
                service,
                "_get_review_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_review,
            ),
            patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=doc_id,
            ),
        ):
            result = await service.apply_review(review_id=uuid4(), tenant_id="t1")

        assert result.status == "applied"
        assert result.applied_at is not None
        assert result.applied_document_id == doc_id

    @pytest.mark.asyncio
    async def test_apply_rejects_pending(self, service):
        """Cannot apply a pending review."""
        mock_review = MagicMock()
        mock_review.status = "pending"

        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=mock_review,
        ):
            with pytest.raises(ContentReviewStateError):
                await service.apply_review(review_id=uuid4(), tenant_id="t1")


class TestRejectReview:
    @pytest.mark.asyncio
    async def test_reject_sets_rejected(self, service):
        """Status transitions to rejected."""
        mock_review = MagicMock()
        mock_review.status = "flagged"

        with patch.object(
            service,
            "_get_review_for_tenant",
            new_callable=AsyncMock,
            return_value=mock_review,
        ):
            result = await service.reject_review(
                review_id=uuid4(), tenant_id="t1", reason="Not relevant"
            )

        assert result.status == "rejected"
        assert result.rejection_reason == "Not relevant"
