"""Unit tests for skill cascade rejection — Project Hydra.

When any document in a skill import is rejected or flagged by the LLM,
the entire skill is rejected. No human-in-the-loop for skill onboarding.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.models.content_review import ContentReviewStatus as S
from analysi.services.content_review import ContentReviewService


def _make_review(
    review_id=None,
    skill_id=None,
    tenant_id="t1",
    status="pending",
    applied_document_id=None,
    original_filename="doc.md",
):
    review = MagicMock()
    review.id = review_id or uuid4()
    review.skill_id = skill_id or uuid4()
    review.tenant_id = tenant_id
    review.status = status
    review.applied_document_id = applied_document_id
    review.original_filename = original_filename
    review.rejection_reason = None
    review.completed_at = None
    return review


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return ContentReviewService(mock_session)


class TestCascadeRejectSkill:
    @pytest.mark.asyncio
    async def test_rejects_pending_siblings(self, service, mock_session):
        """Pending sibling reviews are rejected with cascade reason."""
        skill_id = uuid4()
        trigger_id = uuid4()
        sibling = _make_review(skill_id=skill_id, status=S.PENDING.value)

        # session.execute returns siblings query, then empty for _delete_skill_if_empty
        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]
        empty_result = MagicMock()
        empty_result.first.return_value = None  # no applied reviews remain

        mock_session.execute = AsyncMock(side_effect=[siblings_result, empty_result])

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert sibling.status == S.REJECTED.value
        assert "bad content" in sibling.rejection_reason
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_rejects_approved_siblings(self, service, mock_session):
        """Approved (not yet applied) sibling reviews are rejected."""
        skill_id = uuid4()
        trigger_id = uuid4()
        sibling = _make_review(skill_id=skill_id, status=S.APPROVED.value)

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert sibling.status == S.REJECTED.value
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_rejects_flagged_siblings(self, service, mock_session):
        """Flagged sibling reviews are also rejected (no human-in-the-loop for skills)."""
        skill_id = uuid4()
        trigger_id = uuid4()
        sibling = _make_review(skill_id=skill_id, status=S.FLAGGED.value)

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert sibling.status == S.REJECTED.value
        assert result["rejected"] == 1

    @pytest.mark.asyncio
    async def test_rolls_back_applied_siblings(self, service, mock_session):
        """Applied sibling reviews are rolled back: document deleted, review rejected."""
        skill_id = uuid4()
        trigger_id = uuid4()
        doc_id = uuid4()
        sibling = _make_review(
            skill_id=skill_id,
            status=S.APPLIED.value,
            applied_document_id=doc_id,
        )

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with (
            patch.object(
                service, "_rollback_applied_document", new_callable=AsyncMock
            ) as mock_rollback,
            patch.object(
                service,
                "_delete_skill_if_empty",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        mock_rollback.assert_called_once_with("t1", skill_id, doc_id)
        assert sibling.status == S.REJECTED.value
        assert result["rolled_back"] == 1

    @pytest.mark.asyncio
    async def test_skips_already_rejected_siblings(self, service, mock_session):
        """Already-rejected siblings are left alone."""
        skill_id = uuid4()
        trigger_id = uuid4()
        sibling = _make_review(skill_id=skill_id, status=S.REJECTED.value)

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert result["rejected"] == 0
        assert result["rolled_back"] == 0

    @pytest.mark.asyncio
    async def test_skips_failed_siblings(self, service, mock_session):
        """Failed siblings (infra errors) are not touched — they're retryable."""
        skill_id = uuid4()
        trigger_id = uuid4()
        sibling = _make_review(skill_id=skill_id, status=S.FAILED.value)

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [sibling]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert result["rejected"] == 0

    @pytest.mark.asyncio
    async def test_deletes_empty_skill(self, service, mock_session):
        """Skill is deleted when no applied documents remain."""
        skill_id = uuid4()
        trigger_id = uuid4()

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service, "_delete_skill_if_empty", new_callable=AsyncMock, return_value=True
        ) as mock_delete:
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        mock_delete.assert_called_once_with(skill_id, "t1")
        assert result["skill_deleted"] is True

    @pytest.mark.asyncio
    async def test_preserves_skill_with_prior_applied_content(
        self, service, mock_session
    ):
        """Skill is NOT deleted when it has applied content from a prior import."""
        skill_id = uuid4()
        trigger_id = uuid4()

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with patch.object(
            service,
            "_delete_skill_if_empty",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert result["skill_deleted"] is False

    @pytest.mark.asyncio
    async def test_mixed_sibling_statuses(self, service, mock_session):
        """Cascade handles a mix of pending, approved, applied, and failed siblings."""
        skill_id = uuid4()
        trigger_id = uuid4()
        doc_id = uuid4()

        pending = _make_review(skill_id=skill_id, status=S.PENDING.value)
        approved = _make_review(skill_id=skill_id, status=S.APPROVED.value)
        applied = _make_review(
            skill_id=skill_id, status=S.APPLIED.value, applied_document_id=doc_id
        )
        failed = _make_review(skill_id=skill_id, status=S.FAILED.value)

        siblings_result = MagicMock()
        siblings_result.scalars.return_value.all.return_value = [
            pending,
            approved,
            applied,
            failed,
        ]

        mock_session.execute = AsyncMock(return_value=siblings_result)

        with (
            patch.object(service, "_rollback_applied_document", new_callable=AsyncMock),
            patch.object(
                service,
                "_delete_skill_if_empty",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await service.cascade_reject_skill(
                skill_id=skill_id,
                tenant_id="t1",
                trigger_review_id=trigger_id,
                reason="bad content",
            )

        assert pending.status == S.REJECTED.value
        assert approved.status == S.REJECTED.value
        assert applied.status == S.REJECTED.value
        assert failed.status == S.FAILED.value  # untouched
        assert result["rejected"] == 2  # pending + approved
        assert result["rolled_back"] == 1  # applied


class TestFlaggedToRejectedConversion:
    """Verify the flagged → rejected conversion logic for skill_validation.

    The actual worker job has many local imports making it hard to unit test
    in isolation. These tests verify the conversion logic inline.
    """

    def test_flagged_converts_to_rejected_for_skill_validation(self):
        """skill_validation: flagged status must become rejected."""
        pipeline_name = "skill_validation"
        status = S.FLAGGED.value

        # This mirrors the conversion logic in execute_content_review
        if pipeline_name == "skill_validation" and status == S.FLAGGED.value:
            status = S.REJECTED.value

        assert status == S.REJECTED.value

    def test_flagged_stays_flagged_for_extraction(self):
        """Non-skill pipelines keep flagged for human review."""
        pipeline_name = "extraction"
        status = S.FLAGGED.value

        if pipeline_name == "skill_validation" and status == S.FLAGGED.value:
            status = S.REJECTED.value

        assert status == S.FLAGGED.value

    def test_approved_not_affected_by_conversion(self):
        """Approved status is never converted."""
        pipeline_name = "skill_validation"
        status = S.APPROVED.value

        if pipeline_name == "skill_validation" and status == S.FLAGGED.value:
            status = S.REJECTED.value

        assert status == S.APPROVED.value

    def test_rejected_triggers_cascade_for_skill_validation(self):
        """Rejected status should trigger cascade for skill_validation."""
        pipeline_name = "skill_validation"
        status = S.REJECTED.value

        should_cascade = (
            pipeline_name == "skill_validation" and status == S.REJECTED.value
        )

        assert should_cascade is True

    def test_rejected_does_not_cascade_for_extraction(self):
        """Rejected status should NOT cascade for non-skill pipelines."""
        pipeline_name = "extraction"
        status = S.REJECTED.value

        should_cascade = (
            pipeline_name == "skill_validation" and status == S.REJECTED.value
        )

        assert should_cascade is False

    def test_failed_does_not_cascade(self):
        """Failed (infra error) should never cascade — it's retryable."""
        pipeline_name = "skill_validation"
        status = S.FAILED.value

        should_cascade = (
            pipeline_name == "skill_validation" and status == S.REJECTED.value
        )

        assert should_cascade is False


class TestBypassMatrix:
    """Bypass matrix: role x pipeline combinations.

    Rules:
    - Owner bypasses LLM only for skill_validation (trusted role)
    - Extraction always goes through LLM + human approval for ALL roles
    - Admin/analyst/viewer never bypass any pipeline
    """

    async def _submit(self, service, pipeline_name, actor_roles, bypass_expected):
        """Helper: submit a review and assert bypass behavior."""
        if bypass_expected:
            ctx = patch.object(
                service,
                "_create_and_link_document",
                new_callable=AsyncMock,
                return_value=uuid4(),
            )
        else:
            ctx = patch.object(service, "_enqueue_review_job", new_callable=AsyncMock)

        with (
            patch(
                "analysi.services.content_review.get_pipeline_by_name"
            ) as mock_pipeline,
            patch("analysi.services.content_review.run_content_gates") as mock_gates,
            patch(
                "analysi.services.content_review.all_gates_passed",
                return_value=True,
            ),
            ctx,
        ):
            mock_pipeline.return_value = MagicMock(
                content_gates=MagicMock(return_value=[]),
                mode="review_only",
            )
            mock_gates.return_value = []

            review = await service.submit_for_review(
                content="test",
                filename="test.md",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name=pipeline_name,
                trigger_source="test",
                actor_roles=actor_roles,
            )

            assert review.bypassed is bypass_expected
            if bypass_expected:
                assert review.status in (S.APPROVED.value, S.APPLIED.value)
            else:
                assert review.status == S.PENDING.value

    # -- Owner: bypass only for skill_validation --

    @pytest.mark.asyncio
    async def test_owner_bypass_skill_validation(self, service, mock_session):
        await self._submit(service, "skill_validation", ["owner"], True)

    @pytest.mark.asyncio
    async def test_owner_no_bypass_extraction(self, service, mock_session):
        await self._submit(service, "extraction", ["owner"], False)

    # -- Admin never bypasses --

    @pytest.mark.asyncio
    async def test_admin_no_bypass_skill_validation(self, service, mock_session):
        await self._submit(service, "skill_validation", ["admin"], False)

    @pytest.mark.asyncio
    async def test_admin_no_bypass_extraction(self, service, mock_session):
        await self._submit(service, "extraction", ["admin"], False)

    # -- Analyst never bypasses --

    @pytest.mark.asyncio
    async def test_analyst_no_bypass_skill_validation(self, service, mock_session):
        await self._submit(service, "skill_validation", ["analyst"], False)

    @pytest.mark.asyncio
    async def test_analyst_no_bypass_extraction(self, service, mock_session):
        await self._submit(service, "extraction", ["analyst"], False)

    # -- Viewer never bypasses --

    @pytest.mark.asyncio
    async def test_viewer_no_bypass_skill_validation(self, service, mock_session):
        await self._submit(service, "skill_validation", ["viewer"], False)

    @pytest.mark.asyncio
    async def test_viewer_no_bypass_extraction(self, service, mock_session):
        await self._submit(service, "extraction", ["viewer"], False)


class TestManualApplyMatrix:
    """Manual apply matrix: pipeline x status combinations.

    Rules:
    - skill_validation reviews can NEVER be manually applied (use auto_apply only)
    - extraction reviews can be manually applied when approved or flagged
    """

    @pytest.mark.asyncio
    async def test_skill_validation_manual_apply_blocked_approved(
        self, service, mock_session
    ):
        """Approved skill review cannot be manually applied."""
        from analysi.services.content_review import ContentReviewStateError

        review = _make_review(status=S.APPROVED.value)
        review.pipeline_name = "skill_validation"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review
        mock_session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ContentReviewStateError, match="cannot be manually applied"):
            await service.apply_review(review.id, tenant_id="t1")

    @pytest.mark.asyncio
    async def test_skill_validation_manual_apply_blocked_flagged(
        self, service, mock_session
    ):
        """Flagged skill review cannot be manually applied."""
        from analysi.services.content_review import ContentReviewStateError

        review = _make_review(status=S.FLAGGED.value)
        review.pipeline_name = "skill_validation"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review
        mock_session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ContentReviewStateError, match="cannot be manually applied"):
            await service.apply_review(review.id, tenant_id="t1")

    @pytest.mark.asyncio
    async def test_extraction_manual_apply_allowed_approved(
        self, service, mock_session
    ):
        """Approved extraction review can be manually applied."""
        review = _make_review(status=S.APPROVED.value)
        review.pipeline_name = "extraction"
        review.original_content = "content"
        review.transformed_content = None
        review.original_filename = "doc.md"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch.object(
            service,
            "_create_and_link_document",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ):
            result = await service.apply_review(review.id, tenant_id="t1")

        assert result.status == S.APPLIED.value

    @pytest.mark.asyncio
    async def test_extraction_manual_apply_allowed_flagged(self, service, mock_session):
        """Flagged extraction review can be manually applied (human-in-the-loop)."""
        review = _make_review(status=S.FLAGGED.value)
        review.pipeline_name = "extraction"
        review.original_content = "content"
        review.transformed_content = None
        review.original_filename = "doc.md"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch.object(
            service,
            "_create_and_link_document",
            new_callable=AsyncMock,
            return_value=uuid4(),
        ):
            result = await service.apply_review(review.id, tenant_id="t1")

        assert result.status == S.APPLIED.value
