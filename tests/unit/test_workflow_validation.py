"""
Unit tests for workflow DAG validation logic.
These tests verify pure DAG validation functions.
"""

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow import validate_workflow_dag, validate_workflow_schema


@pytest.mark.unit
class TestDAGValidation:
    """Test DAG validation functions."""

    def test_validate_empty_workflow_graph(self):
        """Test DAG validation with empty graph."""
        nodes = []
        edges = []

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_single_node_graph(self):
        """Test DAG validation with single node."""
        nodes = [{"node_id": "start", "kind": "transformation"}]
        edges = []

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_linear_graph(self):
        """Test DAG validation with linear graph A→B→C."""
        nodes = [
            {"node_id": "a", "kind": "transformation"},
            {"node_id": "b", "kind": "transformation"},
            {"node_id": "c", "kind": "task"},
        ]
        edges = [
            {"from_node_id": "a", "to_node_id": "b"},
            {"from_node_id": "b", "to_node_id": "c"},
        ]

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_diamond_graph(self):
        """Test DAG validation with diamond pattern A→[B,C]→D."""
        nodes = [
            {"node_id": "a", "kind": "transformation"},
            {"node_id": "b", "kind": "transformation"},
            {"node_id": "c", "kind": "transformation"},
            {"node_id": "d", "kind": "task"},
        ]
        edges = [
            {"from_node_id": "a", "to_node_id": "b"},
            {"from_node_id": "a", "to_node_id": "c"},
            {"from_node_id": "b", "to_node_id": "d"},
            {"from_node_id": "c", "to_node_id": "d"},
        ]

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_cyclic_graph_should_fail(self):
        """Test DAG validation with cycle A→B→C→A."""
        nodes = [
            {"node_id": "a", "kind": "transformation"},
            {"node_id": "b", "kind": "transformation"},
            {"node_id": "c", "kind": "transformation"},
        ]
        edges = [
            {"from_node_id": "a", "to_node_id": "b"},
            {"from_node_id": "b", "to_node_id": "c"},
            {"from_node_id": "c", "to_node_id": "a"},  # Creates cycle
        ]

        # Cyclic graphs should be invalid (return False)
        result = validate_workflow_dag(nodes, edges)
        assert result is False

    def test_validate_self_loop_should_fail(self):
        """Test DAG validation with self-loop A→A."""
        nodes = [{"node_id": "a", "kind": "transformation"}]
        edges = [{"from_node_id": "a", "to_node_id": "a"}]  # Self loop

        # Self loops should be invalid (return False)
        result = validate_workflow_dag(nodes, edges)
        assert result is False

    def test_validate_disconnected_components(self):
        """Test DAG validation with disconnected components."""
        nodes = [
            {"node_id": "a", "kind": "transformation"},
            {"node_id": "b", "kind": "transformation"},
            {"node_id": "c", "kind": "transformation"},
            {"node_id": "d", "kind": "transformation"},
        ]
        edges = [
            {"from_node_id": "a", "to_node_id": "b"},
            {"from_node_id": "c", "to_node_id": "d"},  # Disconnected from A-B
        ]

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True

    def test_validate_invalid_edge_references(self):
        """Test DAG validation with invalid edge references."""
        nodes = [{"node_id": "a", "kind": "transformation"}]
        edges = [{"from_node_id": "a", "to_node_id": "nonexistent"}]

        # Invalid edge references should raise ValueError
        with pytest.raises(
            ValueError, match="Edge references non-existent node: nonexistent"
        ):
            validate_workflow_dag(nodes, edges)

    def test_validate_complex_fan_out_fan_in(self):
        """Test DAG validation with complex fan-out/fan-in pattern."""
        nodes = [
            {"node_id": "start", "kind": "transformation"},
            {"node_id": "branch1", "kind": "transformation"},
            {"node_id": "branch2", "kind": "transformation"},
            {"node_id": "branch3", "kind": "transformation"},
            {"node_id": "merge1", "kind": "transformation"},
            {"node_id": "merge2", "kind": "transformation"},
            {"node_id": "end", "kind": "task"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "branch1"},
            {"from_node_id": "start", "to_node_id": "branch2"},
            {"from_node_id": "start", "to_node_id": "branch3"},
            {"from_node_id": "branch1", "to_node_id": "merge1"},
            {"from_node_id": "branch2", "to_node_id": "merge1"},
            {"from_node_id": "branch3", "to_node_id": "merge2"},
            {"from_node_id": "merge1", "to_node_id": "end"},
            {"from_node_id": "merge2", "to_node_id": "end"},
        ]

        # This should fail because our stub raises NotImplementedError
        result = validate_workflow_dag(nodes, edges)
        assert result is True


@pytest.mark.unit
class TestSchemaValidation:
    """Test workflow schema validation functions."""

    def test_validate_minimal_workflow_schema(self):
        """Test schema validation with minimal Rodos-compliant workflow."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                    "required": ["data"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"data": "test"}],
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

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_validate_complex_workflow_schema(self):
        """Test schema validation with complex Rodos-compliant workflow."""
        workflow_data = {
            "name": "Complex Workflow",
            "description": "A complex multi-node workflow",
            "is_dynamic": False,
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "alert": {"type": "object"},
                        "threshold": {"type": "number"},
                    },
                    "required": ["alert"],
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                },
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"alert": {"id": "123"}, "threshold": 0.5}],
            "nodes": [
                {
                    "node_id": "n1",
                    "kind": "transformation",
                    "name": "Extract Data",
                    "is_start_node": True,
                    "node_template_id": "550e8400-e29b-41d4-a716-446655440000",
                    "schemas": {
                        "input": {"type": "object"},
                        "output_envelope": {"type": "object"},
                        "output_result": {"type": "object"},
                    },
                },
                {
                    "node_id": "n2",
                    "kind": "task",
                    "name": "Security Analysis",
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "n1",
                    "to_node_id": "n2",
                    "alias": "extracted_data",
                }
            ],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_validate_invalid_workflow_schema_missing_fields(self):
        """Test schema validation with missing required fields."""
        workflow_data = {
            "name": "Incomplete Workflow",
            # Missing io_schema, created_by, nodes, edges
        }

        # Missing required fields should raise ValueError
        with pytest.raises(ValueError, match="Missing required field: io_schema"):
            validate_workflow_schema(workflow_data)

    def test_validate_invalid_workflow_schema_bad_types(self):
        """Test schema validation with incorrect field types."""
        workflow_data = {
            "name": 123,  # Should be string
            "is_dynamic": "yes",  # Should be boolean
            "io_schema": "not an object",  # Should be object
            "created_by": None,  # Should be string
            "data_samples": [],  # Empty list (will fail later, but passes required field check)
            "nodes": "not an array",  # Should be array
            "edges": {"not": "array"},  # Should be array
        }

        # Invalid field types should raise ValueError - name is checked first
        with pytest.raises(ValueError, match="Name must be a non-empty string"):
            validate_workflow_schema(workflow_data)

    def test_validate_workflow_with_foreach_node(self):
        """Test schema validation with Rodos-compliant workflow containing foreach node."""
        workflow_data = {
            "name": "Foreach Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"items": {"type": "array"}}},
                "output": {"type": "array"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"items": [1, 2, 3]}],
            "nodes": [
                {
                    "node_id": "entry",
                    "kind": "transformation",
                    "name": "Workflow Entry",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                },
                {
                    "node_id": "n1",
                    "kind": "foreach",
                    "name": "Process Items",
                    "foreach_config": {
                        "array_path": "$.items",
                        "child_template": "process_item",
                        "max_items": 10,
                    },
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "array"},
                    },
                },
            ],
            "edges": [{"from_node_id": "entry", "to_node_id": "n1"}],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True


@pytest.mark.unit
class TestRodosWorkflowValidation:
    """Test Rodos-compliant workflow validation requirements.

    Rodos enforces:
    - Exactly one entry node (is_start_node=True)
    - Entry node must be transformation (with template) OR task (with task_id)
    - Input schema must define properties (no bare objects)
    - data_samples must be provided
    - data_samples must validate against input schema
    """

    def test_require_input_schema_with_properties(self):
        """Test that input schema must define properties field."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object"},  # No properties - invalid!
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError, match="io_schema.input must define 'properties'"
        ):
            validate_workflow_schema(workflow_data)

    def test_input_schema_with_proper_properties(self):
        """Test that input schema with properties validates successfully."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["ip"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4", "context": "firewall_alert"}],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_require_data_samples(self):
        """Test that data_samples field is required."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            # Missing data_samples!
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(ValueError, match="Missing required field: data_samples"):
            validate_workflow_schema(workflow_data)

    def test_require_non_empty_data_samples(self):
        """Test that data_samples must contain at least one sample."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [],  # Empty list - invalid!
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError, match="data_samples must contain at least one sample"
        ):
            validate_workflow_schema(workflow_data)

    def test_data_samples_must_match_input_schema(self):
        """Test that data_samples are validated against input schema."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "port": {"type": "number"},
                    },
                    "required": ["ip", "port"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [
                {"ip": "1.2.3.4"}  # Missing required "port" field!
            ],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError, match="data_samples\\[0\\] does not match io_schema.input"
        ):
            validate_workflow_schema(workflow_data)

    def test_data_samples_valid_sample_passes(self):
        """Test that valid data_samples pass validation."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "port": {"type": "number"},
                    },
                    "required": ["ip", "port"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [
                {"ip": "1.2.3.4", "port": 443},
                {"ip": "5.6.7.8", "port": 80, "extra_field": "allowed"},
            ],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_require_exactly_one_entry_node(self):
        """Test that workflow must have exactly one entry node."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start1",
                    "kind": "transformation",
                    "is_start_node": False,  # No entry node!
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                },
                {
                    "node_id": "task1",
                    "kind": "task",
                    "is_start_node": False,
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "schemas": {},
                },
            ],
            "edges": [{"from_node_id": "start1", "to_node_id": "task1"}],
        }

        with pytest.raises(
            ValueError,
            match="Workflow must have exactly one entry node with is_start_node=True",
        ):
            validate_workflow_schema(workflow_data)

    def test_reject_multiple_entry_nodes(self):
        """Test that workflow cannot have multiple entry nodes."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start1",
                    "kind": "transformation",
                    "is_start_node": True,  # First entry node
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                },
                {
                    "node_id": "start2",
                    "kind": "transformation",
                    "is_start_node": True,  # Second entry node - invalid!
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                },
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError, match="Workflow must have exactly one entry node, found 2"
        ):
            validate_workflow_schema(workflow_data)

    def test_entry_node_cannot_be_foreach(self):
        """Test that entry node cannot be a foreach node."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "foreach",  # Wrong! Cannot be foreach
                    "is_start_node": True,
                    "foreach_config": {"array_path": "$.items"},
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError,
            match="Entry node 'start' must be kind='transformation' or kind='task'",
        ):
            validate_workflow_schema(workflow_data)

    def test_entry_node_must_have_template(self):
        """Test that entry node must reference a NodeTemplate."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "transformation",
                    "is_start_node": True,
                    # Missing node_template_id!
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError,
            match="Entry node 'start' with kind='transformation' must reference a NodeTemplate",
        ):
            validate_workflow_schema(workflow_data)

    def test_task_entry_node_must_have_task_id(self):
        """Test that task entry nodes must reference a task_id."""
        workflow_data = {
            "name": "Test Workflow",
            "io_schema": {
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "1.2.3.4"}],
            "nodes": [
                {
                    "node_id": "start",
                    "kind": "task",
                    "is_start_node": True,
                    # Missing task_id!
                    "schemas": {},
                }
            ],
            "edges": [],
        }

        with pytest.raises(
            ValueError,
            match="Entry node 'start' with kind='task' must reference a Task via task_id",
        ):
            validate_workflow_schema(workflow_data)

    def test_task_node_as_valid_entry_point(self):
        """Test that task nodes can be valid entry points."""
        workflow_data = {
            "name": "Task Entry Workflow",
            "description": "Workflow with task as entry point",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["ip"],
                },
                "output": {"type": "object"},
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [{"ip": "192.168.1.1", "context": "threat_intel"}],
            "nodes": [
                {
                    "node_id": "initial-check",
                    "kind": "task",
                    "name": "Initial Security Check",
                    "is_start_node": True,
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "schemas": {},
                },
                {
                    "node_id": "followup",
                    "kind": "task",
                    "name": "Follow-up Action",
                    "task_id": "550e8400-e29b-41d4-a716-446655440002",
                    "schemas": {},
                },
            ],
            "edges": [{"from_node_id": "initial-check", "to_node_id": "followup"}],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True

    def test_valid_rodos_compliant_workflow(self):
        """Test that a fully Rodos-compliant workflow validates successfully."""
        workflow_data = {
            "name": "Rodos Compliant Workflow",
            "description": "A workflow following all Rodos requirements",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {
                        "ip": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["ip", "context"],
                },
                "output": {
                    "type": "object",
                    "properties": {"threat_score": {"type": "number"}},
                },
            },
            "created_by": str(SYSTEM_USER_ID),
            "data_samples": [
                {"ip": "1.2.3.4", "context": "firewall_alert"},
                {"ip": "5.6.7.8", "context": "ids_alert"},
            ],
            "nodes": [
                {
                    "node_id": "entry",
                    "kind": "transformation",
                    "name": "Workflow Entry",
                    "is_start_node": True,
                    "node_template_id": "00000000-0000-0000-0000-000000000001",
                    "schemas": {},
                },
                {
                    "node_id": "analyze",
                    "kind": "task",
                    "name": "Analyze IP",
                    "is_start_node": False,
                    "task_id": "550e8400-e29b-41d4-a716-446655440001",
                    "schemas": {},
                },
            ],
            "edges": [{"from_node_id": "entry", "to_node_id": "analyze"}],
        }

        result = validate_workflow_schema(workflow_data)
        assert result is True
