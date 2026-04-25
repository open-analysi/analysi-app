"""Unit tests for KDG NodeResponse created_by field."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component, ComponentKind
from analysi.schemas.kdg import NodeResponse, NodeType
from analysi.services.kdg import KDGService


class TestNodeResponseCreatedBy:
    """Test that NodeResponse includes created_by from Component."""

    @pytest.fixture
    def service(self):
        mock_session = AsyncMock(spec=AsyncSession)
        svc = KDGService(mock_session)
        svc.repository = AsyncMock()
        return svc

    def _make_component(self, *, kind=ComponentKind.TASK, created_by=None):
        """Build a mock Component with created_by."""
        comp = MagicMock(spec=Component)
        comp.id = uuid4()
        comp.name = "Test Component"
        comp.description = "Description"
        comp.kind = kind
        comp.version = "1.0.0"
        comp.status = "active"
        comp.categories = ["security"]
        comp.created_at = datetime.now(tz=UTC)
        comp.updated_at = datetime.now(tz=UTC)
        comp.created_by = created_by
        comp.task = MagicMock()
        comp.task.function = "reasoning"
        comp.task.scope = "processing"
        comp.knowledge_unit = None
        return comp

    def test_task_node_includes_created_by(self, service):
        """Test that a task node includes created_by in its response."""
        user_id = uuid4()
        component = self._make_component(created_by=user_id)

        node = service._component_to_node_response(component)

        assert isinstance(node, NodeResponse)
        assert node.created_by == user_id
        assert node.type == NodeType.TASK

    def test_node_created_by_none_when_not_set(self, service):
        """Test that created_by is None when not set on the component."""
        component = self._make_component(created_by=None)

        node = service._component_to_node_response(component)

        assert node.created_by is None

    def test_ku_node_includes_created_by(self, service):
        """Test that a KU node includes created_by."""
        user_id = uuid4()
        comp = self._make_component(kind=ComponentKind.KU, created_by=user_id)
        comp.task = None
        ku = MagicMock()
        ku.ku_type = "document"
        ku.document = MagicMock()
        ku.document.doc_format = "markdown"
        comp.knowledge_unit = ku

        node = service._component_to_node_response(comp)

        assert node.created_by == user_id
        assert node.type == NodeType.DOCUMENT

    @pytest.mark.asyncio
    async def test_graph_response_nodes_have_created_by(self, service):
        """Test that get_node_graph returns nodes with created_by."""
        user_id = uuid4()
        component = self._make_component(created_by=user_id)

        service.repository.get_subgraph.return_value = ([component], [])

        graph = await service.get_node_graph(
            node_id=component.id, tenant_id="test-tenant", depth=1
        )

        assert len(graph.nodes) == 1
        assert graph.nodes[0].created_by == user_id

    def test_web_format_includes_created_by(self, service):
        """Test that _node_to_web_format includes created_by in data."""
        user_id = uuid4()
        node = NodeResponse(
            id=uuid4(),
            type=NodeType.TASK,
            name="Test",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            created_by=user_id,
        )

        web_data = service._node_to_web_format(node)

        assert web_data["data"]["created_by"] == str(user_id)

    def test_web_format_created_by_none(self, service):
        """Test that _node_to_web_format handles None created_by."""
        node = NodeResponse(
            id=uuid4(),
            type=NodeType.TASK,
            name="Test",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            created_by=None,
        )

        web_data = service._node_to_web_format(node)

        assert web_data["data"]["created_by"] is None
