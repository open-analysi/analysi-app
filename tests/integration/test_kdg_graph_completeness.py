"""Integration tests for KDG graph completeness and node visibility.

This test suite specifically validates that the global graph endpoint returns
all types of nodes (tasks, tables, documents, indexes) and their relationships.

It replicates the bug where KUs were not appearing in the global graph due to
incorrect join conditions in the KDG repository.
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.services.task_feedback import TaskFeedbackService


@pytest.mark.asyncio
@pytest.mark.integration
class TestKDGGraphCompleteness:
    """Test that global graph endpoint returns complete node and edge data."""

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
    async def test_components(self, client: AsyncClient) -> dict:
        """Create comprehensive test data including all component types."""
        tenant = "graph-test-tenant"

        # Create a task
        task_response = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": "Test Security Task",
                "description": "A task for testing graph completeness",
                "script": "TASK test: RETURN 'complete'",
                "scope": "processing",
                "function": "analysis",
            },
        )
        assert task_response.status_code == 201
        task = task_response.json()["data"]

        # Create a table KU
        table_response = await client.post(
            f"/v1/{tenant}/knowledge-units/tables",
            json={
                "name": "Test Security Table",
                "description": "A table for testing graph completeness",
                "content": {"data": [{"id": 1, "value": "test"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )
        assert table_response.status_code == 201
        table = table_response.json()["data"]

        # Create a document KU
        doc_response = await client.post(
            f"/v1/{tenant}/knowledge-units/documents",
            json={
                "name": "Test Security Document",
                "description": "A document for testing graph completeness",
                "content": "This is test security documentation.",
                "document_type": "markdown",
            },
        )
        assert doc_response.status_code == 201
        document = doc_response.json()["data"]

        # Create an index KU
        index_response = await client.post(
            f"/v1/{tenant}/knowledge-units/indexes",
            json={
                "name": "Test Security Index",
                "description": "An index for testing graph completeness",
                "index_type": "vector",
                "vector_database": "pinecone",
                "embedding_model": "text-embedding-ada-002",
                "chunking_config": {"chunk_size": 1000},
            },
        )
        assert index_response.status_code == 201
        index = index_response.json()["data"]

        return {
            "tenant": tenant,
            "task": task,
            "table": table,
            "document": document,
            "index": index,
        }

    @pytest.fixture
    async def test_edges(self, client: AsyncClient, test_components: dict) -> dict:
        """Create edges between the test components."""
        tenant = test_components["tenant"]

        # Create task -> table edge
        task_table_edge = await client.post(
            f"/v1/{tenant}/kdg/edges",
            json={
                "source_id": test_components["task"]["id"],
                "target_id": test_components["table"]["id"],
                "relationship_type": "uses",
                "is_required": True,
                "metadata": {"purpose": "Testing task-table relationship"},
            },
        )
        assert task_table_edge.status_code == 201

        # Create task -> document edge
        task_doc_edge = await client.post(
            f"/v1/{tenant}/kdg/edges",
            json={
                "source_id": test_components["task"]["id"],
                "target_id": test_components["document"]["id"],
                "relationship_type": "uses",
                "is_required": False,
                "metadata": {"purpose": "Testing task-document relationship"},
            },
        )
        assert task_doc_edge.status_code == 201

        # Create document -> index edge
        doc_index_edge = await client.post(
            f"/v1/{tenant}/kdg/edges",
            json={
                "source_id": test_components["document"]["id"],
                "target_id": test_components["index"]["id"],
                "relationship_type": "indexes_into",
                "is_required": False,
                "metadata": {"purpose": "Testing document-index relationship"},
            },
        )
        assert doc_index_edge.status_code == 201

        return {
            "task_table": task_table_edge.json()["data"],
            "task_doc": task_doc_edge.json()["data"],
            "doc_index": doc_index_edge.json()["data"],
        }

    @pytest.mark.asyncio
    async def test_global_graph_includes_all_node_types(
        self, client: AsyncClient, test_components: dict, test_edges: dict
    ):
        """Test that global graph endpoint returns all node types."""
        tenant = test_components["tenant"]

        # Get the global graph
        response = await client.get(f"/v1/{tenant}/kdg/graph")
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Verify response structure
        assert "nodes" in graph_data
        assert "edges" in graph_data
        assert isinstance(graph_data["nodes"], list)
        assert isinstance(graph_data["edges"], list)

        # Should have exactly 4 nodes (1 task + 1 table + 1 document + 1 index)
        assert len(graph_data["nodes"]) == 4, (
            f"Expected 4 nodes, got {len(graph_data['nodes'])}"
        )

        # Should have exactly 3 edges
        assert len(graph_data["edges"]) == 3, (
            f"Expected 3 edges, got {len(graph_data['edges'])}"
        )

        # Extract node types
        node_types = [node["type"] for node in graph_data["nodes"]]

        # Verify all expected node types are present
        expected_types = {"task", "table", "document", "index"}
        actual_types = set(node_types)

        assert actual_types == expected_types, (
            f"Missing node types. Expected: {expected_types}, "
            f"Got: {actual_types}, "
            f"Missing: {expected_types - actual_types}"
        )

        # Verify each node has proper structure
        for node in graph_data["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert "data" in node
            assert "name" in node["data"]
            assert "description" in node["data"]

    @pytest.mark.asyncio
    async def test_graph_filtering_includes_knowledge_units_only(
        self, client: AsyncClient, test_components: dict, test_edges: dict
    ):
        """Test that KU-only filtering works correctly (this was the main bug).

        This test specifically validates the fix for the bug where Knowledge Units
        were not appearing in the global graph endpoint due to incorrect SQL join
        conditions in KDGRepository.list_nodes().

        Bug details:
        - Original code: Component.id == KnowledgeUnit.id (WRONG)
        - Fixed code: Component.id == KnowledgeUnit.component_id (CORRECT)

        Without the fix, this test would fail with 0 nodes instead of 3 KU nodes.
        """
        tenant = test_components["tenant"]

        # Get graph with only KUs
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_tasks=false&include_knowledge_units=true"
        )
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Should have exactly 3 KU nodes (table + document + index)
        assert len(graph_data["nodes"]) == 3, (
            f"Expected 3 KU nodes, got {len(graph_data['nodes'])}"
        )

        # Extract node types
        node_types = [node["type"] for node in graph_data["nodes"]]

        # Should only have KU types, no tasks
        expected_ku_types = {"table", "document", "index"}
        actual_types = set(node_types)

        assert actual_types == expected_ku_types, (
            f"KU-only filter failed. Expected: {expected_ku_types}, Got: {actual_types}"
        )

        # Should not have any task nodes
        assert "task" not in node_types, "Found task node when filtering for KUs only"

        # Should have 1 edge (document -> index, since task edges are excluded)
        assert len(graph_data["edges"]) == 1, (
            f"Expected 1 edge between KUs, got {len(graph_data['edges'])}"
        )

        # Verify the edge is document -> index
        edge = graph_data["edges"][0]
        assert edge["type"] == "indexes_into"

    @pytest.mark.asyncio
    async def test_graph_filtering_includes_tasks_only(
        self, client: AsyncClient, test_components: dict, test_edges: dict
    ):
        """Test that task-only filtering works correctly."""
        tenant = test_components["tenant"]

        # Get graph with only tasks
        response = await client.get(
            f"/v1/{tenant}/kdg/graph?include_tasks=true&include_knowledge_units=false"
        )
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Should have exactly 1 task node
        assert len(graph_data["nodes"]) == 1, (
            f"Expected 1 task node, got {len(graph_data['nodes'])}"
        )

        # Should be a task type
        node = graph_data["nodes"][0]
        assert node["type"] == "task", f"Expected task node, got {node['type']}"

        # Should have no edges (since no KUs to connect to)
        assert len(graph_data["edges"]) == 0, (
            f"Expected 0 edges for task-only, got {len(graph_data['edges'])}"
        )

    @pytest.mark.asyncio
    async def test_graph_edge_connectivity_is_correct(
        self, client: AsyncClient, test_components: dict, test_edges: dict
    ):
        """Test that edges properly connect the expected nodes."""
        tenant = test_components["tenant"]

        # Get the full graph
        response = await client.get(f"/v1/{tenant}/kdg/graph")
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Create lookup for node IDs by type and name
        nodes_by_type = {}
        for node in graph_data["nodes"]:
            node_type = node["type"]
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(node)

        # Should have one of each type
        assert len(nodes_by_type["task"]) == 1
        assert len(nodes_by_type["table"]) == 1
        assert len(nodes_by_type["document"]) == 1
        assert len(nodes_by_type["index"]) == 1

        task_id = nodes_by_type["task"][0]["id"]
        table_id = nodes_by_type["table"][0]["id"]
        document_id = nodes_by_type["document"][0]["id"]
        index_id = nodes_by_type["index"][0]["id"]

        # Verify edge connections
        edges = graph_data["edges"]

        # Find task -> table edge
        task_table_edges = [
            e for e in edges if e["source"] == task_id and e["target"] == table_id
        ]
        assert len(task_table_edges) == 1, "Missing task -> table edge"
        assert task_table_edges[0]["type"] == "uses"

        # Find task -> document edge
        task_doc_edges = [
            e for e in edges if e["source"] == task_id and e["target"] == document_id
        ]
        assert len(task_doc_edges) == 1, "Missing task -> document edge"
        assert task_doc_edges[0]["type"] == "uses"

        # Find document -> index edge
        doc_index_edges = [
            e for e in edges if e["source"] == document_id and e["target"] == index_id
        ]
        assert len(doc_index_edges) == 1, "Missing document -> index edge"
        assert doc_index_edges[0]["type"] == "indexes_into"

    @pytest.mark.asyncio
    async def test_graph_max_nodes_parameter_works_with_mixed_types(
        self, client: AsyncClient, test_components: dict, test_edges: dict
    ):
        """Test that max_nodes parameter works correctly with mixed node types."""
        tenant = test_components["tenant"]

        # Get graph with max_nodes=2
        response = await client.get(f"/v1/{tenant}/kdg/graph?max_nodes=2")
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Should have exactly 2 nodes
        assert len(graph_data["nodes"]) == 2, (
            f"Expected 2 nodes with max_nodes=2, got {len(graph_data['nodes'])}"
        )

        # Edges should only connect the included nodes
        node_ids = {node["id"] for node in graph_data["nodes"]}

        for edge in graph_data["edges"]:
            assert edge["source"] in node_ids, (
                f"Edge source {edge['source']} not in included nodes"
            )
            assert edge["target"] in node_ids, (
                f"Edge target {edge['target']} not in included nodes"
            )

    @pytest.mark.asyncio
    async def test_graph_with_no_relationships_returns_unconnected_nodes(
        self, client: AsyncClient
    ):
        """Test that nodes without relationships still appear in the graph."""
        tenant = "isolated-nodes-test"

        # Create isolated components (no edges)
        task_response = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": "Isolated Task",
                "description": "A task with no relationships",
                "script": "TASK isolated: RETURN 'alone'",
                "scope": "processing",
            },
        )
        assert task_response.status_code == 201

        table_response = await client.post(
            f"/v1/{tenant}/knowledge-units/tables",
            json={
                "name": "Isolated Table",
                "description": "A table with no relationships",
                "content": {"data": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        assert table_response.status_code == 201

        # Get the graph (should include both nodes even without edges)
        response = await client.get(f"/v1/{tenant}/kdg/graph")
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Should have both nodes
        assert len(graph_data["nodes"]) == 2, (
            f"Expected 2 isolated nodes, got {len(graph_data['nodes'])}"
        )

        # Should have no edges
        assert len(graph_data["edges"]) == 0, (
            f"Expected 0 edges for isolated nodes, got {len(graph_data['edges'])}"
        )

        # Verify both node types are present
        node_types = {node["type"] for node in graph_data["nodes"]}
        assert node_types == {
            "task",
            "table",
        }, f"Expected task and table types, got {node_types}"

    @pytest.mark.asyncio
    async def test_empty_tenant_returns_empty_graph(self, client: AsyncClient):
        """Test that empty tenant returns empty but valid graph structure."""
        empty_tenant = "empty-tenant-test"

        # Get graph for tenant with no data
        response = await client.get(f"/v1/{empty_tenant}/kdg/graph")
        assert response.status_code == 200

        graph_data = response.json()["data"]

        # Should have empty but valid structure
        assert "nodes" in graph_data
        assert "edges" in graph_data
        assert graph_data["nodes"] == []
        assert graph_data["edges"] == []
        assert len(graph_data["nodes"]) == 0
        assert len(graph_data["edges"]) == 0

    @pytest.mark.asyncio
    async def test_node_graph_includes_feedback_edges(self, client: AsyncClient):
        """Test that GET /kdg/nodes/{id}/graph returns feedback edges.

        Reproduces Project Zakynthos bug: feedback document nodes appeared in
        the BFS graph response but the FEEDBACK_FOR edges connecting them to the
        task were silently dropped because the schema EdgeType StrEnum was
        missing the 'feedback_for' value.
        """
        tenant = f"feedback-graph-{uuid4().hex[:8]}"

        # Create a task
        task_resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": "Task With Feedback",
                "description": "Task to test feedback edges in graph",
                "script": "TASK feedback_test: RETURN 'ok'",
                "scope": "processing",
            },
        )
        assert task_resp.status_code == 201
        task_id = task_resp.json()["data"]["id"]

        # Add feedback entries
        for text in ["First feedback", "Second feedback"]:
            fb_resp = await client.post(
                f"/v1/{tenant}/tasks/{task_id}/feedback",
                json={"feedback": text},
            )
            assert fb_resp.status_code == 201

        # Fetch the BFS graph starting from the task node
        graph_resp = await client.get(f"/v1/{tenant}/kdg/nodes/{task_id}/graph")
        assert graph_resp.status_code == 200

        graph = graph_resp.json()["data"]

        # Should have 3 nodes: 1 task + 2 feedback documents
        assert graph["total_nodes"] == 3, (
            f"Expected 3 nodes (1 task + 2 feedback), got {graph['total_nodes']}"
        )

        # Should have 2 edges: one FEEDBACK_FOR per feedback entry
        assert graph["total_edges"] == 2, (
            f"Expected 2 feedback_for edges, got {graph['total_edges']}"
        )

        edge_types = [e["relationship_type"] for e in graph["edges"]]
        assert all(t == "feedback_for" for t in edge_types), (
            f"Expected all edges to be feedback_for, got {edge_types}"
        )

    @pytest.mark.asyncio
    async def test_deleted_feedback_removed_from_graph(
        self, client: AsyncClient, integration_test_session: AsyncSession
    ):
        """Test that deleting feedback removes its edge from the KDG graph.

        When feedback is soft-deleted the FEEDBACK_FOR edge must also be
        removed so the BFS graph no longer traverses to the disabled node.
        """
        tenant = f"feedback-del-{uuid4().hex[:8]}"

        # Create a task
        task_resp = await client.post(
            f"/v1/{tenant}/tasks",
            json={
                "name": "Task Delete Feedback Graph",
                "description": "Test deleted feedback disappears from graph",
                "script": "TASK del_fb: RETURN 'ok'",
                "scope": "processing",
            },
        )
        assert task_resp.status_code == 201
        task_id = task_resp.json()["data"]["id"]

        # Add two feedback entries
        fb_ids = []
        for text in ["Keep this", "Delete this"]:
            fb_resp = await client.post(
                f"/v1/{tenant}/tasks/{task_id}/feedback",
                json={"feedback": text},
            )
            assert fb_resp.status_code == 201
            fb_ids.append(fb_resp.json()["data"]["id"])

        # Delete the second feedback via the service layer (bypasses ownership check)
        service = TaskFeedbackService(integration_test_session)
        deleted = await service.deactivate_feedback(tenant, UUID(fb_ids[1]))
        assert deleted is True
        await integration_test_session.commit()

        # Fetch the BFS graph — should only show the remaining feedback
        graph_resp = await client.get(f"/v1/{tenant}/kdg/nodes/{task_id}/graph")
        assert graph_resp.status_code == 200

        graph = graph_resp.json()["data"]

        assert graph["total_nodes"] == 2, (
            f"Expected 2 nodes (1 task + 1 remaining feedback), got {graph['total_nodes']}"
        )
        assert graph["total_edges"] == 1, (
            f"Expected 1 feedback_for edge, got {graph['total_edges']}"
        )
