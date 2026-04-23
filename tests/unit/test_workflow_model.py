"""
Unit tests for Workflow model structure and validation.
These tests don't require a database - they test model structure only.
"""

from datetime import datetime
from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow import NodeTemplate, Workflow, WorkflowEdge, WorkflowNode


@pytest.mark.unit
class TestWorkflowModel:
    """Test Workflow model structure and validation."""

    def test_workflow_model_attributes(self):
        """Test that Workflow model has expected attributes."""
        # Test required attributes exist
        assert hasattr(Workflow, "id")
        assert hasattr(Workflow, "tenant_id")
        assert hasattr(Workflow, "name")
        assert hasattr(Workflow, "description")
        assert hasattr(Workflow, "is_dynamic")
        assert hasattr(Workflow, "io_schema")
        assert hasattr(Workflow, "created_by")
        assert hasattr(Workflow, "created_at")
        assert hasattr(Workflow, "planner_id")

        # Test relationship attributes exist
        assert hasattr(Workflow, "nodes")
        assert hasattr(Workflow, "edges")

    def test_workflow_initialization_minimal(self):
        """Test Workflow model initialization with minimal fields."""
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
            is_dynamic=False,  # Explicitly set default
        )

        # Verify basic attributes are set
        assert workflow.tenant_id == "test-tenant"
        assert workflow.name == "Test Workflow"
        assert workflow.created_by == str(SYSTEM_USER_ID)
        assert workflow.is_dynamic is False  # Default value
        assert workflow.io_schema == {
            "input": {"type": "object"},
            "output": {"type": "object"},
        }

        # Optional fields should be None
        assert workflow.description is None
        assert workflow.planner_id is None

    def test_workflow_initialization_full(self):
        """Test Workflow with all fields."""
        planner_id = uuid4()
        io_schema = {
            "input": {"type": "object", "properties": {"alert": {"type": "object"}}},
            "output": {"type": "object", "properties": {"result": {"type": "string"}}},
        }

        workflow = Workflow(
            tenant_id="full-test-tenant",
            name="Full Test Workflow",
            description="A comprehensive test workflow",
            is_dynamic=True,
            io_schema=io_schema,
            created_by=str(SYSTEM_USER_ID),
            planner_id=planner_id,
        )

        # Verify all fields are set
        assert workflow.tenant_id == "full-test-tenant"
        assert workflow.name == "Full Test Workflow"
        assert workflow.description == "A comprehensive test workflow"
        assert workflow.is_dynamic is True
        assert workflow.io_schema == io_schema
        assert workflow.created_by == str(SYSTEM_USER_ID)
        assert workflow.planner_id == planner_id

    def test_workflow_repr(self):
        """Test Workflow string representation."""
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="repr-tenant",
            name="Repr Test",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        # Manually set ID for testing
        workflow.id = workflow_id

        repr_str = repr(workflow)
        assert "Workflow" in repr_str
        assert str(workflow_id) in repr_str
        assert "Repr Test" in repr_str
        assert "repr-tenant" in repr_str

    def test_workflow_table_name(self):
        """Test that Workflow has correct table name."""
        assert Workflow.__tablename__ == "workflows"


@pytest.mark.unit
class TestWorkflowNodeModel:
    """Test WorkflowNode model structure and validation."""

    def test_workflow_node_attributes(self):
        """Test that WorkflowNode model has expected attributes."""
        assert hasattr(WorkflowNode, "id")
        assert hasattr(WorkflowNode, "workflow_id")
        assert hasattr(WorkflowNode, "node_id")
        assert hasattr(WorkflowNode, "kind")
        assert hasattr(WorkflowNode, "name")
        assert hasattr(WorkflowNode, "task_id")
        assert hasattr(WorkflowNode, "node_template_id")
        assert hasattr(WorkflowNode, "foreach_config")
        assert hasattr(WorkflowNode, "schemas")
        assert hasattr(WorkflowNode, "created_at")

        # Test relationships
        assert hasattr(WorkflowNode, "workflow")
        assert hasattr(WorkflowNode, "node_template")

    def test_task_node_initialization(self):
        """Test WorkflowNode initialization for task nodes."""
        workflow_id = uuid4()
        task_id = uuid4()

        node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-security-check",
            kind="task",
            name="Security Check Task",
            task_id=task_id,
            schemas={"input": {"type": "object"}, "output": {"type": "object"}},
        )

        assert node.workflow_id == workflow_id
        assert node.node_id == "n-security-check"
        assert node.kind == "task"
        assert node.name == "Security Check Task"
        assert node.task_id == task_id
        assert node.node_template_id is None
        assert node.foreach_config is None

    def test_transformation_node_initialization(self):
        """Test WorkflowNode initialization for transformation nodes."""
        workflow_id = uuid4()
        template_id = uuid4()

        node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-transform-data",
            kind="transformation",
            name="Data Transformation",
            node_template_id=template_id,
            schemas={
                "input": {"type": "object"},
                "output_envelope": {"type": "object"},
                "output_result": {"type": "object"},
            },
        )

        assert node.workflow_id == workflow_id
        assert node.node_id == "n-transform-data"
        assert node.kind == "transformation"
        assert node.name == "Data Transformation"
        assert node.task_id is None
        assert node.node_template_id == template_id
        assert node.foreach_config is None

    def test_foreach_node_initialization(self):
        """Test WorkflowNode initialization for foreach nodes."""
        workflow_id = uuid4()
        foreach_config = {
            "array_path": "$.items",
            "child_node_template": "process_item",
            "max_items": 10,
        }

        node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-foreach-items",
            kind="foreach",
            name="Process Each Item",
            foreach_config=foreach_config,
            schemas={"input": {"type": "object"}, "output": {"type": "array"}},
        )

        assert node.workflow_id == workflow_id
        assert node.node_id == "n-foreach-items"
        assert node.kind == "foreach"
        assert node.name == "Process Each Item"
        assert node.task_id is None
        assert node.node_template_id is None
        assert node.foreach_config == foreach_config

    def test_workflow_node_table_name(self):
        """Test that WorkflowNode has correct table name."""
        assert WorkflowNode.__tablename__ == "workflow_nodes"


@pytest.mark.unit
class TestWorkflowEdgeModel:
    """Test WorkflowEdge model structure and validation."""

    def test_workflow_edge_attributes(self):
        """Test that WorkflowEdge model has expected attributes."""
        assert hasattr(WorkflowEdge, "id")
        assert hasattr(WorkflowEdge, "workflow_id")
        assert hasattr(WorkflowEdge, "edge_id")
        assert hasattr(WorkflowEdge, "from_node_uuid")
        assert hasattr(WorkflowEdge, "to_node_uuid")
        assert hasattr(WorkflowEdge, "alias")
        assert hasattr(WorkflowEdge, "created_at")

        # Test relationships
        assert hasattr(WorkflowEdge, "workflow")
        assert hasattr(WorkflowEdge, "from_node")
        assert hasattr(WorkflowEdge, "to_node")

    def test_workflow_edge_initialization(self):
        """Test WorkflowEdge initialization."""
        workflow_id = uuid4()
        from_node_id = uuid4()
        to_node_id = uuid4()

        edge = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e1",
            from_node_uuid=from_node_id,
            to_node_uuid=to_node_id,
            alias="data_flow",
        )

        assert edge.workflow_id == workflow_id
        assert edge.edge_id == "e1"
        assert edge.from_node_uuid == from_node_id
        assert edge.to_node_uuid == to_node_id
        assert edge.alias == "data_flow"

    def test_workflow_edge_without_alias(self):
        """Test WorkflowEdge initialization without alias."""
        workflow_id = uuid4()
        from_node_id = uuid4()
        to_node_id = uuid4()

        edge = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e2",
            from_node_uuid=from_node_id,
            to_node_uuid=to_node_id,
        )

        assert edge.workflow_id == workflow_id
        assert edge.edge_id == "e2"
        assert edge.from_node_uuid == from_node_id
        assert edge.to_node_uuid == to_node_id
        assert edge.alias is None

    def test_workflow_edge_table_name(self):
        """Test that WorkflowEdge has correct table name."""
        assert WorkflowEdge.__tablename__ == "workflow_edges"


@pytest.mark.unit
class TestNodeTemplateModel:
    """Test NodeTemplate model structure and validation."""

    def test_node_template_attributes(self):
        """Test that NodeTemplate model has expected attributes."""
        assert hasattr(NodeTemplate, "id")
        assert hasattr(NodeTemplate, "resource_id")
        assert hasattr(NodeTemplate, "name")
        assert hasattr(NodeTemplate, "description")
        assert hasattr(NodeTemplate, "input_schema")
        assert hasattr(NodeTemplate, "output_schema")
        assert hasattr(NodeTemplate, "code")
        assert hasattr(NodeTemplate, "language")
        assert hasattr(NodeTemplate, "type")
        assert hasattr(NodeTemplate, "enabled")
        assert hasattr(NodeTemplate, "revision_num")
        assert hasattr(NodeTemplate, "created_at")

    def test_node_template_initialization_minimal(self):
        """Test NodeTemplate initialization with minimal fields."""
        resource_id = uuid4()
        input_schema = {"type": "object"}
        output_schema = {"type": "object"}

        template = NodeTemplate(
            resource_id=resource_id,
            name="basic_template",
            input_schema=input_schema,
            output_schema=output_schema,
            code="return inp",
            language="python",  # Explicitly set default
            type="static",  # Explicitly set default
            enabled=True,  # Explicitly set default
            revision_num=1,  # Explicitly set default
        )

        assert template.resource_id == resource_id
        assert template.name == "basic_template"
        assert template.input_schema == input_schema
        assert template.output_schema == output_schema
        assert template.code == "return inp"

        # Test defaults
        assert template.language == "python"
        assert template.type == "static"
        assert template.enabled is True
        assert template.revision_num == 1

    def test_node_template_initialization_full(self):
        """Test NodeTemplate with all fields."""
        resource_id = uuid4()
        input_schema = {"type": "object", "properties": {"data": {"type": "string"}}}
        output_schema = {"type": "object", "properties": {"result": {"type": "string"}}}

        template = NodeTemplate(
            resource_id=resource_id,
            name="complex_template",
            description="A complex transformation template",
            input_schema=input_schema,
            output_schema=output_schema,
            code="result = process_data(inp['data'])\nreturn {'result': result}",
            language="python",
            type="dynamic",
            enabled=True,
            revision_num=3,
        )

        assert template.resource_id == resource_id
        assert template.name == "complex_template"
        assert template.description == "A complex transformation template"
        assert template.input_schema == input_schema
        assert template.output_schema == output_schema
        assert (
            template.code
            == "result = process_data(inp['data'])\nreturn {'result': result}"
        )
        assert template.language == "python"
        assert template.type == "dynamic"
        assert template.enabled is True
        assert template.revision_num == 3

    def test_node_template_table_name(self):
        """Test that NodeTemplate has correct table name."""
        assert NodeTemplate.__tablename__ == "node_templates"

    def test_node_template_repr(self):
        """Test NodeTemplate string representation."""
        template_id = uuid4()
        template = NodeTemplate(
            resource_id=uuid4(),
            name="test_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return inp",
            revision_num=2,
        )
        template.id = template_id

        repr_str = repr(template)
        assert "NodeTemplate" in repr_str
        assert str(template_id) in repr_str
        assert "test_template" in repr_str
        assert "version=2" in repr_str


@pytest.mark.unit
class TestWorkflowModelValidationFunctions:
    """Test the validation functions in workflow models."""

    def test_validate_workflow_dag_calls_stubbed_function(self):
        """Test that validate_workflow_dag calls the stubbed implementation."""
        nodes = [{"node_id": "a"}, {"node_id": "b"}]
        edges = [{"from_node_id": "a", "to_node_id": "b"}]

        # This should pass now that we have real implementation
        from analysi.models.workflow import validate_workflow_dag

        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_workflow_schema_calls_stubbed_function(self):
        """Test that validate_workflow_schema validates Rodos-compliant workflows."""
        workflow_data = {
            "name": "Test",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                    "required": ["data"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"data": "test_value"}],
            "nodes": [
                {
                    "node_id": "entry",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        # This should pass now that we have real implementation
        from analysi.models.workflow import validate_workflow_schema

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_enrich_workflow_json_calls_stubbed_function(self):
        """Test that enrich_workflow_json calls the stubbed implementation."""
        from uuid import uuid4

        # Create a mock workflow object with required fields
        workflow = Workflow(
            tenant_id="test",
            name="Test",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        # Set required fields manually for test
        workflow.id = uuid4()
        from datetime import UTC

        workflow.created_at = datetime.now(UTC)
        workflow.nodes = []
        workflow.edges = []

        # This should pass now that we have real implementation
        from analysi.models.workflow import enrich_workflow_json

        result = enrich_workflow_json(workflow)
        assert isinstance(result, dict)
        assert "id" in result
        assert "name" in result
