"""
Unit tests for workflow execution service classes.
These tests use mocked repositories and follow TDD principles.
All tests should FAIL initially since implementation isn't complete yet.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.workflow_execution import (
    WorkflowNodeInstance,
)
from analysi.services.workflow_execution import (
    TransformationNodeExecutor,
    WorkflowExecutionService,
    WorkflowExecutor,
)


@pytest.mark.unit
class TestWorkflowExecutor:
    """Test WorkflowExecutor progressive execution algorithm."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        """Create a WorkflowExecutor instance with mock session."""
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_workflow_executor_initialization(self, executor, mock_session):
        """Test WorkflowExecutor setup."""
        assert executor.session == mock_session
        assert executor.polling_interval == 0.1  # 100ms default
        assert hasattr(executor, "session")

    @pytest.mark.asyncio
    async def test_execute_workflow_async_start(self, executor):
        """Test workflow execution starts asynchronously and returns run ID."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": {"type": "security", "severity": "high"}}

        # Mock repository methods
        executor.run_repo.create_workflow_run = AsyncMock(
            return_value=MagicMock(id=uuid4())
        )
        executor.storage.store = AsyncMock(return_value={"location": "mock/location"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        # Test the actual implementation
        result = await executor.execute_workflow(tenant_id, workflow_id, input_data)

        # Verify result is UUID
        assert isinstance(result, str | type(uuid4()))
        executor.run_repo.create_workflow_run.assert_called_once()
        executor.storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_node_instance_when_ready(self, executor):
        """Test when node instances should be created."""
        workflow_run_id = uuid4()
        node_id = "n-transform-1"
        node_uuid = uuid4()

        # Mock repository method
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        executor.node_repo.create_node_instance = AsyncMock(return_value=mock_instance)
        executor.session.commit = AsyncMock()

        # Test the actual implementation
        result = await executor.create_node_instance(
            workflow_run_id, node_id, node_uuid
        )

        # Verify result
        assert result == mock_instance
        executor.node_repo.create_node_instance.assert_called_once()
        executor.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_node_instance_by_type(self, executor):
        """Test node execution dispatched by type."""
        # Mock node instance
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-transform"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.status = "pending"
        mock_instance.template_id = None

        # Mock session and repositories
        executor.session.execute = AsyncMock()
        executor.session.commit = AsyncMock()
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.node_repo.save_node_instance_output = AsyncMock()
        executor.run_repo.get_workflow_run = AsyncMock()

        # Mock workflow node
        mock_node = MagicMock()
        mock_node.kind = "transformation"
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_node
        executor.session.execute.return_value = mock_result

        # Mock workflow run for tenant_id
        mock_workflow_run = MagicMock()
        mock_workflow_run.tenant_id = "test-tenant"
        executor.run_repo.get_workflow_run.return_value = mock_workflow_run

        # Mock storage
        executor.storage.select_storage_type = MagicMock(return_value="inline")
        executor.storage.store = AsyncMock(return_value={"location": "test-location"})

        # Mock aggregate_predecessor_outputs
        executor.aggregate_predecessor_outputs = AsyncMock(
            return_value={"input": "test"}
        )

        # Should execute without error
        await executor.execute_node_instance(mock_instance)

        # Verify node_repo methods were called (should be called twice: running then completed)
        assert executor.node_repo.update_node_instance_status.call_count == 2
        executor.session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_check_predecessors_complete_single(self, executor):
        """Test logic for checking single predecessor completion."""
        workflow_run_id = uuid4()
        node_id = "n-dependent"

        # Mock the session and repository
        executor.session.execute = AsyncMock()
        mock_result = MagicMock()

        # Mock the query result to return instances with the right status
        mock_instance = MagicMock()
        mock_instance.status = "completed"
        mock_result.scalars.return_value.all.return_value = [mock_instance]
        executor.session.execute.return_value = mock_result

        # Should return True when all predecessors are complete
        result = await executor.check_predecessors_complete(workflow_run_id, node_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_predecessors_complete_multiple(self, executor):
        """Test logic for checking multiple predecessor completion (fan-in)."""
        workflow_run_id = uuid4()
        node_id = "n-aggregator"  # Node with multiple inputs

        # Mock the session and repository
        executor.session.execute = AsyncMock()
        mock_result = MagicMock()

        # Mock multiple completed instances
        mock_instances = []
        for _i in range(3):
            mock_instance = MagicMock()
            mock_instance.status = "completed"
            mock_instances.append(mock_instance)

        mock_result.scalars.return_value.all.return_value = mock_instances
        executor.session.execute.return_value = mock_result

        # Should return True when all predecessors are complete
        result = await executor.check_predecessors_complete(workflow_run_id, node_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_aggregate_predecessor_outputs_single(self, executor):
        """Test aggregation with single predecessor returns consistent dict format."""
        workflow_run_id = uuid4()
        node_id = "n-simple-transform"

        # Mock repository methods directly
        mock_predecessor = MagicMock()
        mock_predecessor.node_id = "n-pred"
        mock_predecessor.output_type = "inline"
        mock_predecessor.output_location = '{"result": "test-output"}'

        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=[mock_predecessor]
        )

        # Mock storage retrieval (with envelope format from TransformationNodeExecutor)
        executor.storage.retrieve = AsyncMock(
            return_value='{"node_id": "transformation", "context": {}, "description": "Output from transformation", "result": {"field1": "value1", "field2": "value2"}}'
        )

        result = await executor.aggregate_predecessor_outputs(workflow_run_id, node_id)
        # For single predecessor, should return standard envelope contract (consistent with multi-predecessor)
        assert isinstance(result, dict)

        # Should have all envelope fields
        assert "node_id" in result
        assert "context" in result
        assert "description" in result
        assert "result" in result

        # Verify envelope structure
        assert result["node_id"] == f"single-{node_id}"
        assert result["context"] == {}
        assert "Single predecessor result" in result["description"]

        # The actual result should be in the result field
        assert result["result"] == {"field1": "value1", "field2": "value2"}

    @pytest.mark.asyncio
    async def test_aggregate_predecessor_outputs_multiple(self, executor):
        """Test aggregation with multiple predecessors returns standard envelope with predecessors array in result field."""
        workflow_run_id = uuid4()
        node_id = "n-fan-in-aggregator"

        # Mock repository methods directly
        mock_predecessors = []
        for i in range(2):
            mock_pred = MagicMock()
            mock_pred.node_id = f"n-pred{i + 1}"
            mock_pred.output_type = "inline"
            mock_pred.output_location = f'{{"result": "output{i + 1}"}}'
            mock_predecessors.append(mock_pred)

        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=mock_predecessors
        )

        # Mock storage retrieval (with envelope format from TransformationNodeExecutor)
        executor.storage.retrieve = AsyncMock(
            side_effect=[
                '{"node_id": "transformation", "context": {}, "description": "Output from transformation", "result": "output1"}',
                '{"node_id": "transformation", "context": {}, "description": "Output from transformation", "result": "output2"}',
            ]
        )

        result = await executor.aggregate_predecessor_outputs(workflow_run_id, node_id)

        # For multiple predecessors, should return standard envelope contract
        assert isinstance(result, dict)

        # Should have all envelope fields
        assert "node_id" in result
        assert "context" in result
        assert "description" in result
        assert "result" in result

        # Verify envelope structure
        assert result["node_id"] == f"aggregation-{node_id}"
        assert result["context"] == {}
        assert "Fan-in aggregation" in result["description"]

        # The predecessors array should be in the result field (maintaining envelope contract)
        # After envelope fix: result contains plain array of results (no node_id wrappers)
        predecessors_array = result["result"]
        assert isinstance(predecessors_array, list)
        assert len(predecessors_array) == 2
        assert (
            predecessors_array[0] == "output1"
        )  # Just the result, no {node_id, result} wrapper
        assert (
            predecessors_array[1] == "output2"
        )  # Just the result, no {node_id, result} wrapper

    @pytest.mark.asyncio
    async def test_workflow_state_transitions(self, executor):
        """Test workflow status state machine."""
        workflow_run_id = uuid4()

        # Test valid state transitions

        # Mock run repository
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        for status, error_message in [
            ("failed", "Node execution error"),
            ("completed", None),
        ]:
            await executor.update_workflow_status(
                workflow_run_id, status, error_message
            )
            # Verify the repository method was called
            executor.run_repo.update_workflow_run_status.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_execution_polling_loop(self, executor):
        """Test main execution monitoring loop."""
        workflow_run_id = uuid4()

        # Mock all dependencies to simulate a short execution cycle
        executor.run_repo.get_workflow_run = AsyncMock()
        executor.node_repo.get_pending_instances = AsyncMock(return_value=[])
        executor.node_repo.get_running_instances = AsyncMock(return_value=[])
        executor.session.commit = AsyncMock()

        # Mock workflow run that completes immediately
        mock_run = MagicMock()
        mock_run.status = "completed"
        executor.run_repo.get_workflow_run.return_value = mock_run

        # Should complete without error
        await executor.monitor_execution(workflow_run_id)


@pytest.mark.unit
class TestTransformationNodeExecutor:
    """Test TransformationNodeExecutor Python template execution."""

    @pytest.fixture
    def executor(self):
        """Create a TransformationNodeExecutor instance."""
        return TransformationNodeExecutor()

    def test_transformation_executor_initialization(self, executor):
        """Test TransformationNodeExecutor setup."""
        assert executor.sandbox is None  # Will be implemented later
        assert hasattr(executor, "sandbox")

    @pytest.mark.asyncio
    async def test_execute_template_passthrough(self, executor):
        """Test simple passthrough template execution."""
        code = "return inp"
        input_data = {"message": "hello world"}

        result = await executor.execute_template(code, input_data)
        # Result is wrapped in an envelope
        assert result["node_id"] == "transformation"
        assert result["result"] == {"message": "hello world"}

    @pytest.mark.asyncio
    async def test_execute_template_field_extraction(self, executor):
        """Test field extraction template."""
        code = "return {'extracted_field': inp.get('source_field')}"
        input_data = {"source_field": "extracted_value", "other_field": "ignored"}

        result = await executor.execute_template(code, input_data)
        assert result["node_id"] == "transformation"
        assert result["result"] == {"extracted_field": "extracted_value"}

    @pytest.mark.asyncio
    async def test_execute_template_arithmetic(self, executor):
        """Test basic arithmetic template."""
        code = "return {'sum': inp.get('a', 0) + inp.get('b', 0)}"
        input_data = {"a": 5, "b": 3}

        result = await executor.execute_template(code, input_data)
        assert result["node_id"] == "transformation"
        assert result["result"] == {"sum": 8}

    @pytest.mark.asyncio
    async def test_execute_template_string_manipulation(self, executor):
        """Test string operations template."""
        code = "return {'uppercase': inp.get('text', '').upper()}"
        input_data = {"text": "hello world"}

        result = await executor.execute_template(code, input_data)
        assert result["node_id"] == "transformation"
        assert result["result"] == {"uppercase": "HELLO WORLD"}

    def test_build_envelope_structure(self, executor):
        """Test standard envelope format building."""
        node_id = "n-transform-1"
        result = {"processed_data": "value"}
        context = {"execution_time_ms": 150}
        description = "Data transformation completed"

        envelope = executor.build_envelope(node_id, result, context, description)
        assert envelope["node_id"] == node_id
        assert envelope["result"] == result
        assert envelope["context"] == context
        assert envelope["description"] == description

    def test_build_envelope_minimal(self, executor):
        """Test envelope with minimal required fields."""
        node_id = "n-simple"
        result = "simple string result"

        envelope = executor.build_envelope(node_id, result)
        assert envelope["node_id"] == node_id
        assert envelope["result"] == result
        assert "context" in envelope
        assert "description" in envelope

    def test_validate_output_schema_success(self, executor):
        """Test output validation against valid schema."""
        output = {"result": "success", "count": 42}
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}, "count": {"type": "number"}},
            "required": ["result"],
        }

        # Should not raise an exception for valid data
        result = executor.validate_output_schema(output, schema)
        assert result is True

    def test_validate_output_schema_failure(self, executor):
        """Test output validation against invalid schema."""
        output = 123  # Should be object but is number
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }

        # Should return False for invalid data
        result = executor.validate_output_schema(output, schema)
        assert result is False


@pytest.mark.unit
class TestWorkflowExecutionService:
    """Test WorkflowExecutionService high-level coordination."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self):
        """Create a WorkflowExecutionService instance."""
        return WorkflowExecutionService()

    def test_service_initialization(self, service):
        """Test service initialization without session dependency."""
        # Service follows pattern of not storing session
        assert hasattr(service, "transformation_executor")
        assert isinstance(service.transformation_executor, TransformationNodeExecutor)

    @pytest.mark.asyncio
    async def test_start_workflow_validation_and_creation(self, service, mock_session):
        """Test workflow startup with validation."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": {"type": "security"}}

        # Mock session.execute to return no workflow (not found)
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should raise ValueError for non-existent workflow
        with pytest.raises(ValueError, match="Workflow .* not found"):
            await service.start_workflow(
                mock_session, tenant_id, workflow_id, input_data
            )

    @pytest.mark.asyncio
    async def test_start_workflow_invalid_workflow_id(self, service, mock_session):
        """Test workflow startup with non-existent workflow."""
        tenant_id = "test-tenant"
        invalid_workflow_id = uuid4()
        input_data = {"test": "data"}

        # Mock session.execute to return no workflow (not found)
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should raise ValueError for non-existent workflow
        with pytest.raises(ValueError, match="Workflow .* not found"):
            await service.start_workflow(
                mock_session, tenant_id, invalid_workflow_id, input_data
            )

    @pytest.mark.asyncio
    async def test_start_workflow_input_validation_failure(self, service, mock_session):
        """Test workflow startup with invalid input data."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        invalid_input = {"missing_required_field": True}

        # Mock session.execute to return no workflow (not found)
        mock_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should raise ValueError for non-existent workflow (validation fails)
        with pytest.raises(ValueError, match="Workflow .* not found"):
            await service.start_workflow(
                mock_session, tenant_id, workflow_id, invalid_input
            )

    @pytest.mark.asyncio
    async def test_get_workflow_run_status_lightweight(self, service, mock_session):
        """Test lightweight status retrieval for polling."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock the WorkflowRunRepository
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value

            # Create a mock workflow run
            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "running"
            mock_workflow_run.created_at = datetime.now(UTC)
            mock_workflow_run.updated_at = datetime.now(UTC)
            mock_workflow_run.started_at = datetime.now(UTC)
            mock_workflow_run.completed_at = None
            mock_workflow_run.error_message = None

            mock_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            result = await service.get_workflow_run_status(
                mock_session, tenant_id, workflow_run_id
            )

            assert result["workflow_run_id"] == str(workflow_run_id)
            assert result["status"] == "running"
            assert "created_at" in result
            assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_get_workflow_run_status_returns_json_serializable(
        self, service, mock_session
    ):
        """get_workflow_run_status result is returned directly by MCP tools.

        MCP framework serializes tool results with json.dumps(). Raw datetime
        objects cause 'Object of type datetime is not JSON serializable'.
        """
        import json

        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value

            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "running"
            mock_workflow_run.created_at = datetime.now(UTC)
            mock_workflow_run.updated_at = datetime.now(UTC)
            mock_workflow_run.started_at = datetime.now(UTC)
            mock_workflow_run.completed_at = None
            mock_workflow_run.error_message = None

            mock_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            result = await service.get_workflow_run_status(
                mock_session, tenant_id, workflow_run_id
            )

            # This is what MCP framework does — must not raise TypeError
            json.dumps(result, default=None)

            # Datetime fields must be ISO strings
            assert isinstance(result["created_at"], str)
            assert isinstance(result["updated_at"], str)
            assert isinstance(result["started_at"], str)
            # workflow_run_id is a UUID — must also be a string
            assert isinstance(result["workflow_run_id"], str)

    @pytest.mark.asyncio
    async def test_get_workflow_run_details_with_io(self, service, mock_session):
        """Test full run details including input/output retrieval."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock the WorkflowRunRepository
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value

            # Create a mock workflow run with I/O details
            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "completed"
            mock_workflow_run.input_type = "inline"
            mock_workflow_run.input_location = '{"data": "input"}'
            mock_workflow_run.output_type = "s3"
            mock_workflow_run.output_location = "s3://bucket/output.json"

            mock_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            result = await service.get_workflow_run_details(
                mock_session, tenant_id, workflow_run_id
            )

            assert result == mock_workflow_run
            assert result.id == workflow_run_id
            assert result.input_type == "inline"
            assert result.output_type == "s3"

    @pytest.mark.asyncio
    async def test_get_workflow_run_details_not_found(self, service, mock_session):
        """Test run details for non-existent workflow run."""
        tenant_id = "test-tenant"
        non_existent_id = uuid4()

        # Mock the WorkflowRunRepository to return None (not found)
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_workflow_run = AsyncMock(return_value=None)

            result = await service.get_workflow_run_details(
                mock_session, tenant_id, non_existent_id
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_complete(self, service, mock_session):
        """Test materialized execution graph for completed workflow."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock all repository classes
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value
            mock_run_repo = mock_run_repo_class.return_value

            # Mock workflow run as "completed"
            mock_workflow_run = MagicMock()
            mock_workflow_run.status = "completed"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            # Create mock node instances (all completed)
            mock_nodes = []
            for i in range(3):
                mock_node = MagicMock()
                mock_node.id = uuid4()
                mock_node.node_id = f"n-{i}"
                mock_node.status = "completed"
                mock_nodes.append(mock_node)

            mock_node_repo.list_node_instances = AsyncMock(return_value=mock_nodes)
            mock_edge_repo.get_outgoing_edges = AsyncMock(
                return_value=[]
            )  # No edges for simplicity

            result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )

            assert result["workflow_run_id"] == str(workflow_run_id)
            assert result["is_complete"] is True  # All nodes completed
            assert result["status"] == "completed"
            assert "snapshot_at" in result
            assert "nodes" in result
            assert "edges" in result

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_in_progress(self, service, mock_session):
        """Test partial execution graph for running workflow."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock all repository classes
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value
            mock_run_repo = mock_run_repo_class.return_value

            # Mock workflow run as "running"
            mock_workflow_run = MagicMock()
            mock_workflow_run.status = "running"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            # Create mock node instances (some running, some completed)
            mock_nodes = []
            statuses = ["completed", "running", "pending"]
            for i, status in enumerate(statuses):
                mock_node = MagicMock()
                mock_node.id = uuid4()
                mock_node.node_id = f"n-{i}"
                mock_node.status = status
                mock_nodes.append(mock_node)

            mock_node_repo.list_node_instances = AsyncMock(return_value=mock_nodes)
            mock_edge_repo.get_outgoing_edges = AsyncMock(
                return_value=[]
            )  # No edges for simplicity

            result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )

            assert result["workflow_run_id"] == str(workflow_run_id)
            assert result["is_complete"] is False  # Some nodes not completed
            assert "snapshot_at" in result
            assert "nodes" in result
            assert "edges" in result

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_workflow_failed_stops_polling(
        self, service, mock_session
    ):
        """Test that is_complete=True when workflow run status is 'failed'.

        This is critical for stopping the frontend polling when a task fails
        and not all nodes have been instantiated yet.
        """
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        with (
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value
            mock_run_repo = mock_run_repo_class.return_value

            # Mock workflow run as "failed" - this should make is_complete=True
            mock_workflow_run = MagicMock()
            mock_workflow_run.status = "failed"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            # Only one node was instantiated (the one that failed)
            # Other nodes in the workflow definition were never created
            mock_node = MagicMock()
            mock_node.id = uuid4()
            mock_node.node_id = "n-failed-task"
            mock_node.status = "failed"

            mock_node_repo.list_node_instances = AsyncMock(return_value=[mock_node])
            mock_edge_repo.get_outgoing_edges = AsyncMock(return_value=[])

            result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )

            # CRITICAL: is_complete should be True because workflow run is "failed"
            assert result["is_complete"] is True
            assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_workflow_cancelled_stops_polling(
        self, service, mock_session
    ):
        """Test that is_complete=True when workflow run status is 'cancelled'."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        with (
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value
            mock_run_repo = mock_run_repo_class.return_value

            # Mock workflow run as "cancelled"
            mock_workflow_run = MagicMock()
            mock_workflow_run.status = "cancelled"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            # Some nodes might still be "running" when cancelled
            mock_node = MagicMock()
            mock_node.id = uuid4()
            mock_node.node_id = "n-running-task"
            mock_node.status = "running"

            mock_node_repo.list_node_instances = AsyncMock(return_value=[mock_node])
            mock_edge_repo.get_outgoing_edges = AsyncMock(return_value=[])

            result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )

            # is_complete should be True because workflow run is "cancelled"
            assert result["is_complete"] is True
            assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_all_nodes_failed_stops_polling(
        self, service, mock_session
    ):
        """Test that is_complete=True when all nodes are in 'failed' status."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        with (
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value
            mock_run_repo = mock_run_repo_class.return_value

            # Mock workflow run as "running" but nodes are all failed
            mock_workflow_run = MagicMock()
            mock_workflow_run.status = "running"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            # All instantiated nodes are "failed"
            mock_nodes = []
            for i in range(2):
                mock_node = MagicMock()
                mock_node.id = uuid4()
                mock_node.node_id = f"n-{i}"
                mock_node.status = "failed"
                mock_nodes.append(mock_node)

            mock_node_repo.list_node_instances = AsyncMock(return_value=mock_nodes)
            mock_edge_repo.get_outgoing_edges = AsyncMock(return_value=[])

            result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )

            # is_complete should be True because all nodes are terminal (failed)
            assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_cancel_workflow_run_success(self, service, mock_session):
        """Test successful workflow cancellation."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock both repository classes
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
        ):
            mock_run_repo = mock_run_repo_class.return_value
            mock_node_repo = mock_node_repo_class.return_value

            # Create a mock running workflow run
            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "running"

            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)
            mock_run_repo.update_workflow_run_status = AsyncMock()
            mock_node_repo.list_node_instances = AsyncMock(
                return_value=[]
            )  # No running nodes

            # Mock session commit
            mock_session.commit = AsyncMock()

            result = await service.cancel_workflow_run(
                mock_session, tenant_id, workflow_run_id
            )

            assert result is True
            mock_run_repo.update_workflow_run_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_workflow_run_already_completed(self, service, mock_session):
        """Test cancelling already completed workflow."""
        tenant_id = "test-tenant"
        workflow_run_id = uuid4()

        # Mock both repository classes
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch("analysi.services.workflow_execution.WorkflowNodeInstanceRepository"),
        ):
            mock_run_repo = mock_run_repo_class.return_value

            # Create a mock completed workflow run
            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "completed"  # Already completed

            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)

            result = await service.cancel_workflow_run(
                mock_session, tenant_id, workflow_run_id
            )

            # Should return False because workflow is already completed
            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_workflow_run_not_found(self, service, mock_session):
        """Test cancelling non-existent workflow run."""
        tenant_id = "test-tenant"
        non_existent_id = uuid4()

        # Mock repository to return None (not found)
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as mock_run_repo_class:
            mock_run_repo = mock_run_repo_class.return_value
            mock_run_repo.get_workflow_run = AsyncMock(return_value=None)

            result = await service.cancel_workflow_run(
                mock_session, tenant_id, non_existent_id
            )

            # Should return False because workflow run not found
            assert result is False


@pytest.mark.unit
class TestWorkflowExecutionServiceIntegration:
    """Test service integration patterns and dependencies."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self):
        """Create a WorkflowExecutionService instance."""
        return WorkflowExecutionService()

    def test_service_follows_session_per_method_pattern(self, service, mock_session):
        """Test that service follows session-per-method pattern (not stored)."""
        # Service should not store session as instance variable
        assert not hasattr(service, "session")

        # Methods should accept session as parameter
        import inspect

        start_workflow_sig = inspect.signature(service.start_workflow)
        assert "session" in start_workflow_sig.parameters

        get_status_sig = inspect.signature(service.get_workflow_run_status)
        assert "session" in get_status_sig.parameters

    def test_service_has_transformation_executor(self, service):
        """Test service has embedded transformation executor."""
        assert hasattr(service, "transformation_executor")
        assert isinstance(service.transformation_executor, TransformationNodeExecutor)

    @pytest.mark.asyncio
    async def test_service_method_signatures_consistent(self, service, mock_session):
        """Test all service methods have consistent signature patterns and work with mocking."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        workflow_run_id = uuid4()
        input_data = {}

        # Mock session commit for all tests
        mock_session.commit = AsyncMock()

        # Test start_workflow with proper mocking (don't mock Workflow class as SQLAlchemy needs it)
        with patch("analysi.services.workflow_execution.WorkflowExecutor"):
            mock_session.execute = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # Workflow not found
            mock_session.execute.return_value = mock_result

            # start_workflow should raise ValueError for non-existent workflow
            try:
                await service.start_workflow(
                    mock_session, tenant_id, workflow_id, input_data
                )
                raise AssertionError("Should have raised ValueError")
            except ValueError:
                pass  # Expected

        # Test other methods with repository mocking
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"
            ) as mock_edge_repo_class,
        ):
            # Setup basic mocks
            mock_run_repo = mock_run_repo_class.return_value
            mock_node_repo = mock_node_repo_class.return_value
            mock_edge_repo = mock_edge_repo_class.return_value

            # Mock a basic workflow run
            mock_workflow_run = MagicMock()
            mock_workflow_run.id = workflow_run_id
            mock_workflow_run.status = "running"
            mock_workflow_run.created_at = datetime.now(UTC)
            mock_workflow_run.updated_at = datetime.now(UTC)
            mock_workflow_run.started_at = datetime.now(UTC)
            mock_workflow_run.completed_at = None
            mock_workflow_run.error_message = None

            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_workflow_run)
            mock_run_repo.update_workflow_run_status = AsyncMock()
            mock_node_repo.list_node_instances = AsyncMock(return_value=[])
            mock_edge_repo.get_outgoing_edges = AsyncMock(return_value=[])

            # Test all methods work without raising NotImplementedError
            status_result = await service.get_workflow_run_status(
                mock_session, tenant_id, workflow_run_id
            )
            assert "workflow_run_id" in status_result

            details_result = await service.get_workflow_run_details(
                mock_session, tenant_id, workflow_run_id
            )
            assert details_result == mock_workflow_run

            graph_result = await service.get_workflow_run_graph(
                mock_session, tenant_id, workflow_run_id
            )
            assert "workflow_run_id" in graph_result

            cancel_result = await service.cancel_workflow_run(
                mock_session, tenant_id, workflow_run_id
            )
            assert isinstance(cancel_result, bool)


# ──────────────────────────────────────────────────────────────────────────────
# Additional tests for improved coverage (~65% target)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTransformationNodeExecutorEdgeCases:
    """Test TransformationNodeExecutor edge cases for improved coverage."""

    @pytest.fixture
    def executor(self):
        return TransformationNodeExecutor()

    # ── execute_template edge cases ──

    @pytest.mark.asyncio
    async def test_execute_template_with_none_input(self, executor):
        """Template receives None as input and handles it."""
        code = "return {'is_none': inp is None}"
        result = await executor.execute_template(code, None)
        assert result["result"] == {"is_none": True}

    @pytest.mark.asyncio
    async def test_execute_template_with_empty_dict_input(self, executor):
        """Template receives empty dict as input."""
        code = "return {'count': len(inp)}"
        result = await executor.execute_template(code, {})
        assert result["result"] == {"count": 0}

    @pytest.mark.asyncio
    async def test_execute_template_with_empty_list_input(self, executor):
        """Template receives empty list as input."""
        code = "return {'count': len(inp)}"
        result = await executor.execute_template(code, [])
        assert result["result"] == {"count": 0}

    @pytest.mark.asyncio
    async def test_execute_template_with_nested_data(self, executor):
        """Template processes deeply nested data structures."""
        code = "return {'deep': inp['level1']['level2']['level3']}"
        input_data = {"level1": {"level2": {"level3": "deep_value"}}}
        result = await executor.execute_template(code, input_data)
        assert result["result"] == {"deep": "deep_value"}

    @pytest.mark.asyncio
    async def test_execute_template_with_list_of_dicts(self, executor):
        """Template processes list of dictionaries."""
        code = "return {'names': [item['name'] for item in inp]}"
        input_data = [{"name": "alice"}, {"name": "bob"}, {"name": "charlie"}]
        result = await executor.execute_template(code, input_data)
        assert result["result"] == {"names": ["alice", "bob", "charlie"]}

    @pytest.mark.asyncio
    async def test_execute_template_raises_on_syntax_error(self, executor):
        """Template with syntax error raises ValueError (caught by AST validation)."""
        code = "return {{{invalid syntax"
        with pytest.raises(ValueError, match="syntax error"):
            await executor.execute_template(code, {})

    @pytest.mark.asyncio
    async def test_execute_template_raises_on_runtime_error(self, executor):
        """Template that triggers a runtime error propagates it."""
        code = "return 1 / 0"
        with pytest.raises(ZeroDivisionError):
            await executor.execute_template(code, {})

    @pytest.mark.asyncio
    async def test_execute_template_raises_on_error_dict_result(self, executor):
        """Template returning dict with 'error' key raises ValueError."""
        code = "return {'error': 'something went wrong'}"
        with pytest.raises(ValueError, match="Transformation produced error output"):
            await executor.execute_template(code, {})

    @pytest.mark.asyncio
    async def test_execute_template_multiline_code(self, executor):
        """Template with multi-line code executes correctly."""
        code = "total = 0\nfor item in inp:\n    total += item\nreturn {'total': total}"
        result = await executor.execute_template(code, [1, 2, 3, 4, 5])
        assert result["result"] == {"total": 15}

    @pytest.mark.asyncio
    async def test_execute_template_with_envelope_parameter(self, executor):
        """Template accesses the full envelope via workflow_input param."""
        code = "return {'from_envelope': workflow_input.get('context', {}).get('key')}"
        input_data = {"simplified": True}
        envelope = {"context": {"key": "envelope_value"}, "result": input_data}
        result = await executor.execute_template(code, input_data, envelope=envelope)
        assert result["result"] == {"from_envelope": "envelope_value"}

    @pytest.mark.asyncio
    async def test_execute_template_with_none_envelope(self, executor):
        """Template with None envelope (default) does not crash."""
        code = "return {'has_envelope': workflow_input is not None}"
        result = await executor.execute_template(code, {"data": 1}, envelope=None)
        assert result["result"] == {"has_envelope": False}

    @pytest.mark.asyncio
    async def test_execute_template_uses_builtin_enumerate(self, executor):
        """Template can use enumerate (whitelisted builtin)."""
        code = "return {'indexed': [(i, v) for i, v in enumerate(inp)]}"
        result = await executor.execute_template(code, ["a", "b"])
        assert result["result"] == {"indexed": [(0, "a"), (1, "b")]}

    @pytest.mark.asyncio
    async def test_execute_template_uses_builtin_isinstance(self, executor):
        """Template can use isinstance (whitelisted builtin)."""
        code = "return {'is_dict': isinstance(inp, dict)}"
        result = await executor.execute_template(code, {"key": "val"})
        assert result["result"] == {"is_dict": True}

    @pytest.mark.asyncio
    async def test_execute_template_returns_string_result(self, executor):
        """Template can return a plain string (non-dict, non-error)."""
        code = "return 'hello world'"
        result = await executor.execute_template(code, {})
        assert result["result"] == "hello world"
        assert result["node_id"] == "transformation"

    @pytest.mark.asyncio
    async def test_execute_template_returns_list_result(self, executor):
        """Template can return a list."""
        code = "return [1, 2, 3]"
        result = await executor.execute_template(code, {})
        assert result["result"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_execute_template_returns_numeric_result(self, executor):
        """Template can return a numeric value."""
        code = "return 42"
        result = await executor.execute_template(code, {})
        assert result["result"] == 42

    # ── build_envelope edge cases ──

    def test_build_envelope_with_none_context(self, executor):
        """build_envelope defaults context to empty dict when None."""
        envelope = executor.build_envelope("node-1", "result-data", context=None)
        assert envelope["context"] == {}

    def test_build_envelope_with_none_description(self, executor):
        """build_envelope defaults description when None."""
        envelope = executor.build_envelope("node-1", "result-data", description=None)
        assert envelope["description"] == "Output from node-1"

    def test_build_envelope_with_custom_context_and_description(self, executor):
        """build_envelope uses provided context and description."""
        ctx = {"execution_time_ms": 42}
        desc = "Custom description"
        envelope = executor.build_envelope("n1", "data", context=ctx, description=desc)
        assert envelope["context"] == ctx
        assert envelope["description"] == desc

    def test_build_envelope_with_none_result(self, executor):
        """build_envelope wraps None result without error."""
        envelope = executor.build_envelope("n1", None)
        assert envelope["result"] is None

    def test_build_envelope_with_list_result(self, executor):
        """build_envelope wraps list result."""
        envelope = executor.build_envelope("n1", [1, 2, 3])
        assert envelope["result"] == [1, 2, 3]

    # ── validate_output_schema edge cases ──

    def test_validate_output_schema_complex_nested(self, executor):
        """Validate output with deeply nested schema."""
        output = {"data": {"inner": {"value": 42}}}
        schema = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "inner": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                        }
                    },
                }
            },
        }
        assert executor.validate_output_schema(output, schema) is True

    def test_validate_output_schema_empty_schema(self, executor):
        """Empty schema validates anything."""
        assert executor.validate_output_schema({"anything": "goes"}, {}) is True
        assert executor.validate_output_schema(42, {}) is True
        assert executor.validate_output_schema("string", {}) is True

    def test_validate_output_schema_with_none_output(self, executor):
        """None output validated against type:object schema fails."""
        schema = {"type": "object"}
        assert executor.validate_output_schema(None, schema) is False

    def test_validate_output_schema_with_string_output(self, executor):
        """String output validated against string schema passes."""
        schema = {"type": "string"}
        assert executor.validate_output_schema("hello", schema) is True

    def test_validate_output_schema_with_string_output_wrong_type(self, executor):
        """String output validated against number schema fails."""
        schema = {"type": "number"}
        assert executor.validate_output_schema("hello", schema) is False

    def test_validate_output_schema_with_array_schema(self, executor):
        """Array output validated against array schema with items passes."""
        schema = {"type": "array", "items": {"type": "integer"}}
        assert executor.validate_output_schema([1, 2, 3], schema) is True

    def test_validate_output_schema_with_array_wrong_items(self, executor):
        """Array with wrong item types fails validation."""
        schema = {"type": "array", "items": {"type": "integer"}}
        assert executor.validate_output_schema(["a", "b"], schema) is False

    def test_validate_output_schema_with_required_fields_missing(self, executor):
        """Missing required fields fails validation."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        assert executor.validate_output_schema({"name": "Alice"}, schema) is False

    def test_validate_output_schema_with_malformed_schema(self, executor):
        """Malformed schema returns False (not an exception)."""
        # A schema with invalid type
        schema = {"type": "not_a_real_type"}
        # jsonschema may or may not raise on invalid type; the method should catch it
        result = executor.validate_output_schema({"key": "val"}, schema)
        assert isinstance(result, bool)


@pytest.mark.unit
class TestWorkflowExecutorEdgeCases:
    """Test WorkflowExecutor edge cases for improved coverage."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    # ── execute_workflow with execution_context ──

    @pytest.mark.asyncio
    async def test_execute_workflow_with_execution_context(self, executor):
        """execute_workflow passes execution_context to run_repo."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": "data"}
        execution_context = {"analysis_id": str(uuid4())}

        mock_run = MagicMock(id=uuid4())
        executor.run_repo.create_workflow_run = AsyncMock(return_value=mock_run)
        executor.storage.store = AsyncMock(return_value={"location": "loc"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        result = await executor.execute_workflow(
            tenant_id, workflow_id, input_data, execution_context=execution_context
        )

        assert result == mock_run.id
        call_kwargs = executor.run_repo.create_workflow_run.call_args
        assert call_kwargs.kwargs.get("execution_context") == execution_context

    # ── execute_node_instance for task node type ──

    @pytest.mark.asyncio
    async def test_execute_node_instance_task_node_success(self, executor):
        """execute_node_instance handles task node type end-to-end."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-task-1"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        # Setup mock node (kind=task)
        mock_node = MagicMock()
        mock_node.kind = "task"
        mock_node.task_id = uuid4()
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        # Mock aggregate_predecessor_outputs
        executor.aggregate_predecessor_outputs = AsyncMock(
            return_value={"result": {"key": "value"}}
        )

        # Mock workflow run repo
        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.execution_context = None
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)

        # Mock node repo
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.node_repo.save_node_instance_output = AsyncMock()

        # Mock storage
        executor.storage.select_storage_type = MagicMock(return_value="inline")
        executor.storage.store = AsyncMock(return_value={"location": "output-loc"})
        executor.storage.retrieve = AsyncMock(
            return_value='{"result_key": "result_val"}'
        )

        # Mock TaskRunService and TaskExecutionService
        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()

        mock_updated_task_run = MagicMock()
        mock_updated_task_run.status = "completed"
        mock_updated_task_run.output_location = "some-loc"
        mock_updated_task_run.output_type = "inline"

        with (
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExecSvc,
        ):
            from analysi.schemas.task_execution import (
                TaskExecutionResult,
                TaskExecutionStatus,
            )

            mock_trs = MockTaskRunSvc.return_value
            mock_trs.create_execution = AsyncMock(return_value=mock_task_run)
            mock_trs.update_status = AsyncMock()

            mock_tes = MockTaskExecSvc.return_value
            mock_tes.execute_single_task = AsyncMock(
                return_value=TaskExecutionResult(
                    status=TaskExecutionStatus.COMPLETED,
                    output_data={"result_key": "result_val"},
                    error_message=None,
                    execution_time_ms=100,
                    task_run_id=mock_task_run.id,
                )
            )

            await executor.execute_node_instance(mock_instance)

        # Verify task run was created and executed
        mock_trs.create_execution.assert_called_once()
        mock_tes.execute_single_task.assert_called_once()
        # Verify status was updated to completed
        assert executor.node_repo.update_node_instance_status.call_count >= 2

    @pytest.mark.asyncio
    async def test_execute_node_instance_task_node_failed(self, executor):
        """execute_node_instance handles failed task run correctly."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-task-fail"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        # Setup mock node (kind=task)
        mock_node = MagicMock()
        mock_node.kind = "task"
        mock_node.task_id = uuid4()
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(
            return_value={"result": {"key": "value"}}
        )

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.execution_context = None
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)

        executor.node_repo.update_node_instance_status = AsyncMock()

        # Mock failed task run
        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()

        mock_failed_run = MagicMock()
        mock_failed_run.status = "failed"
        mock_failed_run.output_location = "err-loc"
        mock_failed_run.output_type = "inline"

        executor.storage.retrieve = AsyncMock(
            return_value='{"error": "Cy script compilation failed"}'
        )

        with (
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExecSvc,
        ):
            from analysi.schemas.task_execution import (
                TaskExecutionResult,
                TaskExecutionStatus,
            )

            mock_trs = MockTaskRunSvc.return_value
            mock_trs.create_execution = AsyncMock(return_value=mock_task_run)
            mock_trs.update_status = AsyncMock()
            mock_tes = MockTaskExecSvc.return_value
            mock_tes.execute_single_task = AsyncMock(
                return_value=TaskExecutionResult(
                    status=TaskExecutionStatus.FAILED,
                    output_data=None,
                    error_message="Cy script compilation failed",
                    execution_time_ms=50,
                    task_run_id=mock_task_run.id,
                )
            )

            await executor.execute_node_instance(mock_instance)

        # Verify node was marked as failed
        last_status_call = (
            executor.node_repo.update_node_instance_status.call_args_list[-1]
        )
        assert last_status_call.args[1] == "failed"

    # ── execute_node_instance for template/identity node ──

    @pytest.mark.asyncio
    async def test_execute_node_instance_transformation_with_template(self, executor):
        """execute_node_instance executes transformation node with template code."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-transform"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = uuid4()

        # Mock node (kind=transformation)
        mock_node = MagicMock()
        mock_node.kind = "transformation"

        # Need to handle two separate session.execute calls:
        # 1. WorkflowNode query
        # 2. NodeTemplate query
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node

        mock_template_result = MagicMock()
        mock_template_result.scalar_one_or_none.return_value = (
            "return {'transformed': True}"
        )

        executor.session.execute = AsyncMock(
            side_effect=[mock_node_result, mock_template_result]
        )
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(
            return_value={
                "node_id": "prev",
                "context": {},
                "description": "prev output",
                "result": {"data": 1},
            }
        )

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.node_repo.save_node_instance_output = AsyncMock()
        executor.storage.select_storage_type = MagicMock(return_value="inline")
        executor.storage.store = AsyncMock(return_value={"location": "out-loc"})

        await executor.execute_node_instance(mock_instance)

        # Should complete successfully (status updated twice: running, completed)
        assert executor.node_repo.update_node_instance_status.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_node_instance_identity_passthrough(self, executor):
        """execute_node_instance for non-task/non-transformation node passes through."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-identity"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        # Mock node (kind=identity, which falls into else branch)
        mock_node = MagicMock()
        mock_node.kind = "identity"
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(
            return_value={"result": "passthrough"}
        )

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.node_repo.save_node_instance_output = AsyncMock()
        executor.storage.select_storage_type = MagicMock(return_value="inline")
        executor.storage.store = AsyncMock(return_value={"location": "out-loc"})

        await executor.execute_node_instance(mock_instance)

        assert executor.node_repo.update_node_instance_status.call_count == 2

    # ── execute_node_instance error handling ──

    @pytest.mark.asyncio
    async def test_execute_node_instance_error_marks_failed(self, executor):
        """Node execution error marks node as failed and re-raises."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-error"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        # Make session.execute raise on node query
        executor.session.execute = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
        executor.session.commit = AsyncMock()
        executor.node_repo.update_node_instance_status = AsyncMock()

        with pytest.raises(RuntimeError, match="DB connection lost"):
            await executor.execute_node_instance(mock_instance)

        # Verify node was marked as failed
        last_call = executor.node_repo.update_node_instance_status.call_args_list[-1]
        assert last_call.kwargs.get("status") == "failed" or (
            len(last_call.args) > 1 and last_call.args[1] == "failed"
        )

    # ── check_predecessors_complete edge cases ──

    @pytest.mark.asyncio
    async def test_check_predecessors_when_no_workflow_run_found(self, executor):
        """check_predecessors_complete returns False when workflow_run not found."""
        workflow_run_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        executor.session.execute = AsyncMock(return_value=mock_result)

        result = await executor.check_predecessors_complete(workflow_run_id, "n-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_predecessors_when_workflow_not_found(self, executor):
        """check_predecessors_complete returns False when workflow not found."""
        workflow_run_id = uuid4()

        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()

        # First call returns workflow_run, second returns None for workflow
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await executor.check_predecessors_complete(workflow_run_id, "n-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_predecessors_no_incoming_edges(self, executor):
        """check_predecessors_complete returns True when node has no predecessors."""
        workflow_run_id = uuid4()

        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()

        mock_workflow = MagicMock()
        mock_workflow.edges = []  # No edges at all
        mock_workflow.nodes = []

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await executor.check_predecessors_complete(workflow_run_id, "n-start")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_predecessors_some_pending(self, executor):
        """check_predecessors_complete returns False when some predecessors are pending."""
        workflow_run_id = uuid4()

        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()

        # Create edges: pred1 -> target, pred2 -> target
        mock_edge1 = MagicMock()
        mock_edge1.to_node.node_id = "n-target"
        mock_edge1.from_node.node_id = "n-pred1"

        mock_edge2 = MagicMock()
        mock_edge2.to_node.node_id = "n-target"
        mock_edge2.from_node.node_id = "n-pred2"

        mock_workflow = MagicMock()
        mock_workflow.edges = [mock_edge1, mock_edge2]

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        # pred1 completed, pred2 still pending (None = not found)
        mock_pred1 = MagicMock()
        mock_pred1.status = "completed"
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            side_effect=[mock_pred1, None]
        )

        result = await executor.check_predecessors_complete(workflow_run_id, "n-target")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_predecessors_some_failed(self, executor):
        """check_predecessors_complete returns False when a predecessor has failed."""
        workflow_run_id = uuid4()

        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()

        mock_edge = MagicMock()
        mock_edge.to_node.node_id = "n-target"
        mock_edge.from_node.node_id = "n-pred1"

        mock_workflow = MagicMock()
        mock_workflow.edges = [mock_edge]

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        # Predecessor exists but failed
        mock_pred = MagicMock()
        mock_pred.status = "failed"
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=mock_pred
        )

        result = await executor.check_predecessors_complete(workflow_run_id, "n-target")
        assert result is False

    # ── aggregate_predecessor_outputs edge cases ──

    @pytest.mark.asyncio
    async def test_aggregate_no_predecessors_returns_workflow_input(self, executor):
        """When no predecessors exist, returns workflow input data."""
        workflow_run_id = uuid4()
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[])

        # Mock the session.execute for WorkflowRun lookup
        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.input_type = "inline"
        mock_wf_run.input_location = '{"alert": "data"}'

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wf_run
        executor.session.execute = AsyncMock(return_value=mock_result)

        # Mock run_repo.get_workflow_run
        mock_full_run = MagicMock()
        mock_full_run.input_type = "inline"
        mock_full_run.input_location = '{"alert": "data"}'
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_full_run)

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-start"
        )
        assert result == {"alert": "data"}

    @pytest.mark.asyncio
    async def test_aggregate_no_predecessors_no_workflow_run(self, executor):
        """When no predecessors and no workflow run, returns empty dict."""
        workflow_run_id = uuid4()
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        executor.session.execute = AsyncMock(return_value=mock_result)

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-start"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_aggregate_single_predecessor_no_output_location(self, executor):
        """Single predecessor with no output_location returns empty envelope."""
        workflow_run_id = uuid4()

        mock_pred = MagicMock()
        mock_pred.node_id = "n-prev"
        mock_pred.output_location = None

        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=[mock_pred]
        )

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-target"
        )
        assert result["result"] == {}
        assert "Empty result" in result["description"]

    @pytest.mark.asyncio
    async def test_aggregate_multiple_predecessors_some_without_output(self, executor):
        """Multiple predecessors where some have no output location."""
        workflow_run_id = uuid4()

        mock_pred1 = MagicMock()
        mock_pred1.node_id = "n-pred1"
        mock_pred1.output_type = "inline"
        mock_pred1.output_location = "some-loc"

        mock_pred2 = MagicMock()
        mock_pred2.node_id = "n-pred2"
        mock_pred2.output_location = None  # No output

        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=[mock_pred1, mock_pred2]
        )

        executor.storage.retrieve = AsyncMock(
            return_value='{"node_id": "t", "result": "output1"}'
        )

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-target"
        )
        # Only one predecessor had output
        assert len(result["result"]) == 1
        assert result["result"][0] == "output1"

    # ── update_workflow_status edge cases ──

    @pytest.mark.asyncio
    async def test_update_workflow_status_running(self, executor):
        """update_workflow_status with 'running' sets started_at."""
        workflow_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(workflow_run_id, "running")

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args
        assert call_kwargs.kwargs["status"] == "running"
        assert "started_at" in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_update_workflow_status_completed(self, executor):
        """update_workflow_status with 'completed' sets completed_at."""
        workflow_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(workflow_run_id, "completed")

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args
        assert call_kwargs.kwargs["status"] == "completed"
        assert "completed_at" in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_update_workflow_status_failed_with_message(self, executor):
        """update_workflow_status with 'failed' includes error_message."""
        workflow_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(
            workflow_run_id, "failed", error_message="Node X blew up"
        )

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args
        assert call_kwargs.kwargs["status"] == "failed"
        assert "completed_at" in call_kwargs.kwargs
        assert "error_message" in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_update_workflow_status_cancelled(self, executor):
        """update_workflow_status with 'cancelled' sets completed_at."""
        workflow_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(workflow_run_id, "cancelled")

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args
        assert call_kwargs.kwargs["status"] == "cancelled"
        assert "completed_at" in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_update_workflow_status_pending_no_timing(self, executor):
        """update_workflow_status with 'pending' does not set timing fields."""
        workflow_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(workflow_run_id, "pending")

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args
        assert call_kwargs.kwargs["status"] == "pending"
        assert "started_at" not in call_kwargs.kwargs
        assert "completed_at" not in call_kwargs.kwargs

    # ── create_node_instance with template_id ──

    @pytest.mark.asyncio
    async def test_create_node_instance_with_template(self, executor):
        """create_node_instance passes template_id to repo."""
        workflow_run_id = uuid4()
        node_id = "n-transform"
        node_uuid = uuid4()
        template_id = uuid4()

        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        executor.node_repo.create_node_instance = AsyncMock(return_value=mock_instance)
        executor.session.commit = AsyncMock()

        result = await executor.create_node_instance(
            workflow_run_id, node_id, node_uuid, template_id=template_id
        )

        assert result == mock_instance
        call_kwargs = executor.node_repo.create_node_instance.call_args.kwargs
        assert call_kwargs["template_id"] == template_id


@pytest.mark.unit
class TestWorkflowExecutionServiceAdditional:
    """Additional tests for WorkflowExecutionService coverage."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self):
        return WorkflowExecutionService()

    # ── start_workflow with valid workflow ──

    @pytest.mark.asyncio
    async def test_start_workflow_success(self, service, mock_session):
        """start_workflow with existing workflow returns run info."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": "data"}

        # Mock workflow exists
        mock_workflow = MagicMock()
        mock_workflow.io_schema = None  # No schema validation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock WorkflowExecutor
        expected_run_id = uuid4()
        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor"
        ) as MockExecutor:
            mock_exec = MockExecutor.return_value
            mock_exec.execute_workflow = AsyncMock(return_value=expected_run_id)

            result = await service.start_workflow(
                mock_session, tenant_id, workflow_id, input_data
            )

        assert result["workflow_run_id"] == expected_run_id
        assert result["status"] == "pending"
        assert result["message"] == "Workflow execution initiated"

    @pytest.mark.asyncio
    async def test_start_workflow_with_execution_context(self, service, mock_session):
        """start_workflow passes execution_context through to executor."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": "data"}
        execution_context = {"analysis_id": "abc123"}

        mock_workflow = MagicMock()
        mock_workflow.io_schema = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor"
        ) as MockExecutor:
            mock_exec = MockExecutor.return_value
            mock_exec.execute_workflow = AsyncMock(return_value=uuid4())

            await service.start_workflow(
                mock_session,
                tenant_id,
                workflow_id,
                input_data,
                execution_context=execution_context,
            )

            call_kwargs = mock_exec.execute_workflow.call_args
            assert (
                call_kwargs.args[3] == execution_context
                or call_kwargs.kwargs.get("execution_context") == execution_context
            )

    @pytest.mark.asyncio
    async def test_start_workflow_with_io_schema_validation_mismatch(
        self, service, mock_session
    ):
        """start_workflow logs warning but proceeds when input mismatches io_schema."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"wrong_field": "value"}  # Does not match schema

        mock_workflow = MagicMock()
        mock_workflow.io_schema = {
            "input": {
                "type": "object",
                "properties": {"alert": {"type": "string"}},
                "required": ["alert"],
            }
        }
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor"
        ) as MockExecutor:
            mock_exec = MockExecutor.return_value
            mock_exec.execute_workflow = AsyncMock(return_value=uuid4())

            # Should NOT raise - validation is best-effort
            result = await service.start_workflow(
                mock_session, tenant_id, workflow_id, input_data
            )
            assert result["status"] == "pending"

    # ── list_workflow_runs ──

    @pytest.mark.asyncio
    async def test_list_workflow_runs(self, service, mock_session):
        """list_workflow_runs returns runs from repository."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()

        mock_run1 = MagicMock()
        mock_run1.id = uuid4()
        mock_run2 = MagicMock()
        mock_run2.id = uuid4()

        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_workflow_runs = AsyncMock(
                return_value=([mock_run1, mock_run2], 2)
            )

            result = await service.list_workflow_runs(
                mock_session, tenant_id, workflow_id
            )

        assert len(result) == 2
        assert result[0].id == mock_run1.id
        assert result[1].id == mock_run2.id

    @pytest.mark.asyncio
    async def test_list_workflow_runs_with_limit(self, service, mock_session):
        """list_workflow_runs passes limit to repository."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()

        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_workflow_runs = AsyncMock(return_value=([], 0))

            await service.list_workflow_runs(
                mock_session, tenant_id, workflow_id, limit=5
            )

            call_kwargs = mock_repo.list_workflow_runs.call_args
            assert call_kwargs.kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_list_workflow_runs_empty(self, service, mock_session):
        """list_workflow_runs returns empty list when no runs exist."""
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.list_workflow_runs = AsyncMock(return_value=([], 0))

            result = await service.list_workflow_runs(mock_session, "tenant", uuid4())
            assert result == []

    # ── get_workflow_run_status when run not found ──

    @pytest.mark.asyncio
    async def test_get_workflow_run_status_not_found(self, service, mock_session):
        """get_workflow_run_status returns error dict when run not found."""
        with patch(
            "analysi.services.workflow_execution.WorkflowRunRepository"
        ) as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_workflow_run = AsyncMock(return_value=None)

            result = await service.get_workflow_run_status(
                mock_session, "tenant", uuid4()
            )

        assert "error" in result
        assert result["error"] == "Workflow run not found"

    # ── get_workflow_run_graph when run not found ──

    @pytest.mark.asyncio
    async def test_get_workflow_run_graph_run_not_found(self, service, mock_session):
        """get_workflow_run_graph returns None for missing workflow run (tenant isolation)."""
        workflow_run_id = uuid4()

        with (
            patch("analysi.services.workflow_execution.WorkflowNodeInstanceRepository"),
            patch("analysi.services.workflow_execution.WorkflowEdgeInstanceRepository"),
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
        ):
            mock_run_repo = mock_run_repo_class.return_value
            mock_run_repo.get_workflow_run = AsyncMock(return_value=None)

            result = await service.get_workflow_run_graph(
                mock_session, "tenant", workflow_run_id
            )

        # Must return None to enforce tenant isolation — callers raise 404
        assert result is None

    # ── cancel_workflow_run with running nodes ──

    @pytest.mark.asyncio
    async def test_cancel_workflow_run_with_running_nodes(self, service, mock_session):
        """cancel_workflow_run cancels all running node instances."""
        workflow_run_id = uuid4()

        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
        ):
            mock_run_repo = mock_run_repo_class.return_value
            mock_node_repo = mock_node_repo_class.return_value

            mock_wf_run = MagicMock()
            mock_wf_run.status = "running"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)
            mock_run_repo.update_workflow_run_status = AsyncMock()

            # Two running nodes
            mock_node1 = MagicMock()
            mock_node1.id = uuid4()
            mock_node2 = MagicMock()
            mock_node2.id = uuid4()
            mock_node_repo.list_node_instances = AsyncMock(
                return_value=[mock_node1, mock_node2]
            )
            mock_node_repo.update_node_instance_status = AsyncMock()
            mock_session.commit = AsyncMock()

            result = await service.cancel_workflow_run(
                mock_session, "tenant", workflow_run_id
            )

        assert result is True
        assert mock_node_repo.update_node_instance_status.call_count == 2

    @pytest.mark.asyncio
    async def test_cancel_pending_workflow(self, service, mock_session):
        """cancel_workflow_run works for pending (not yet started) workflows."""
        workflow_run_id = uuid4()

        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository"
            ) as mock_node_repo_class,
        ):
            mock_run_repo = mock_run_repo_class.return_value
            mock_node_repo = mock_node_repo_class.return_value

            mock_wf_run = MagicMock()
            mock_wf_run.status = "pending"  # Not yet started
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)
            mock_run_repo.update_workflow_run_status = AsyncMock()
            mock_node_repo.list_node_instances = AsyncMock(return_value=[])
            mock_session.commit = AsyncMock()

            result = await service.cancel_workflow_run(
                mock_session, "tenant", workflow_run_id
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_already_failed_workflow(self, service, mock_session):
        """cancel_workflow_run returns False for already failed workflow."""
        with (
            patch(
                "analysi.services.workflow_execution.WorkflowRunRepository"
            ) as mock_run_repo_class,
            patch("analysi.services.workflow_execution.WorkflowNodeInstanceRepository"),
        ):
            mock_run_repo = mock_run_repo_class.return_value
            mock_wf_run = MagicMock()
            mock_wf_run.status = "failed"
            mock_run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)

            result = await service.cancel_workflow_run(mock_session, "tenant", uuid4())
            assert result is False

    @pytest.mark.asyncio
    async def test_start_workflow_with_io_schema_generic_exception(
        self, service, mock_session
    ):
        """start_workflow handles generic exception during io_schema validation gracefully."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert": "data"}

        mock_workflow = MagicMock()
        # io_schema with "input" key that will trigger validation attempt
        # but make jsonschema_validate raise a non-ValidationError exception
        mock_workflow.io_schema = {"input": "not-a-valid-schema"}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor"
        ) as MockExecutor:
            mock_exec = MockExecutor.return_value
            mock_exec.execute_workflow = AsyncMock(return_value=uuid4())

            # Should NOT raise - generic exception is caught and logged
            result = await service.start_workflow(
                mock_session, tenant_id, workflow_id, input_data
            )
            assert result["status"] == "pending"


@pytest.mark.unit
class TestWorkflowExecutorCaptureOutput:
    """Test _capture_workflow_output method."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_capture_output_single_terminal_node(self, executor):
        """Captures output from single terminal node with inline storage."""
        workflow_run_id = uuid4()

        # _capture_workflow_output accepts pre-computed
        # terminal_node_ids (list[str]) instead of a Workflow ORM object.
        terminal_node_ids = ["n-final"]

        # Mock node instance with completed status and inline output
        mock_instance = MagicMock()
        mock_instance.status = "completed"
        mock_instance.output_type = "inline"
        mock_instance.output_location = (
            '{"node_id": "transformation", "result": {"answer": 42}}'
        )

        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=mock_instance
        )
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

        # _capture_workflow_output stores output while keeping status="running"
        # (the caller sets "completed" status separately in monitor_execution)
        executor.run_repo.update_workflow_run_status.assert_called_once()
        call_kwargs = executor.run_repo.update_workflow_run_status.call_args.kwargs
        assert call_kwargs["output_type"] == "inline"
        # The output_location should contain the extracted result (not the envelope)
        import json

        stored_output = json.loads(call_kwargs["output_location"])
        assert stored_output == {"answer": 42}

    @pytest.mark.asyncio
    async def test_capture_output_multiple_terminal_nodes(self, executor):
        """Captures combined output from multiple terminal nodes."""
        workflow_run_id = uuid4()

        terminal_node_ids = ["n-final-1", "n-final-2"]

        # Mock completed node instances
        mock_inst1 = MagicMock()
        mock_inst1.status = "completed"
        mock_inst1.output_type = "inline"
        mock_inst1.output_location = '{"result": "output1"}'

        mock_inst2 = MagicMock()
        mock_inst2.status = "completed"
        mock_inst2.output_type = "inline"
        mock_inst2.output_location = '{"result": "output2"}'

        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            side_effect=[mock_inst1, mock_inst2]
        )
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args.kwargs
        import json

        stored_output = json.loads(call_kwargs["output_location"])
        assert stored_output == {"n-final-1": "output1", "n-final-2": "output2"}

    @pytest.mark.asyncio
    async def test_capture_output_no_terminal_nodes(self, executor):
        """Does nothing when there are no terminal nodes."""
        workflow_run_id = uuid4()

        terminal_node_ids = []  # No terminal nodes

        executor.run_repo.update_workflow_run_status = AsyncMock()

        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

        # Should not call update since there are no terminal nodes
        executor.run_repo.update_workflow_run_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_output_terminal_node_not_completed(self, executor):
        """Does not store output when terminal node is not completed."""
        workflow_run_id = uuid4()

        terminal_node_ids = ["n-final"]

        # Node exists but failed
        mock_instance = MagicMock()
        mock_instance.status = "failed"
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=mock_instance
        )
        executor.run_repo.update_workflow_run_status = AsyncMock()

        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

        # Should not update output since node is not completed
        executor.run_repo.update_workflow_run_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_output_exception_does_not_propagate(self, executor):
        """Exception during capture does not propagate (fail-safe)."""
        workflow_run_id = uuid4()

        terminal_node_ids = ["n-final"]

        # Make the node repo raise an error
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            side_effect=RuntimeError("Unexpected DB error")
        )

        # Should NOT raise
        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

    @pytest.mark.asyncio
    async def test_capture_output_raw_data_without_envelope(self, executor):
        """Captures raw data when output is not wrapped in an envelope."""
        workflow_run_id = uuid4()

        terminal_node_ids = ["n-final"]

        mock_instance = MagicMock()
        mock_instance.status = "completed"
        mock_instance.output_type = "inline"
        mock_instance.output_location = '{"raw_key": "raw_value"}'  # No "result" key

        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=mock_instance
        )
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor._capture_workflow_output(workflow_run_id, terminal_node_ids)

        call_kwargs = executor.run_repo.update_workflow_run_status.call_args.kwargs
        import json

        stored_output = json.loads(call_kwargs["output_location"])
        assert stored_output == {"raw_key": "raw_value"}


@pytest.mark.unit
class TestWorkflowExecutorMonitorExecution:
    """Test monitor_execution method edge cases."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_monitor_execution_workflow_run_not_found(self, executor):
        """monitor_execution returns early when workflow run not found."""
        workflow_run_id = uuid4()

        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        # First call for status update (running), then for workflow_run lookup
        mock_result_empty = MagicMock()
        mock_result_empty.scalar_one_or_none.return_value = None
        mock_result_empty.fetchall.return_value = []

        executor.session.execute = AsyncMock(return_value=mock_result_empty)

        # Should complete without error (returns early)
        await executor.monitor_execution(workflow_run_id)

    @pytest.mark.asyncio
    async def test_monitor_execution_all_nodes_completed(self, executor):
        """monitor_execution completes successfully when all nodes finish."""
        workflow_run_id = uuid4()

        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        # Mock workflow run
        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.tenant_id = "test-tenant"

        # Mock workflow with one node, no edges
        mock_wf_node = MagicMock()
        mock_wf_node.node_id = "n-only"
        mock_wf_node.id = uuid4()
        mock_wf_node.node_template_id = None

        mock_workflow = MagicMock()
        mock_workflow.name = "Test Workflow"
        mock_workflow.nodes = [mock_wf_node]
        mock_workflow.edges = []

        # Session execute side effects:
        # 1. workflow_run lookup
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        # 2. workflow lookup
        mock_result2 = MagicMock()
        mock_result2.scalar_one.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        # Node instance creation succeeds
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        executor.node_repo.create_node_instance = AsyncMock(
            return_value=MagicMock(spec=WorkflowNodeInstance)
        )

        # First iteration: no failed nodes, one pending node, predecessors complete,
        # execution succeeds, then no more pending -> all completed -> done
        mock_pending_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_pending_instance.node_id = "n-only"
        mock_pending_instance.id = uuid4()

        mock_completed_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_completed_instance.status = "completed"
        mock_completed_instance.node_id = "n-only"

        executor.node_repo.list_node_instances = AsyncMock(
            side_effect=[
                [],  # No failed nodes (first check)
                [mock_pending_instance],  # Pending nodes
                [],  # No failed nodes (second iteration)
                [],  # No pending nodes
                [mock_completed_instance],  # All nodes complete
            ]
        )

        executor.check_predecessors_complete = AsyncMock(return_value=True)
        executor.execute_node_instance = AsyncMock()
        executor._create_successor_instances = AsyncMock()
        executor._capture_workflow_output = AsyncMock()

        await executor.monitor_execution(workflow_run_id)

        # Verify workflow status was set to running and then completed
        status_calls = executor.run_repo.update_workflow_run_status.call_args_list
        assert len(status_calls) >= 2

    @pytest.mark.asyncio
    async def test_monitor_execution_node_fails_stops_workflow(self, executor):
        """monitor_execution stops when a node fails (fail-fast)."""
        workflow_run_id = uuid4()

        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()

        mock_wf_run = MagicMock()
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.tenant_id = "test-tenant"

        mock_wf_node = MagicMock()
        mock_wf_node.node_id = "n-fail"
        mock_wf_node.id = uuid4()
        mock_wf_node.node_template_id = None

        mock_workflow = MagicMock()
        mock_workflow.name = "Test Workflow"
        mock_workflow.nodes = [mock_wf_node]
        mock_workflow.edges = []

        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = mock_wf_run
        mock_result2 = MagicMock()
        mock_result2.scalar_one.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        executor.node_repo.create_node_instance = AsyncMock(
            return_value=MagicMock(spec=WorkflowNodeInstance)
        )

        # First iteration: failed node found immediately
        mock_failed = MagicMock()
        mock_failed.node_id = "n-fail"
        executor.node_repo.list_node_instances = AsyncMock(
            return_value=[mock_failed]  # Failed nodes found
        )

        await executor.monitor_execution(workflow_run_id)

        # Verify workflow was marked as failed
        last_status_call = executor.run_repo.update_workflow_run_status.call_args_list[
            -1
        ]
        assert last_status_call.kwargs.get("status") == "failed" or "failed" in str(
            last_status_call
        )


@pytest.mark.unit
class TestWorkflowExecutorAggregateS3:
    """Test aggregate_predecessor_outputs with S3 storage paths."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_aggregate_no_predecessors_s3_input(self, executor):
        """When no predecessors and workflow uses S3 input, retrieves from storage."""
        workflow_run_id = uuid4()
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[])

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.input_type = "s3"
        mock_wf_run.input_location = "s3://bucket/path/input.json"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wf_run
        executor.session.execute = AsyncMock(return_value=mock_result)

        # Mock full workflow run from repo
        mock_full_run = MagicMock()
        mock_full_run.input_type = "s3"
        mock_full_run.input_location = "s3://bucket/path/input.json"
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_full_run)

        # Mock storage retrieval
        executor.storage.retrieve = AsyncMock(return_value='{"from_s3": true}')

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-start"
        )
        assert result == {"from_s3": True}
        executor.storage.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_aggregate_no_predecessors_no_input_location(self, executor):
        """Returns empty dict when workflow run has no input_location."""
        workflow_run_id = uuid4()
        executor.node_repo.get_predecessor_instances = AsyncMock(return_value=[])

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.input_location = None  # No input location

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_wf_run
        executor.session.execute = AsyncMock(return_value=mock_result)

        mock_full_run = MagicMock()
        mock_full_run.input_location = None
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_full_run)

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-start"
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_aggregate_single_predecessor_raw_output_no_envelope(self, executor):
        """Single predecessor with raw output (no result/envelope field)."""
        workflow_run_id = uuid4()

        mock_pred = MagicMock()
        mock_pred.node_id = "n-prev"
        mock_pred.output_type = "inline"
        mock_pred.output_location = "loc"

        executor.node_repo.get_predecessor_instances = AsyncMock(
            return_value=[mock_pred]
        )
        # Return raw data without "result" key
        executor.storage.retrieve = AsyncMock(return_value='{"raw_field": "raw_value"}')

        result = await executor.aggregate_predecessor_outputs(
            workflow_run_id, "n-target"
        )
        assert result["result"] == {"raw_field": "raw_value"}


@pytest.mark.unit
class TestWorkflowExecutorTaskErrorRetrieval:
    """Test task execution error retrieval edge cases."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_task_failed_error_retrieval_fails_gracefully(self, executor):
        """When task fails and error retrieval also fails, uses default message."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-task-err"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        mock_node = MagicMock()
        mock_node.kind = "task"
        mock_node.task_id = uuid4()
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(return_value={"result": {}})

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.execution_context = None
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)
        executor.node_repo.update_node_instance_status = AsyncMock()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()

        # Task failed, and retrieving error output also fails
        mock_failed_run = MagicMock()
        mock_failed_run.status = "failed"
        mock_failed_run.output_location = "some-loc"
        mock_failed_run.output_type = "inline"

        executor.storage.retrieve = AsyncMock(
            side_effect=RuntimeError("Storage unavailable")
        )

        with (
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExecSvc,
        ):
            from analysi.schemas.task_execution import (
                TaskExecutionResult,
                TaskExecutionStatus,
            )

            mock_trs = MockTaskRunSvc.return_value
            mock_trs.create_execution = AsyncMock(return_value=mock_task_run)
            mock_trs.update_status = AsyncMock()
            mock_tes = MockTaskExecSvc.return_value
            mock_tes.execute_single_task = AsyncMock(
                return_value=TaskExecutionResult(
                    status=TaskExecutionStatus.FAILED,
                    output_data=None,
                    error_message="Task execution failed",
                    execution_time_ms=10,
                    task_run_id=mock_task_run.id,
                )
            )

            await executor.execute_node_instance(mock_instance)

        # Should still mark as failed
        last_call = executor.node_repo.update_node_instance_status.call_args_list[-1]
        assert "failed" in str(last_call)

    @pytest.mark.asyncio
    async def test_task_failed_no_output_location(self, executor):
        """When task fails, node is marked failed using error from TaskExecutionResult."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-task-err2"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        mock_node = MagicMock()
        mock_node.kind = "task"
        mock_node.task_id = uuid4()
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(return_value={"result": {}})

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.execution_context = None
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)
        executor.node_repo.update_node_instance_status = AsyncMock()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()

        with (
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExecSvc,
        ):
            from analysi.schemas.task_execution import (
                TaskExecutionResult,
                TaskExecutionStatus,
            )

            mock_trs = MockTaskRunSvc.return_value
            mock_trs.create_execution = AsyncMock(return_value=mock_task_run)
            mock_trs.update_status = AsyncMock()
            mock_tes = MockTaskExecSvc.return_value
            mock_tes.execute_single_task = AsyncMock(
                return_value=TaskExecutionResult(
                    status=TaskExecutionStatus.FAILED,
                    output_data=None,
                    error_message="Task execution failed",
                    execution_time_ms=10,
                    task_run_id=mock_task_run.id,
                )
            )

            await executor.execute_node_instance(mock_instance)

        last_call = executor.node_repo.update_node_instance_status.call_args_list[-1]
        assert "failed" in str(last_call)

    @pytest.mark.asyncio
    async def test_task_completed_no_output_uses_fallback(self, executor):
        """When task completes with no output_data, uses fallback envelope."""
        mock_instance = MagicMock(spec=WorkflowNodeInstance)
        mock_instance.id = uuid4()
        mock_instance.node_id = "n-task-no-out"
        mock_instance.node_uuid = uuid4()
        mock_instance.workflow_run_id = uuid4()
        mock_instance.template_id = None

        mock_node = MagicMock()
        mock_node.kind = "task"
        mock_node.task_id = uuid4()
        mock_node_result = MagicMock()
        mock_node_result.scalar_one.return_value = mock_node
        executor.session.execute = AsyncMock(return_value=mock_node_result)
        executor.session.commit = AsyncMock()

        executor.aggregate_predecessor_outputs = AsyncMock(return_value={"result": {}})

        mock_wf_run = MagicMock()
        mock_wf_run.tenant_id = "test-tenant"
        mock_wf_run.execution_context = None
        executor.run_repo.get_workflow_run_by_id = AsyncMock(return_value=mock_wf_run)
        executor.run_repo.get_workflow_run = AsyncMock(return_value=mock_wf_run)
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.node_repo.save_node_instance_output = AsyncMock()
        executor.storage.select_storage_type = MagicMock(return_value="inline")
        executor.storage.store = AsyncMock(return_value={"location": "out"})

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()

        with (
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExecSvc,
        ):
            from analysi.schemas.task_execution import (
                TaskExecutionResult,
                TaskExecutionStatus,
            )

            mock_trs = MockTaskRunSvc.return_value
            mock_trs.create_execution = AsyncMock(return_value=mock_task_run)
            mock_trs.update_status = AsyncMock()
            mock_tes = MockTaskExecSvc.return_value
            # Task completed but with no output_data
            mock_tes.execute_single_task = AsyncMock(
                return_value=TaskExecutionResult(
                    status=TaskExecutionStatus.COMPLETED,
                    output_data=None,
                    error_message=None,
                    execution_time_ms=10,
                    task_run_id=mock_task_run.id,
                )
            )

            await executor.execute_node_instance(mock_instance)

        # Should still complete (fallback output used)
        assert executor.node_repo.update_node_instance_status.call_count >= 2
