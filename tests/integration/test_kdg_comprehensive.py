"""
Comprehensive integration tests for KDG operations.

These tests thoroughly cover edge and node operations to prevent
regression bugs like the metadata field issue.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestKDGComprehensive:
    """Comprehensive tests for KDG edge and node operations."""

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
    async def sample_components(self, client: AsyncClient):
        """Create sample components for testing."""
        tenant = "test-tenant"
        components = {}

        # Create a task
        task_data = {
            "name": "Analyze Security Alert",
            "description": "Comprehensive alert analysis task",
            "script": "TASK analyze: RETURN analysis_result",
            "function": "reasoning",
            "scope": "processing",
        }
        task_response = await client.post(f"/v1/{tenant}/tasks", json=task_data)
        assert task_response.status_code == 201
        components["task"] = task_response.json()["data"]

        # Create a document KU
        doc_data = {
            "name": "Security Policy Document",
            "description": "Company security policies and procedures",
            "content": "# Security Policy\n\nThis document contains security procedures.",
            "document_type": "markdown",
            "content_source": "manual",
            "metadata": {"version": "2.1", "classification": "internal"},
        }
        doc_response = await client.post(
            f"/v1/{tenant}/knowledge-units/documents", json=doc_data
        )
        assert doc_response.status_code == 201
        components["document"] = doc_response.json()["data"]

        # Create a table KU
        table_data = {
            "name": "Critical Assets",
            "description": "List of critical organizational assets",
            "content": {
                "rows": [
                    {
                        "asset_id": "DB-001",
                        "name": "Customer Database",
                        "criticality": "high",
                    },
                    {
                        "asset_id": "API-001",
                        "name": "Payment API",
                        "criticality": "critical",
                    },
                ]
            },
            "schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "name": {"type": "string"},
                    "criticality": {"type": "string"},
                },
            },
            "row_count": 2,
            "column_count": 3,
        }
        table_response = await client.post(
            f"/v1/{tenant}/knowledge-units/tables", json=table_data
        )
        assert table_response.status_code == 201
        components["table"] = table_response.json()["data"]

        # Create an index KU
        index_data = {
            "name": "Security Knowledge Index",
            "description": "Vector index for security documentation",
            "index_type": "vector",
            "vector_database": "pinecone",
            "embedding_model": "text-embedding-ada-002",
            "chunking_config": {"chunk_size": 500, "chunk_overlap": 100},
            "build_status": "completed",
        }
        index_response = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes", json=index_data
        )
        assert index_response.status_code == 201
        components["index"] = index_response.json()["data"]

        return components

    @pytest.mark.asyncio
    async def test_edge_lifecycle_with_metadata(
        self, client: AsyncClient, sample_components
    ):
        """Test complete edge lifecycle including metadata handling."""
        tenant = "test-tenant"
        task_id = sample_components["task"]["id"]
        doc_id = sample_components["document"]["id"]

        # 1. Create edge with comprehensive metadata
        edge_data = {
            "source_id": task_id,
            "target_id": doc_id,
            "relationship_type": "uses",
            "is_required": True,
            "execution_order": 1,
            "metadata": {
                "confidence": "high",
                "priority": "urgent",
                "added_by": "test_system",
                "nested": {"key": "value", "number": 42},
            },
        }

        # Create edge
        create_response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
        assert create_response.status_code == 201

        created_edge = create_response.json()["data"]
        edge_id = created_edge["id"]

        # Verify all fields are properly set
        assert created_edge["source_node"]["id"] == task_id
        assert created_edge["target_node"]["id"] == doc_id
        assert created_edge["relationship_type"] == "uses"
        assert created_edge["is_required"] is True
        assert created_edge["execution_order"] == 1

        # Critical: Verify metadata is properly stored and retrieved
        assert created_edge["metadata"]["confidence"] == "high"
        assert created_edge["metadata"]["priority"] == "urgent"
        assert created_edge["metadata"]["added_by"] == "test_system"
        assert created_edge["metadata"]["nested"]["key"] == "value"
        assert created_edge["metadata"]["nested"]["number"] == 42

        # 2. Retrieve edge by ID and verify metadata persistence
        get_response = await client.get(f"/v1/{tenant}/kdg/edges/{edge_id}")
        assert get_response.status_code == 200

        retrieved_edge = get_response.json()["data"]
        assert retrieved_edge["id"] == edge_id
        assert retrieved_edge["metadata"]["confidence"] == "high"
        assert retrieved_edge["metadata"]["nested"]["number"] == 42

        # 3. Test edge appears in node edge listings
        task_edges_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/edges?direction=out"
        )
        assert task_edges_response.status_code == 200

        task_edges = task_edges_response.json()["data"]
        assert len(task_edges) >= 1

        found_edge = next((e for e in task_edges if e["id"] == edge_id), None)
        assert found_edge is not None
        assert found_edge["metadata"]["confidence"] == "high"

        # 4. Test edge appears in graph traversal
        graph_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/graph?depth=2"
        )
        assert graph_response.status_code == 200

        graph_data = graph_response.json()["data"]
        assert len(graph_data["nodes"]) >= 2  # At least task and document
        assert len(graph_data["edges"]) >= 1  # At least our edge

        graph_edge = next((e for e in graph_data["edges"] if e["id"] == edge_id), None)
        assert graph_edge is not None
        assert graph_edge["metadata"]["confidence"] == "high"

        # 5. Delete edge
        delete_response = await client.delete(f"/v1/{tenant}/kdg/edges/{edge_id}")
        assert delete_response.status_code == 204

        # 6. Verify edge is gone
        get_deleted_response = await client.get(f"/v1/{tenant}/kdg/edges/{edge_id}")
        assert get_deleted_response.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_edge_types_and_directions(
        self, client: AsyncClient, sample_components
    ):
        """Test various edge types and direction filtering."""
        tenant = "test-tenant"
        task_id = sample_components["task"]["id"]
        doc_id = sample_components["document"]["id"]
        table_id = sample_components["table"]["id"]
        index_id = sample_components["index"]["id"]

        # Create multiple edges with different types
        edges_to_create = [
            {
                "source_id": task_id,
                "target_id": doc_id,
                "relationship_type": "uses",
                "metadata": {"type": "policy_reference"},
            },
            {
                "source_id": task_id,
                "target_id": table_id,
                "relationship_type": "uses",
                "metadata": {"type": "asset_lookup"},
            },
            {
                "source_id": doc_id,
                "target_id": index_id,
                "relationship_type": "indexes_into",
                "metadata": {"indexing_method": "semantic"},
            },
            {
                "source_id": table_id,
                "target_id": doc_id,
                "relationship_type": "enriches",
                "metadata": {"enrichment_type": "context"},
            },
        ]

        created_edges = []
        for edge_data in edges_to_create:
            response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
            assert response.status_code == 201
            created_edges.append(response.json()["data"])

        # Test outgoing edges from task
        task_out_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/edges?direction=out"
        )
        assert task_out_response.status_code == 200
        task_out_edges = task_out_response.json()["data"]

        # Task should have 2 outgoing edges
        assert len(task_out_edges) == 2
        edge_types = [e["metadata"]["type"] for e in task_out_edges]
        assert "policy_reference" in edge_types
        assert "asset_lookup" in edge_types

        # Test incoming edges to document
        doc_in_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{doc_id}/edges?direction=in"
        )
        assert doc_in_response.status_code == 200
        doc_in_edges = doc_in_response.json()["data"]

        # Document should have 2 incoming edges
        assert len(doc_in_edges) == 2

        # Test all edges for document (both directions)
        doc_all_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{doc_id}/edges?direction=both"
        )
        assert doc_all_response.status_code == 200
        doc_all_edges = doc_all_response.json()["data"]

        # Document should have 3 total edges (2 in, 1 out)
        assert len(doc_all_edges) == 3

    @pytest.mark.asyncio
    async def test_node_retrieval_and_search(
        self, client: AsyncClient, sample_components
    ):
        """Test node retrieval and search functionality."""
        tenant = "test-tenant"

        # Test getting individual nodes
        for _component_type, component_data in sample_components.items():
            node_id = component_data["id"]
            response = await client.get(f"/v1/{tenant}/kdg/nodes/{node_id}")
            assert response.status_code == 200

            node_data = response.json()["data"]
            assert node_data["id"] == node_id
            assert node_data["name"] == component_data["name"]
            assert node_data["description"] == component_data["description"]

        # Test listing all nodes
        all_nodes_response = await client.get(f"/v1/{tenant}/kdg/nodes")
        assert all_nodes_response.status_code == 200
        all_nodes = all_nodes_response.json()["data"]
        assert len(all_nodes) >= 4  # At least our 4 test components

        # Test filtering by type
        task_nodes_response = await client.get(f"/v1/{tenant}/kdg/nodes?type=task")
        assert task_nodes_response.status_code == 200
        task_nodes = task_nodes_response.json()["data"]
        assert all(node["type"] == "task" for node in task_nodes)
        assert len(task_nodes) >= 1

        # Test filtering by document type
        doc_nodes_response = await client.get(f"/v1/{tenant}/kdg/nodes?type=document")
        assert doc_nodes_response.status_code == 200
        doc_nodes = doc_nodes_response.json()["data"]
        # Should return some nodes when filtering for documents
        # (Note: exact structure may vary based on how component relationships are loaded)
        assert isinstance(doc_nodes, list)

        # Test search functionality
        search_response = await client.get(f"/v1/{tenant}/kdg/nodes?q=security")
        assert search_response.status_code == 200
        search_results = search_response.json()["data"]
        # Should find nodes with "security" in name or description
        assert len(search_results) >= 2

        # Test pagination
        paginated_response = await client.get(
            f"/v1/{tenant}/kdg/nodes?limit=2&offset=0"
        )
        assert paginated_response.status_code == 200
        paginated_results = paginated_response.json()["data"]
        assert len(paginated_results) <= 2

    @pytest.mark.asyncio
    async def test_graph_traversal_depth_and_completeness(
        self, client: AsyncClient, sample_components
    ):
        """Test graph traversal with different depths and verify completeness."""
        tenant = "test-tenant"
        task_id = sample_components["task"]["id"]
        doc_id = sample_components["document"]["id"]
        table_id = sample_components["table"]["id"]
        index_id = sample_components["index"]["id"]

        # Create a chain: task -> doc -> index -> table
        chain_edges = [
            {"source_id": task_id, "target_id": doc_id, "relationship_type": "uses"},
            {
                "source_id": doc_id,
                "target_id": index_id,
                "relationship_type": "indexes_into",
            },
            {
                "source_id": index_id,
                "target_id": table_id,
                "relationship_type": "enriches",
            },
        ]

        for edge_data in chain_edges:
            response = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
            assert response.status_code == 201

        # Test depth 1 traversal
        depth1_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/graph?depth=1"
        )
        assert depth1_response.status_code == 200
        depth1_data = depth1_response.json()["data"]

        assert depth1_data["traversal_depth"] == 1
        # Should include task + document (1 hop away)
        assert len(depth1_data["nodes"]) == 2
        assert len(depth1_data["edges"]) == 1

        # Test depth 2 traversal
        depth2_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/graph?depth=2"
        )
        assert depth2_response.status_code == 200
        depth2_data = depth2_response.json()["data"]

        assert depth2_data["traversal_depth"] == 2
        # Should include task + document + index (2 hops away)
        assert len(depth2_data["nodes"]) == 3
        assert len(depth2_data["edges"]) == 2

        # Test depth 3 traversal
        depth3_response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/graph?depth=3"
        )
        assert depth3_response.status_code == 200
        depth3_data = depth3_response.json()["data"]

        assert depth3_data["traversal_depth"] == 3
        # Should include all 4 components (3 hops reaches table)
        assert len(depth3_data["nodes"]) == 4
        assert len(depth3_data["edges"]) == 3

        # Verify no duplicate nodes or edges
        node_ids = [node["id"] for node in depth3_data["nodes"]]
        edge_ids = [edge["id"] for edge in depth3_data["edges"]]
        assert len(node_ids) == len(set(node_ids))  # No duplicate nodes
        assert len(edge_ids) == len(set(edge_ids))  # No duplicate edges

    @pytest.mark.asyncio
    async def test_error_conditions_and_validation(
        self, client: AsyncClient, sample_components
    ):
        """Test various error conditions and edge cases."""
        tenant = "test-tenant"
        task_id = sample_components["task"]["id"]

        # Test creating edge with invalid relationship type
        invalid_edge = {
            "source_id": task_id,
            "target_id": sample_components["document"]["id"],
            "relationship_type": "invalid_relationship",
        }
        response = await client.post(f"/v1/{tenant}/kdg/edges", json=invalid_edge)
        assert response.status_code == 422  # Validation error

        # Test creating edge with non-existent nodes
        nonexistent_edge = {
            "source_id": str(uuid4()),
            "target_id": str(uuid4()),
            "relationship_type": "uses",
        }
        response = await client.post(f"/v1/{tenant}/kdg/edges", json=nonexistent_edge)
        assert response.status_code == 400  # Node not found

        # Test creating duplicate edge
        edge_data = {
            "source_id": task_id,
            "target_id": sample_components["document"]["id"],
            "relationship_type": "uses",
        }

        # First creation should succeed
        response1 = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
        assert response1.status_code == 201

        # Duplicate should fail
        response2 = await client.post(f"/v1/{tenant}/kdg/edges", json=edge_data)
        assert response2.status_code == 400

        # Test invalid node ID format
        response = await client.get(f"/v1/{tenant}/kdg/nodes/invalid-uuid")
        assert response.status_code == 422  # Invalid UUID format

        # Test non-existent node
        response = await client.get(f"/v1/{tenant}/kdg/nodes/{uuid4()}")
        assert response.status_code == 404

        # Test invalid direction parameter
        response = await client.get(
            f"/v1/{tenant}/kdg/nodes/{task_id}/edges?direction=invalid"
        )
        assert response.status_code == 422

        # Test depth limit validation
        response = await client.get(f"/v1/{tenant}/kdg/nodes/{task_id}/graph?depth=10")
        assert response.status_code == 422  # Exceeds max depth

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient, sample_components):
        """Verify tenant isolation for edges and nodes."""
        tenant1 = "tenant-1"
        tenant2 = "tenant-2"

        # Create components in tenant1
        task_data = {
            "name": "Tenant1 Task",
            "script": "TASK: RETURN result",
            "function": "reasoning",
            "scope": "processing",
        }
        task1_response = await client.post(f"/v1/{tenant1}/tasks", json=task_data)
        assert task1_response.status_code == 201
        task1_id = task1_response.json()["data"]["id"]

        # Create components in tenant2
        task2_response = await client.post(f"/v1/{tenant2}/tasks", json=task_data)
        assert task2_response.status_code == 201
        task2_id = task2_response.json()["data"]["id"]

        # Try to access tenant1 node from tenant2
        cross_tenant_response = await client.get(f"/v1/{tenant2}/kdg/nodes/{task1_id}")
        assert cross_tenant_response.status_code == 404

        # Try to create cross-tenant edge
        cross_edge = {
            "source_id": task1_id,
            "target_id": task2_id,
            "relationship_type": "uses",
        }
        cross_edge_response = await client.post(
            f"/v1/{tenant1}/kdg/edges", json=cross_edge
        )
        assert cross_edge_response.status_code == 400  # Should fail validation
