"""Integration tests for pending/flagged review counts on SkillResponse.

Verifies that GET /skills and GET /skills/{id} include accurate
pending_reviews_count and flagged_reviews_count from content_reviews.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.content_review import ContentReview
from analysi.schemas.skill import SkillCreate
from analysi.services.knowledge_module import KnowledgeModuleService


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillReviewCounts:
    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            suffix = uuid.uuid4().hex[:8]
            tenant_id = f"test-counts-{suffix}"

            km_service = KnowledgeModuleService(integration_test_session)
            skill = await km_service.create_skill(
                tenant_id,
                SkillCreate(
                    name=f"Counts Skill {suffix}",
                    cy_name=f"counts_skill_{suffix}",
                    description="For review count tests",
                ),
            )
            await integration_test_session.flush()

            c.tenant_id = tenant_id
            c.skill_id = skill.component.id
            c.session = integration_test_session

            yield c

        app.dependency_overrides.clear()

    def _add_review(self, client, status: str) -> ContentReview:
        now = datetime.now(UTC)
        review = ContentReview(
            id=uuid.uuid4(),
            tenant_id=client.tenant_id,
            skill_id=client.skill_id,
            pipeline_name="skill_validation",
            pipeline_mode="review",
            trigger_source="test",
            original_filename="test.md",
            original_content="# Test",
            content_gates_passed=True,
            status=status,
            created_at=now,
            updated_at=now,
        )
        client.session.add(review)
        return review

    async def test_detail_returns_zero_counts_with_no_reviews(self, client):
        """GET /skills/{id} returns 0 counts when no reviews exist."""
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills/{client.skill_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pending_reviews_count"] == 0
        assert data["flagged_reviews_count"] == 0

    async def test_detail_counts_pending_reviews(self, client):
        """GET /skills/{id} counts pending reviews correctly."""
        self._add_review(client, "pending")
        self._add_review(client, "pending")
        self._add_review(client, "approved")  # should not count
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills/{client.skill_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pending_reviews_count"] == 2
        assert data["flagged_reviews_count"] == 0

    async def test_detail_counts_flagged_reviews(self, client):
        """GET /skills/{id} counts flagged reviews correctly."""
        self._add_review(client, "flagged")
        self._add_review(client, "flagged")
        self._add_review(client, "flagged")
        self._add_review(client, "applied")  # should not count
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills/{client.skill_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pending_reviews_count"] == 0
        assert data["flagged_reviews_count"] == 3

    async def test_detail_counts_both_pending_and_flagged(self, client):
        """GET /skills/{id} counts both pending and flagged."""
        self._add_review(client, "pending")
        self._add_review(client, "flagged")
        self._add_review(client, "flagged")
        self._add_review(client, "failed")  # should not count
        self._add_review(client, "rejected")  # should not count
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills/{client.skill_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pending_reviews_count"] == 1
        assert data["flagged_reviews_count"] == 2

    async def test_list_includes_review_counts(self, client):
        """GET /skills includes review counts per skill."""
        self._add_review(client, "pending")
        self._add_review(client, "pending")
        self._add_review(client, "flagged")
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills")
        assert resp.status_code == 200
        skills = resp.json()["data"]

        target = next(s for s in skills if s["id"] == str(client.skill_id))
        assert target["pending_reviews_count"] == 2
        assert target["flagged_reviews_count"] == 1

    async def test_list_excludes_terminal_statuses(self, client):
        """GET /skills does not count applied/rejected/failed/approved."""
        self._add_review(client, "applied")
        self._add_review(client, "rejected")
        self._add_review(client, "failed")
        self._add_review(client, "approved")
        await client.session.commit()

        resp = await client.get(f"/v1/{client.tenant_id}/skills")
        assert resp.status_code == 200
        skills = resp.json()["data"]

        target = next(s for s in skills if s["id"] == str(client.skill_id))
        assert target["pending_reviews_count"] == 0
        assert target["flagged_reviews_count"] == 0
