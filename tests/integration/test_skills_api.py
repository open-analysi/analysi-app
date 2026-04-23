"""Integration tests for Skills (Knowledge Modules) API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillsCRUDAPI:
    """Test Skills CRUD API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_skill(self, client: AsyncClient):
        """Create a new skill module via API."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill_data = {
            "name": "Test Skill",
            "description": "A test skill for integration testing",
            "categories": ["testing", "automation"],
        }

        response = await client.post(f"/v1/{tenant_id}/skills", json=skill_data)

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Test Skill"
        assert data["description"] == "A test skill for integration testing"
        assert data["module_type"] == "skill"
        assert data["tenant_id"] == tenant_id
        assert "id" in data
        assert "cy_name" in data
        assert data["cy_name"] is not None
        assert data["namespace"] == "/"

    @pytest.mark.asyncio
    async def test_create_skill_with_custom_cy_name(self, client: AsyncClient):
        """Create a skill with custom cy_name."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        skill_data = {
            "name": "Custom CyName Skill",
            "description": "Skill with custom cy_name",
            "cy_name": "my_custom_skill",
        }

        response = await client.post(f"/v1/{tenant_id}/skills", json=skill_data)

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["cy_name"] == "my_custom_skill"

    @pytest.mark.asyncio
    async def test_get_skill(self, client: AsyncClient):
        """Get a skill by ID."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill first
        skill_data = {"name": "Skill To Get", "description": "Get me"}
        create_response = await client.post(f"/v1/{tenant_id}/skills", json=skill_data)
        skill_id = create_response.json()["data"]["id"]

        # Get the skill
        response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == skill_id
        assert data["name"] == "Skill To Get"
        assert data["namespace"] == "/"

    @pytest.mark.asyncio
    async def test_get_skill_not_found(self, client: AsyncClient):
        """Get skill returns 404 when not found."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        fake_id = str(uuid4())

        response = await client.get(f"/v1/{tenant_id}/skills/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_skills(self, client: AsyncClient):
        """List skills with pagination."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create multiple skills
        for i in range(3):
            await client.post(
                f"/v1/{tenant_id}/skills",
                json={"name": f"Skill {i}", "description": f"Description {i}"},
            )

        # List skills
        response = await client.get(f"/v1/{tenant_id}/skills")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 3
        assert body["meta"]["total"] == 3

    @pytest.mark.asyncio
    async def test_list_skills_with_search(self, client: AsyncClient):
        """List skills with search filter."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create skills with different names
        await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Security Analysis", "description": "Analyze security"},
        )
        await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Performance Testing", "description": "Test performance"},
        )

        # Search for "security"
        response = await client.get(f"/v1/{tenant_id}/skills", params={"q": "security"})

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "Security Analysis"

    @pytest.mark.asyncio
    async def test_update_skill(self, client: AsyncClient):
        """Update an existing skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        create_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Original Name", "description": "Original"},
        )
        skill_id = create_response.json()["data"]["id"]

        # Update the skill
        response = await client.put(
            f"/v1/{tenant_id}/skills/{skill_id}",
            json={"name": "Updated Name", "description": "Updated description"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_skill(self, client: AsyncClient):
        """Delete a skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        create_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Skill To Delete", "description": "Delete me"},
        )
        skill_id = create_response.json()["data"]["id"]

        # Delete the skill
        response = await client.delete(f"/v1/{tenant_id}/skills/{skill_id}")
        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_check_skill_delete(self, client: AsyncClient):
        """Check delete validation for a skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        create_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Check Delete Skill", "description": "Check me"},
        )
        skill_id = create_response.json()["data"]["id"]

        # Check delete
        response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/check-delete")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["can_delete"] is True
        assert data["contained_documents"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillsDocumentManagementAPI:
    """Test Skills document management API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_link_document_to_skill(
        self, client: AsyncClient, integration_test_session
    ):
        """Link a document to a skill with namespace path."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill via API
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Doc Linking Skill", "description": "For doc linking"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create a document KU via repository (we need the document_id)
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "Test Document",
                "content": "Document content",
                "document_type": "markdown",
            },
        )
        document_id = str(doc.component.id)

        # Link document to skill
        response = await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={"document_id": document_id, "namespace_path": "references/api.md"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["skill_id"] == skill_id
        assert data["document_id"] == document_id
        assert data["namespace_path"] == "references/api.md"

    @pytest.mark.asyncio
    async def test_link_document_path_conflict(
        self, client: AsyncClient, integration_test_session
    ):
        """Linking document with existing path returns conflict."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Path Conflict Skill", "description": "Test path conflict"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create two documents
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        doc1 = await ku_repo.create_document_ku(
            tenant_id, {"name": "Doc 1", "content": "Content 1"}
        )
        doc2 = await ku_repo.create_document_ku(
            tenant_id, {"name": "Doc 2", "content": "Content 2"}
        )

        # Link first document
        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={
                "document_id": str(doc1.component.id),
                "namespace_path": "SKILL.md",
            },
        )

        # Try to link second document with same path
        response = await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={
                "document_id": str(doc2.component.id),
                "namespace_path": "SKILL.md",
            },
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_get_skill_tree(self, client: AsyncClient, integration_test_session):
        """Get file tree for a skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Tree Skill", "description": "For tree testing"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create and link documents
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        for path in ["SKILL.md", "references/api.md", "examples/basic.md"]:
            doc = await ku_repo.create_document_ku(
                tenant_id, {"name": f"Doc for {path}", "content": f"Content for {path}"}
            )
            await client.post(
                f"/v1/{tenant_id}/skills/{skill_id}/documents",
                json={"document_id": str(doc.component.id), "namespace_path": path},
            )

        # Get tree
        response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/tree")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["skill_id"] == skill_id
        assert data["total"] == 3
        paths = [f["path"] for f in data["files"]]
        assert "SKILL.md" in paths
        assert "references/api.md" in paths
        assert "examples/basic.md" in paths

    @pytest.mark.asyncio
    async def test_read_skill_file(self, client: AsyncClient, integration_test_session):
        """Read document content by path within skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Read File Skill", "description": "For file reading"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create and link a document
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "Skill Doc",
                "content": "This is the skill content.",
                "document_type": "markdown",
            },
        )
        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={"document_id": str(doc.component.id), "namespace_path": "SKILL.md"},
        )

        # Read the file
        response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/files/SKILL.md")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["path"] == "SKILL.md"
        assert data["content"] == "This is the skill content."
        assert data["name"] == "Skill Doc"

    @pytest.mark.asyncio
    async def test_read_skill_file_with_null_metadata(
        self, client: AsyncClient, integration_test_session
    ):
        """Reading a file whose document has null metadata should return 200 with empty dict."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Metadata Skill", "description": "Test null metadata"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create doc, then set metadata to NULL to simulate REST-created docs
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        doc = await ku_repo.create_document_ku(
            tenant_id, {"name": "No Meta Doc", "content": "Some content"}
        )
        doc.doc_metadata = None
        await integration_test_session.flush()
        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={
                "document_id": str(doc.component.id),
                "namespace_path": "nested/path/doc.md",
            },
        )

        response = await client.get(
            f"/v1/{tenant_id}/skills/{skill_id}/files/nested/path/doc.md"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["path"] == "nested/path/doc.md"
        assert data["content"] == "Some content"
        assert data["metadata"] == {}

    @pytest.mark.asyncio
    async def test_read_skill_file_not_found(self, client: AsyncClient):
        """Reading non-existent file returns 404."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "No File Skill", "description": "No files here"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Try to read non-existent file
        response = await client.get(
            f"/v1/{tenant_id}/skills/{skill_id}/files/nonexistent.md"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unlink_document_from_skill(
        self, client: AsyncClient, integration_test_session
    ):
        """Unlink a document from a skill."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a skill
        skill_response = await client.post(
            f"/v1/{tenant_id}/skills",
            json={"name": "Unlink Skill", "description": "For unlinking"},
        )
        skill_id = skill_response.json()["data"]["id"]

        # Create and link a document
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        doc = await ku_repo.create_document_ku(
            tenant_id, {"name": "Linked Doc", "content": "Content"}
        )
        document_id = str(doc.component.id)

        await client.post(
            f"/v1/{tenant_id}/skills/{skill_id}/documents",
            json={"document_id": document_id, "namespace_path": "doc.md"},
        )

        # Verify it's linked
        tree_response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/tree")
        assert tree_response.json()["data"]["total"] == 1

        # Unlink the document
        response = await client.delete(
            f"/v1/{tenant_id}/skills/{skill_id}/documents/{document_id}"
        )

        assert response.status_code == 204

        # Verify it's unlinked
        tree_response = await client.get(f"/v1/{tenant_id}/skills/{skill_id}/tree")
        assert tree_response.json()["data"]["total"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
class TestSkillsTenantIsolation:
    """Test tenant isolation for skills."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_skills_tenant_isolation(self, client: AsyncClient):
        """Skills are isolated by tenant."""
        tenant1 = f"tenant1-{uuid4().hex[:8]}"
        tenant2 = f"tenant2-{uuid4().hex[:8]}"

        # Create skill in tenant1
        response1 = await client.post(
            f"/v1/{tenant1}/skills",
            json={"name": "Tenant1 Skill", "description": "Belongs to tenant1"},
        )
        skill_id = response1.json()["data"]["id"]

        # List skills in tenant1 - should see 1
        list1 = await client.get(f"/v1/{tenant1}/skills")
        assert list1.json()["meta"]["total"] == 1

        # List skills in tenant2 - should see 0
        list2 = await client.get(f"/v1/{tenant2}/skills")
        assert list2.json()["meta"]["total"] == 0

        # Try to get tenant1's skill from tenant2 - should fail
        get_cross = await client.get(f"/v1/{tenant2}/skills/{skill_id}")
        assert get_cross.status_code == 404

        # Try to delete tenant1's skill from tenant2 - should fail
        delete_cross = await client.delete(f"/v1/{tenant2}/skills/{skill_id}")
        assert delete_cross.status_code == 404
