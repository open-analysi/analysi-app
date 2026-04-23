"""
Unit tests for workflow mutation repository methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from analysi.models.workflow import NodeTemplate, Workflow, WorkflowEdge, WorkflowNode
from analysi.repositories.workflow import NodeTemplateRepository, WorkflowRepository
from analysi.schemas.workflow import (
    WorkflowCreate,
    WorkflowNodeCreate,
)


@pytest.mark.unit
class TestWorkflowMutationRepository:
    """Test WorkflowRepository mutation methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        """Create a WorkflowRepository instance with mock session."""
        return WorkflowRepository(mock_session)

    @pytest.fixture
    def sample_workflow(self):
        """Create a sample workflow model."""
        workflow = MagicMock(spec=Workflow)
        workflow.id = uuid4()
        workflow.tenant_id = "test-tenant"
        workflow.name = "Test Workflow"
        workflow.description = "Test description"
        workflow.nodes = []
        workflow.edges = []
        return workflow

    @pytest.fixture
    def sample_node(self, sample_workflow):
        """Create a sample workflow node."""
        node = MagicMock(spec=WorkflowNode)
        node.id = uuid4()
        node.workflow_id = sample_workflow.id
        node.node_id = "n-test-1"
        node.kind = "transformation"
        node.name = "Test Node"
        node.is_start_node = True
        node.schemas = {"input": {"type": "object"}, "output": {"type": "object"}}
        return node

    # ========== Positive Tests ==========

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_name(
        self, repo, mock_session, sample_workflow
    ):
        """Test updating workflow name succeeds."""
        # Arrange
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        update_data = {"name": "Updated Workflow Name"}

        # Mock get_workflow_by_id to return the workflow
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        # Act
        result = await repo.update_workflow_metadata(
            tenant_id, workflow_id, update_data
        )

        # Assert
        assert result is not None
        assert result.name == "Updated Workflow Name"

    @pytest.mark.asyncio
    async def test_update_workflow_metadata_multiple_fields(
        self, repo, mock_session, sample_workflow
    ):
        """Test updating multiple workflow fields in one call."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        update_data = {
            "name": "New Name",
            "description": "New Description",
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.update_workflow_metadata(
            tenant_id, workflow_id, update_data
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_add_node_to_workflow(self, repo, mock_session, sample_workflow):
        """Test adding a node returns WorkflowNode with correct fields."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_data = {
            "node_id": "n-new-1",
            "kind": "transformation",
            "name": "New Node",
            "is_start_node": False,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.add_node(tenant_id, workflow_id, node_data)

        assert result is not None
        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_add_node_start_node(self, repo, mock_session, sample_workflow):
        """Test adding a node with is_start_node=True."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_data = {
            "node_id": "n-start",
            "kind": "transformation",
            "name": "Start Node",
            "is_start_node": True,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.add_node(tenant_id, workflow_id, node_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_node_name(
        self, repo, mock_session, sample_workflow, sample_node
    ):
        """Test updating node name succeeds."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_id = "n-test-1"
        update_data = {"name": "Updated Node Name"}

        sample_workflow.nodes = [sample_node]
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.update_node(tenant_id, workflow_id, node_id, update_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_node_schemas(
        self, repo, mock_session, sample_workflow, sample_node
    ):
        """Test updating node schemas succeeds."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_id = "n-test-1"
        update_data = {
            "schemas": {"input": {"type": "string"}, "output": {"type": "number"}}
        }

        sample_workflow.nodes = [sample_node]
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.update_node(tenant_id, workflow_id, node_id, update_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_remove_node_success(
        self, repo, mock_session, sample_workflow, sample_node
    ):
        """Test removing a node returns True."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_id = "n-test-1"

        sample_workflow.nodes = [sample_node]
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)
        repo.get_edges_for_node = AsyncMock(return_value=[])

        result = await repo.remove_node(tenant_id, workflow_id, node_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_add_edge_success(self, repo, mock_session, sample_workflow):
        """Test adding an edge between two nodes."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        # Create two nodes
        node1 = MagicMock(spec=WorkflowNode)
        node1.id = uuid4()
        node1.node_id = "n-1"

        node2 = MagicMock(spec=WorkflowNode)
        node2.id = uuid4()
        node2.node_id = "n-2"

        sample_workflow.nodes = [node1, node2]

        edge_data = {
            "edge_id": "e-1",
            "from_node_id": "n-1",
            "to_node_id": "n-2",
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.add_edge(tenant_id, workflow_id, edge_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_add_edge_with_alias(self, repo, mock_session, sample_workflow):
        """Test adding an edge with alias field."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        node1 = MagicMock(spec=WorkflowNode)
        node1.id = uuid4()
        node1.node_id = "n-1"

        node2 = MagicMock(spec=WorkflowNode)
        node2.id = uuid4()
        node2.node_id = "n-2"

        sample_workflow.nodes = [node1, node2]

        edge_data = {
            "edge_id": "e-1",
            "from_node_id": "n-1",
            "to_node_id": "n-2",
            "alias": "data_output",
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.add_edge(tenant_id, workflow_id, edge_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_remove_edge_success(self, repo, mock_session, sample_workflow):
        """Test removing an edge returns True."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        edge_id = "e-1"

        edge = MagicMock(spec=WorkflowEdge)
        edge.edge_id = "e-1"
        sample_workflow.edges = [edge]

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.remove_edge(tenant_id, workflow_id, edge_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_edges_for_node(self, repo, mock_session):
        """Test getting all edges connected to a node."""
        workflow_id = uuid4()
        node_uuid = uuid4()

        # Mock query result
        edge1 = MagicMock(spec=WorkflowEdge)
        edge2 = MagicMock(spec=WorkflowEdge)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [edge1, edge2]
        mock_session.execute.return_value = mock_result

        result = await repo.get_edges_for_node(workflow_id, node_uuid)

        assert len(result) == 2

    # ========== Negative Tests ==========

    @pytest.mark.asyncio
    async def test_update_workflow_not_found(self, repo, mock_session):
        """Test updating non-existent workflow raises error or returns None."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        update_data = {"name": "New Name"}

        repo.get_workflow_by_id = AsyncMock(return_value=None)

        # Should either raise ValueError or return None
        result = await repo.update_workflow_metadata(
            tenant_id, workflow_id, update_data
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_add_node_duplicate_node_id(
        self, repo, mock_session, sample_workflow, sample_node
    ):
        """Test adding node with existing node_id raises IntegrityError."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        # Node with same node_id already exists
        sample_workflow.nodes = [sample_node]
        node_data = {
            "node_id": "n-test-1",  # Same as existing
            "kind": "transformation",
            "name": "Duplicate Node",
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)
        mock_session.flush.side_effect = IntegrityError("duplicate", None, None)

        with pytest.raises(IntegrityError):
            await repo.add_node(tenant_id, workflow_id, node_data)

    @pytest.mark.asyncio
    async def test_update_node_not_found(self, repo, mock_session, sample_workflow):
        """Test updating non-existent node returns None."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_id = "nonexistent-node"
        update_data = {"name": "New Name"}

        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.update_node(tenant_id, workflow_id, node_id, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_remove_node_not_found(self, repo, mock_session, sample_workflow):
        """Test removing non-existent node returns False."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        node_id = "nonexistent-node"

        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.remove_node(tenant_id, workflow_id, node_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_add_edge_invalid_from_node(
        self, repo, mock_session, sample_workflow
    ):
        """Test adding edge with non-existent from_node raises error."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        node = MagicMock(spec=WorkflowNode)
        node.id = uuid4()
        node.node_id = "n-1"
        sample_workflow.nodes = [node]

        edge_data = {
            "edge_id": "e-1",
            "from_node_id": "nonexistent",  # Invalid
            "to_node_id": "n-1",
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        with pytest.raises(ValueError):
            await repo.add_edge(tenant_id, workflow_id, edge_data)

    @pytest.mark.asyncio
    async def test_add_edge_invalid_to_node(self, repo, mock_session, sample_workflow):
        """Test adding edge with non-existent to_node raises error."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        node = MagicMock(spec=WorkflowNode)
        node.id = uuid4()
        node.node_id = "n-1"
        sample_workflow.nodes = [node]

        edge_data = {
            "edge_id": "e-1",
            "from_node_id": "n-1",
            "to_node_id": "nonexistent",  # Invalid
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        with pytest.raises(ValueError):
            await repo.add_edge(tenant_id, workflow_id, edge_data)

    @pytest.mark.asyncio
    async def test_add_edge_duplicate_edge_id(
        self, repo, mock_session, sample_workflow
    ):
        """Test adding edge with existing edge_id raises IntegrityError."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id

        node1 = MagicMock(spec=WorkflowNode)
        node1.id = uuid4()
        node1.node_id = "n-1"

        node2 = MagicMock(spec=WorkflowNode)
        node2.id = uuid4()
        node2.node_id = "n-2"

        existing_edge = MagicMock(spec=WorkflowEdge)
        existing_edge.edge_id = "e-1"

        sample_workflow.nodes = [node1, node2]
        sample_workflow.edges = [existing_edge]

        edge_data = {
            "edge_id": "e-1",  # Duplicate
            "from_node_id": "n-1",
            "to_node_id": "n-2",
        }

        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)
        mock_session.flush.side_effect = IntegrityError("duplicate", None, None)

        with pytest.raises(IntegrityError):
            await repo.add_edge(tenant_id, workflow_id, edge_data)

    @pytest.mark.asyncio
    async def test_remove_edge_not_found(self, repo, mock_session, sample_workflow):
        """Test removing non-existent edge returns False."""
        tenant_id = "test-tenant"
        workflow_id = sample_workflow.id
        edge_id = "nonexistent-edge"

        sample_workflow.edges = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        result = await repo.remove_edge(tenant_id, workflow_id, edge_id)

        assert result is False


@pytest.mark.unit
class TestWorkflowRepoTemplateValidation:
    """Test that WorkflowRepository delegates template lookups to NodeTemplateRepository.

    Regression tests for: AttributeError 'WorkflowRepository' has no attribute 'get_template_by_id'
    """

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return WorkflowRepository(mock_session)

    @pytest.fixture
    def enabled_template(self):
        tmpl = MagicMock(spec=NodeTemplate)
        tmpl.enabled = True
        return tmpl

    @pytest.fixture
    def disabled_template(self):
        tmpl = MagicMock(spec=NodeTemplate)
        tmpl.enabled = False
        return tmpl

    # ========== create_workflow template validation ==========

    @pytest.mark.asyncio
    async def test_create_workflow_with_template_delegates_to_template_repo(
        self, repo, mock_session, enabled_template
    ):
        """create_workflow should look up templates via NodeTemplateRepository, not self."""
        tenant_id = "test-tenant"
        template_id = uuid4()

        workflow_data = WorkflowCreate(
            name="Tmpl Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            data_samples=[{}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="transformation",
                    name="Node",
                    is_start_node=True,
                    node_template_id=template_id,
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        # Patch NodeTemplateRepository.get_template_by_id to return enabled template
        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = enabled_template

            # Mock workflow flush to assign an id, and get_workflow_by_id for the return
            mock_workflow = MagicMock(spec=Workflow)
            mock_workflow.id = uuid4()
            repo.get_workflow_by_id = AsyncMock(return_value=mock_workflow)

            result = await repo.create_workflow(tenant_id, workflow_data)

            # Template lookup must have been called with the right args
            mock_get_tmpl.assert_called_once_with(template_id, tenant_id)
            assert result is mock_workflow

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_disabled_template(
        self, repo, mock_session, disabled_template
    ):
        """create_workflow should raise ValueError for disabled templates."""
        tenant_id = "test-tenant"
        template_id = uuid4()

        workflow_data = WorkflowCreate(
            name="Disabled Tmpl Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            data_samples=[{}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="transformation",
                    name="Node",
                    is_start_node=True,
                    node_template_id=template_id,
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = disabled_template

            with pytest.raises(ValueError, match="inaccessible or disabled template"):
                await repo.create_workflow(tenant_id, workflow_data)

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_nonexistent_template(
        self, repo, mock_session
    ):
        """create_workflow should raise ValueError when template not found."""
        tenant_id = "test-tenant"
        template_id = uuid4()

        workflow_data = WorkflowCreate(
            name="Missing Tmpl Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            data_samples=[{}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="transformation",
                    name="Node",
                    is_start_node=True,
                    node_template_id=template_id,
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = None

            with pytest.raises(ValueError, match="inaccessible or disabled template"):
                await repo.create_workflow(tenant_id, workflow_data)

    @pytest.mark.asyncio
    async def test_create_workflow_skips_template_check_when_no_template(
        self, repo, mock_session
    ):
        """create_workflow should skip template validation when node_template_id is None."""
        tenant_id = "test-tenant"

        workflow_data = WorkflowCreate(
            name="No Tmpl Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            data_samples=[{}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="task",
                    name="Task Node",
                    is_start_node=True,
                    task_id=uuid4(),
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_workflow = MagicMock(spec=Workflow)
            mock_workflow.id = uuid4()
            repo.get_workflow_by_id = AsyncMock(return_value=mock_workflow)
            repo._validate_task_ownership = AsyncMock()

            await repo.create_workflow(tenant_id, workflow_data)

            # Template lookup should NOT have been called
            mock_get_tmpl.assert_not_called()

    # ========== add_node template validation ==========

    @pytest.mark.asyncio
    async def test_add_node_with_template_delegates_to_template_repo(
        self, repo, mock_session, enabled_template
    ):
        """add_node should look up templates via NodeTemplateRepository, not self."""
        tenant_id = "test-tenant"
        template_id = uuid4()
        workflow_id = uuid4()

        sample_workflow = MagicMock(spec=Workflow)
        sample_workflow.id = workflow_id
        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        node_data = {
            "node_id": "n-tmpl",
            "kind": "transformation",
            "name": "Template Node",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = enabled_template

            result = await repo.add_node(tenant_id, workflow_id, node_data)

            mock_get_tmpl.assert_called_once_with(template_id, tenant_id)
            assert result is not None

    @pytest.mark.asyncio
    async def test_add_node_rejects_disabled_template(
        self, repo, mock_session, disabled_template
    ):
        """add_node should raise ValueError for disabled templates."""
        tenant_id = "test-tenant"
        template_id = uuid4()
        workflow_id = uuid4()

        sample_workflow = MagicMock(spec=Workflow)
        sample_workflow.id = workflow_id
        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        node_data = {
            "node_id": "n-disabled",
            "kind": "transformation",
            "name": "Disabled Tmpl Node",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = disabled_template

            with pytest.raises(ValueError, match="inaccessible or disabled template"):
                await repo.add_node(tenant_id, workflow_id, node_data)

    @pytest.mark.asyncio
    async def test_add_node_rejects_nonexistent_template(self, repo, mock_session):
        """add_node should raise ValueError when template not found."""
        tenant_id = "test-tenant"
        template_id = uuid4()
        workflow_id = uuid4()

        sample_workflow = MagicMock(spec=Workflow)
        sample_workflow.id = workflow_id
        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        node_data = {
            "node_id": "n-missing",
            "kind": "transformation",
            "name": "Missing Tmpl Node",
            "node_template_id": template_id,
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            mock_get_tmpl.return_value = None

            with pytest.raises(ValueError, match="inaccessible or disabled template"):
                await repo.add_node(tenant_id, workflow_id, node_data)

    @pytest.mark.asyncio
    async def test_add_node_skips_template_check_when_no_template(
        self, repo, mock_session
    ):
        """add_node should skip template validation when node_template_id is None."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()

        sample_workflow = MagicMock(spec=Workflow)
        sample_workflow.id = workflow_id
        sample_workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=sample_workflow)

        node_data = {
            "node_id": "n-no-tmpl",
            "kind": "task",
            "name": "Task Node",
            "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
        }

        with patch.object(
            NodeTemplateRepository, "get_template_by_id", new_callable=AsyncMock
        ) as mock_get_tmpl:
            await repo.add_node(tenant_id, workflow_id, node_data)

            mock_get_tmpl.assert_not_called()
