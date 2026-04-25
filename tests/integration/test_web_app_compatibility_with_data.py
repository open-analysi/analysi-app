"""Integration tests for web app compatibility with actual data."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestWebAppCompatibilityWithData:
    """Test web app compatibility features with actual data."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.fixture
    async def test_data(self, client: AsyncClient) -> dict:
        """Create test data for comprehensive testing."""
        tenant = "test-tenant"

        # Create a few KUs with different statuses
        table_enabled = await client.post(
            f"/v1/{tenant}/knowledge-units/tables",
            json={
                "name": "Enabled Security Table",
                "description": "Active security rules table",
                "content": {"rules": [{"ip": "192.168.1.1", "action": "allow"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )

        table_disabled = await client.post(
            f"/v1/{tenant}/knowledge-units/tables",
            json={
                "name": "Disabled Legacy Table",
                "description": "Old security rules table",
                "content": {"rules": [{"ip": "10.0.0.1", "action": "deny"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )

        # Disable the second table by updating its status
        table_disabled_id = table_disabled.json()["data"]["id"]
        await client.put(
            f"/v1/{tenant}/knowledge-units/tables/{table_disabled_id}",
            json={
                "name": "Disabled Legacy Table"
                # Note: We can't actually set status=disabled through the API yet
                # This is a limitation - we need to add status update capability
            },
        )

        doc_enabled = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": "Active Security Policy",
                "description": "Current security policy document",
                "content": "This is the active security policy.",
                "document_type": "markdown",
            },
        )

        # Create a task
        task = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": "Security Analysis Task",
                "description": "Analyzes security threats",
                "script": "TASK security: RETURN 'analysis complete'",
                "scope": "processing",
            },
        )

        return {
            "tenant": tenant,
            "table_enabled": table_enabled.json()["data"],
            "table_disabled": table_disabled.json()["data"],
            "doc_enabled": doc_enabled.json()["data"],
            "task": task.json()["data"],
        }

    @pytest.mark.asyncio
    async def test_ku_status_filtering_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test KU status filtering with actual created data."""
        tenant = test_data["tenant"]

        # Test listing all KUs (should get all regardless of status for now)
        response = await client.get(f"/v1/{tenant}/knowledge-units")
        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert len(data["data"]) >= 2  # At least our test KUs

        # Test enabled filter (should work even if all are enabled by default)
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=enabled")
        assert response.status_code == 200
        enabled_data = response.json()

        # All should be enabled by default in our current system
        for ku in enabled_data["data"]:
            assert ku.get("status") in ["enabled", None]  # Default might be None

        # Test disabled filter (might return empty since we can't easily create disabled KUs)
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=disabled")
        assert response.status_code == 200
        response.json()  # Just validate response is valid JSON

        # Test invalid status
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=invalid")
        assert response.status_code == 400
        error_data = response.json()
        assert "Invalid status value" in error_data.get("detail", "")

    @pytest.mark.asyncio
    async def test_ku_combined_filters_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test combined KU filtering with real data."""
        tenant = test_data["tenant"]

        # Test status + type filter
        response = await client.get(
            f"/v1/{tenant}/knowledge-units?status=enabled&ku_type=table"
        )
        assert response.status_code == 200
        data = response.json()

        for ku in data["data"]:
            assert ku.get("ku_type") == "table"
            assert ku.get("status") in ["enabled", None]

        # Test status + search filter
        response = await client.get(
            f"/v1/{tenant}/knowledge-units?status=enabled&q=security"
        )
        assert response.status_code == 200
        data = response.json()

        for ku in data["data"]:
            name = ku.get("name", "").lower()
            desc = ku.get("description", "").lower()
            assert "security" in name or "security" in desc
            assert ku.get("status") in ["enabled", None]

    @pytest.mark.asyncio
    async def test_global_graph_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test global knowledge graph with actual data."""
        tenant = test_data["tenant"]

        # Test basic graph endpoint
        response = await client.get(f"/v1/{tenant}/kdg/graph")
        assert response.status_code == 200
        data = response.json()["data"]

        # Verify response structure
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

        # Should have at least our test task (KUs might not appear as nodes if they're not connected)
        assert len(data["nodes"]) >= 1

        # Verify node format
        for node in data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert "data" in node

            # Verify data structure
            node_data = node["data"]
            assert "name" in node_data
            assert "description" in node_data
            assert "created_at" in node_data
            assert "updated_at" in node_data

    @pytest.mark.asyncio
    async def test_graph_filtering_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test graph filtering with real data."""
        tenant = test_data["tenant"]

        # Test tasks only
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_tasks=true&include_knowledge_units=false"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # Should only have task nodes
        for node in data["nodes"]:
            assert node["type"] == "task"

        # Test KUs only
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_knowledge_units=true&include_tasks=false"
        )
        assert response.status_code == 200
        data = response.json()["data"]

        # Should only have KU nodes (no tasks)
        for node in data["nodes"]:
            assert node["type"] in ["table", "document", "index", "tool"]

        # Test max_nodes limitation
        response = await client.get(f"/v1/{tenant}/kdg/graph?max_nodes=2")
        assert response.status_code == 200
        data = response.json()["data"]

        # Should respect max_nodes limit
        assert len(data["nodes"]) <= 2

    @pytest.mark.asyncio
    async def test_graph_edge_format_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test graph edge format with real data (if any edges exist)."""
        tenant = test_data["tenant"]

        # Get the graph
        response = await client.get(f"/v1/{tenant}/kdg/graph")
        assert response.status_code == 200
        data = response.json()["data"]

        # If we have edges, verify their format
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "type" in edge
            assert "data" in edge
            assert isinstance(edge["data"], dict)

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        """Test that tenant isolation works for both endpoints."""
        # Test with non-existent tenant
        response = await client.get("/v1/nonexistent-tenant/knowledge-units")
        assert response.status_code == 200  # Should return empty list, not error
        data = response.json()
        assert len(data["data"]) == 0

        response = await client.get("/v1/nonexistent-tenant/kdg/graph")
        assert response.status_code == 200  # Should return empty graph, not error
        data = response.json()["data"]
        assert len(data["nodes"]) == 0
        assert len(data["edges"]) == 0

    @pytest.mark.asyncio
    async def test_pagination_with_real_data(
        self, client: AsyncClient, test_data: dict
    ):
        """Test pagination works with real data."""
        tenant = test_data["tenant"]

        # Test pagination
        response = await client.get(f"/v1/{tenant}/knowledge-units?limit=1")
        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "meta" in data
        assert len(data["data"]) <= 1
