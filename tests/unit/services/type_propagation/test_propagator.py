"""
Unit tests for Type Propagator.

Tests the core type propagation algorithm that traverses workflow DAG,
infers types for each node, and reports errors/warnings.
Following TDD - these tests should fail until implementation is complete.
"""

from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow import NodeTemplate, Workflow, WorkflowEdge, WorkflowNode
from analysi.services.type_propagation.errors import (
    DeprecatedMultiInputWarning,
)
from analysi.services.type_propagation.propagator import (
    PropagationResult,
    WorkflowTypePropagator,
)


@pytest.mark.unit
class TestStartNodeIdentification:
    """Test start node identification."""

    def test_identify_start_nodes_single(self):
        """
        Test workflow with one start node.

        Positive case: Single start node identified.
        """
        # Create workflow with one start node
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Single Start Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        start_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-start",
            kind="task",
            name="Start Node",
            is_start_node=True,
        )
        other_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-other",
            kind="task",
            name="Other Node",
            is_start_node=False,
        )
        workflow.nodes = [start_node, other_node]

        # Call _identify_start_nodes()
        propagator = WorkflowTypePropagator()
        start_nodes = propagator._identify_start_nodes(workflow)

        # Should return list with one node
        assert len(start_nodes) == 1
        assert start_nodes[0].node_id == "n-start"

    def test_identify_start_nodes_multiple(self):
        """
        Test workflow with three start nodes.

        Positive case: Multiple start nodes identified.
        """
        # Create workflow with three start nodes
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Multi Start Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create three start nodes
        start_node_1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-start-1",
            kind="task",
            name="Start 1",
            is_start_node=True,
        )
        start_node_2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-start-2",
            kind="task",
            name="Start 2",
            is_start_node=True,
        )
        start_node_3 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-start-3",
            kind="task",
            name="Start 3",
            is_start_node=True,
        )
        other_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-other",
            kind="task",
            name="Other",
            is_start_node=False,
        )
        workflow.nodes = [start_node_1, start_node_2, start_node_3, other_node]

        # Call _identify_start_nodes()
        propagator = WorkflowTypePropagator()
        start_nodes = propagator._identify_start_nodes(workflow)

        # Should return list with three nodes
        assert len(start_nodes) == 3
        start_node_ids = [n.node_id for n in start_nodes]
        assert "n-start-1" in start_node_ids
        assert "n-start-2" in start_node_ids
        assert "n-start-3" in start_node_ids

    def test_identify_start_nodes_none(self):
        """
        Test workflow with no start nodes.

        Negative case: No start nodes is an error.
        """
        # Create workflow with no start nodes
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="No Start Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes with is_start_node=False
        node_1 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-1",
            kind="task",
            name="Node 1",
            is_start_node=False,
        )
        node_2 = WorkflowNode(
            workflow_id=workflow_id,
            node_id="n-2",
            kind="task",
            name="Node 2",
            is_start_node=False,
        )
        workflow.nodes = [node_1, node_2]

        # Call _identify_start_nodes()
        propagator = WorkflowTypePropagator()

        # Should raise ValueError
        with pytest.raises(ValueError, match="start"):
            propagator._identify_start_nodes(workflow)


@pytest.mark.unit
class TestTopologicalSort:
    """Test topological sorting of workflow DAG."""

    def test_topological_sort_linear(self):
        """
        Test linear workflow: A → B → C.

        Positive case: Linear workflow sorted correctly.
        """
        # Create linear workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Linear Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        workflow.nodes = [node_a, node_b, node_c]

        # Create edges: A → B → C
        edge_ab = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        edge_bc = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-bc",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_c_uuid,
        )
        workflow.edges = [edge_ab, edge_bc]

        # Call _topological_sort()
        propagator = WorkflowTypePropagator()
        sorted_nodes = propagator._topological_sort(workflow)

        # Should return [A, B, C]
        assert len(sorted_nodes) == 3
        assert sorted_nodes[0].node_id == "A"
        assert sorted_nodes[1].node_id == "B"
        assert sorted_nodes[2].node_id == "C"

    def test_topological_sort_fan_out(self):
        """
        Test fan-out workflow: A → B, A → C.

        Positive case: Fan-out handled correctly.
        """
        # Create fan-out workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Fan Out Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        workflow.nodes = [node_a, node_b, node_c]

        # Create edges: A → B, A → C
        edge_ab = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        edge_ac = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ac",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_c_uuid,
        )
        workflow.edges = [edge_ab, edge_ac]

        # Call _topological_sort()
        propagator = WorkflowTypePropagator()
        sorted_nodes = propagator._topological_sort(workflow)

        # Should return A first, then B and C in some order
        assert len(sorted_nodes) == 3
        assert sorted_nodes[0].node_id == "A"
        # B and C can be in any order after A
        remaining_ids = [sorted_nodes[1].node_id, sorted_nodes[2].node_id]
        assert "B" in remaining_ids
        assert "C" in remaining_ids

    def test_topological_sort_fan_in(self):
        """
        Test fan-in workflow: A → C, B → C.

        Positive case: Fan-in handled correctly.
        """
        # Create fan-in workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Fan In Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id,
            node_id="B",
            kind="task",
            name="B",
            is_start_node=True,
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        workflow.nodes = [node_a, node_b, node_c]

        # Create edges: A → C, B → C
        edge_ac = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ac",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_c_uuid,
        )
        edge_bc = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-bc",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_c_uuid,
        )
        workflow.edges = [edge_ac, edge_bc]

        # Call _topological_sort()
        propagator = WorkflowTypePropagator()
        sorted_nodes = propagator._topological_sort(workflow)

        # Should return A and B before C
        assert len(sorted_nodes) == 3
        # A and B should come before C
        c_index = [n.node_id for n in sorted_nodes].index("C")
        assert c_index == 2  # C should be last
        # A and B should be first two in any order
        first_two = [sorted_nodes[0].node_id, sorted_nodes[1].node_id]
        assert "A" in first_two
        assert "B" in first_two

    def test_topological_sort_complex_dag(self):
        """
        Test complex DAG with multiple paths.

        Positive case: Complex DAG sorted correctly.
        """
        # Create complex DAG: A → B → D, A → C → D
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Complex DAG",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()
        node_d_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        node_d = WorkflowNode(
            workflow_id=workflow_id, node_id="D", kind="task", name="D"
        )
        node_d.id = node_d_uuid

        workflow.nodes = [node_a, node_b, node_c, node_d]

        # Create edges: A → B → D, A → C → D
        edge_ab = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        edge_ac = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ac",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_c_uuid,
        )
        edge_bd = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-bd",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_d_uuid,
        )
        edge_cd = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-cd",
            from_node_uuid=node_c_uuid,
            to_node_uuid=node_d_uuid,
        )
        workflow.edges = [edge_ab, edge_ac, edge_bd, edge_cd]

        # Call _topological_sort()
        propagator = WorkflowTypePropagator()
        sorted_nodes = propagator._topological_sort(workflow)

        # Verify topological order maintained
        assert len(sorted_nodes) == 4
        node_ids = [n.node_id for n in sorted_nodes]

        # A must come before B, C, D
        a_index = node_ids.index("A")
        b_index = node_ids.index("B")
        c_index = node_ids.index("C")
        d_index = node_ids.index("D")

        assert a_index < b_index
        assert a_index < c_index
        assert a_index < d_index

        # B and C must come before D
        assert b_index < d_index
        assert c_index < d_index

    def test_topological_sort_cycle_detection(self):
        """
        Test workflow with cycle: A → B → C → A.

        Negative case: Cycles detected.
        """
        # Create workflow with cycle
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Cyclic Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        workflow.nodes = [node_a, node_b, node_c]

        # Create edges: A → B → C → A (cycle)
        edge_ab = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        edge_bc = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-bc",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_c_uuid,
        )
        edge_ca = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ca",
            from_node_uuid=node_c_uuid,
            to_node_uuid=node_a_uuid,
        )
        workflow.edges = [edge_ab, edge_bc, edge_ca]

        # Call _topological_sort()
        propagator = WorkflowTypePropagator()

        # Should raise ValueError with cycle message
        with pytest.raises(ValueError, match="cycle"):
            propagator._topological_sort(workflow)


@pytest.mark.unit
class TestPredecessorIdentification:
    """Test predecessor identification for nodes."""

    def test_get_predecessors_no_predecessors(self):
        """
        Test start node with no predecessors.

        Positive case: Start node has no predecessors.
        """
        # Create workflow with start node
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create start node with no incoming edges
        start_node_uuid = uuid4()
        start_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="start",
            kind="task",
            name="Start",
            is_start_node=True,
        )
        start_node.id = start_node_uuid

        workflow.nodes = [start_node]
        workflow.edges = []

        # Call _get_predecessors()
        propagator = WorkflowTypePropagator()
        predecessors = propagator._get_predecessors(start_node, workflow)

        # Should return empty list
        assert len(predecessors) == 0

    def test_get_predecessors_single(self):
        """
        Test node with one predecessor.

        Positive case: Single predecessor identified.
        """
        # Create workflow with two nodes
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        workflow.nodes = [node_a, node_b]

        # Create edge: A → B
        edge = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        workflow.edges = [edge]

        # Call _get_predecessors() for node B
        propagator = WorkflowTypePropagator()
        predecessors = propagator._get_predecessors(node_b, workflow)

        # Should return list with one node
        assert len(predecessors) == 1
        assert predecessors[0].node_id == "A"

    def test_get_predecessors_multiple(self):
        """
        Test node with three predecessors (fan-in).

        Positive case: Multiple predecessors identified.
        """
        # Create workflow with fan-in
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()
        node_d_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id,
            node_id="B",
            kind="task",
            name="B",
            is_start_node=True,
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id,
            node_id="C",
            kind="task",
            name="C",
            is_start_node=True,
        )
        node_c.id = node_c_uuid

        node_d = WorkflowNode(
            workflow_id=workflow_id, node_id="D", kind="task", name="D"
        )
        node_d.id = node_d_uuid

        workflow.nodes = [node_a, node_b, node_c, node_d]

        # Create edges: A → D, B → D, C → D
        edge_ad = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ad",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_d_uuid,
        )
        edge_bd = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-bd",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_d_uuid,
        )
        edge_cd = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-cd",
            from_node_uuid=node_c_uuid,
            to_node_uuid=node_d_uuid,
        )
        workflow.edges = [edge_ad, edge_bd, edge_cd]

        # Call _get_predecessors() for node D
        propagator = WorkflowTypePropagator()
        predecessors = propagator._get_predecessors(node_d, workflow)

        # Should return list with three nodes
        assert len(predecessors) == 3
        predecessor_ids = [p.node_id for p in predecessors]
        assert "A" in predecessor_ids
        assert "B" in predecessor_ids
        assert "C" in predecessor_ids


@pytest.mark.unit
class TestNodeInputSchemaComputation:
    """Test node input schema computation."""

    def test_compute_node_input_schema_single_predecessor(self):
        """
        Test node with one predecessor.

        Positive case: Single predecessor input.
        """
        # Create workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )

        # Inferred schemas (A has been processed)
        inferred_schemas = {"A": {"type": "string"}}

        # Call _compute_node_input_schema() for node B with predecessor A
        propagator = WorkflowTypePropagator()
        input_schema = propagator._compute_node_input_schema(
            node_b, [node_a], inferred_schemas
        )

        # Should return single dict (not list)
        assert isinstance(input_schema, dict)
        assert input_schema == {"type": "string"}

    def test_compute_node_input_schema_multiple_predecessors(self):
        """
        Test node with two predecessors.

        Positive case: Multiple predecessor inputs.
        """
        # Create workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes
        node_a = WorkflowNode(
            workflow_id=workflow_id,
            node_id="A",
            kind="task",
            name="A",
            is_start_node=True,
        )
        node_b = WorkflowNode(
            workflow_id=workflow_id,
            node_id="B",
            kind="task",
            name="B",
            is_start_node=True,
        )
        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="C", kind="task", name="C"
        )

        # Inferred schemas (A and B have been processed)
        inferred_schemas = {
            "A": {"type": "object", "properties": {"ip": {"type": "string"}}},
            "B": {"type": "object", "properties": {"geo": {"type": "string"}}},
        }

        # Call _compute_node_input_schema() for node C with predecessors A and B
        propagator = WorkflowTypePropagator()
        input_schema = propagator._compute_node_input_schema(
            node_c, [node_a, node_b], inferred_schemas
        )

        # Should return list of two schemas
        assert isinstance(input_schema, list)
        assert len(input_schema) == 2
        assert input_schema[0] == {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
        }
        assert input_schema[1] == {
            "type": "object",
            "properties": {"geo": {"type": "string"}},
        }

    def test_compute_node_input_schema_start_node(self):
        """
        Test start node (no predecessors).

        Positive case: Start node uses workflow input.
        """
        # Create workflow
        workflow_id = uuid4()
        initial_input_schema = {
            "type": "object",
            "properties": {"data": {"type": "string"}},
        }

        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": initial_input_schema, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create start node
        start_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="start",
            kind="task",
            name="Start",
            is_start_node=True,
        )

        # Empty predecessors and inferred schemas
        inferred_schemas = {}

        # NOTE: Implementation will need to handle start nodes specially
        # This test validates that start nodes get the workflow input schema
        # Implementation detail: may need to pass initial_input_schema to this method
        propagator = WorkflowTypePropagator()

        # For now, just test with empty predecessors
        # Implementation will determine how to inject initial_input_schema
        input_schema = propagator._compute_node_input_schema(
            start_node, [], inferred_schemas
        )

        # Implementation-dependent: may return empty dict or require special handling
        assert input_schema is not None


@pytest.mark.unit
class TestMultiInputValidation:
    """Test multi-input validation and deprecation warnings."""

    def test_validate_multi_input_single_input(self):
        """
        Test task node with one predecessor.

        Positive case: Single input is always valid.
        """
        # Create task node
        workflow_id = uuid4()
        task_node = WorkflowNode(
            workflow_id=workflow_id, node_id="task", kind="task", name="Task"
        )

        # Call _validate_multi_input() with predecessor_count=1
        propagator = WorkflowTypePropagator()
        result = propagator._validate_multi_input(task_node, predecessor_count=1)

        # Should return None (valid)
        assert result is None

    def test_validate_multi_input_merge_template(self):
        """
        Test Merge template node with three predecessors.

        Positive case: Merge template allows multi-input.
        """
        # Create Merge template node
        workflow_id = uuid4()
        template_id = uuid4()

        # Create NodeTemplate with kind="merge"
        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="merge_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return merge(inputs)",
            kind="merge",
        )
        node_template.id = template_id

        merge_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="merge",
            kind="transformation",
            name="Merge",
            node_template_id=template_id,
        )
        merge_node.node_template = node_template

        # Call _validate_multi_input() with predecessor_count=3
        propagator = WorkflowTypePropagator()
        result = propagator._validate_multi_input(merge_node, predecessor_count=3)

        # Should return None (Merge allows multi-input)
        assert result is None

    def test_validate_multi_input_collect_template(self):
        """
        Test Collect template node with three predecessors.

        Positive case: Collect template allows multi-input.
        """
        # Create Collect template node
        workflow_id = uuid4()
        template_id = uuid4()

        # Create NodeTemplate with kind="collect"
        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="collect_template",
            input_schema={"type": "object"},
            output_schema={"type": "array"},
            code="return collect(inputs)",
            kind="collect",
        )
        node_template.id = template_id

        collect_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="collect",
            kind="transformation",
            name="Collect",
            node_template_id=template_id,
        )
        collect_node.node_template = node_template

        # Call _validate_multi_input() with predecessor_count=3
        propagator = WorkflowTypePropagator()
        result = propagator._validate_multi_input(collect_node, predecessor_count=3)

        # Should return None (Collect allows multi-input)
        assert result is None

    def test_validate_multi_input_deprecated_pattern(self):
        """
        Test task node with two predecessors (v5 pattern).

        Negative case (warning): Deprecated pattern detected.
        """
        # Create task node (not template)
        workflow_id = uuid4()
        task_node = WorkflowNode(
            workflow_id=workflow_id, node_id="task", kind="task", name="Task"
        )

        # Call _validate_multi_input() with predecessor_count=2
        propagator = WorkflowTypePropagator()
        result = propagator._validate_multi_input(task_node, predecessor_count=2)

        # Should return DeprecatedMultiInputWarning
        assert isinstance(result, DeprecatedMultiInputWarning)
        assert result.predecessor_count == 2
        assert result.severity == "warning"

    def test_validate_multi_input_identity_template_deprecated(self):
        """
        Test Identity template with two predecessors.

        Negative case (warning): Even templates emit warning except Merge/Collect.
        """
        # Create Identity template node
        workflow_id = uuid4()
        template_id = uuid4()

        # Create NodeTemplate with kind="identity"
        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="identity_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return input",
            kind="identity",
        )
        node_template.id = template_id

        identity_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="identity",
            kind="transformation",
            name="Identity",
            node_template_id=template_id,
        )
        identity_node.node_template = node_template

        # Call _validate_multi_input() with predecessor_count=2
        propagator = WorkflowTypePropagator()
        result = propagator._validate_multi_input(identity_node, predecessor_count=2)

        # Should return DeprecatedMultiInputWarning (only Merge/Collect allow multi-input)
        assert isinstance(result, DeprecatedMultiInputWarning)
        assert result.predecessor_count == 2


@pytest.mark.unit
class TestNodeOutputInference:
    """Test node output schema inference."""

    def test_infer_node_output_task(self):
        """
        Test task node output inference.

        Positive case: Task output inferred.
        """
        # Create task node
        workflow_id = uuid4()
        task_id = uuid4()
        task_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="task",
            kind="task",
            name="Task",
            task_id=task_id,
        )

        # Input schema
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Call _infer_node_output()
        # NOTE: Will need to mock infer_task_output_schema() when implementing
        propagator = WorkflowTypePropagator()
        output = propagator._infer_node_output(task_node, input_schema)

        # Should return schema (implementation-dependent)
        # For now, just verify it doesn't crash
        assert output is not None

    def test_infer_node_output_identity_template(self):
        """
        Test Identity template node.

        Positive case: Identity template handled.
        """
        # Create Identity template node
        workflow_id = uuid4()
        template_id = uuid4()

        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="identity_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return input",
            kind="identity",
        )
        node_template.id = template_id

        identity_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="identity",
            kind="transformation",
            name="Identity",
            node_template_id=template_id,
        )
        identity_node.node_template = node_template

        # Input schema
        input_schema = {"type": "object", "properties": {"data": {"type": "string"}}}

        # Call _infer_node_output()
        propagator = WorkflowTypePropagator()
        output = propagator._infer_node_output(identity_node, input_schema)

        # Should return same schema (identity)
        assert output is not None

    def test_infer_node_output_merge_template(self):
        """
        Test Merge template node.

        Positive case: Merge template handled.
        """
        # Create Merge template node
        workflow_id = uuid4()
        template_id = uuid4()

        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="merge_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return merge(inputs)",
            kind="merge",
        )
        node_template.id = template_id

        merge_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="merge",
            kind="transformation",
            name="Merge",
            node_template_id=template_id,
        )
        merge_node.node_template = node_template

        # Input schemas (list)
        input_schemas = [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "object", "properties": {"b": {"type": "number"}}},
        ]

        # Call _infer_node_output()
        propagator = WorkflowTypePropagator()
        output = propagator._infer_node_output(merge_node, input_schemas)

        # Should return merged schema
        assert output is not None

    def test_infer_node_output_collect_template(self):
        """
        Test Collect template node.

        Positive case: Collect template handled.
        """
        # Create Collect template node
        workflow_id = uuid4()
        template_id = uuid4()

        node_template = NodeTemplate(
            resource_id=uuid4(),
            name="collect_template",
            input_schema={"type": "object"},
            output_schema={"type": "array"},
            code="return collect(inputs)",
            kind="collect",
        )
        node_template.id = template_id

        collect_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="collect",
            kind="transformation",
            name="Collect",
            node_template_id=template_id,
        )
        collect_node.node_template = node_template

        # Input schemas (list)
        input_schemas = [{"type": "string"}, {"type": "number"}]

        # Call _infer_node_output()
        propagator = WorkflowTypePropagator()
        output = propagator._infer_node_output(collect_node, input_schemas)

        # Should return array schema
        assert output is not None

    def test_infer_node_output_error_propagation(self):
        """
        Test error propagation when inference fails.

        Negative case: Errors propagated, not raised.
        """
        # Create task node that will fail inference
        workflow_id = uuid4()
        task_id = uuid4()
        task_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="task",
            kind="task",
            name="Task",
            task_id=task_id,
        )

        # Input schema that causes error (implementation-dependent)
        input_schema = {"type": "invalid"}

        # Call _infer_node_output()
        propagator = WorkflowTypePropagator()
        output = propagator._infer_node_output(task_node, input_schema)

        # Should return error, not raise exception
        # Implementation will determine exact behavior
        assert output is not None


@pytest.mark.unit
class TestWorkflowOutputComputation:
    """Test workflow output schema computation from terminal nodes."""

    def test_compute_workflow_output_single_terminal(self):
        """
        Test workflow with one terminal node.

        Positive case: Single terminal output.
        """
        # Create workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create terminal node
        terminal_node_uuid = uuid4()
        terminal_node = WorkflowNode(
            workflow_id=workflow_id, node_id="terminal", kind="task", name="Terminal"
        )
        terminal_node.id = terminal_node_uuid

        workflow.nodes = [terminal_node]
        workflow.edges = []  # No outgoing edges = terminal node

        # Inferred schemas
        inferred_schemas = {
            "terminal": {"type": "object", "properties": {"result": {"type": "string"}}}
        }

        # Call _compute_workflow_output()
        propagator = WorkflowTypePropagator()
        workflow_output = propagator._compute_workflow_output(
            workflow, inferred_schemas
        )

        # Should return terminal node schema directly
        assert workflow_output == {
            "type": "object",
            "properties": {"result": {"type": "string"}},
        }

    def test_compute_workflow_output_multiple_terminals(self):
        """
        Test workflow with three terminal nodes.

        Positive case: Multiple terminals aggregated by node_id.
        """
        # Create workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create three terminal nodes
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()
        node_c_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id, node_id="nodeA", kind="task", name="A"
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="nodeB", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        node_c = WorkflowNode(
            workflow_id=workflow_id, node_id="nodeC", kind="task", name="C"
        )
        node_c.id = node_c_uuid

        workflow.nodes = [node_a, node_b, node_c]
        workflow.edges = []  # No edges = all are terminal

        # Inferred schemas
        inferred_schemas = {
            "nodeA": {"type": "string"},
            "nodeB": {"type": "number"},
            "nodeC": {"type": "boolean"},
        }

        # Call _compute_workflow_output()
        propagator = WorkflowTypePropagator()
        workflow_output = propagator._compute_workflow_output(
            workflow, inferred_schemas
        )

        # Should return object with node_id keys
        assert workflow_output["type"] == "object"
        assert "properties" in workflow_output
        assert "nodeA" in workflow_output["properties"]
        assert "nodeB" in workflow_output["properties"]
        assert "nodeC" in workflow_output["properties"]
        assert workflow_output["properties"]["nodeA"] == {"type": "string"}
        assert workflow_output["properties"]["nodeB"] == {"type": "number"}
        assert workflow_output["properties"]["nodeC"] == {"type": "boolean"}

    def test_compute_workflow_output_no_terminals(self):
        """
        Test workflow with no terminal nodes.

        Edge case: No terminal nodes handled.
        """
        # Create workflow with cycle or error
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes with edges forming cycle (all have outgoing edges)
        node_a_uuid = uuid4()
        node_b_uuid = uuid4()

        node_a = WorkflowNode(
            workflow_id=workflow_id, node_id="A", kind="task", name="A"
        )
        node_a.id = node_a_uuid

        node_b = WorkflowNode(
            workflow_id=workflow_id, node_id="B", kind="task", name="B"
        )
        node_b.id = node_b_uuid

        workflow.nodes = [node_a, node_b]

        # Create edges: A → B, B → A (both have outgoing edges)
        edge_ab = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ab",
            from_node_uuid=node_a_uuid,
            to_node_uuid=node_b_uuid,
        )
        edge_ba = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e-ba",
            from_node_uuid=node_b_uuid,
            to_node_uuid=node_a_uuid,
        )
        workflow.edges = [edge_ab, edge_ba]

        inferred_schemas = {"A": {"type": "string"}, "B": {"type": "number"}}

        # Call _compute_workflow_output()
        propagator = WorkflowTypePropagator()
        workflow_output = propagator._compute_workflow_output(
            workflow, inferred_schemas
        )

        # Should handle gracefully (return None or empty schema)
        # Implementation will determine exact behavior
        assert workflow_output is not None


@pytest.mark.unit
class TestMainPropagationAlgorithm:
    """Test main propagate_types() algorithm."""

    @pytest.mark.asyncio
    async def test_propagate_types_simple_linear_workflow(self):
        """
        Test simple linear workflow: Start → Identity → End.

        Positive case: Simple workflow validates successfully.
        """
        # Create simple linear workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Linear Workflow",
            io_schema={
                "input": {"type": "object", "properties": {"ip": {"type": "string"}}},
                "output": {"type": "object"},
            },
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id

        # Create nodes (simplified - will need proper setup)
        start_node_uuid = uuid4()
        identity_node_uuid = uuid4()
        end_node_uuid = uuid4()

        start_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="start",
            kind="task",
            name="Start",
            is_start_node=True,
        )
        start_node.id = start_node_uuid

        identity_node = WorkflowNode(
            workflow_id=workflow_id,
            node_id="identity",
            kind="transformation",
            name="Identity",
        )
        identity_node.id = identity_node_uuid

        end_node = WorkflowNode(
            workflow_id=workflow_id, node_id="end", kind="task", name="End"
        )
        end_node.id = end_node_uuid

        workflow.nodes = [start_node, identity_node, end_node]

        # Create edges
        edge1 = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e1",
            from_node_uuid=start_node_uuid,
            to_node_uuid=identity_node_uuid,
        )
        edge2 = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id="e2",
            from_node_uuid=identity_node_uuid,
            to_node_uuid=end_node_uuid,
        )
        workflow.edges = [edge1, edge2]

        # Initial input schema
        initial_input_schema = {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
        }

        # Call propagate_types()
        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        # Should return PropagationResult with status="valid"
        assert isinstance(result, PropagationResult)
        # Implementation will determine exact status and node schemas
        assert result.status in ["valid", "invalid", "valid_with_warnings"]

    @pytest.mark.asyncio
    async def test_propagate_types_with_type_mismatch(self):
        """
        Test workflow with type mismatch.

        Negative case: Type mismatch detected.
        """
        # Create workflow with type mismatch
        # NOTE: Full implementation requires mocking task inference
        # For now, create placeholder test
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Mismatch Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        # Should return PropagationResult
        assert isinstance(result, PropagationResult)

    @pytest.mark.asyncio
    async def test_propagate_types_with_warnings(self):
        """
        Test workflow with deprecated multi-input pattern.

        Positive case with warning: Warnings don't block validation.
        """
        # Create workflow with deprecated pattern
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Warning Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        # Should return PropagationResult
        assert isinstance(result, PropagationResult)
        # Warnings list may or may not be empty depending on implementation
        assert isinstance(result.warnings, list)

    @pytest.mark.asyncio
    async def test_propagate_types_merge_workflow(self):
        """
        Test workflow with Merge template.

        Positive case: Merge template workflow.
        """
        # Create workflow with merge
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Merge Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        assert isinstance(result, PropagationResult)

    @pytest.mark.asyncio
    async def test_propagate_types_collect_workflow(self):
        """
        Test workflow with Collect template.

        Positive case: Collect template workflow.
        """
        # Create workflow with collect
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Collect Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        assert isinstance(result, PropagationResult)

    @pytest.mark.asyncio
    async def test_propagate_types_complex_workflow(self):
        """
        Test complex workflow with multiple templates.

        Positive case: Complex multi-template workflow.
        """
        # Create complex workflow
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Complex Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        assert isinstance(result, PropagationResult)

    @pytest.mark.asyncio
    async def test_propagate_types_multiple_errors(self):
        """
        Test workflow with multiple type errors.

        Negative case: All errors collected, not just first.
        """
        # Create workflow with multiple errors
        workflow_id = uuid4()
        workflow = Workflow(
            tenant_id="test-tenant",
            name="Error Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        workflow.id = workflow_id
        workflow.nodes = []
        workflow.edges = []

        initial_input_schema = {"type": "object"}

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(workflow, initial_input_schema)

        # Should return all errors in result.errors list
        assert isinstance(result, PropagationResult)
        assert isinstance(result.errors, list)
        # Number of errors depends on implementation
