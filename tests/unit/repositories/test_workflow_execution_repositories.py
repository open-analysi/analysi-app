"""
Unit tests for workflow execution repository classes.
These tests use mocked database sessions and follow TDD principles.
All tests should FAIL initially since implementation isn't complete yet.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.workflow_execution import (
    WorkflowEdgeInstance,
    WorkflowNodeInstance,
    WorkflowRun,
)
from analysi.repositories.workflow_execution import (
    WorkflowEdgeInstanceRepository,
    WorkflowNodeInstanceRepository,
    WorkflowRunRepository,
)


@pytest.mark.unit
class TestWorkflowRunRepository:
    """Test WorkflowRunRepository operations with mocked database."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create a WorkflowRunRepository instance with mock session."""
        return WorkflowRunRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_workflow_run_success(self, repository, mock_session):
        """Test successful workflow run creation."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_type = "inline"
        input_location = "{'key': 'value'}"

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Test the actual implementation
        result = await repository.create_workflow_run(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            input_type=input_type,
            input_location=input_location,
        )

        # Verify result is a WorkflowRun instance
        assert isinstance(result, WorkflowRun)
        assert result.tenant_id == tenant_id
        assert result.workflow_id == workflow_id
        assert result.input_type == input_type
        assert result.input_location == input_location
        assert result.status == "pending"

        # Verify session operations were called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workflow_run_success(self, repository, mock_session):
        """Test retrieving workflow run by ID and tenant."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock workflow run and workflow name (LEFT JOIN result)
        mock_run = MagicMock(spec=WorkflowRun)
        mock_run.id = workflow_run_id
        mock_run.tenant_id = tenant_id
        workflow_name = "Test Workflow"

        # Mock query result - LEFT JOIN returns tuple (WorkflowRun, workflow_name)
        mock_result = MagicMock()
        mock_result.first.return_value = (mock_run, workflow_name)
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_workflow_run(tenant_id, workflow_run_id)

        # Verify result - should be the WorkflowRun with workflow_name attribute set
        assert result == mock_run
        assert hasattr(result, "workflow_name")
        assert result.workflow_name == workflow_name
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workflow_run_not_found(self, repository, mock_session):
        """Test retrieving non-existent workflow run returns None."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock query result to return None (no row found)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_workflow_run(tenant_id, workflow_run_id)

        # Verify result is None
        assert result is None
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workflow_run_status_success(self, repository, mock_session):
        """Test successful workflow run status update."""
        workflow_run_id = uuid4()
        status = "running"
        started_at = datetime.now(UTC)

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        # Test the actual implementation
        await repository.update_workflow_run_status(
            workflow_run_id=workflow_run_id,
            status=status,
            started_at=started_at,
        )

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_workflow_run_status_with_error(
        self, repository, mock_session
    ):
        """Test workflow run status update with error message."""
        workflow_run_id = uuid4()
        status = "failed"
        error_message = "Node execution failed: syntax error"
        completed_at = datetime.now(UTC)

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        # Test the actual implementation
        await repository.update_workflow_run_status(
            workflow_run_id=workflow_run_id,
            status=status,
            error_message=error_message,
            completed_at=completed_at,
        )

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_workflow_runs_with_filters(self, repository, mock_session):
        """Test listing workflow runs with filtering and pagination."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        status = "completed"

        # Mock workflow runs
        mock_runs = [MagicMock(spec=WorkflowRun) for _ in range(5)]
        workflow_names = [f"Workflow {i}" for i in range(5)]

        # Mock count query result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = len(mock_runs)

        # Mock list query result - LEFT JOIN returns tuples (WorkflowRun, workflow_name)
        mock_list_result = MagicMock()
        mock_rows = [(mock_runs[i], workflow_names[i]) for i in range(5)]
        mock_list_result.all.return_value = mock_rows

        # Setup execute calls: first count query, then list query
        mock_session.execute.side_effect = [mock_count_result, mock_list_result]

        # Test the actual implementation
        result = await repository.list_workflow_runs(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            status=status,
            skip=0,
            limit=10,
        )

        # Verify result is now a tuple (list, total_count)
        workflow_runs, total_count = result
        assert len(workflow_runs) == len(mock_runs)
        assert total_count == len(mock_runs)
        # Verify workflow_name attributes are set on the returned objects
        for i, workflow_run in enumerate(workflow_runs):
            assert hasattr(workflow_run, "workflow_name")
            assert workflow_run.workflow_name == workflow_names[i]
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_workflow_runs_no_filters(self, repository, mock_session):
        """Test listing all workflow runs for a tenant."""
        tenant_id = "test-tenant"

        # Mock workflow runs
        mock_runs = [MagicMock(spec=WorkflowRun) for _ in range(25)]
        workflow_names = [f"Workflow {i}" for i in range(25)]

        # Mock count query result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = len(mock_runs)

        # Mock list query result - LEFT JOIN returns tuples (WorkflowRun, workflow_name)
        mock_list_result = MagicMock()
        mock_rows = [(mock_runs[i], workflow_names[i]) for i in range(25)]
        mock_list_result.all.return_value = mock_rows

        # Setup execute calls: first count query, then list query
        mock_session.execute.side_effect = [mock_count_result, mock_list_result]

        # Test the actual implementation
        result = await repository.list_workflow_runs(
            tenant_id=tenant_id,
            skip=0,
            limit=50,
        )

        # Verify result is now a tuple (list, total_count)
        workflow_runs, total_count = result
        assert len(workflow_runs) == len(mock_runs)
        assert total_count == len(mock_runs)
        # Verify workflow_name attributes are set on the returned objects
        for i, workflow_run in enumerate(workflow_runs):
            assert hasattr(workflow_run, "workflow_name")
            assert workflow_run.workflow_name == workflow_names[i]
        assert mock_session.execute.call_count == 2


@pytest.mark.unit
class TestWorkflowNodeInstanceRepository:
    """Test WorkflowNodeInstanceRepository operations with mocked database."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create a WorkflowNodeInstanceRepository instance with mock session."""
        return WorkflowNodeInstanceRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_node_instance_success(self, repository, mock_session):
        """Test successful node instance creation."""
        workflow_run_id = uuid4()
        node_id = "n-transform-1"
        node_uuid = uuid4()

        # Mock node instance
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.status = "pending"

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Test the actual implementation
        result = await repository.create_node_instance(
            workflow_run_id=workflow_run_id,
            node_id=node_id,
            node_uuid=node_uuid,
        )

        # Verify result is a WorkflowNodeInstance
        assert isinstance(result, WorkflowNodeInstance)
        assert result.workflow_run_id == workflow_run_id
        assert result.node_id == node_id
        assert result.node_uuid == node_uuid
        assert result.status == "pending"

        # Verify session operations were called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_node_instance_with_parent(self, repository, mock_session):
        """Test node instance creation with parent instance (foreach child)."""
        workflow_run_id = uuid4()
        node_id = "n-child-item"
        node_uuid = uuid4()
        parent_instance_id = uuid4()
        loop_context = {"item_index": 2, "total_items": 5}

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Test the actual implementation
        result = await repository.create_node_instance(
            workflow_run_id=workflow_run_id,
            node_id=node_id,
            node_uuid=node_uuid,
            parent_instance_id=parent_instance_id,
            loop_context=loop_context,
        )

        # Verify result
        assert isinstance(result, WorkflowNodeInstance)
        assert result.workflow_run_id == workflow_run_id
        assert result.node_id == node_id
        assert result.node_uuid == node_uuid
        assert result.parent_instance_id == parent_instance_id
        assert result.loop_context == loop_context
        assert result.status == "pending"

        # Verify session operations were called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_node_instance_success(self, repository, mock_session):
        """Test retrieving node instance by ID."""
        node_instance_id = uuid4()

        # Mock node instance
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = node_instance_id

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_node_instance(node_instance_id)

        # Verify result
        assert result == mock_instance
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_node_instances_with_filters(self, repository, mock_session):
        """Test listing node instances with status and parent filters."""
        workflow_run_id = uuid4()
        status = "completed"
        parent_instance_id = uuid4()

        # Mock node instances
        mock_instances = [MagicMock(spec=WorkflowNodeInstance) for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_instances
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.list_node_instances(
            workflow_run_id=workflow_run_id,
            status=status,
            parent_instance_id=parent_instance_id,
        )

        # Verify result
        assert result == mock_instances
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_predecessor_instances(self, repository, mock_session):
        """Test getting predecessor node instances via workflow definition."""
        workflow_run_id = uuid4()
        workflow_id = uuid4()
        node_id = "n-target"

        # Mock workflow run
        mock_workflow_run = MagicMock()
        mock_workflow_run.workflow_id = workflow_id

        # Mock workflow nodes
        mock_pred_node1 = MagicMock()
        mock_pred_node1.node_id = "n-pred1"
        mock_pred_node2 = MagicMock()
        mock_pred_node2.node_id = "n-pred2"
        mock_target_node = MagicMock()
        mock_target_node.node_id = node_id

        # Mock workflow edges
        mock_edge1 = MagicMock()
        mock_edge1.from_node = mock_pred_node1
        mock_edge1.to_node = mock_target_node
        mock_edge2 = MagicMock()
        mock_edge2.from_node = mock_pred_node2
        mock_edge2.to_node = mock_target_node

        # Mock workflow with edges
        mock_workflow = MagicMock()
        mock_workflow.edges = [mock_edge1, mock_edge2]

        # Mock predecessor instances (completed)
        mock_predecessors = [MagicMock(spec=WorkflowNodeInstance) for _ in range(2)]

        # Setup multiple execute calls
        # 1. Get workflow run
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = mock_workflow_run

        # 2. Get workflow with edges
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = mock_workflow

        # 3. Get predecessor instances
        pred_result = MagicMock()
        pred_result.scalars.return_value.all.return_value = mock_predecessors

        mock_session.execute.side_effect = [run_result, workflow_result, pred_result]

        # Test the actual implementation
        result = await repository.get_predecessor_instances(workflow_run_id, node_id)

        # Verify result
        assert result == mock_predecessors
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_update_node_instance_status_success(self, repository, mock_session):
        """Test successful node instance status update."""
        node_instance_id = uuid4()
        status = "running"
        started_at = datetime.now(UTC)

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Test the actual implementation
        await repository.update_node_instance_status(
            node_instance_id=node_instance_id,
            status=status,
            started_at=started_at,
        )

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_node_instance_status_with_error(
        self, repository, mock_session
    ):
        """Test node instance status update with error."""
        node_instance_id = uuid4()
        status = "failed"
        error_message = "Template execution failed"
        completed_at = datetime.now(UTC)

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Test the actual implementation
        await repository.update_node_instance_status(
            node_instance_id=node_instance_id,
            status=status,
            completed_at=completed_at,
            error_message=error_message,
        )

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_node_instance_output(self, repository, mock_session):
        """Test saving node instance output location."""
        node_instance_id = uuid4()
        output_type = "s3"
        output_location = "s3://bucket/workflows/runs/uuid/nodes/uuid/output.json"

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Test the actual implementation
        await repository.save_node_instance_output(
            node_instance_id=node_instance_id,
            output_type=output_type,
            output_location=output_location,
        )

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()


@pytest.mark.unit
class TestWorkflowEdgeInstanceRepository:
    """Test WorkflowEdgeInstanceRepository operations with mocked database."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create a WorkflowEdgeInstanceRepository instance with mock session."""
        return WorkflowEdgeInstanceRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_edge_instance_success(self, repository, mock_session):
        """Test successful edge instance creation."""
        workflow_run_id = uuid4()
        edge_id = "e1"
        edge_uuid = uuid4()
        from_instance_id = uuid4()
        to_instance_id = uuid4()

        # Mock edge instance
        mock_edge = MagicMock(spec=WorkflowEdgeInstance)
        mock_edge.id = uuid4()

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Test the actual implementation
        result = await repository.create_edge_instance(
            workflow_run_id=workflow_run_id,
            edge_id=edge_id,
            edge_uuid=edge_uuid,
            from_instance_id=from_instance_id,
            to_instance_id=to_instance_id,
        )

        # Verify result is a WorkflowEdgeInstance
        assert isinstance(result, WorkflowEdgeInstance)
        assert result.workflow_run_id == workflow_run_id
        assert result.edge_id == edge_id
        assert result.edge_uuid == edge_uuid
        assert result.from_instance_id == from_instance_id
        assert result.to_instance_id == to_instance_id

        # Verify session operations were called
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_edge_delivered(self, repository, mock_session):
        """Test marking edge as delivered."""
        edge_instance_id = uuid4()
        delivered_at = datetime.now(UTC)

        # Mock session operations
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        # Test the actual implementation
        await repository.mark_edge_delivered(edge_instance_id, delivered_at)

        # Verify session operations were called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_incoming_edges(self, repository, mock_session):
        """Test getting incoming edges for a node instance."""
        workflow_run_id = uuid4()
        to_instance_id = uuid4()

        # Mock incoming edges
        mock_edges = [MagicMock(spec=WorkflowEdgeInstance) for _ in range(2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_edges
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_incoming_edges(workflow_run_id, to_instance_id)

        # Verify result
        assert result == mock_edges
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_outgoing_edges(self, repository, mock_session):
        """Test getting outgoing edges from a node instance."""
        workflow_run_id = uuid4()
        from_instance_id = uuid4()

        # Mock outgoing edges
        mock_edges = [MagicMock(spec=WorkflowEdgeInstance) for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_edges
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_outgoing_edges(workflow_run_id, from_instance_id)

        # Verify result
        assert result == mock_edges
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_incoming_edges_empty(self, repository, mock_session):
        """Test getting incoming edges when none exist (root nodes)."""
        workflow_run_id = uuid4()
        to_instance_id = uuid4()

        # Mock empty result for root nodes
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_incoming_edges(workflow_run_id, to_instance_id)

        # Verify result is empty list
        assert result == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_outgoing_edges_empty(self, repository, mock_session):
        """Test getting outgoing edges when none exist (leaf nodes)."""
        workflow_run_id = uuid4()
        from_instance_id = uuid4()

        # Mock empty result for leaf nodes
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Test the actual implementation
        result = await repository.get_outgoing_edges(workflow_run_id, from_instance_id)

        # Verify result is empty list
        assert result == []
        mock_session.execute.assert_called_once()


@pytest.mark.unit
class TestRepositoryInitializationPatterns:
    """Test repository initialization patterns match project conventions."""

    def test_workflow_run_repository_initialization(self):
        """Test WorkflowRunRepository initialization with session."""
        mock_session = MagicMock(spec=AsyncSession)
        repository = WorkflowRunRepository(mock_session)

        assert repository.session == mock_session
        assert hasattr(repository, "session")

    def test_node_instance_repository_initialization(self):
        """Test WorkflowNodeInstanceRepository initialization with session."""
        mock_session = MagicMock(spec=AsyncSession)
        repository = WorkflowNodeInstanceRepository(mock_session)

        assert repository.session == mock_session
        assert hasattr(repository, "session")

    def test_edge_instance_repository_initialization(self):
        """Test WorkflowEdgeInstanceRepository initialization with session."""
        mock_session = MagicMock(spec=AsyncSession)
        repository = WorkflowEdgeInstanceRepository(mock_session)

        assert repository.session == mock_session
        assert hasattr(repository, "session")

    def test_repository_session_per_instance_pattern(self):
        """Test that repositories store session per instance (not per method call)."""
        # This matches the existing pattern in the codebase
        mock_session1 = MagicMock(spec=AsyncSession)
        mock_session2 = MagicMock(spec=AsyncSession)

        repo1 = WorkflowRunRepository(mock_session1)
        repo2 = WorkflowRunRepository(mock_session2)

        assert repo1.session == mock_session1
        assert repo2.session == mock_session2
        assert repo1.session != repo2.session
