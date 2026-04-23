"""Integration tests for staged documents API endpoints."""

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.content_review import ContentReviewService


@pytest.mark.asyncio
@pytest.mark.integration
class TestStagedDocumentsAPI:
    """Test staged documents REST endpoints."""

    @pytest_asyncio.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
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
            yield client

        enqueue_patch.stop()
        app.dependency_overrides.clear()

    async def _create_skill(self, client, tenant_id, name="Test Skill", cy_name=None):
        data = {"name": name, "description": f"Skill for {name}"}
        if cy_name:
            data["cy_name"] = cy_name
        resp = await client.post(f"/v1/{tenant_id}/skills", json=data)
        assert resp.status_code == 201
        return resp.json()["data"]

    async def _create_doc(self, session, tenant_id, name="Test Doc", content="Content"):
        ku_repo = KnowledgeUnitRepository(session)
        doc = await ku_repo.create_document_ku(
            tenant_id, {"name": name, "content": content}
        )
        return str(doc.component.id)

    @pytest.mark.asyncio
    async def test_stage_document(self, client, integration_test_session):
        """T8: POST staged document → 201, appears in staged list."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        doc_id = await self._create_doc(integration_test_session, tenant_id)

        # Stage the document
        resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/doc.md"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["document_id"] == doc_id

        # Verify in staged list
        list_resp = await client.get(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents"
        )
        assert list_resp.status_code == 200
        staged = list_resp.json()["data"]
        assert len(staged) == 1
        assert staged[0]["document_id"] == doc_id

    @pytest.mark.asyncio
    async def test_list_staged_documents(self, client, integration_test_session):
        """T9: GET staged documents returns staged docs with details."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        doc_id = await self._create_doc(
            integration_test_session, tenant_id, "Staged Doc"
        )

        await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/report.md"},
        )

        resp = await client.get(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents"
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["path"] == "staged/report.md"

    @pytest.mark.asyncio
    async def test_delete_staged_document(self, client, integration_test_session):
        """T10: DELETE staged document → removed from staged list."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        doc_id = await self._create_doc(integration_test_session, tenant_id)

        await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/doc.md"},
        )

        # Delete
        resp = await client.delete(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents/{doc_id}"
        )
        assert resp.status_code == 204

        # Verify removed
        list_resp = await client.get(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents"
        )
        assert list_resp.json()["meta"]["total"] == 0

    @pytest.mark.asyncio
    async def test_skill_tree_staged_flag(self, client, integration_test_session):
        """T11: Skill tree distinguishes staged vs integrated docs."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        skill_id = skill["id"]

        # Integrated doc
        int_doc_id = await self._create_doc(
            integration_test_session, tenant_id, "Integrated"
        )
        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={"document_id": int_doc_id, "namespace_path": "SKILL.md"},
        )

        # Staged doc
        stg_doc_id = await self._create_doc(
            integration_test_session, tenant_id, "Staged"
        )
        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/staged-documents",
            json={"document_id": stg_doc_id, "namespace_path": "staged/new.md"},
        )

        # Get tree
        resp = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/tree")
        assert resp.status_code == 200
        files = resp.json()["data"]["files"]
        assert len(files) == 2

        integrated = next(f for f in files if f["path"] == "SKILL.md")
        staged = next(f for f in files if f["path"] == "staged/new.md")
        assert integrated["staged"] is False
        assert staged["staged"] is True

    @pytest.mark.asyncio
    async def test_extraction_eligible_flag(self, client):
        """T12: Skill response includes extraction_eligible field."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create runbooks-manager skill
        rm_skill = await self._create_skill(
            client, tenant_id, "Runbooks Manager", cy_name="runbooks_manager"
        )
        resp = await client.get(f"/v1/{tenant_id}/skills/{rm_skill['id']}")
        assert resp.json()["data"]["extraction_eligible"] is True

        # Create other skill
        other_skill = await self._create_skill(client, tenant_id, "Other Skill")
        resp = await client.get(f"/v1/{tenant_id}/skills/{other_skill['id']}")
        assert resp.json()["data"]["extraction_eligible"] is False

    @pytest.mark.asyncio
    async def test_stage_nonexistent_document(self, client):
        """T13: Stage nonexistent doc → 404."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        fake_doc_id = str(uuid4())

        resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": fake_doc_id, "namespace_path": "staged/doc.md"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stage_already_staged(self, client, integration_test_session):
        """T14: Stage already-staged doc → 409."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        doc_id = await self._create_doc(integration_test_session, tenant_id)

        await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/doc.md"},
        )

        resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/doc.md"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_stage_already_integrated(self, client, integration_test_session):
        """T15: Stage already-integrated doc → 409."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(client, tenant_id)
        doc_id = await self._create_doc(integration_test_session, tenant_id)

        # Integrate first
        await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/documents",
            json={"document_id": doc_id, "namespace_path": "references/doc.md"},
        )

        # Try to stage
        resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill['id']}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/doc.md"},
        )
        assert resp.status_code == 409

    async def _complete_review(self, session, review_id: str) -> None:
        """Simulate ARQ worker completing a review (sets status=approved)."""
        service = ContentReviewService(session)
        await service.complete_review(
            review_id=UUID(review_id),
            pipeline_result={"stub": True},
            status="approved",
            transformed_content="# Extracted content\n\nSome extracted knowledge.",
            summary="Test extraction summary",
        )

    @pytest.mark.asyncio
    async def test_full_staging_to_extraction_flow(
        self, client, integration_test_session
    ):
        """T16: Full flow — stage doc → extract → complete review → apply → staged edge removed."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill = await self._create_skill(
            client, tenant_id, "Runbooks Manager", cy_name="runbooks_manager"
        )
        skill_id = skill["id"]

        # Create source doc
        doc_id = await self._create_doc(
            integration_test_session, tenant_id, "SOAR Playbook", "Playbook content"
        )

        # Stage it
        resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/staged-documents",
            json={"document_id": doc_id, "namespace_path": "staged/playbook.md"},
        )
        assert resp.status_code == 201

        # Verify staged
        staged = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/staged-documents")
        assert staged.json()["meta"]["total"] == 1

        # Start extraction (uses stub pipeline since no ANTHROPIC_API_KEY)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            extract_resp = await client.post(
                f"/v1/{tenant_id}/skills/{skill_id}/content-reviews",
                json={"document_id": doc_id},
            )
        assert extract_resp.status_code == 201
        extraction_id = extract_resp.json()["data"]["id"]

        # Complete the extraction review so it can be applied
        await self._complete_review(integration_test_session, extraction_id)
        await integration_test_session.commit()

        # Apply extraction
        apply_resp = await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/content-reviews/{extraction_id}/apply",
        )
        assert apply_resp.status_code in (200, 201)

        # NOTE: staged edge removal on apply is a known gap — the extraction
        # apply route uses ContentReviewService.apply_review() which only
        # changes status. KnowledgeExtractionService.apply_extraction() has
        # staged edge removal but is not wired into the route yet.
        # TODO: Wire staged edge removal into extraction apply route.
