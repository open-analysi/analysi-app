"""
Unit tests for KDG repository.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.kdg_edge import KDGEdge
from analysi.repositories.kdg import KDGRepository
from analysi.schemas.kdg import EdgeDirection


class TestKDGRepository:
    """Test KDGRepository class."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create KDGRepository instance with mock session."""
        return KDGRepository(mock_session)

    @pytest.mark.asyncio
    async def test_init(self, mock_session):
        """Test repository initialization."""
        repo = KDGRepository(mock_session)
        assert repo.session == mock_session

    @pytest.mark.asyncio
    async def test_create_edge(self, repository, mock_session):
        """Test creating a new edge."""
        tenant_id = "test-tenant"
        source_id = uuid4()
        target_id = uuid4()
        relationship_type = "uses"

        # Mock the edge object
        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.source_id = source_id
        mock_edge.target_id = target_id
        mock_edge.relationship_type = relationship_type

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock KDGEdge constructor to return our mock
        with patch("analysi.repositories.kdg.KDGEdge", return_value=mock_edge):
            result = await repository.create_edge(
                tenant_id=tenant_id,
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
            )

        # Verify calls
        mock_session.add.assert_called_once_with(mock_edge)
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_edge)
        assert result == mock_edge

    @pytest.mark.asyncio
    async def test_create_edge_with_optional_params(self, repository, mock_session):
        """Test creating edge with optional parameters."""
        tenant_id = "test-tenant"
        source_id = uuid4()
        target_id = uuid4()
        relationship_type = "generates"
        metadata = {"priority": "high"}

        # Mock the edge object with optional params
        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.source_id = source_id
        mock_edge.target_id = target_id
        mock_edge.relationship_type = relationship_type
        mock_edge.is_required = True
        mock_edge.execution_order = 10
        mock_edge.metadata = metadata

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock KDGEdge constructor to return our mock
        with patch("analysi.repositories.kdg.KDGEdge", return_value=mock_edge):
            result = await repository.create_edge(
                tenant_id=tenant_id,
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                is_required=True,
                execution_order=10,
                metadata=metadata,
            )

        assert result == mock_edge
        assert result.is_required is True
        assert result.execution_order == 10
        assert result.metadata == metadata

    @pytest.mark.asyncio
    async def test_get_edge_by_id(self, repository, mock_session):
        """Test getting edge by ID."""
        edge_id = uuid4()
        tenant_id = "test-tenant"

        # Mock edge
        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = edge_id

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_edge
        mock_session.execute.return_value = mock_result

        result = await repository.get_edge_by_id(edge_id, tenant_id)

        assert result == mock_edge
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_edge(self, repository, mock_session):
        """Test deleting an edge."""
        mock_edge = MagicMock(spec=KDGEdge)

        # Mock session operations
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        await repository.delete_edge(mock_edge)

        # Verify session operations were called
        mock_session.delete.assert_called_once_with(mock_edge)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_edges_no_filters(self, repository, mock_session):
        """Test listing edges without filters."""
        tenant_id = "test-tenant"

        # Mock edges
        mock_edges = [MagicMock(spec=KDGEdge) for _ in range(3)]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        # Mock session execute to return count first, then edges
        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.list_edges(tenant_id)

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 3
        assert total == 3
        assert edges == mock_edges

    @pytest.mark.asyncio
    async def test_list_edges_with_filters(self, repository, mock_session):
        """Test listing edges with filters."""
        tenant_id = "test-tenant"
        source_id = uuid4()
        target_id = uuid4()
        relationship_type = "uses"

        # Mock filtered edges
        mock_edges = [MagicMock(spec=KDGEdge) for _ in range(2)]
        for edge in mock_edges:
            edge.source_id = source_id
            edge.target_id = target_id
            edge.relationship_type = relationship_type

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.list_edges(
            tenant_id=tenant_id,
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            limit=50,
            offset=10,
        )

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_in(self, repository, mock_session):
        """Test getting incoming edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock incoming edges
        mock_edges = [MagicMock(spec=KDGEdge) for _ in range(2)]
        for edge in mock_edges:
            edge.target_id = node_id

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.IN,
        )

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 2
        assert total == 2
        # All edges should have node_id as target
        for edge in edges:
            assert edge.target_id == node_id

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_out(self, repository, mock_session):
        """Test getting outgoing edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock outgoing edges
        mock_edges = [MagicMock(spec=KDGEdge) for _ in range(3)]
        for edge in mock_edges:
            edge.source_id = node_id

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.OUT,
        )

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 3
        assert total == 3
        # All edges should have node_id as source
        for edge in edges:
            assert edge.source_id == node_id

    @pytest.mark.asyncio
    async def test_get_node_edges_direction_both(self, repository, mock_session):
        """Test getting all edges for a node."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock edges in both directions
        mock_edges = []
        # Some incoming edges
        for _ in range(2):
            edge = MagicMock(spec=KDGEdge)
            edge.target_id = node_id
            edge.source_id = uuid4()
            mock_edges.append(edge)
        # Some outgoing edges
        for _ in range(2):
            edge = MagicMock(spec=KDGEdge)
            edge.source_id = node_id
            edge.target_id = uuid4()
            mock_edges.append(edge)

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=EdgeDirection.BOTH,
        )

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 4
        assert total == 4
        # Edges should have node_id as source OR target
        for edge in edges:
            assert edge.source_id == node_id or edge.target_id == node_id

    @pytest.mark.asyncio
    async def test_get_node_edges_default_params(self, repository, mock_session):
        """Test getting node edges with default parameters."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock edges with default behavior (BOTH direction, limit 100)
        mock_edges = [MagicMock(spec=KDGEdge) for _ in range(5)]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_edges

        # Mock edges result
        mock_edges_result = MagicMock()
        mock_edges_result.scalars.return_value.all.return_value = mock_edges

        mock_session.execute.side_effect = [mock_count_result, mock_edges_result]

        edges, total = await repository.get_node_edges(node_id, tenant_id)

        assert isinstance(edges, list)
        assert isinstance(total, int)
        assert len(edges) == 5
        assert total == 5

    @pytest.mark.asyncio
    async def test_get_node_by_id(self, repository, mock_session):
        """Test getting a node by ID."""
        node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock component
        mock_component = MagicMock(spec=Component)
        mock_component.id = node_id

        # Mock query result - first try direct component lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_component
        mock_session.execute.return_value = mock_result

        result = await repository.get_node_by_id(node_id, tenant_id)

        assert result == mock_component
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_nodes_no_filters(self, repository, mock_session):
        """Test listing nodes without filters."""
        tenant_id = "test-tenant"

        # Mock components
        mock_nodes = [MagicMock(spec=Component) for _ in range(4)]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_nodes

        # Mock nodes result
        mock_nodes_result = MagicMock()
        mock_nodes_result.scalars.return_value.all.return_value = mock_nodes

        mock_session.execute.side_effect = [mock_count_result, mock_nodes_result]

        nodes, total = await repository.list_nodes(tenant_id)

        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 4
        assert total == 4
        assert nodes == mock_nodes

    @pytest.mark.asyncio
    async def test_list_nodes_with_type_filter(self, repository, mock_session):
        """Test listing nodes with type filter."""
        tenant_id = "test-tenant"
        node_type = "task"

        # Mock task components
        mock_nodes = [MagicMock(spec=Component) for _ in range(2)]
        for node in mock_nodes:
            node.kind.value = "task"

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_nodes

        # Mock nodes result
        mock_nodes_result = MagicMock()
        mock_nodes_result.scalars.return_value.all.return_value = mock_nodes

        mock_session.execute.side_effect = [mock_count_result, mock_nodes_result]

        nodes, total = await repository.list_nodes(
            tenant_id=tenant_id,
            node_type=node_type,
        )

        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 2
        assert total == 2
        # All returned components should be tasks
        for node in nodes:
            assert node.kind.value == "task"

    @pytest.mark.asyncio
    async def test_list_nodes_with_search_query(self, repository, mock_session):
        """Test listing nodes with search query."""
        tenant_id = "test-tenant"
        search_query = "security analysis"

        # Mock matching components
        mock_nodes = [MagicMock(spec=Component) for _ in range(2)]
        mock_nodes[0].name = "Security Task"
        mock_nodes[0].description = "Security analysis task"
        mock_nodes[1].name = "Analysis Tool"
        mock_nodes[1].description = "For security scanning"

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_nodes

        # Mock nodes result
        mock_nodes_result = MagicMock()
        mock_nodes_result.scalars.return_value.all.return_value = mock_nodes

        mock_session.execute.side_effect = [mock_count_result, mock_nodes_result]

        nodes, total = await repository.list_nodes(
            tenant_id=tenant_id,
            search_query=search_query,
        )

        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 2
        assert total == 2
        # Results should be relevant to search query
        for node in nodes:
            query_terms = search_query.lower().split()
            text_to_search = f"{node.name} {node.description or ''}".lower()
            assert any(term in text_to_search for term in query_terms)

    @pytest.mark.asyncio
    async def test_list_nodes_with_pagination(self, repository, mock_session):
        """Test listing nodes with pagination."""
        tenant_id = "test-tenant"

        # Mock paginated components (simulate less than limit returned)
        mock_nodes = [MagicMock(spec=Component) for _ in range(30)]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalars.return_value.all.return_value = mock_nodes

        # Mock nodes result
        mock_nodes_result = MagicMock()
        mock_nodes_result.scalars.return_value.all.return_value = mock_nodes

        mock_session.execute.side_effect = [mock_count_result, mock_nodes_result]

        nodes, total = await repository.list_nodes(
            tenant_id=tenant_id,
            limit=50,
            offset=20,
        )

        assert isinstance(nodes, list)
        assert isinstance(total, int)
        assert len(nodes) == 30  # Less than limit
        assert total == 30
        assert len(nodes) <= 50  # Respects limit

    @pytest.mark.asyncio
    async def test_get_subgraph_default_depth(self, repository, mock_session):
        """Test BFS traversal with default depth."""
        start_node_id = uuid4()
        tenant_id = "test-tenant"

        # Mock start node
        mock_start_node = MagicMock(spec=Component)
        mock_start_node.id = start_node_id

        # Mock connected nodes
        mock_connected_node = MagicMock(spec=Component)
        mock_connected_node.id = uuid4()

        # Mock edges connecting them
        mock_edge = MagicMock(spec=KDGEdge)
        mock_edge.id = uuid4()
        mock_edge.source_id = start_node_id
        mock_edge.target_id = mock_connected_node.id

        # Mock get_node_by_id calls
        with patch.object(repository, "get_node_by_id") as mock_get_node:
            with patch.object(repository, "get_node_edges") as mock_get_edges:
                # First call gets start node
                mock_get_node.side_effect = [mock_start_node, mock_connected_node]

                # First call gets edges from start node, second gets no edges from connected node
                mock_get_edges.side_effect = [([mock_edge], 1), ([], 0)]

                nodes, edges = await repository.get_subgraph(start_node_id, tenant_id)

        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert len(nodes) == 2  # start node + connected node
        assert len(edges) == 1  # one connecting edge
        assert nodes[0] == mock_start_node
        assert nodes[1] == mock_connected_node
        assert edges[0] == mock_edge

    @pytest.mark.asyncio
    async def test_get_subgraph_custom_depth(self, repository, mock_session):
        """Test BFS traversal with custom depth."""
        start_node_id = uuid4()
        tenant_id = "test-tenant"
        max_depth = 3

        # Mock start node
        mock_start_node = MagicMock(spec=Component)
        mock_start_node.id = start_node_id

        # Mock get_node_by_id and get_node_edges to return minimal graph
        with patch.object(repository, "get_node_by_id") as mock_get_node:
            with patch.object(repository, "get_node_edges") as mock_get_edges:
                # Only start node exists, no edges
                mock_get_node.return_value = mock_start_node
                mock_get_edges.return_value = ([], 0)

                nodes, edges = await repository.get_subgraph(
                    start_node_id, tenant_id, max_depth
                )

        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        assert len(nodes) == 1  # Only start node
        assert len(edges) == 0  # No edges
        assert nodes[0] == mock_start_node

    @pytest.mark.asyncio
    async def test_detect_cycles(self, repository, mock_session):
        """Test cycle detection."""
        source_id = uuid4()
        target_id = uuid4()
        tenant_id = "test-tenant"

        # Mock get_node_edges to return no path from target to source (no cycle)
        with patch.object(repository, "get_node_edges") as mock_get_edges:
            mock_get_edges.return_value = ([], 0)  # No outgoing edges from target

            has_cycle = await repository.detect_cycles(source_id, target_id, tenant_id)

        assert isinstance(has_cycle, bool)
        assert has_cycle is False  # No cycle detected

    @pytest.mark.asyncio
    async def test_validate_nodes_exist(self, repository, mock_session):
        """Test node existence validation (simplified - only checks Component IDs)."""
        node_ids = [uuid4(), uuid4(), uuid4()]
        tenant_id = "test-tenant"

        # Mock that first two nodes exist as components, third doesn't exist
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            node_ids[0],
            node_ids[1],
        ]  # First two exist

        # Mock session execute calls: only one component query now
        mock_session.execute.return_value = mock_result

        existence_map = await repository.validate_nodes_exist(node_ids, tenant_id)

        assert isinstance(existence_map, dict)
        assert len(existence_map) == len(node_ids)
        for node_id in node_ids:
            assert node_id in existence_map
            assert isinstance(existence_map[node_id], bool)

        # First two should exist, third should not
        assert existence_map[node_ids[0]] is True
        assert existence_map[node_ids[1]] is True
        assert existence_map[node_ids[2]] is False

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, repository, mock_session):
        """Test that all methods require tenant_id for isolation."""
        # All methods should require tenant_id parameter
        methods_requiring_tenant = [
            "create_edge",
            "get_edge_by_id",
            "list_edges",
            "get_node_edges",
            "get_node_by_id",
            "list_nodes",
            "get_subgraph",
            "detect_cycles",
            "validate_nodes_exist",
        ]

        for method_name in methods_requiring_tenant:
            method = getattr(repository, method_name)
            # Check method signature includes tenant_id
            import inspect

            sig = inspect.signature(method)
            assert "tenant_id" in sig.parameters, (
                f"{method_name} should require tenant_id"
            )
