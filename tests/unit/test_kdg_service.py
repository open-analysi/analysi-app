"""
Unit tests for KDG service.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.kdg_edge import KDGEdge
from analysi.repositories.kdg import KDGRepository
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
from analysi.services.kdg import KDGService


class TestKDGService:
    """Test KDGService class."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_repository(self):
        """Create a mock KDGRepository."""
        return AsyncMock(spec=KDGRepository)

    @pytest.fixture
    def service(self, mock_session, mock_repository):
        """Create KDGService instance with mock session and repository."""
        service = KDGService(mock_session)
        service.repository = mock_repository
        return service

    @pytest.mark.asyncio
    async def test_init(self, mock_session):
        """Test service initialization."""
        service = KDGService(mock_session)
        assert service.session == mock_session
        assert hasattr(service, "repository")

    @pytest.mark.asyncio
    async def test_create_edge(self, service, mock_repository):
        """Test creating a new edge with validation."""
        edge_data = EdgeCreate(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=EdgeType.USES,
        )
        tenant_id = "test-tenant"

        # Mock repository methods
        mock_repository.validate_nodes_exist.return_value = {
            edge_data.source_id: True,
            edge_data.target_id: True,
        }
        mock_repository.detect_cycles.return_value = False
        mock_repository.list_edges.return_value = ([], 0)  # No existing edges

        # Mock created edge with required attributes
        from datetime import UTC, datetime

        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = uuid4()
        mock_edge.source_id = edge_data.source_id
        mock_edge.target_id = edge_data.target_id
        mock_edge.relationship_type = edge_data.relationship_type.value
        mock_edge.is_required = False
        mock_edge.execution_order = 0
        mock_edge.edge_metadata = {}
        mock_edge.tenant_id = tenant_id
        mock_edge.created_at = datetime.now(tz=UTC)
        mock_edge.updated_at = datetime.now(tz=UTC)
        mock_repository.create_edge.return_value = mock_edge

        # Mock source and target nodes with proper attributes
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        mock_source = MagicMock(spec=Component)
        mock_source.id = edge_data.source_id
        mock_source.name = "Source Node"
        mock_source.description = "Source description"
        mock_source.kind = ComponentKind.TASK
        mock_source.version = "1.0.0"
        mock_source.status = "active"
        mock_source.categories = []
        mock_source.created_at = datetime.now(tz=UTC)
        mock_source.updated_at = datetime.now(tz=UTC)
        mock_source.task = MagicMock()
        mock_source.task.function = "reasoning"
        mock_source.task.scope = "processing"

        mock_target = MagicMock(spec=Component)
        mock_target.id = edge_data.target_id
        mock_target.name = "Target Node"
        mock_target.description = "Target description"
        mock_target.kind = ComponentKind.TASK
        mock_target.version = "1.0.0"
        mock_target.status = "active"
        mock_target.categories = []
        mock_target.created_at = datetime.now(tz=UTC)
        mock_target.updated_at = datetime.now(tz=UTC)
        mock_target.task = MagicMock()
        mock_target.task.function = "extraction"
        mock_target.task.scope = "processing"

        mock_repository.get_node_by_id.side_effect = [mock_source, mock_target]

        result = await service.create_edge(edge_data, tenant_id)

        # Verify repository calls
        mock_repository.validate_nodes_exist.assert_called_once_with(
            [edge_data.source_id, edge_data.target_id], tenant_id
        )
        mock_repository.detect_cycles.assert_called_once_with(
            edge_data.source_id, edge_data.target_id, tenant_id
        )
        mock_repository.create_edge.assert_called_once()

        assert isinstance(result, EdgeResponse)
        assert result.source_node.id == edge_data.source_id
        assert result.target_node.id == edge_data.target_id
        assert result.relationship_type == edge_data.relationship_type.value

    @pytest.mark.asyncio
    async def test_create_edge_with_metadata(self, service, mock_repository):
        """Test creating edge with metadata."""
        metadata = {"priority": "high", "notes": "Critical dependency"}
        edge_data = EdgeCreate(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=EdgeType.GENERATES,
            is_required=True,
            execution_order=10,
            metadata=metadata,
        )
        tenant_id = "test-tenant"

        # Mock repository methods
        mock_repository.validate_nodes_exist.return_value = {
            edge_data.source_id: True,
            edge_data.target_id: True,
        }
        mock_repository.detect_cycles.return_value = False
        mock_repository.list_edges.return_value = ([], 0)  # No existing edges

        # Mock created edge with metadata
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = uuid4()
        mock_edge.source_id = edge_data.source_id
        mock_edge.target_id = edge_data.target_id
        mock_edge.relationship_type = edge_data.relationship_type.value
        mock_edge.is_required = True
        mock_edge.execution_order = 10
        mock_edge.edge_metadata = metadata
        mock_edge.tenant_id = tenant_id
        mock_edge.created_at = datetime.now(tz=UTC)
        mock_edge.updated_at = datetime.now(tz=UTC)
        mock_repository.create_edge.return_value = mock_edge

        # Mock nodes with proper attributes
        mock_source = MagicMock(spec=Component)
        mock_source.id = edge_data.source_id
        mock_source.name = "Source Node"
        mock_source.description = "Source description"
        mock_source.kind = ComponentKind.TASK
        mock_source.version = "1.0.0"
        mock_source.status = "active"
        mock_source.categories = []
        mock_source.created_at = datetime.now(tz=UTC)
        mock_source.updated_at = datetime.now(tz=UTC)
        mock_source.task = MagicMock()
        mock_source.task.function = "reasoning"
        mock_source.task.scope = "processing"

        mock_target = MagicMock(spec=Component)
        mock_target.id = edge_data.target_id
        mock_target.name = "Target Node"
        mock_target.description = "Target description"
        mock_target.kind = ComponentKind.TASK
        mock_target.version = "1.0.0"
        mock_target.status = "active"
        mock_target.categories = []
        mock_target.created_at = datetime.now(tz=UTC)
        mock_target.updated_at = datetime.now(tz=UTC)
        mock_target.task = MagicMock()
        mock_target.task.function = "extraction"
        mock_target.task.scope = "processing"

        mock_repository.get_node_by_id.side_effect = [mock_source, mock_target]

        result = await service.create_edge(edge_data, tenant_id)

        assert isinstance(result, EdgeResponse)
        assert result.is_required is True
        assert result.execution_order == 10
        assert result.metadata == metadata

    @pytest.mark.asyncio
    async def test_get_edge(self, service, mock_repository):
        """Test getting edge with full node details."""
        edge_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return None (edge not found)
        mock_repository.get_edge_by_id.return_value = None

        result = await service.get_edge(edge_id, tenant_id)

        mock_repository.get_edge_by_id.assert_called_once_with(edge_id, tenant_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_edge(self, service, mock_repository):
        """Test deleting an edge."""
        edge_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return existing edge
        mock_edge = MagicMock(spec=KDGEdge)
        mock_repository.get_edge_by_id.return_value = mock_edge
        mock_repository.delete_edge.return_value = None

        result = await service.delete_edge(edge_id, tenant_id)

        mock_repository.get_edge_by_id.assert_called_once_with(edge_id, tenant_id)
        mock_repository.delete_edge.assert_called_once_with(mock_edge)
        assert result is True

    @pytest.mark.asyncio
    async def test_update_edge(self, service, mock_repository):
        """Test updating edge metadata."""
        edge_id = uuid4()
        update_data = EdgeUpdate(is_required=True, metadata={"updated": True})
        tenant_id = "test-tenant"

        # Mock repository to return None (edge not found)
        mock_repository.get_edge_by_id.return_value = None

        result = await service.update_edge(edge_id, update_data, tenant_id)

        mock_repository.get_edge_by_id.assert_called_once_with(edge_id, tenant_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_node(self, service, mock_repository):
        """Test getting node details (Task or KU)."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return None (node not found)
        mock_repository.get_node_by_id.return_value = None

        result = await service.get_node(node_id, tenant_id)

        mock_repository.get_node_by_id.assert_called_once_with(node_id, tenant_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_nodes_no_filters(self, service, mock_repository):
        """Test listing nodes without filters."""
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        mock_repository.list_nodes.return_value = ([], 0)

        nodes, total = await service.list_nodes(tenant_id)

        mock_repository.list_nodes.assert_called_once_with(
            tenant_id=tenant_id, node_type=None, search_query=None, limit=100, offset=0
        )
        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_nodes_with_type_filter(self, service, mock_repository):
        """Test listing nodes with type filter."""
        tenant_id = "test-tenant"
        node_type = NodeType.TASK

        # Mock repository to return empty list with task filter
        mock_repository.list_nodes.return_value = ([], 0)

        nodes, total = await service.list_nodes(
            tenant_id=tenant_id,
            node_type=node_type,
        )

        mock_repository.list_nodes.assert_called_once_with(
            tenant_id=tenant_id,
            node_type=node_type.value,
            search_query=None,
            limit=100,
            offset=0,
        )
        assert isinstance(nodes, list)
        assert len(nodes) == 0
        assert isinstance(total, int)
        # All returned nodes should be of specified type
        for node in nodes:
            assert isinstance(node, NodeResponse)
            assert node.type == NodeType.TASK

    @pytest.mark.asyncio
    async def test_list_nodes_with_search_query(self, service, mock_repository):
        """Test listing nodes with search query."""
        tenant_id = "test-tenant"
        search_query = "security analysis"

        # Mock repository to return empty list with search
        mock_repository.list_nodes.return_value = ([], 0)

        nodes, total = await service.list_nodes(
            tenant_id=tenant_id,
            search_query=search_query,
        )

        mock_repository.list_nodes.assert_called_once_with(
            tenant_id=tenant_id,
            node_type=None,
            search_query=search_query,
            limit=100,
            offset=0,
        )
        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_list_nodes_with_pagination(self, service, mock_repository):
        """Test listing nodes with pagination."""
        tenant_id = "test-tenant"

        # Mock repository to return empty list with pagination
        mock_repository.list_nodes.return_value = ([], 0)

        nodes, total = await service.list_nodes(
            tenant_id=tenant_id,
            limit=50,
            offset=20,
        )

        mock_repository.list_nodes.assert_called_once_with(
            tenant_id=tenant_id, node_type=None, search_query=None, limit=50, offset=20
        )
        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_in(self, service, mock_repository):
        """Test getting incoming edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        mock_repository.get_node_edges.return_value = ([], 0)

        edges, total = await service.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.IN,
        )

        mock_repository.get_node_edges.assert_called_once_with(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.IN,
            limit=100,
            offset=0,
        )
        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_out(self, service, mock_repository):
        """Test getting outgoing edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        mock_repository.get_node_edges.return_value = ([], 0)

        edges, total = await service.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.OUT,
        )

        mock_repository.get_node_edges.assert_called_once_with(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.OUT,
            limit=100,
            offset=0,
        )
        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_both(self, service, mock_repository):
        """Test getting all edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        mock_repository.get_node_edges.return_value = ([], 0)

        edges, total = await service.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.BOTH,
        )

        mock_repository.get_node_edges.assert_called_once_with(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.BOTH,
            limit=100,
            offset=0,
        )
        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_get_node_edges_with_pagination(self, service, mock_repository):
        """Test getting node edges with pagination."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        mock_repository.get_node_edges.return_value = ([], 0)

        edges, total = await service.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            limit=50,
            offset=10,
        )

        mock_repository.get_node_edges.assert_called_once_with(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.BOTH,
            limit=50,
            offset=10,
        )
        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_get_node_graph_default_depth(self, service, mock_repository):
        """Test getting subgraph with default depth."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty graph
        mock_repository.get_subgraph.return_value = ([], [])

        result = await service.get_node_graph(node_id, tenant_id)

        mock_repository.get_subgraph.assert_called_once_with(
            start_node_id=node_id, tenant_id=tenant_id, max_depth=2
        )
        assert isinstance(result, GraphResponse)
        assert result.traversal_depth == 2  # Default
        assert isinstance(result.nodes, list)
        assert isinstance(result.edges, list)
        assert len(result.nodes) == 0
        assert len(result.edges) == 0

    @pytest.mark.asyncio
    async def test_get_node_graph_custom_depth(self, service, mock_repository):
        """Test getting subgraph with custom depth."""
        node_id = uuid4()
        tenant_id = "test-tenant"
        depth = 3

        # Mock repository to return empty graph
        mock_repository.get_subgraph.return_value = ([], [])

        result = await service.get_node_graph(node_id, tenant_id, depth)

        mock_repository.get_subgraph.assert_called_once_with(
            start_node_id=node_id, tenant_id=tenant_id, max_depth=depth
        )
        assert isinstance(result, GraphResponse)
        assert result.traversal_depth == depth

    @pytest.mark.asyncio
    async def test_validate_no_cycles(self, service, mock_repository):
        """Test cycle validation."""
        source_id = uuid4()
        target_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return no cycle detected
        mock_repository.detect_cycles.return_value = False

        is_safe = await service.validate_no_cycles(source_id, target_id, tenant_id)

        mock_repository.detect_cycles.assert_called_once_with(
            source_id, target_id, tenant_id
        )
        assert isinstance(is_safe, bool)
        assert is_safe is True

    @pytest.mark.asyncio
    async def test_component_to_node_response(self, service, mock_repository):
        """Test converting Component model to NodeResponse schema."""
        from datetime import UTC, datetime

        from analysi.models.component import Component, ComponentKind

        # Create mock component
        mock_component = MagicMock(spec=Component)
        mock_component.id = uuid4()
        mock_component.kind = ComponentKind.TASK
        mock_component.name = "Test Task"
        mock_component.description = "Test description"
        mock_component.version = "1.0.0"
        mock_component.status = "active"
        mock_component.categories = []
        mock_component.created_at = datetime.now(tz=UTC)
        mock_component.updated_at = datetime.now(tz=UTC)
        mock_component.knowledge_unit = None
        mock_component.task = MagicMock()
        mock_component.task.function = "reasoning"
        mock_component.task.scope = "processing"

        result = service._component_to_node_response(mock_component)

        assert isinstance(result, NodeResponse)
        assert result.id == mock_component.id
        assert result.name == mock_component.name

    @pytest.mark.asyncio
    async def test_edge_to_response(self, service, mock_repository):
        """Test converting KDGEdge model to EdgeResponse schema."""
        from datetime import UTC, datetime

        # Create mock edge
        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = uuid4()
        mock_edge.source_id = uuid4()
        mock_edge.target_id = uuid4()
        mock_edge.relationship_type = "uses"
        mock_edge.is_required = False
        mock_edge.execution_order = 0
        mock_edge.edge_metadata = {}
        mock_edge.created_at = datetime.now(tz=UTC)
        mock_edge.updated_at = datetime.now(tz=UTC)

        # Mock repository calls for getting nodes
        from analysi.models.component import ComponentKind

        mock_source = MagicMock(spec=Component)
        mock_source.id = mock_edge.source_id
        mock_source.kind = ComponentKind.TASK
        mock_source.name = "Source Node"
        mock_source.description = "Source description"
        mock_source.version = "1.0.0"
        mock_source.status = "active"
        mock_source.categories = []
        mock_source.created_at = datetime.now(tz=UTC)
        mock_source.updated_at = datetime.now(tz=UTC)
        mock_source.knowledge_unit = None
        mock_source.task = MagicMock()
        mock_source.task.function = "reasoning"
        mock_source.task.scope = "processing"

        mock_target = MagicMock(spec=Component)
        mock_target.id = mock_edge.target_id
        mock_target.kind = ComponentKind.TASK
        mock_target.name = "Target Node"
        mock_target.description = "Target description"
        mock_target.version = "1.0.0"
        mock_target.status = "active"
        mock_target.categories = []
        mock_target.created_at = datetime.now(tz=UTC)
        mock_target.updated_at = datetime.now(tz=UTC)
        mock_target.knowledge_unit = None
        mock_target.task = MagicMock()
        mock_target.task.function = "extraction"
        mock_target.task.scope = "processing"

        mock_repository.get_node_by_id.side_effect = [mock_source, mock_target]

        result = await service._edge_to_response(mock_edge)

        assert isinstance(result, EdgeResponse)
        assert result.id == mock_edge.id
        assert result.relationship_type == mock_edge.relationship_type

    @pytest.mark.asyncio
    async def test_business_logic_validation_scope(self, service, mock_repository):
        """Test that service handles business logic validation."""
        # Create edge that would normally be validated
        edge_data = EdgeCreate(
            source_id=uuid4(),
            target_id=uuid4(),
            relationship_type=EdgeType.USES,
        )
        tenant_id = "test-tenant"

        # Mock successful validations
        mock_repository.validate_nodes_exist.return_value = {
            edge_data.source_id: True,
            edge_data.target_id: True,
        }
        mock_repository.detect_cycles.return_value = False
        mock_repository.list_edges.return_value = ([], 0)  # No existing edges

        # Mock created edge and components with proper attributes
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = uuid4()
        mock_edge.source_id = edge_data.source_id
        mock_edge.target_id = edge_data.target_id
        mock_edge.relationship_type = edge_data.relationship_type.value
        mock_edge.is_required = False
        mock_edge.execution_order = 0
        mock_edge.edge_metadata = {}
        mock_edge.tenant_id = tenant_id
        mock_edge.created_at = datetime.now(tz=UTC)
        mock_edge.updated_at = datetime.now(tz=UTC)
        mock_repository.create_edge.return_value = mock_edge

        mock_source = MagicMock(spec=Component)
        mock_source.id = edge_data.source_id
        mock_source.kind = ComponentKind.TASK
        mock_source.name = "Source Node"
        mock_source.description = "Source description"
        mock_source.version = "1.0.0"
        mock_source.status = "active"
        mock_source.categories = []
        mock_source.created_at = datetime.now(tz=UTC)
        mock_source.updated_at = datetime.now(tz=UTC)
        mock_source.knowledge_unit = None
        mock_source.task = MagicMock()
        mock_source.task.function = "reasoning"
        mock_source.task.scope = "processing"

        mock_target = MagicMock(spec=Component)
        mock_target.id = edge_data.target_id
        mock_target.kind = ComponentKind.TASK
        mock_target.name = "Target Node"
        mock_target.description = "Target description"
        mock_target.version = "1.0.0"
        mock_target.status = "active"
        mock_target.categories = []
        mock_target.created_at = datetime.now(tz=UTC)
        mock_target.updated_at = datetime.now(tz=UTC)
        mock_target.knowledge_unit = None
        mock_target.task = MagicMock()
        mock_target.task.function = "extraction"
        mock_target.task.scope = "processing"

        mock_repository.get_node_by_id.side_effect = [mock_source, mock_target]

        result = await service.create_edge(edge_data, tenant_id)

        # Should return valid EdgeResponse if all validations pass
        assert isinstance(result, EdgeResponse)

    @pytest.mark.asyncio
    async def test_graph_traversal_performance_considerations(
        self, service, mock_repository
    ):
        """Test that graph traversal has performance constraints."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return empty graph
        mock_repository.get_subgraph.return_value = ([], [])

        # Should handle max depth (5) without issues
        result = await service.get_node_graph(node_id, tenant_id, depth=5)

        mock_repository.get_subgraph.assert_called_once_with(
            start_node_id=node_id, tenant_id=tenant_id, max_depth=5
        )
        assert isinstance(result, GraphResponse)
        assert result.traversal_depth == 5

    @pytest.mark.asyncio
    async def test_tenant_isolation_all_methods(self, service, mock_repository):
        """Test that all service methods enforce tenant isolation."""
        methods_requiring_tenant = [
            "create_edge",
            "get_edge",
            "delete_edge",
            "update_edge",
            "get_node",
            "list_nodes",
            "get_node_edges",
            "get_node_graph",
            "validate_no_cycles",
        ]

        for method_name in methods_requiring_tenant:
            method = getattr(service, method_name)
            # Check method signature includes tenant_id
            import inspect

            sig = inspect.signature(method)
            assert "tenant_id" in sig.parameters, (
                f"{method_name} should require tenant_id"
            )

    @pytest.mark.asyncio
    async def test_component_to_node_response_skill_type(self, service):
        """Test that MODULE components map to SKILL node type with ku_type=None."""
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        mock_component = MagicMock(spec=Component)
        mock_component.id = uuid4()
        mock_component.kind = ComponentKind.MODULE
        mock_component.name = "Test Skill"
        mock_component.description = "A test skill"
        mock_component.version = "1.0.0"
        mock_component.status = "active"
        mock_component.categories = []
        mock_component.created_at = datetime.now(tz=UTC)
        mock_component.updated_at = datetime.now(tz=UTC)
        mock_component.knowledge_unit = None
        mock_component.knowledge_module = MagicMock()

        result = service._component_to_node_response(mock_component)

        assert isinstance(result, NodeResponse)
        assert result.type == NodeType.SKILL
        assert result.ku_type is None

    @pytest.mark.asyncio
    async def test_get_global_graph_includes_skills(self, service, mock_repository):
        """Test that get_global_graph includes skill nodes when enabled."""
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        tenant_id = "test-tenant"

        # Create a mock skill node
        skill_id = uuid4()
        mock_skill_component = MagicMock(spec=Component)
        mock_skill_component.id = skill_id
        mock_skill_component.kind = ComponentKind.MODULE
        mock_skill_component.name = "My Skill"
        mock_skill_component.description = "Skill description"
        mock_skill_component.version = "1.0.0"
        mock_skill_component.status = "active"
        mock_skill_component.categories = []
        mock_skill_component.created_at = datetime.now(tz=UTC)
        mock_skill_component.updated_at = datetime.now(tz=UTC)
        mock_skill_component.knowledge_unit = None
        mock_skill_component.knowledge_module = MagicMock()

        skill_node = service._component_to_node_response(mock_skill_component)

        # list_nodes returns empty for all types except SKILL
        async def mock_list_nodes(tenant_id, node_type=None, limit=1000, offset=0):
            if node_type == NodeType.SKILL:
                return [skill_node], 1
            return [], 0

        service.list_nodes = AsyncMock(side_effect=mock_list_nodes)
        mock_repository.get_all_edges.return_value = []

        result = await service.get_global_graph(tenant_id, include_skills=True)

        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == str(skill_id)
        assert result["nodes"][0]["type"] == NodeType.SKILL

    @pytest.mark.asyncio
    async def test_get_global_graph_excludes_skills_when_disabled(
        self, service, mock_repository
    ):
        """Test that get_global_graph excludes skills when include_skills=False."""
        tenant_id = "test-tenant"

        call_args_list = []

        async def mock_list_nodes(tenant_id, node_type=None, limit=1000, offset=0):
            call_args_list.append(node_type)
            return [], 0

        service.list_nodes = AsyncMock(side_effect=mock_list_nodes)
        mock_repository.get_all_edges.return_value = []

        await service.get_global_graph(tenant_id, include_skills=False)

        assert NodeType.SKILL not in call_args_list

    @pytest.mark.asyncio
    async def test_get_global_graph_filters_edges_to_included_nodes(
        self, service, mock_repository
    ):
        """Test that edges with source/target not in node_ids are excluded."""
        from datetime import UTC, datetime

        from analysi.models.component import ComponentKind

        tenant_id = "test-tenant"

        # Create two task nodes
        task1_id = uuid4()
        task2_id = uuid4()
        orphan_id = uuid4()  # Not in the returned nodes

        mock_task1 = MagicMock(spec=Component)
        mock_task1.id = task1_id
        mock_task1.kind = ComponentKind.TASK
        mock_task1.name = "Task 1"
        mock_task1.description = "Task 1"
        mock_task1.version = "1.0.0"
        mock_task1.status = "active"
        mock_task1.categories = []
        mock_task1.created_at = datetime.now(tz=UTC)
        mock_task1.updated_at = datetime.now(tz=UTC)
        mock_task1.knowledge_unit = None
        mock_task1.task = MagicMock(function="reasoning", scope="processing")

        mock_task2 = MagicMock(spec=Component)
        mock_task2.id = task2_id
        mock_task2.kind = ComponentKind.TASK
        mock_task2.name = "Task 2"
        mock_task2.description = "Task 2"
        mock_task2.version = "1.0.0"
        mock_task2.status = "active"
        mock_task2.categories = []
        mock_task2.created_at = datetime.now(tz=UTC)
        mock_task2.updated_at = datetime.now(tz=UTC)
        mock_task2.knowledge_unit = None
        mock_task2.task = MagicMock(function="search", scope="processing")

        task1_node = service._component_to_node_response(mock_task1)
        task2_node = service._component_to_node_response(mock_task2)

        async def mock_list_nodes(tenant_id, node_type=None, limit=1000, offset=0):
            if node_type == NodeType.TASK:
                return [task1_node, task2_node], 2
            return [], 0

        service.list_nodes = AsyncMock(side_effect=mock_list_nodes)

        # Create edges: one valid (task1->task2), one orphan (task1->orphan_id)
        valid_edge = MagicMock(spec=KDGEdge)
        valid_edge.source_id = task1_id
        valid_edge.target_id = task2_id
        valid_edge.relationship_type = "uses"
        valid_edge.edge_metadata = {}

        orphan_edge = MagicMock(spec=KDGEdge)
        orphan_edge.source_id = task1_id
        orphan_edge.target_id = orphan_id
        orphan_edge.relationship_type = "uses"
        orphan_edge.edge_metadata = {}

        mock_repository.get_all_edges.return_value = [valid_edge, orphan_edge]

        result = await service.get_global_graph(
            tenant_id,
            include_knowledge_units=False,
            include_tools=False,
            include_skills=False,
        )

        assert len(result["edges"]) == 1
        assert result["edges"][0]["source"] == str(task1_id)
        assert result["edges"][0]["target"] == str(task2_id)
