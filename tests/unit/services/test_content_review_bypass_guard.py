"""Bypass guard tests for content review.

These tests protect against privilege escalation. If you're changing bypass
logic, ALL of these tests must still pass.

Security invariant: Only the 'owner' role may bypass the LLM tier.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.content_review import (
    BYPASS_ROLES,
    ContentReviewService,
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


def _make_passing_pipeline():
    pipeline = MagicMock()
    pipeline.name = "test_pipeline"
    pipeline.mode = "review"
    check = MagicMock(side_effect=lambda content, filename: [])
    check.__name__ = "mock_check"
    pipeline.content_gates.return_value = [check]
    return pipeline


class TestBypassGuard:
    def test_permission_map_owner_is_only_bypass_role(self):
        """Bypass roles must be exactly ['owner'] — no other role."""
        assert BYPASS_ROLES == ["owner"]

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_only_owner_can_bypass_content_review(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """viewer, analyst, admin, system → bypass ignored, LLM tier runs."""
        mock_get_pipeline.return_value = _make_passing_pipeline()

        for role in ["viewer", "analyst", "admin", "system"]:
            review = await service.submit_for_review(
                content="test content",
                filename="test.md",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name="test_pipeline",
                trigger_source="ku_create",
                actor_roles=[role],
            )
            assert review.bypassed is False, f"{role} should NOT be able to bypass"
            assert review.status == "pending", f"{role} review should be pending"

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    async def test_owner_bypass_skips_llm_but_runs_gates(
        self, mock_get_pipeline, service
    ):
        """Owner bypass: content gates still run. If gate fails → error raised."""
        pipeline = MagicMock()
        pipeline.name = "test_pipeline"
        pipeline.mode = "review"
        # Content gate that fails
        failing_check = MagicMock(
            side_effect=lambda content, filename: ["malicious import detected"]
        )
        failing_check.__name__ = "python_ast_gate"
        pipeline.content_gates.return_value = [failing_check]
        mock_get_pipeline.return_value = pipeline

        from analysi.services.content_review import ContentReviewGateError

        with pytest.raises(ContentReviewGateError):
            await service.submit_for_review(
                content="import os; os.system('rm -rf /')",
                filename="evil.py",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name="test_pipeline",
                trigger_source="ku_create",
                actor_roles=["owner"],
            )

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    async def test_owner_skill_validation_still_blocked_by_structural_gates(
        self, mock_get_pipeline, service
    ):
        """Owner + skill_validation: structural gates (format, empty, length) still block.

        content_policy_gate and python_ast_gate are skipped for owners, but
        structural violations still reject the content.
        """
        pipeline = MagicMock()
        pipeline.name = "skill_validation"
        pipeline.mode = "review"
        format_check = MagicMock(
            side_effect=lambda c, f: ["File extension '.exe' not allowed"]
        )
        format_check.__name__ = "format_gate"
        pipeline.content_gates.return_value = [format_check]
        mock_get_pipeline.return_value = pipeline

        from analysi.services.content_review import ContentReviewGateError

        with pytest.raises(ContentReviewGateError):
            await service.submit_for_review(
                content="binary content",
                filename="malware.exe",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name="skill_validation",
                trigger_source="link_document",
                actor_roles=["owner"],
            )

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(
        ContentReviewService, "_create_and_link_document", new_callable=AsyncMock
    )
    async def test_owner_bypass_creates_approved_record(
        self, mock_create_doc, mock_get_pipeline, service
    ):
        """Owner with passing content gates → bypassed=True, auto-applied, no job enqueued."""
        mock_get_pipeline.return_value = _make_passing_pipeline()
        mock_create_doc.return_value = uuid4()

        review = await service.submit_for_review(
            content="safe content",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="skill_validation",
            trigger_source="ku_create",
            actor_roles=["owner"],
        )

        assert review.bypassed is True
        assert review.status == "applied"
        mock_create_doc.assert_called_once()

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(
        ContentReviewService, "_create_and_link_document", new_callable=AsyncMock
    )
    async def test_owner_skill_validation_skips_policy_and_ast_gates(
        self, mock_create_doc, mock_get_pipeline, service
    ):
        """Owner + skill_validation: content_policy_gate and python_ast_gate skipped.

        Cybersecurity skills legitimately contain XSS payloads, SQL injection
        examples, and utility Python scripts. Both gates would reject them,
        but owners uploading to skill_validation should not be blocked.
        Structural gates (empty, length, format) still run.
        """
        pipeline = MagicMock()
        pipeline.name = "skill_validation"
        pipeline.mode = "review"
        passing_check = MagicMock(side_effect=lambda c, f: [])
        passing_check.__name__ = "empty_content_gate"
        policy_check = MagicMock(
            side_effect=lambda c, f: ["Content contains suspicious pattern: <script"]
        )
        policy_check.__name__ = "content_policy_gate"
        ast_check = MagicMock(side_effect=lambda c, f: ["Blocked import: 'sys'"])
        ast_check.__name__ = "python_ast_gate"
        pipeline.content_gates.return_value = [passing_check, policy_check, ast_check]
        mock_get_pipeline.return_value = pipeline
        mock_create_doc.return_value = uuid4()

        # This should NOT raise ContentReviewGateError for owner
        review = await service.submit_for_review(
            content='<script>alert("XSS")</script>',
            filename="xss-detection.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="skill_validation",
            trigger_source="link_document",
            actor_roles=["owner"],
        )

        assert review.bypassed is True
        assert review.status == "applied"

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_non_owner_still_blocked_by_content_policy_gate(
        self, mock_enqueue, mock_get_pipeline, service
    ):
        """Non-owner roles are still blocked by content_policy_gate failures."""
        pipeline = MagicMock()
        pipeline.name = "skill_validation"
        pipeline.mode = "review"
        policy_check = MagicMock(
            side_effect=lambda c, f: ["Content contains suspicious pattern: <script"]
        )
        policy_check.__name__ = "content_policy_gate"
        pipeline.content_gates.return_value = [policy_check]
        mock_get_pipeline.return_value = pipeline

        from analysi.services.content_review import ContentReviewGateError

        with pytest.raises(ContentReviewGateError):
            await service.submit_for_review(
                content='<script>alert("XSS")</script>',
                filename="xss-detection.md",
                skill_id=uuid4(),
                tenant_id="t1",
                pipeline_name="skill_validation",
                trigger_source="link_document",
                actor_roles=["analyst"],
            )

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_admin_cannot_bypass(self, mock_enqueue, mock_get_pipeline, service):
        """Admin has all skill CRUD but cannot bypass content review."""
        mock_get_pipeline.return_value = _make_passing_pipeline()

        review = await service.submit_for_review(
            content="content",
            filename="test.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test_pipeline",
            trigger_source="ku_create",
            actor_roles=["admin"],
        )

        assert review.bypassed is False
        assert review.status == "pending"
        mock_enqueue.assert_called_once()

    @pytest.mark.asyncio
    @patch("analysi.services.content_review.get_pipeline_by_name")
    @patch.object(ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock)
    async def test_system_cannot_bypass(self, mock_enqueue, mock_get_pipeline, service):
        """System/workers cannot bypass (content from Kea/Hydra must be reviewed)."""
        mock_get_pipeline.return_value = _make_passing_pipeline()

        review = await service.submit_for_review(
            content="agent output",
            filename="runbook.md",
            skill_id=uuid4(),
            tenant_id="t1",
            pipeline_name="test_pipeline",
            trigger_source="ku_create",
            actor_roles=["system"],
        )

        assert review.bypassed is False
        assert review.status == "pending"
        mock_enqueue.assert_called_once()
