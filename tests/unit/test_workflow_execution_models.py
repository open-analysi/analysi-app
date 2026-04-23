"""
Unit tests for Workflow Execution models structure and validation.
These tests don't require a database - they test model structure only.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from analysi.models.workflow_execution import (
    WorkflowEdgeInstance,
    WorkflowNodeInstance,
    WorkflowRun,
)


@pytest.mark.unit
class TestWorkflowRunModel:
    """Test WorkflowRun model structure and validation."""

    def test_workflow_run_model_attributes(self):
        """Test that WorkflowRun model has expected attributes."""
        # Test required attributes exist
        assert hasattr(WorkflowRun, "id")
        assert hasattr(WorkflowRun, "tenant_id")
        assert hasattr(WorkflowRun, "workflow_id")
        assert hasattr(WorkflowRun, "status")
        assert hasattr(WorkflowRun, "started_at")
        assert hasattr(WorkflowRun, "completed_at")
        assert hasattr(WorkflowRun, "input_type")
        assert hasattr(WorkflowRun, "input_location")
        assert hasattr(WorkflowRun, "output_type")
        assert hasattr(WorkflowRun, "output_location")
        assert hasattr(WorkflowRun, "error_message")
        assert hasattr(WorkflowRun, "created_at")
        assert hasattr(WorkflowRun, "updated_at")

    def test_workflow_run_initialization_minimal(self):
        """Test WorkflowRun model initialization with minimal fields."""
        workflow_id = uuid4()

        run = WorkflowRun(
            tenant_id="test-tenant",
            workflow_id=workflow_id,
            status="pending",  # Explicitly set default for unit tests
        )

        # Verify basic attributes are set
        assert run.tenant_id == "test-tenant"
        assert run.workflow_id == workflow_id
        assert run.status == "pending"

        # Optional fields should be None
        assert run.started_at is None
        assert run.completed_at is None
        assert run.input_type is None
        assert run.input_location is None
        assert run.output_type is None
        assert run.output_location is None
        assert run.error_message is None

    def test_workflow_run_initialization_full(self):
        """Test WorkflowRun with all fields."""
        workflow_id = uuid4()
        run_id = uuid4()
        now = datetime.now(UTC)

        run = WorkflowRun(
            id=run_id,
            tenant_id="test-tenant",
            workflow_id=workflow_id,
            status="completed",
            started_at=now,
            completed_at=now,
            input_type="inline",
            input_location='{"data": "test"}',
            output_type="s3",
            output_location="s3://bucket/path/output.json",
            error_message=None,
            created_at=now,
            updated_at=now,
        )

        # Verify all fields are set
        assert run.id == run_id
        assert run.tenant_id == "test-tenant"
        assert run.workflow_id == workflow_id
        assert run.status == "completed"
        assert run.started_at == now
        assert run.completed_at == now
        assert run.input_type == "inline"
        assert run.input_location == '{"data": "test"}'
        assert run.output_type == "s3"
        assert run.output_location == "s3://bucket/path/output.json"
        assert run.error_message is None
        assert run.created_at == now
        assert run.updated_at == now

    def test_workflow_run_repr(self):
        """Test WorkflowRun string representation."""
        workflow_id = uuid4()
        run_id = uuid4()

        run = WorkflowRun(
            id=run_id,
            tenant_id="test-tenant",
            workflow_id=workflow_id,
            status="running",
        )

        repr_str = repr(run)
        assert "WorkflowRun" in repr_str
        assert str(run_id) in repr_str
        assert "running" in repr_str

    def test_workflow_run_table_name(self):
        """Test that WorkflowRun has correct table name."""
        assert WorkflowRun.__tablename__ == "workflow_runs"

    def test_workflow_run_field_types(self):
        """Test that WorkflowRun fields have expected Python types."""
        workflow_id = uuid4()
        run_id = uuid4()
        now = datetime.now(UTC)

        run = WorkflowRun(
            id=run_id,
            tenant_id="test-tenant",
            workflow_id=workflow_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )

        # Test field types
        assert isinstance(run.id, UUID)
        assert isinstance(run.tenant_id, str)
        assert isinstance(run.workflow_id, UUID)
        assert isinstance(run.status, str)
        assert isinstance(run.created_at, datetime)
        assert isinstance(run.updated_at, datetime)


@pytest.mark.unit
class TestWorkflowNodeInstanceModel:
    """Test WorkflowNodeInstance model structure and validation."""

    def test_workflow_node_instance_model_attributes(self):
        """Test that WorkflowNodeInstance model has expected attributes."""
        # Test required attributes exist
        assert hasattr(WorkflowNodeInstance, "id")
        assert hasattr(WorkflowNodeInstance, "workflow_run_id")
        assert hasattr(WorkflowNodeInstance, "node_id")
        assert hasattr(WorkflowNodeInstance, "node_uuid")
        assert hasattr(WorkflowNodeInstance, "task_run_id")
        assert hasattr(WorkflowNodeInstance, "parent_instance_id")
        assert hasattr(WorkflowNodeInstance, "loop_context")
        assert hasattr(WorkflowNodeInstance, "status")
        assert hasattr(WorkflowNodeInstance, "started_at")
        assert hasattr(WorkflowNodeInstance, "completed_at")
        assert hasattr(WorkflowNodeInstance, "input_type")
        assert hasattr(WorkflowNodeInstance, "input_location")
        assert hasattr(WorkflowNodeInstance, "output_type")
        assert hasattr(WorkflowNodeInstance, "output_location")
        assert hasattr(WorkflowNodeInstance, "template_id")
        assert hasattr(WorkflowNodeInstance, "error_message")
        assert hasattr(WorkflowNodeInstance, "created_at")
        assert hasattr(WorkflowNodeInstance, "updated_at")

    def test_workflow_node_instance_initialization_minimal(self):
        """Test WorkflowNodeInstance model initialization with minimal fields."""
        workflow_run_id = uuid4()
        node_uuid = uuid4()

        instance = WorkflowNodeInstance(
            workflow_run_id=workflow_run_id,
            node_id="n-transform-1",
            node_uuid=node_uuid,
            status="pending",  # Explicitly set default for unit tests
        )

        # Verify required fields
        assert instance.workflow_run_id == workflow_run_id
        assert instance.node_id == "n-transform-1"
        assert instance.node_uuid == node_uuid
        assert instance.status == "pending"

        # Optional fields should be None
        assert instance.task_run_id is None
        assert instance.parent_instance_id is None
        assert instance.loop_context is None
        assert instance.started_at is None
        assert instance.completed_at is None
        assert instance.template_id is None
        assert instance.error_message is None

    def test_workflow_node_instance_with_loop_context(self):
        """Test WorkflowNodeInstance with foreach loop context."""
        workflow_run_id = uuid4()
        node_uuid = uuid4()
        parent_instance_id = uuid4()

        loop_context = {
            "item_index": 2,
            "item_key": "user_123",
            "total_items": 5,
        }

        instance = WorkflowNodeInstance(
            workflow_run_id=workflow_run_id,
            node_id="n-foreach-child",
            node_uuid=node_uuid,
            status="running",
            parent_instance_id=parent_instance_id,
            loop_context=loop_context,
        )

        assert instance.parent_instance_id == parent_instance_id
        assert instance.loop_context == loop_context
        assert instance.loop_context["item_index"] == 2
        assert instance.loop_context["total_items"] == 5

    def test_workflow_node_instance_repr(self):
        """Test WorkflowNodeInstance string representation."""
        workflow_run_id = uuid4()
        node_uuid = uuid4()
        instance_id = uuid4()

        instance = WorkflowNodeInstance(
            id=instance_id,
            workflow_run_id=workflow_run_id,
            node_id="n-test-node",
            node_uuid=node_uuid,
            status="completed",
        )

        repr_str = repr(instance)
        assert "WorkflowNodeInstance" in repr_str
        assert str(instance_id) in repr_str
        assert "n-test-node" in repr_str
        assert "completed" in repr_str

    def test_workflow_node_instance_table_name(self):
        """Test that WorkflowNodeInstance has correct table name."""
        assert WorkflowNodeInstance.__tablename__ == "workflow_node_instances"


@pytest.mark.unit
class TestWorkflowEdgeInstanceModel:
    """Test WorkflowEdgeInstance model structure and validation."""

    def test_workflow_edge_instance_model_attributes(self):
        """Test that WorkflowEdgeInstance model has expected attributes."""
        # Test required attributes exist
        assert hasattr(WorkflowEdgeInstance, "id")
        assert hasattr(WorkflowEdgeInstance, "workflow_run_id")
        assert hasattr(WorkflowEdgeInstance, "edge_id")
        assert hasattr(WorkflowEdgeInstance, "edge_uuid")
        assert hasattr(WorkflowEdgeInstance, "from_instance_id")
        assert hasattr(WorkflowEdgeInstance, "to_instance_id")
        assert hasattr(WorkflowEdgeInstance, "delivered_at")
        assert hasattr(WorkflowEdgeInstance, "created_at")

    def test_workflow_edge_instance_initialization(self):
        """Test WorkflowEdgeInstance model initialization."""
        workflow_run_id = uuid4()
        edge_uuid = uuid4()
        from_instance_id = uuid4()
        to_instance_id = uuid4()
        edge_instance_id = uuid4()
        now = datetime.now(UTC)

        edge = WorkflowEdgeInstance(
            id=edge_instance_id,
            workflow_run_id=workflow_run_id,
            edge_id="e1",
            edge_uuid=edge_uuid,
            from_instance_id=from_instance_id,
            to_instance_id=to_instance_id,
            delivered_at=now,
            created_at=now,
        )

        # Verify required fields
        assert edge.id == edge_instance_id
        assert edge.workflow_run_id == workflow_run_id
        assert edge.edge_id == "e1"
        assert edge.edge_uuid == edge_uuid
        assert edge.from_instance_id == from_instance_id
        assert edge.to_instance_id == to_instance_id
        assert edge.delivered_at == now
        assert edge.created_at == now

    def test_workflow_edge_instance_repr(self):
        """Test WorkflowEdgeInstance string representation."""
        workflow_run_id = uuid4()
        edge_uuid = uuid4()
        from_instance_id = uuid4()
        to_instance_id = uuid4()
        edge_instance_id = uuid4()

        edge = WorkflowEdgeInstance(
            id=edge_instance_id,
            workflow_run_id=workflow_run_id,
            edge_id="e-test",
            edge_uuid=edge_uuid,
            from_instance_id=from_instance_id,
            to_instance_id=to_instance_id,
        )

        repr_str = repr(edge)
        assert "WorkflowEdgeInstance" in repr_str
        assert str(edge_instance_id) in repr_str
        assert "e-test" in repr_str

    def test_workflow_edge_instance_table_name(self):
        """Test that WorkflowEdgeInstance has correct table name."""
        assert WorkflowEdgeInstance.__tablename__ == "workflow_edge_instances"


@pytest.mark.unit
class TestWorkflowExecutionModelsTimestampDefaults:
    """Test timestamp handling in workflow execution models."""

    def test_workflow_run_timezone_aware_timestamps(self):
        """Test WorkflowRun timestamps are timezone-aware."""
        workflow_id = uuid4()
        now = datetime.now(UTC)

        run = WorkflowRun(
            tenant_id="test-tenant",
            workflow_id=workflow_id,
            status="pending",
            created_at=now,
            updated_at=now,
        )

        # Timestamps should be timezone-aware
        assert run.created_at.tzinfo is not None
        assert run.updated_at.tzinfo is not None

    def test_workflow_node_instance_timezone_aware_timestamps(self):
        """Test WorkflowNodeInstance timestamps are timezone-aware."""
        workflow_run_id = uuid4()
        node_uuid = uuid4()
        now = datetime.now(UTC)

        instance = WorkflowNodeInstance(
            workflow_run_id=workflow_run_id,
            node_id="n-timezone-test",
            node_uuid=node_uuid,
            status="pending",
            created_at=now,
            updated_at=now,
        )

        assert instance.created_at.tzinfo is not None
        assert instance.updated_at.tzinfo is not None

    def test_workflow_edge_instance_timezone_aware_timestamps(self):
        """Test WorkflowEdgeInstance timestamps are timezone-aware."""
        workflow_run_id = uuid4()
        edge_uuid = uuid4()
        from_instance_id = uuid4()
        to_instance_id = uuid4()
        now = datetime.now(UTC)

        edge = WorkflowEdgeInstance(
            workflow_run_id=workflow_run_id,
            edge_id="e-timezone-test",
            edge_uuid=edge_uuid,
            from_instance_id=from_instance_id,
            to_instance_id=to_instance_id,
            created_at=now,
        )

        assert edge.created_at.tzinfo is not None
