"""Integration tests for Knowledge Extraction hardening.

Tests input validation, state transitions, and error handling at the API level.
Updated for the content review flow.
"""

import os
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
class TestKnowledgeExtractionHardening:
    """Integration tests for extraction hardening under the content review flow."""

    @pytest_asyncio.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create test client with seeded skill and document."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Force stub pipeline (no real LLM calls)
        env_patch = patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""})
        env_patch.start()

        # Mock ARQ enqueue — no Redis in test environment
        enqueue_patch = patch.object(
            ContentReviewService, "_enqueue_review_job", new_callable=AsyncMock
        )
        enqueue_patch.start()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            suffix = uuid.uuid4().hex[:8]
            tenant = f"test-hardening-{suffix}"

            # Seed a skill
            skill_resp = await client.post(
                f"/v1/{tenant}/skills",
                json={
                    "name": f"Test Skill {suffix}",
                    "cy_name": f"test_skill_{suffix}",
                    "description": "Skill for hardening tests",
                },
            )
            assert skill_resp.status_code == 201, (
                f"Skill creation failed: {skill_resp.text}"
            )
            skill_data = skill_resp.json()["data"]

            # Seed a source document with normal content
            doc_resp = await client.post(
                f"/v1/{tenant}/knowledge-units/documents",
                json={
                    "name": f"Source Doc {suffix}",
                    "content": "# SOAR Playbook\n\nStep 1: Check IP\nStep 2: Block",
                    "doc_format": "markdown",
                    "document_type": "soar_playbook",
                },
            )
            assert doc_resp.status_code == 201, f"Doc creation failed: {doc_resp.text}"
            doc_data = doc_resp.json()["data"]

            client._test_tenant = tenant
            client._test_skill_id = skill_data["id"]
            client._test_document_id = doc_data["id"]
            client._test_session = integration_test_session

            yield client

        enqueue_patch.stop()
        env_patch.stop()
        app.dependency_overrides.clear()

    def _base_url(self, client: AsyncClient) -> str:
        return (
            f"/v1/{client._test_tenant}/skills/{client._test_skill_id}/content-reviews"
        )

    async def _complete_review(self, session: AsyncSession, review_id: str) -> None:
        """Simulate ARQ worker completing a review (sets status=approved)."""
        service = ContentReviewService(session)
        await service.complete_review(
            review_id=uuid.UUID(review_id),
            pipeline_result={"stub": True},
            status="approved",
            transformed_content="# Extracted content\n\nSome extracted knowledge.",
            summary="Test extraction summary",
        )
        await session.flush()

    # --- Input Validation ---

    async def test_extraction_oversized_content_returns_422(self, client: AsyncClient):
        """Document content > 50K chars fails content gates → 422."""
        big_content = "x" * 50_001
        doc_resp = await client.post(
            f"/v1/{client._test_tenant}/knowledge-units/documents",
            json={
                "name": "Oversized Doc",
                "content": big_content,
                "doc_format": "markdown",
                "document_type": "soar_playbook",
            },
        )
        assert doc_resp.status_code == 201
        big_doc_id = doc_resp.json()["data"]["id"]

        resp = await client.post(
            self._base_url(client),
            json={"document_id": big_doc_id},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]

    async def test_extraction_empty_content_returns_422(self, client: AsyncClient):
        """Document with empty content fails content gates → 422."""
        doc_resp = await client.post(
            f"/v1/{client._test_tenant}/knowledge-units/documents",
            json={
                "name": "Empty Doc",
                "content": "",
                "doc_format": "markdown",
                "document_type": "soar_playbook",
            },
        )
        assert doc_resp.status_code == 201
        empty_doc_id = doc_resp.json()["data"]["id"]

        resp = await client.post(
            self._base_url(client),
            json={"document_id": empty_doc_id},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]

    # --- Content Review Response Shape ---

    async def test_extraction_response_has_content_review_fields(
        self, client: AsyncClient
    ):
        """GET extraction response uses ContentReviewResponse schema."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        assert create_resp.status_code == 201
        review_id = create_resp.json()["data"]["id"]

        get_resp = await client.get(f"{self._base_url(client)}/{review_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()["data"]

        # ContentReviewResponse fields
        assert "pipeline_name" in data
        assert "pipeline_mode" in data
        assert "content_gates_passed" in data
        assert "status" in data
        assert data["pipeline_name"] == "extraction"

    async def test_extraction_summary_populated_after_completion(
        self, client: AsyncClient
    ):
        """Summary field is populated after ARQ worker completes the review."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        assert create_resp.status_code == 201
        data = create_resp.json()["data"]
        review_id = data["id"]

        # Initially pending — summary is null
        assert data["status"] == "pending"
        assert data["summary"] is None

        # Simulate worker completion
        await self._complete_review(client._test_session, review_id)
        await client._test_session.commit()

        # Now summary should be populated
        get_resp = await client.get(f"{self._base_url(client)}/{review_id}")
        assert get_resp.status_code == 200
        completed_data = get_resp.json()["data"]
        assert completed_data["summary"] is not None
        assert len(completed_data["summary"]) > 0

    # --- State Transitions ---

    async def test_double_apply_returns_409(self, client: AsyncClient):
        """Applying same extraction twice → second returns 409."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        review_id = create_resp.json()["data"]["id"]

        # Complete the review so it can be applied
        await self._complete_review(client._test_session, review_id)
        await client._test_session.commit()

        # First apply
        resp1 = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert resp1.status_code == 200

        # Second apply — already applied
        resp2 = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert resp2.status_code == 409

    async def test_apply_pending_review_returns_409(self, client: AsyncClient):
        """Cannot apply a review still in pending state (worker hasn't finished)."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        review_id = create_resp.json()["data"]["id"]

        # Try to apply without worker completing — status is still pending
        resp = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert resp.status_code == 409

    async def test_reject_pending_review_succeeds(self, client: AsyncClient):
        """Can reject a review in pending state."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        review_id = create_resp.json()["data"]["id"]

        resp = await client.post(
            f"{self._base_url(client)}/{review_id}/reject",
            json={"reason": "Changed my mind"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"
        assert resp.json()["data"]["rejection_reason"] == "Changed my mind"

    async def test_reject_after_apply_returns_409(self, client: AsyncClient):
        """Cannot reject a review that has already been applied."""
        create_resp = await client.post(
            self._base_url(client),
            json={"document_id": client._test_document_id},
        )
        review_id = create_resp.json()["data"]["id"]

        # Complete and apply
        await self._complete_review(client._test_session, review_id)
        await client._test_session.commit()

        apply_resp = await client.post(f"{self._base_url(client)}/{review_id}/apply")
        assert apply_resp.status_code == 200

        # Try to reject
        reject_resp = await client.post(
            f"{self._base_url(client)}/{review_id}/reject",
            json={"reason": "Too late"},
        )
        assert reject_resp.status_code == 409
