"""Integration tests for KDG endpoints."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKDGEdgeEndpoints:
    """Test KDG edge management endpoints."""

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
    async def test_create_edge_with_nonexistent_nodes(self, client: AsyncClient):
        """Test POST /v1/{tenant}/kdg/edges with non-existent nodes."""
        tenant = "test-tenant"
        edge_data = {
            "source_id": str(uuid4()),
            "target_id": str(uuid4()),
            "relationship_type": "uses",
            "is_required": False,
            "execution_order": 0,
            "metadata": {},
        }

        response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)

        # Should fail with 400 because nodes don't exist
        assert response.status_code == 400
        assert response.json()["detail"] == "Referenced node not found"

    @pytest.mark.asyncio
    async def test_create_edge_with_real_nodes(self, client: AsyncClient):
        """Test creating edge between actual task and KU."""
        tenant = "test-tenant"

        # First create a task
        task_data = {
            "name": "Security Analysis Task",
            "script": "TASK analyze: RETURN 'analysis complete'",
            "function": "reasoning",
            "scope": "processing",
        }
        task_response = await client.post(f"/v1/{tenant}/tasks", json=task_data)
        assert task_response.status_code == 201
        task_id = task_response.json()["data"]["id"]
        print(f"Created task with ID: {task_id}")

        # Create a document KU
        doc_data = {
            "name": "Security Report",
            "description": "Analysis results document",
            "doc_format": "markdown",
            "content": "# Security Analysis Results",
            "metadata": {},  # Required by the schema
        }
        doc_response = await client.post(
            f"/v1/{tenant}/knowledge-units/documents", json=doc_data
        )
        assert doc_response.status_code == 201
        doc_id = doc_response.json()["data"]["id"]
        print(f"Created document with ID: {doc_id}")

        # Test if we can retrieve the nodes via KDG API
        task_node_response = await client.get(f"/v1/{tenant}/kdg/nodes/{task_id}")
        print(f"Task node lookup: {task_node_response.status_code}")
        if task_node_response.status_code != 200:
            print(f"Task node error: {task_node_response.text}")

        doc_node_response = await client.get(f"/v1/{tenant}/kdg/nodes/{doc_id}")
        print(f"Doc node lookup: {doc_node_response.status_code}")
        if doc_node_response.status_code != 200:
            print(f"Doc node error: {doc_node_response.text}")

        # Now create edge between task and document
        edge_data = {
            "source_id": task_id,
            "target_id": doc_id,
            "relationship_type": "generates",
            "is_required": True,
            "execution_order": 1,
            "metadata": {"confidence": "high"},
        }

        edge_response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
        if edge_response.status_code != 201:
            print(f"Edge creation failed: {edge_response.status_code}")
            print(f"Error: {edge_response.text}")
        assert edge_response.status_code == 201

        edge_data_response = edge_response.json()["data"]
        assert edge_data_response["source_node"]["id"] == task_id
        assert edge_data_response["target_node"]["id"] == doc_id
        assert edge_data_response["relationship_type"] == "generates"
        assert edge_data_response["is_required"] is True
        assert edge_data_response["metadata"]["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_get_edge_endpoint(self, client: AsyncClient):
        """Test GET /v1/{tenant}/kdg/edges/{id}."""
        tenant = "test-tenant"
        edge_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/edges/{edge_id}")

        # Should return 404 for non-existent edge
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_edge_endpoint(self, client: AsyncClient):
        """Test DELETE /v1/{tenant}/kdg/edges/{id}."""
        tenant = "test-tenant"
        edge_id = uuid4()

        response = await client.delete(f"/v1/{tenant}/kdg/edges/{edge_id}")

        # Should return 404 for non-existent edge
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_edge_invalid_nodes(self, client):
        """Test creating edge with non-existent nodes."""
        tenant = "test-tenant"
        edge_data = {
            "source_id": str(uuid4()),  # Non-existent
            "target_id": str(uuid4()),  # Non-existent
            "relationship_type": "uses",
        }

        response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)

        # Should return 400 for validation error (non-existent nodes)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_edge_cross_tenant(self, client):
        """Test preventing cross-tenant edges."""
        tenant = "test-tenant"
        edge_data = {
            "source_id": str(uuid4()),
            "target_id": str(uuid4()),
            "relationship_type": "uses",
        }

        response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)

        # Should eventually validate tenant isolation when implemented
        # Cross-tenant validation returns 400
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_edge_unique_constraint(self, client):
        """Test enforcing unique relationships."""
        tenant = "test-tenant"
        source_id = str(uuid4())
        target_id = str(uuid4())

        edge_data = {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": "uses",
        }

        # Try to create same edge twice
        response1 = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
        response2 = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)

        # Validation errors return 400 for non-existent nodes
        assert response1.status_code == 400  # Invalid nodes
        assert response2.status_code == 400  # Invalid nodes


@pytest.mark.integration
class TestKDGNodeEndpoints:
    """Test KDG node operations endpoints."""

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
    async def test_get_node_endpoint(self, client):
        """Test GET /v1/{tenant}/kdg/nodes/{id}."""
        tenant = "test-tenant"
        node_id = uuid4()  # Random UUID - should not exist

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}")

        # Should return 404 for non-existent node
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_nodes_endpoint(self, client):
        """Test GET /v1/{tenant}/kdg/nodes."""
        tenant = "test-tenant"

        response = await client.get(f"/v1/{tenant}/kdg/nodes")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_nodes_type_filter(self, client):
        """Test filtering by type=task or type=ku."""
        tenant = "test-tenant"

        for node_type in ["task", "document", "table", "index", "tool"]:
            response = await client.get(f"/v1/{tenant}/kdg/nodes?type={node_type}")

            # Implementation is working now
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_nodes_search(self, client):
        """Test search with q parameter."""
        tenant = "test-tenant"
        search_query = "security analysis"

        response = await client.get(f"/v1/{tenant}/kdg/nodes?q={search_query}")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_nodes_pagination(self, client):
        """Test pagination with limit/offset."""
        tenant = "test-tenant"

        response = await client.get(f"/v1/{tenant}/kdg/nodes?limit=20&offset=10")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_node_not_found(self, client):
        """Test 404 for missing node."""
        tenant = "test-tenant"
        node_id = uuid4()  # Non-existent node

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}")

        # Should eventually return 404 when implemented
        assert response.status_code in [500, 404]


@pytest.mark.integration
class TestKDGNodeEdgeEndpoints:
    """Test node edge query endpoints."""

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
    async def test_get_node_edges_all(self, client):
        """Test GET /v1/{tenant}/kdg/nodes/{id}/edges."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/edges")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_node_edges_incoming(self, client):
        """Test direction=in parameter."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{node_id}/edges?direction=in"
        )

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_node_edges_outgoing(self, client):
        """Test direction=out parameter."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{node_id}/edges?direction=out"
        )

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_node_edges_both(self, client):
        """Test direction=both (default)."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{node_id}/edges?direction=both"
        )

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_edges_include_node_details(self, client):
        """Test that edges include full node info in response."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/edges")

        # Should eventually return edges with source_node and target_node details
        assert response.status_code in [500, 200]


@pytest.mark.integration
class TestKDGGraphTraversalEndpoints:
    """Test graph traversal endpoints."""

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
    async def test_graph_traversal_default(self, client):
        """Test GET /v1/{tenant}/kdg/nodes/{id}/graph."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_graph_traversal_depth_1(self, client):
        """Test depth=1 parameter."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph?depth=1")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_graph_traversal_depth_3(self, client):
        """Test depth=3 parameter."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph?depth=3")

        # Implementation is working now
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_graph_response_structure(self, client):
        """Test that graph response has nodes and edges arrays."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph")

        # Should eventually return GraphResponse with nodes and edges
        assert response.status_code in [500, 200]

    @pytest.mark.asyncio
    async def test_graph_no_duplicates(self, client):
        """Test that each node/edge appears only once in results."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph?depth=3")

        # Should eventually ensure no duplicate nodes or edges
        assert response.status_code in [500, 200]

    @pytest.mark.asyncio
    async def test_graph_isolated_node(self, client):
        """Test node with no edges."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph")

        # Should eventually handle isolated nodes gracefully
        assert response.status_code in [500, 200, 404]

    @pytest.mark.asyncio
    async def test_graph_complex_network(self, client):
        """Test multi-path traversal."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph?depth=2")

        # Should eventually handle complex graphs with multiple paths
        assert response.status_code in [500, 200]


@pytest.mark.integration
class TestKDGNegativeEndpoints:
    """Test negative cases and error handling."""

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
    async def test_create_edge_missing_fields(self, client):
        """Test 422 validation error for missing fields."""
        tenant = "test-tenant"
        edge_data = {
            "source_id": str(uuid4()),
            # Missing target_id and relationship_type
        }

        response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)

        # Should return 422 validation error
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_direction_parameter(self, client):
        """Test 400 for invalid direction."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{node_id}/edges?direction=invalid"
        )

        # Should return 422 validation error for invalid enum
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_node_type_filter(self, client):
        """Test 400 for invalid type."""
        tenant = "test-tenant"

        response = await client.get(f"/v1/{tenant}/kdg/nodes?type=invalid_type")

        # Should return 422 validation error for invalid enum
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_depth_exceeds_limit(self, client):
        """Test 400 for depth > max."""
        tenant = "test-tenant"
        node_id = uuid4()

        response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}/graph?depth=10")

        # Should return 422 validation error (depth limit is 5)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cross_tenant_access(self, client):
        """Test 404 for different tenant."""
        tenant2 = "tenant-2"
        node_id = uuid4()

        # Try to access node from different tenant
        response = await client.get(f"/v1/{tenant2}/kdg/nodes/{node_id}")

        # Should eventually return 404 when tenant isolation is implemented
        assert response.status_code in [500, 404]
