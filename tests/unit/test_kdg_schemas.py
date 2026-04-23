"""
Unit tests for KDG schemas.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysi.schemas.kdg import (
    EdgeCreate,
    EdgeDirection,
    EdgeResponse,
    EdgeType,
    EdgeUpdate,
    GraphResponse,
    NodeResponse,
    NodeType,
)


class TestNodeType:
    """Test NodeType enum."""

    def test_node_types_exist(self):
        """Test all expected node types are defined."""
        expected_types = {"task", "document", "table", "index", "tool", "skill"}
        actual_types = {nt.value for nt in NodeType}
        assert actual_types == expected_types

    def test_node_type_values(self):
        """Test specific node type values."""
        assert NodeType.TASK == "task"
        assert NodeType.DOCUMENT == "document"
        assert NodeType.TABLE == "table"
        assert NodeType.INDEX == "index"
        assert NodeType.TOOL == "tool"
        assert NodeType.SKILL == "skill"


class TestEdgeDirection:
    """Test EdgeDirection enum."""

    def test_direction_values(self):
        """Test edge direction values."""
        assert EdgeDirection.IN == "in"
        assert EdgeDirection.OUT == "out"
        assert EdgeDirection.BOTH == "both"


class TestEdgeType:
    """Test EdgeType enum."""

    def test_edge_types_exist(self):
        """Test all expected edge types are defined."""
        expected_types = {
            "uses",
            "generates",
            "updates",
            "calls",
            "transforms_into",
            "summarizes_into",
            "indexes_into",
            "derived_from",
            "enriches",
            "contains",
            "includes",
            "depends_on",
            "references",
            "staged_for",
            "feedback_for",
        }
        actual_types = {et.value for et in EdgeType}
        assert actual_types == expected_types


class TestNodeResponse:
    """Test NodeResponse schema."""

    def test_node_response_task_validation(self):
        """Test NodeResponse with Task-specific fields."""
        node_data = {
            "id": uuid4(),
            "type": NodeType.TASK,
            "name": "Test Task",
            "description": "A test task",
            "version": "1.0.0",
            "status": "enabled",
            "categories": ["security", "analysis"],
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
            "function": "reasoning",
            "scope": "processing",
        }

        node = NodeResponse(**node_data)
        assert node.type == NodeType.TASK
        assert node.function == "reasoning"
        assert node.scope == "processing"
        assert node.ku_type is None  # Should be None for tasks

    def test_node_response_document_validation(self):
        """Test NodeResponse with Document-specific fields."""
        node_data = {
            "id": uuid4(),
            "type": NodeType.DOCUMENT,
            "name": "Test Document",
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
            "document_type": "pdf",
        }

        node = NodeResponse(**node_data)
        assert node.type == NodeType.DOCUMENT
        assert node.document_type == "pdf"
        assert node.function is None  # Should be None for KUs

    def test_node_response_table_validation(self):
        """Test NodeResponse with Table-specific fields."""
        node_data = {
            "id": uuid4(),
            "type": NodeType.TABLE,
            "name": "Test Table",
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
            "row_count": 100,
            "column_count": 5,
        }

        node = NodeResponse(**node_data)
        assert node.type == NodeType.TABLE
        assert node.row_count == 100
        assert node.column_count == 5

    def test_node_response_index_validation(self):
        """Test NodeResponse with Index-specific fields."""
        node_data = {
            "id": uuid4(),
            "type": NodeType.INDEX,
            "name": "Test Index",
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
            "index_type": "simple_rag",
            "build_status": "ready",
        }

        node = NodeResponse(**node_data)
        assert node.type == NodeType.INDEX
        assert node.index_type == "simple_rag"
        assert node.build_status == "ready"

    def test_node_response_defaults(self):
        """Test NodeResponse default values."""
        node_data = {
            "id": uuid4(),
            "type": NodeType.TASK,
            "name": "Test Task",
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
        }

        node = NodeResponse(**node_data)
        assert node.description is None
        assert node.version == "1.0.0"
        assert node.status == "enabled"
        assert node.categories == []


class TestEdgeCreate:
    """Test EdgeCreate schema."""

    def test_edge_create_validation(self):
        """Test EdgeCreate with required fields."""
        edge_data = {
            "source_id": uuid4(),
            "target_id": uuid4(),
            "relationship_type": EdgeType.USES,
        }

        edge = EdgeCreate(**edge_data)
        assert edge.relationship_type == EdgeType.USES
        assert edge.is_required is False  # Default
        assert edge.execution_order == 0  # Default
        assert edge.metadata == {}  # Default

    def test_edge_create_with_optional_fields(self):
        """Test EdgeCreate with all fields."""
        metadata = {"priority": "high", "notes": "Critical dependency"}
        edge_data = {
            "source_id": uuid4(),
            "target_id": uuid4(),
            "relationship_type": EdgeType.GENERATES,
            "is_required": True,
            "execution_order": 10,
            "metadata": metadata,
        }

        edge = EdgeCreate(**edge_data)
        assert edge.is_required is True
        assert edge.execution_order == 10
        assert edge.metadata == metadata

    def test_invalid_relationship_type_rejected(self):
        """Test invalid relationship types are rejected."""
        with pytest.raises(ValueError, match="Input should be"):
            EdgeCreate(
                source_id=uuid4(), target_id=uuid4(), relationship_type="invalid_type"
            )


class TestEdgeResponse:
    """Test EdgeResponse schema."""

    def test_edge_response_structure(self):
        """Test EdgeResponse includes source and target nodes."""
        source_node = NodeResponse(
            id=uuid4(),
            type=NodeType.TASK,
            name="Source Task",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )
        target_node = NodeResponse(
            id=uuid4(),
            type=NodeType.DOCUMENT,
            name="Target Document",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

        edge_data = {
            "id": uuid4(),
            "source_node": source_node,
            "target_node": target_node,
            "relationship_type": EdgeType.USES,
            "is_required": True,
            "execution_order": 5,
            "metadata": {"test": "data"},
            "created_at": datetime.now(tz=UTC),
            "updated_at": datetime.now(tz=UTC),
        }

        edge = EdgeResponse(**edge_data)
        assert edge.source_node.type == NodeType.TASK
        assert edge.target_node.type == NodeType.DOCUMENT
        assert edge.relationship_type == EdgeType.USES


class TestEdgeUpdate:
    """Test EdgeUpdate schema."""

    def test_edge_update_partial_fields(self):
        """Test EdgeUpdate allows partial updates."""
        # All fields optional
        edge_update = EdgeUpdate()
        assert edge_update.is_required is None
        assert edge_update.execution_order is None
        assert edge_update.metadata is None

        # Update specific fields
        edge_update = EdgeUpdate(is_required=True, metadata={"updated": True})
        assert edge_update.is_required is True
        assert edge_update.execution_order is None
        assert edge_update.metadata == {"updated": True}


class TestGraphResponse:
    """Test GraphResponse schema."""

    def test_graph_response_structure(self):
        """Test GraphResponse contains nodes and edges arrays."""
        nodes = [
            NodeResponse(
                id=uuid4(),
                type=NodeType.TASK,
                name="Task 1",
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
            NodeResponse(
                id=uuid4(),
                type=NodeType.DOCUMENT,
                name="Document 1",
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
        ]

        edges = [
            EdgeResponse(
                id=uuid4(),
                source_node=nodes[0],
                target_node=nodes[1],
                relationship_type=EdgeType.USES,
                is_required=False,
                execution_order=0,
                metadata={},
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
        ]

        graph = GraphResponse(
            nodes=nodes,
            edges=edges,
            traversal_depth=2,
            total_nodes=2,
            total_edges=1,
        )

        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert graph.traversal_depth == 2
        assert graph.total_nodes == 2
        assert graph.total_edges == 1
