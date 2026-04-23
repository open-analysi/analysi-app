"""Integration tests for Knowledge Extraction API.

Extraction router now delegates to ContentReviewService.
Returns ContentReviewResponse instead of ExtractionResponse.
POST start creates a pending content review (async pipeline via ARQ worker).
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.services.content_review import ContentReviewService


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeExtractionAPI:
    """Test the knowledge extraction REST API via content review pipeline."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create test client with seeded skill and document."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Mock ARQ enqueue — no Redis in test environment
        enqueue_patch = patch.object(
            ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock
        )
        enqueue_patch.start()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            suffix = uuid.uuid4().hex[:8]
            tenant = f"test-extraction-{suffix}"

            # Seed a skill
            skill_resp = await client.post(
                f"/v1/{tenant}/skills",
                json={
                    "name": f"Test Skill {suffix}",
                    "cy_name": f"test_skill_{suffix}",
                    "description": "Skill for extraction tests",
                },
            )
            assert skill_resp.status_code == 201, (
                f"Skill creation failed: {skill_resp.text}"
            )
            skill_data = skill_resp.json()["data"]

            # Seed a source document
            doc_resp = await client.post(
                f"/v1/{tenant}/knowledge-units/documents",
                json={
                    "name": f"Source Doc {suffix}",
                    "content": "# SOAR Playbook\n\nStep 1: Check IP reputation\nStep 2: Block if malicious",
                    "doc_format": "markdown",
                    "document_type": "soar_playbook",
                },
            )
            assert doc_resp.status_code == 201, f"Doc creation failed: {doc_resp.text}"
            doc_data = doc_resp.json()["data"]

            # Store test data on client for access in tests
            client._test_tenant = tenant
            client._test_skill_id = skill_data["id"]
            client._test_document_id = doc_data["id"]
            client._test_session = integration_test_session

            yield client

        enqueue_patch.stop()
        app.dependency_overrides.clear()

    def _tenant(self, client: AsyncClient) -> str:
        return client._test_tenant

    def _skill_id(self, client: AsyncClient) -> str:
        return client._test_skill_id

    def _doc_id(self, client: AsyncClient) -> str:
        return client._test_document_id

    def _base_url(self, client: AsyncClient) -> str:
        return f"/v1/{self._tenant(client)}/skills/{self._skill_id(client)}/content-reviews"

    async def _complete_review(self, client: AsyncClient, review_id: str) -> None:
        """Simulate ARQ worker completing a review (sets status=approved)."""
        from analysi.services.content_review import ContentReviewService

        session = client._test_session
        service = ContentReviewService(session)
        await service.complete_review(
            review_id=uuid.UUID(review_id),
            pipeline_result={"stub": True},
            status="approved",
            transformed_content="# Extracted content",
            summary="Test extraction summary",
        )
        await session.flush()

    # --- Create extraction (returns pending content review) ---

    async def test_create_extraction(self, client: AsyncClient):
        """POST create extraction → 201 with status=pending (async pipeline)."""
        resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["skill_id"] == self._skill_id(client)
        assert data["pipeline_name"] == "extraction"
        assert data["pipeline_mode"] == "review_transform"
        assert data["content_gates_passed"] is True

    # --- Get extraction by ID ---

    async def test_get_extraction_by_id(self, client: AsyncClient):
        """GET extraction by ID → 200 with full details."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        assert create_resp.status_code == 201
        review_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"{self._base_url(client)}/{review_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == review_id
        assert data["status"] == "pending"
        assert data["pipeline_name"] == "extraction"

    # --- List extractions ---

    async def test_list_extractions(self, client: AsyncClient):
        """GET list extractions by skill → 200 with results."""
        await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )

        resp = await client.get(self._base_url(client))
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["total"] >= 2
        assert len(body["data"]) >= 2

    # --- List filtered by status ---

    async def test_list_extractions_filtered_by_status(self, client: AsyncClient):
        """GET list extractions filtered by status → correct subset."""
        # Create and reject one (pending → rejected is valid)
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]
        await client.post(
            f"{self._base_url(client)}/{review_id}/reject",
            json={"reason": "test"},
        )

        # Create another (stays pending)
        await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )

        # Filter by rejected
        resp = await client.get(self._base_url(client), params={"status": "rejected"})
        assert resp.status_code == 200
        body = resp.json()
        assert all(e["status"] == "rejected" for e in body["data"])

    # --- Apply extraction (after simulated worker completion) ---

    async def test_apply_extraction(self, client: AsyncClient):
        """POST apply → 200, status=applied after worker completes review."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        # Simulate worker completing the review
        await self._complete_review(client, review_id)

        apply_resp = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()["data"]
        assert apply_data["status"] == "applied"

        # Verify via GET
        get_resp = await client.get(f"{self._base_url(client)}/{review_id}")
        assert get_resp.json()["data"]["status"] == "applied"

    # --- Reject extraction ---

    async def test_reject_extraction(self, client: AsyncClient):
        """POST reject → 200, status=rejected, reason stored."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        reject_resp = await client.post(
            f"{self._base_url(client)}/{review_id}/reject",
            json={"reason": "Not relevant to this skill"},
        )
        assert reject_resp.status_code == 200
        reject_data = reject_resp.json()["data"]
        assert reject_data["status"] == "rejected"
        assert reject_data["rejection_reason"] == "Not relevant to this skill"

    # --- Apply already-applied → 409 ---

    async def test_apply_already_applied_returns_409(self, client: AsyncClient):
        """POST apply already-applied extraction → 409."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        await self._complete_review(client, review_id)
        await client.post(f"{self._base_url(client)}/{review_id}/apply")

        # Apply again → 409
        resp = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert resp.status_code == 409

    # --- Reject already-applied → 409 ---

    async def test_reject_already_applied_returns_409(self, client: AsyncClient):
        """POST reject already-applied extraction → 409."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        await self._complete_review(client, review_id)
        await client.post(f"{self._base_url(client)}/{review_id}/apply")

        # Reject → 409
        resp = await client.post(f"{self._base_url(client)}/{review_id}/reject")
        assert resp.status_code == 409

    # --- Apply already-rejected → 409 ---

    async def test_apply_already_rejected_returns_409(self, client: AsyncClient):
        """POST apply already-rejected extraction → 409."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        # Reject first
        await client.post(f"{self._base_url(client)}/{review_id}/reject")

        # Apply → 409 (rejected is not appliable)
        resp = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert resp.status_code == 409

    # --- Nonexistent document_id → 404 ---

    async def test_extraction_nonexistent_document_returns_404(
        self, client: AsyncClient
    ):
        """POST extraction with nonexistent document_id → 404."""
        fake_doc_id = str(uuid.uuid4())
        resp = await client.post(
            self._base_url(client),
            json={"document_id": fake_doc_id},
        )
        assert resp.status_code == 404

    # --- Nonexistent skill_id → 404 ---

    async def test_extraction_nonexistent_skill_returns_404(self, client: AsyncClient):
        """POST extraction with nonexistent skill_id → 404."""
        fake_skill_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/{self._tenant(client)}/skills/{fake_skill_id}/content-reviews",
            json={"document_id": self._doc_id(client)},
        )
        assert resp.status_code == 404

    # --- Cross-tenant isolation ---

    async def test_cross_tenant_extraction_not_visible(self, client: AsyncClient):
        """GET extraction with wrong tenant → 404."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": self._doc_id(client)},
        )
        review_id = create_resp.json()["data"]["id"]

        # Try to access from different tenant
        resp = await client.get(
            f"/v1/other-tenant/skills/{self._skill_id(client)}/content-reviews/{review_id}"
        )
        assert resp.status_code == 404
