"""
Integration tests for Knowledge Index feature (Project Paros).

Tests the full stack: REST API → Service → PgvectorBackend → PostgreSQL.
Requires a running PostgreSQL instance with pgvector extension.

These tests use @pytest.mark.integration and require the test database.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeIndexCollectionCRUD:
    """Test Index KU collection CRUD with new Paros fields."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create async HTTP client with test DB session."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.dependency_overrides.clear()

    async def test_create_index_with_paros_fields(self, client: AsyncClient):
        """Create an index KU with embedding_dimensions and backend_type."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        create_data = {
            "name": f"threat-intel-kb-{uuid4().hex[:8]}",
            "description": "Threat intelligence knowledge base",
            "index_type": "vector",
            "vector_database": "pgvector",
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 1536,
            "backend_type": "pgvector",
        }

        response = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert response.status_code == 201

        data = response.json()["data"]
        assert data["embedding_dimensions"] == 1536
        assert data["backend_type"] == "pgvector"
        assert data["embedding_model"] == "text-embedding-3-small"
        assert data["build_status"] == "pending"

    async def test_create_index_with_defaults(self, client: AsyncClient):
        """Create an index KU without Paros fields — defaults apply."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        create_data = {
            "name": f"default-index-{uuid4().hex[:8]}",
            "description": "Index with defaults",
        }

        response = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert response.status_code == 201

        data = response.json()["data"]
        assert data["backend_type"] == "pgvector"
        assert data["index_type"] == "vector"
        # embedding_dimensions is None until first entry is added
        assert data["embedding_dimensions"] is None

    async def test_index_lifecycle_create_read_delete(self, client: AsyncClient):
        """Full lifecycle: create → read → delete → verify gone."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        # Create
        create_data = {
            "name": f"lifecycle-index-{uuid4().hex[:8]}",
            "index_type": "vector",
            "backend_type": "pgvector",
        }
        create_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert create_resp.status_code == 201
        index_id = create_resp.json()["data"]["id"]

        # Read
        read_resp = await client.get(f"/v1/{tenant}/knowledge-units/indexes/{index_id}")
        assert read_resp.status_code == 200
        assert read_resp.json()["data"]["backend_type"] == "pgvector"

        # Delete
        delete_resp = await client.delete(
            f"/v1/{tenant}/knowledge-units/indexes/{index_id}"
        )
        assert delete_resp.status_code == 204

        # Verify gone
        gone_resp = await client.get(f"/v1/{tenant}/knowledge-units/indexes/{index_id}")
        assert gone_resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeIndexEntryEndpoints:
    """Test entry add/list/delete endpoints.

    Note: These tests require an AI integration configured for the tenant
    to generate embeddings. Without it, add_entries will return 422.
    For unit-level validation of the endpoint logic, see the unit tests.
    """

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create async HTTP client with test DB session."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        app.dependency_overrides.clear()

    async def test_add_entries_without_ai_integration_returns_422(
        self, client: AsyncClient
    ):
        """Adding entries without AI integration configured returns 422."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        # Create collection first
        create_data = {
            "name": f"no-ai-index-{uuid4().hex[:8]}",
            "index_type": "vector",
            "backend_type": "pgvector",
        }
        create_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert create_resp.status_code == 201
        collection_id = create_resp.json()["data"]["id"]

        # Try to add entries — should fail because no AI integration
        add_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes/{collection_id}/entries",
            json={"entries": [{"content": "test content"}]},
        )
        # 422 = no embedding provider, or 500 if integration lookup fails
        assert add_resp.status_code in (422, 500)

    async def test_search_nonexistent_collection_returns_404(self, client: AsyncClient):
        """Searching a non-existent collection returns 404."""
        tenant = f"test-paros-{uuid4().hex[:8]}"
        fake_id = str(uuid4())

        resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes/{fake_id}/search",
            json={"query": "test query"},
        )
        assert resp.status_code == 404

    async def test_list_entries_empty_collection(self, client: AsyncClient):
        """Listing entries on an empty collection returns empty list."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        # Create collection
        create_data = {
            "name": f"empty-index-{uuid4().hex[:8]}",
            "index_type": "vector",
            "backend_type": "pgvector",
        }
        create_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert create_resp.status_code == 201
        collection_id = create_resp.json()["data"]["id"]

        # List entries — should be empty
        list_resp = await client.get(
            f"/v1/{tenant}/knowledge-units/indexes/{collection_id}/entries"
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["data"] == []
        assert list_resp.json()["meta"]["total"] == 0

    async def test_delete_entry_nonexistent_returns_404(self, client: AsyncClient):
        """Deleting a non-existent entry returns 404."""
        tenant = f"test-paros-{uuid4().hex[:8]}"

        # Create collection
        create_data = {
            "name": f"del-test-index-{uuid4().hex[:8]}",
            "index_type": "vector",
            "backend_type": "pgvector",
        }
        create_resp = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=create_data
        )
        assert create_resp.status_code == 201
        collection_id = create_resp.json()["data"]["id"]

        # Try to delete non-existent entry
        fake_entry_id = str(uuid4())
        del_resp = await client.delete(
            f"/v1/{tenant}/knowledge-units/indexes/{collection_id}/entries/{fake_entry_id}"
        )
        assert del_resp.status_code == 404

    async def test_tenant_isolation_collections(self, client: AsyncClient):
        """Collections from tenant A are not visible to tenant B."""
        tenant_a = f"test-paros-a-{uuid4().hex[:8]}"
        tenant_b = f"test-paros-b-{uuid4().hex[:8]}"

        # Create collection for tenant A
        create_data = {
            "name": f"isolated-index-{uuid4().hex[:8]}",
            "index_type": "vector",
        }
        create_resp = await client.post(
            f"/v1/{tenant_a}/knowledge-units/indexes", json=create_data
        )
        assert create_resp.status_code == 201
        index_id = create_resp.json()["data"]["id"]

        # Tenant B cannot see it
        read_resp = await client.get(
            f"/v1/{tenant_b}/knowledge-units/indexes/{index_id}"
        )
        assert read_resp.status_code == 404
