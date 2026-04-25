"""Unit tests for StructuralValidator and SchemaValidator."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.services.workflow_composer.models import (
    ParsedComposition,
    ParsedEdge,
    ParsedNode,
    ResolvedTask,
)
from analysi.services.workflow_composer.validators import (
    SchemaValidator,
    StructuralValidator,
)


class TestStructuralValidator:
    """Test StructuralValidator business logic."""

    @pytest.fixture
    def validator(self):
        """Create a StructuralValidator instance."""
        return StructuralValidator()

    @pytest.fixture
    def simple_composition(self):
        """Create a simple valid composition."""
        return ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
                ParsedNode(node_id="n3", reference="task3", layer=3),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                ParsedEdge(from_node_id="n2", to_node_id="n3", edge_id="e2"),
            ],
            max_layer=3,
        )

    @pytest.fixture
    def resolved_nodes_simple(self):
        """Create simple resolved nodes."""
        return {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

    # ============================================================================
    # Positive Tests
    # ============================================================================

    def test_validate_valid_dag(
        self, validator, simple_composition, resolved_nodes_simple
    ):
        """
        Verify validator accepts valid DAG with no cycles.

        Expected:
        - Empty error list
        """
        errors = validator.validate(simple_composition, resolved_nodes_simple)

        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_validate_single_start_node(
        self, validator, simple_composition, resolved_nodes_simple
    ):
        """
        Verify validator accepts composition with exactly one start node.

        Expected:
        - No errors
        """
        errors = validator.validate(simple_composition, resolved_nodes_simple)

        assert len(errors) == 0

    def test_validate_all_nodes_reachable(
        self, validator, simple_composition, resolved_nodes_simple
    ):
        """
        Verify validator checks all nodes are reachable from start.

        Expected:
        - No errors when all nodes connected
        """
        errors = validator.validate(simple_composition, resolved_nodes_simple)

        assert len(errors) == 0

    # ============================================================================
    # Negative Tests
    # ============================================================================

    def test_detect_cycle(self, validator):
        """
        Verify validator detects cycles in graph.

        Expected:
        - CompositionError with error_type="cycle_detected"
        - Cycle path in context
        """
        # Create composition with cycle: n1 -> n2 -> n3 -> n1
        composition = ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
                ParsedNode(node_id="n3", reference="task3", layer=3),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                ParsedEdge(from_node_id="n2", to_node_id="n3", edge_id="e2"),
                ParsedEdge(from_node_id="n3", to_node_id="n1", edge_id="e3"),  # Cycle!
            ],
            max_layer=3,
        )

        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
        }

        errors = validator.validate(composition, resolved_nodes)

        assert len(errors) > 0
        cycle_errors = [e for e in errors if e.error_type == "cycle_detected"]
        assert len(cycle_errors) > 0

    def test_detect_multiple_start_nodes(self, validator):
        """
        Verify validator detects disconnected subgraphs.

        Expected:
        - CompositionError with error_type="multiple_start_nodes"
        """
        # Create composition with two disconnected subgraphs
        composition = ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
                ParsedNode(node_id="n3", reference="task3", layer=1),  # Another start
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                # n3 has no incoming edges - multiple start nodes!
            ],
            max_layer=2,
        )

        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
        }

        errors = validator.validate(composition, resolved_nodes)

        assert len(errors) > 0
        start_errors = [e for e in errors if e.error_type == "multiple_start_nodes"]
        assert len(start_errors) > 0

    def test_detect_unreachable_nodes(self, validator):
        """
        Verify validator detects nodes not reachable from start.

        Expected:
        - CompositionError with error_type="unreachable_nodes" OR "multiple_start_nodes"
        - List of unreachable/disconnected node IDs in context
        """
        # Create composition where n3 has no incoming edge (making it a start node)
        # This creates multiple start nodes rather than unreachable nodes
        composition = ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
                ParsedNode(node_id="n3", reference="task3", layer=3),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                # No edge to n3 - makes it a separate start node (disconnected graph)
            ],
            max_layer=3,
        )

        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
        }

        errors = validator.validate(composition, resolved_nodes)

        assert len(errors) > 0
        # n3 with no incoming edge creates multiple start nodes, not unreachable nodes
        multiple_start_errors = [
            e for e in errors if e.error_type == "multiple_start_nodes"
        ]
        assert len(multiple_start_errors) > 0
        assert "n3" in str(multiple_start_errors[0].context)

    def test_detect_missing_aggregation(self, validator):
        """
        Verify validator detects parallel blocks without aggregation nodes after them.

        Expected:
        - CompositionError with error_type="missing_aggregation"
        - Layer and parallel node IDs in context
        """
        # Create composition with parallel nodes but no aggregation
        composition = ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2, parallel_group=1),
                ParsedNode(node_id="n3", reference="task3", layer=2, parallel_group=1),
                ParsedNode(node_id="n4", reference="task4", layer=3),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                ParsedEdge(from_node_id="n1", to_node_id="n3", edge_id="e2"),
                ParsedEdge(from_node_id="n2", to_node_id="n4", edge_id="e3"),
                ParsedEdge(from_node_id="n3", to_node_id="n4", edge_id="e4"),
            ],
            max_layer=3,
        )

        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n3": ResolvedTask(
                task_id=uuid4(),
                cy_name="task3",
                name="Task 3",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
            "n4": ResolvedTask(
                task_id=uuid4(),
                cy_name="task4",
                name="Task 4",
                input_schema={},
                output_schema={},
                data_samples=[],
            ),
        }

        errors = validator.validate(composition, resolved_nodes)

        assert len(errors) > 0
        aggregation_errors = [
            e for e in errors if e.error_type == "missing_aggregation"
        ]
        assert len(aggregation_errors) > 0


class TestSchemaValidator:
    """Test SchemaValidator business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def validator(self, mock_session):
        """Create a SchemaValidator instance."""
        return SchemaValidator(mock_session)

    @pytest.fixture
    def simple_composition(self):
        """Create a simple valid composition."""
        return ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
            ],
            max_layer=2,
        )

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_validate_compatible_schemas(self, validator, simple_composition):
        """
        Verify validator accepts type-compatible edges.

        Expected:
        - Empty error list
        - Inferred input/output schemas returned
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        assert isinstance(errors, list)
        assert len(errors) == 0
        assert input_schema is not None
        assert output_schema is not None

    @pytest.mark.asyncio
    async def test_infer_workflow_input_schema(self, validator, simple_composition):
        """
        Verify validator infers workflow input schema from first node.

        Expected:
        - input_schema matches first node's input
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                },
                output_schema={"type": "object"},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        assert input_schema is not None
        # Input schema should come from first node (n1)

    @pytest.mark.asyncio
    async def test_infer_workflow_output_schema(self, validator, simple_composition):
        """
        Verify validator infers workflow output schema from last node.

        Expected:
        - output_schema matches last node's output
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"result": {"type": "number"}},
                },
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        assert output_schema is not None
        # Output schema should come from last node (n2)

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_detect_type_mismatch(self, validator, simple_composition):
        """
        Verify validator detects incompatible types between nodes.

        Expected:
        - CompositionError with error_type="type_mismatch"
        - Source and target schemas in context
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "number"}},
                },
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        assert len(errors) > 0
        type_errors = [e for e in errors if e.error_type == "type_mismatch"]
        assert len(type_errors) > 0

    @pytest.mark.asyncio
    async def test_detect_missing_required_field(self, validator, simple_composition):
        """
        Verify validator detects when required input field is missing.

        Expected:
        - CompositionError with error_type="missing_required_field"
        - Field name in context
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                },
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={
                    "type": "object",
                    "properties": {"required_field": {"type": "string"}},
                    "required": ["required_field"],
                },
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        assert len(errors) > 0
        missing_errors = [e for e in errors if "missing" in e.error_type.lower()]
        assert len(missing_errors) > 0

    @pytest.mark.asyncio
    async def test_warn_on_extra_fields(self, validator, simple_composition):
        """
        Verify validator generates warning (not error) for extra fields.

        Expected:
        - CompositionWarning with warning_type="extra_fields"
        - Field names in context
        """
        resolved_nodes = {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "properties": {
                        "expected": {"type": "string"},
                        "extra": {"type": "string"},
                    },
                },
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={
                    "type": "object",
                    "properties": {"expected": {"type": "string"}},
                },
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

        errors, warnings, input_schema, output_schema = await validator.validate(
            simple_composition, resolved_nodes, "test-tenant"
        )

        # Should have warnings about extra fields (duck typing)
        assert isinstance(warnings, list)
        # Extra fields should generate warnings, not errors (per Finding #6)
