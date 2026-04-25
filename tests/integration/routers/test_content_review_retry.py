"""Integration tests for POST /{tenant}/skills/{skill_id}/content-reviews/{id}/retry.

Tests the full retry flow against real PostgreSQL: failed → pending re-enqueue,
plus corner cases (wrong status, not found, wrong skill).
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.content_review import ContentReview
from analysi.schemas.skill import SkillCreate
from analysi.services.content_review import ContentReviewService
from analysi.services.knowledge_module import KnowledgeModuleService


@pytest.mark.asyncio
@pytest.mark.integration
class TestRetryContentReviewEndpoint:
    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        env_patch = patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
        env_patch.start()

        # Mock ARQ enqueue — no Redis in test environment
        enqueue_patch = patch.object(
            ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock
        )
        enqueue_patch.start()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            suffix = uuid.uuid4().hex[:8]

            # Create a skill for the tests
            km_service = KnowledgeModuleService(integration_test_session)
            skill = await km_service.create_skill(
                f"test-retry-{suffix}",
                SkillCreate(
                    name=f"Retry Test {suffix}",
                    cy_name=f"retry_test_{suffix}",
                    description="For retry tests",
                ),
            )
            await integration_test_session.flush()

            c.tenant_id = f"test-retry-{suffix}"
            c.skill_id = skill.component.id
            c.session = integration_test_session

            yield c

        enqueue_patch.stop()
        env_patch.stop()
        app.dependency_overrides.clear()

    def _make_review(self, client, status="failed", **overrides):
        review = ContentReview(
            id=uuid.uuid4(),
            tenant_id=client.tenant_id,
            skill_id=client.skill_id,
            pipeline_name="skill_validation",
            pipeline_mode="review",
            trigger_source="test",
            original_filename="test.md",
            original_content="# Test content",
            content_gates_passed=True,
            status=status,
            error_message="Pipeline timed out" if status == "failed" else None,
            created_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        for k, v in overrides.items():
            setattr(review, k, v)
        return review

    def _url(self, client, review_id):
        return (
            f"/v1/{client.tenant_id}/skills/{client.skill_id}"
            f"/content-reviews/{review_id}/retry"
        )

    async def test_retry_failed_review_returns_202(self, client):
        """POST /retry on a failed review returns 202 with pending status."""
        review = self._make_review(client, status="failed")
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))

        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["error_message"] is None

    async def test_retry_clears_pipeline_result(self, client):
        """Retry should clear previous pipeline_result and completed_at."""
        review = self._make_review(
            client,
            status="failed",
            pipeline_result={"old": "data"},
            completed_at=datetime.now(UTC),
        )
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))

        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["pipeline_result"] is None
        assert data["completed_at"] is None

    async def test_retry_pending_returns_409(self, client):
        """Cannot retry a review that is still pending."""
        review = self._make_review(client, status="pending")
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))
        assert resp.status_code == 409

    async def test_retry_approved_returns_409(self, client):
        """Cannot retry an approved review."""
        review = self._make_review(client, status="approved")
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))
        assert resp.status_code == 409

    async def test_retry_applied_returns_409(self, client):
        """Cannot retry an already-applied review."""
        review = self._make_review(client, status="applied")
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))
        assert resp.status_code == 409

    async def test_retry_rejected_returns_409(self, client):
        """Cannot retry a rejected review."""
        review = self._make_review(client, status="rejected")
        client.session.add(review)
        await client.session.flush()

        resp = await client.post(self._url(client, review.id))
        assert resp.status_code == 409

    async def test_retry_nonexistent_returns_404(self, client):
        """Retry for a non-existent review returns 404."""
        fake_id = uuid.uuid4()
        resp = await client.post(self._url(client, fake_id))
        assert resp.status_code == 404

    async def test_retry_wrong_skill_returns_404(self, client):
        """Retry with wrong skill_id returns 404."""
        review = self._make_review(client, status="failed")
        client.session.add(review)
        await client.session.flush()

        wrong_skill_id = uuid.uuid4()
        resp = await client.post(
            f"/v1/{client.tenant_id}/skills/{wrong_skill_id}"
            f"/content-reviews/{review.id}/retry"
        )
        assert resp.status_code == 404
