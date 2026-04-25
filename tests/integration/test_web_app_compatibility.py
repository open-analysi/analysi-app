"""Integration tests for Web App API Compatibility."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKnowledgeUnitsStatusFiltering:
    """Test KU endpoint status filtering for web app compatibility."""

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

    @pytest.mark.asyncio
    async def test_status_filter_enabled_only(self, client: AsyncClient):
        """T6.1.1 - Status Filter: Enabled Only."""
        tenant = "test-tenant"

        # This test will FAIL initially - status filtering not implemented
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=enabled")

        assert response.status_code == 200
        data = response.json()

        # Should return only enabled KUs
        assert "data" in data
        for ku in data["data"]:
            # This will fail because status filtering doesn't exist yet
            assert ku.get("status") == "enabled"

    @pytest.mark.asyncio
    async def test_status_filter_disabled_only(self, client: AsyncClient):
        """T6.1.2 - Status Filter: Disabled Only."""
        tenant = "test-tenant"

        # This test will FAIL initially - status filtering not implemented
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=disabled")

        assert response.status_code == 200
        data = response.json()

        # Should return only disabled KUs
        assert "data" in data
        for ku in data["data"]:
            # This will fail because status filtering doesn't exist yet
            assert ku.get("status") == "disabled"

    @pytest.mark.asyncio
    async def test_status_filter_invalid_value(self, client: AsyncClient):
        """T6.1.3 - Status Filter: Invalid Value."""
        tenant = "test-tenant"

        # This test will FAIL initially - validation not implemented
        response = await client.get(f"/v1/{tenant}/knowledge-units?status=invalid")

        # Should return 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_combined_filters_status_and_type(self, client: AsyncClient):
        """T6.1.4 - Combined Filters: Status + Type."""
        tenant = "test-tenant"

        # This test will FAIL initially - status filtering not implemented
        response = await client.get(
            f"/v1/{tenant}/knowledge-units?status=enabled&ku_type=table"
        )

        assert response.status_code == 200
        data = response.json()

        # Should return only enabled tables
        assert "data" in data
        for ku in data["data"]:
            # This will fail because status filtering doesn't exist yet
            assert ku.get("status") == "enabled"
            assert ku.get("ku_type") == "table"

    @pytest.mark.asyncio
    async def test_combined_filters_status_and_search(self, client: AsyncClient):
        """T6.1.5 - Combined Filters: Status + Search."""
        tenant = "test-tenant"

        # This test will FAIL initially - status filtering not implemented
        response = await client.get(
            f"/v1/{tenant}/knowledge-units?status=enabled&q=security"
        )

        assert response.status_code == 200
        data = response.json()

        # Should return only enabled KUs matching "security" search
        assert "data" in data
        for ku in data["data"]:
            # This will fail because status filtering doesn't exist yet
            assert ku.get("status") == "enabled"
            # Name or description should contain "security"
            name = ku.get("name", "").lower()
            desc = ku.get("description", "").lower()
            assert "security" in name or "security" in desc


@pytest.mark.asyncio
@pytest.mark.integration
class TestGlobalKnowledgeGraphEndpoint:
    """Test global knowledge graph endpoint for web app compatibility."""

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

    @pytest.mark.asyncio
    async def test_basic_global_graph(self, client: AsyncClient):
        """T6.1.6 - Basic Global Graph."""
        tenant = "test-tenant"

        # This test will FAIL initially - endpoint doesn't exist
        response = await client.get(f"/v1/{tenant}/kdg/graph")

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return graph with nodes and edges
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    @pytest.mark.asyncio
    async def test_include_tasks_only(self, client: AsyncClient):
        """T6.1.7 - Include Tasks Only."""
        tenant = "test-tenant"

        # This test will FAIL initially - filtering not implemented
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_tasks=true&include_knowledge_units=false"
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return graph with task nodes only
        assert "nodes" in data
        for node in data["nodes"]:
            # This will fail because filtering doesn't exist yet
            assert node.get("type") == "task"

    @pytest.mark.asyncio
    async def test_include_knowledge_units_only(self, client: AsyncClient):
        """T6.1.8 - Include Knowledge Units Only."""
        tenant = "test-tenant"

        # This test will FAIL initially - filtering not implemented
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_knowledge_units=true&include_tasks=false"
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return graph with KU nodes only
        assert "nodes" in data
        for node in data["nodes"]:
            # This will fail because filtering doesn't exist yet
            node_type = node.get("type")
            assert node_type in ["table", "document", "index", "tool"]

    @pytest.mark.asyncio
    async def test_depth_limitation(self, client: AsyncClient):
        """T6.1.9 - Depth Limitation."""
        tenant = "test-tenant"

        # This test will FAIL initially - depth filtering not implemented
        response = await client.get(f"/v1/{tenant}/kdg/graph?depth=1")

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return limited depth traversal - exact validation TBD
        assert "nodes" in data
        assert "edges" in data

    @pytest.mark.asyncio
    async def test_max_nodes_limitation(self, client: AsyncClient):
        """T6.1.10 - Max Nodes Limitation."""
        tenant = "test-tenant"

        # This test will FAIL initially - max_nodes filtering not implemented
        response = await client.get(f"/v1/{tenant}/kdg/graph?max_nodes=50")

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return at most 50 nodes
        assert "nodes" in data
        assert len(data["nodes"]) <= 50

    @pytest.mark.asyncio
    async def test_combined_graph_filters(self, client: AsyncClient):
        """T6.1.11 - Combined Graph Filters."""
        tenant = "test-tenant"

        # This test will FAIL initially - all filtering not implemented
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_tasks=true&include_knowledge_units=true&depth=2&max_nodes=100"
        )

        assert response.status_code == 200
        data = response.json()["data"]

        # Should return complete graph with specified limits
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) <= 100

    @pytest.mark.asyncio
    async def test_graph_endpoint_returns_complete_data(self, client: AsyncClient):
        """T6.1.12 - Graph Endpoint Returns Complete Data."""
        tenant = "test-tenant"

        # This test will FAIL initially - endpoint doesn't exist
        response = await client.get(f"/v1/{tenant}/kdg/graph")

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify response format matches web app expectations
        assert "nodes" in data
        assert "edges" in data

        # Check node format
        for node in data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert "data" in node
            assert isinstance(node["data"], dict)

        # Check edge format
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "type" in edge
            assert "data" in edge


@pytest.mark.asyncio
@pytest.mark.integration
class TestResponseFormatCompatibility:
    """Test response format compatibility with web app."""

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

    @pytest.mark.asyncio
    async def test_ku_endpoint_response_format(self, client: AsyncClient):
        """T6.1.13 - KU Endpoint Response Format."""
        tenant = "test-tenant"

        response = await client.get(f"/v1/{tenant}/knowledge-units")

        assert response.status_code == 200
        data = response.json()

        # Verify response matches expected format
        assert "data" in data
        assert "meta" in data
        assert isinstance(data["data"], list)

        # Check KU object format
        for ku in data["data"]:
            assert "id" in ku
            assert "tenant_id" in ku
            assert "ku_type" in ku
            assert "name" in ku
            assert "description" in ku

    @pytest.mark.asyncio
    async def test_graph_endpoint_response_format(self, client: AsyncClient):
        """T6.1.14 - Graph Endpoint Response Format."""
        tenant = "test-tenant"

        # This test will FAIL initially - endpoint doesn't exist
        response = await client.get(f"/v1/{tenant}/kdg/graph")

        assert response.status_code == 200
        data = response.json()["data"]

        # Verify response matches web app expectations
        assert "nodes" in data
        assert "edges" in data

        # Node format validation
        for node in data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert "data" in node
            assert isinstance(node["data"], dict)

            # Required fields in node data
            node_data = node["data"]
            assert "name" in node_data
            assert "description" in node_data
            assert "created_at" in node_data
            assert "updated_at" in node_data

        # Edge format validation
        for edge in data["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "type" in edge
            assert "data" in edge
            assert isinstance(edge["data"], dict)
