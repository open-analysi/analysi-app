"""Unit tests for workflow composition reconstruction logic."""

from unittest.mock import Mock
from uuid import uuid4

from analysi.models.workflow import WorkflowNode


class TestBranchPointDetection:
    """Unit tests for _detect_branch_points function."""

    def test_detect_branch_points_with_single_branch(self):
        """Test detection of nodes with multiple outgoing edges."""
        from analysi.mcp.tools.workflow_tools import _detect_branch_points

        # Create mock nodes
        node1_uuid = uuid4()
        node2_uuid = uuid4()
        node3_uuid = uuid4()

        # Node 1 has 2 outgoing edges (branch point)
        edges_from = {
            node1_uuid: [node2_uuid, node3_uuid],  # Branch point!
            node2_uuid: [],
            node3_uuid: [],
        }

        uuid_to_node = {
            node1_uuid: Mock(spec=WorkflowNode, id=node1_uuid),
            node2_uuid: Mock(spec=WorkflowNode, id=node2_uuid),
            node3_uuid: Mock(spec=WorkflowNode, id=node3_uuid),
        }

        branch_points = _detect_branch_points(edges_from, uuid_to_node)

        assert node1_uuid in branch_points, (
            "Node with 2+ outgoing edges should be detected as branch point"
        )
        assert len(branch_points) == 1, (
            f"Expected 1 branch point, found {len(branch_points)}"
        )

    def test_detect_branch_points_with_no_branches(self):
        """Test that linear workflow has no branch points."""
        from analysi.mcp.tools.workflow_tools import _detect_branch_points

        node1_uuid = uuid4()
        node2_uuid = uuid4()
        node3_uuid = uuid4()

        # Linear: node1 → node2 → node3
        edges_from = {
            node1_uuid: [node2_uuid],
            node2_uuid: [node3_uuid],
            node3_uuid: [],
        }

        uuid_to_node = {
            node1_uuid: Mock(spec=WorkflowNode, id=node1_uuid),
            node2_uuid: Mock(spec=WorkflowNode, id=node2_uuid),
            node3_uuid: Mock(spec=WorkflowNode, id=node3_uuid),
        }

        branch_points = _detect_branch_points(edges_from, uuid_to_node)

        assert len(branch_points) == 0, "Linear workflow should have no branch points"

    def test_detect_branch_points_with_multiple_branches(self):
        """Test detection with multiple branch points."""
        from analysi.mcp.tools.workflow_tools import _detect_branch_points

        node1_uuid = uuid4()
        node2_uuid = uuid4()
        node3_uuid = uuid4()
        node4_uuid = uuid4()
        node5_uuid = uuid4()

        # Two branch points: node1 and node2
        edges_from = {
            node1_uuid: [node2_uuid, node3_uuid],  # Branch 1
            node2_uuid: [node4_uuid, node5_uuid],  # Branch 2
            node3_uuid: [],
            node4_uuid: [],
            node5_uuid: [],
        }

        uuid_to_node = {uid: Mock(spec=WorkflowNode, id=uid) for uid in edges_from}

        branch_points = _detect_branch_points(edges_from, uuid_to_node)

        assert len(branch_points) == 2
        assert node1_uuid in branch_points
        assert node2_uuid in branch_points


class TestMergePointDetection:
    """Unit tests for _detect_merge_points function."""

    def test_detect_merge_points_with_single_merge(self):
        """Test detection of nodes with multiple incoming edges."""
        from analysi.mcp.tools.workflow_tools import _detect_merge_points

        node1_uuid = uuid4()
        node2_uuid = uuid4()
        node3_uuid = uuid4()

        # Node 3 has 2 incoming edges (merge point)
        edges_to = {
            node1_uuid: [],
            node2_uuid: [],
            node3_uuid: [node1_uuid, node2_uuid],  # Merge point!
        }

        uuid_to_node = {uid: Mock(spec=WorkflowNode, id=uid) for uid in edges_to}

        merge_points = _detect_merge_points(edges_to, uuid_to_node)

        assert node3_uuid in merge_points, (
            "Node with 2+ incoming edges should be detected as merge point"
        )
        assert len(merge_points) == 1

    def test_detect_merge_points_with_no_merges(self):
        """Test that linear workflow has no merge points."""
        from analysi.mcp.tools.workflow_tools import _detect_merge_points

        node1_uuid = uuid4()
        node2_uuid = uuid4()
        node3_uuid = uuid4()

        # Linear: node1 → node2 → node3
        edges_to = {
            node1_uuid: [],
            node2_uuid: [node1_uuid],
            node3_uuid: [node2_uuid],
        }

        uuid_to_node = {uid: Mock(spec=WorkflowNode, id=uid) for uid in edges_to}

        merge_points = _detect_merge_points(edges_to, uuid_to_node)

        assert len(merge_points) == 0, "Linear workflow should have no merge points"


class TestParallelBranchGrouping:
    """Unit tests for _group_parallel_branches function."""

    def test_group_parallel_branches_simple_case(self):
        """Test grouping of simple parallel branches."""
        from analysi.mcp.tools.workflow_tools import _group_parallel_branches

        # Create simple parallel structure: A → [B, C] → D
        node_a = uuid4()
        node_b = uuid4()
        node_c = uuid4()
        node_d = uuid4()

        edges_from = {
            node_a: [node_b, node_c],  # Branch point
            node_b: [node_d],
            node_c: [node_d],
            node_d: [],
        }

        edges_to = {
            node_a: [],
            node_b: [node_a],
            node_c: [node_a],
            node_d: [node_b, node_c],  # Merge point
        }

        # Create mock nodes with identifiers
        uuid_to_node = {
            node_a: Mock(
                spec=WorkflowNode, id=node_a, kind="transformation", node_id="identity"
            ),
            node_b: Mock(
                spec=WorkflowNode,
                id=node_b,
                kind="task",
                task=Mock(component=Mock(cy_name="task_b")),
            ),
            node_c: Mock(
                spec=WorkflowNode,
                id=node_c,
                kind="task",
                task=Mock(component=Mock(cy_name="task_c")),
            ),
            node_d: Mock(
                spec=WorkflowNode, id=node_d, kind="transformation", node_id="merge"
            ),
        }

        branches = _group_parallel_branches(
            branch_point=node_a,
            merge_point=node_d,
            edges_from=edges_from,
            edges_to=edges_to,
            uuid_to_node=uuid_to_node,
        )

        # Should return 2 branches
        assert len(branches) == 2, f"Expected 2 parallel branches, got {len(branches)}"

        # Each branch should contain the task identifiers
        branch_identifiers = []
        for branch in branches:
            assert isinstance(branch, list), "Each branch should be a list"
            branch_identifiers.extend(branch)

        assert "task_b" in branch_identifiers or "task_c" in branch_identifiers

    def test_group_parallel_branches_with_sequential_nodes(self):
        """Test grouping when branches contain sequential nodes."""
        from analysi.mcp.tools.workflow_tools import _group_parallel_branches

        # Structure: A → [B → C, D] → E
        node_a = uuid4()
        node_b = uuid4()
        node_c = uuid4()
        node_d = uuid4()
        node_e = uuid4()

        edges_from = {
            node_a: [node_b, node_d],  # Branch
            node_b: [node_c],
            node_c: [node_e],
            node_d: [node_e],
            node_e: [],
        }

        edges_to = {
            node_a: [],
            node_b: [node_a],
            node_c: [node_b],
            node_d: [node_a],
            node_e: [node_c, node_d],  # Merge
        }

        uuid_to_node = {
            node_a: Mock(
                spec=WorkflowNode, id=node_a, kind="transformation", node_id="identity"
            ),
            node_b: Mock(
                spec=WorkflowNode,
                id=node_b,
                kind="task",
                task=Mock(component=Mock(cy_name="task_b")),
            ),
            node_c: Mock(
                spec=WorkflowNode,
                id=node_c,
                kind="task",
                task=Mock(component=Mock(cy_name="task_c")),
            ),
            node_d: Mock(
                spec=WorkflowNode,
                id=node_d,
                kind="task",
                task=Mock(component=Mock(cy_name="task_d")),
            ),
            node_e: Mock(
                spec=WorkflowNode, id=node_e, kind="transformation", node_id="merge"
            ),
        }

        branches = _group_parallel_branches(
            branch_point=node_a,
            merge_point=node_e,
            edges_from=edges_from,
            edges_to=edges_to,
            uuid_to_node=uuid_to_node,
        )

        # Should have 2 branches
        assert len(branches) == 2

        # One branch should have 2 tasks (B → C), other should have 1 (D)
        branch_lengths = [len(branch) for branch in branches]
        assert sorted(branch_lengths) == [1, 2], (
            f"Expected branches of length 1 and 2, got {branch_lengths}"
        )


class TestReconstructCompositionWithParallel:
    """Unit tests for complete reconstruction with parallel support."""

    def test_reconstruct_linear_workflow(self):
        """Test that linear workflows still work (regression)."""
        from analysi.mcp.tools.workflow_tools import (
            _reconstruct_composition_with_parallel,
        )

        # Create mock linear workflow
        workflow = Mock()

        node1 = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="transformation",
            node_id="identity",
            is_start_node=True,
            task=None,
        )

        node2 = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="task",
            node_id="n2",
            is_start_node=False,
            task=Mock(component=Mock(cy_name="task_a")),
        )

        node3 = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="task",
            node_id="n3",
            is_start_node=False,
            task=Mock(component=Mock(cy_name="task_b")),
        )

        workflow.nodes = [node1, node2, node3]

        # Linear edges: node1 → node2 → node3
        edge1 = Mock(from_node_uuid=node1.id, to_node_uuid=node2.id)
        edge2 = Mock(from_node_uuid=node2.id, to_node_uuid=node3.id)

        workflow.edges = [edge1, edge2]

        composition = _reconstruct_composition_with_parallel(workflow)

        # Should be flat array
        assert composition == ["identity", "task_a", "task_b"]
        assert all(isinstance(item, str) for item in composition), (
            "Linear workflow should have no nested arrays"
        )

    def test_reconstruct_parallel_workflow(self):
        """Test reconstruction of simple parallel workflow."""
        from analysi.mcp.tools.workflow_tools import (
            _reconstruct_composition_with_parallel,
        )

        workflow = Mock()

        # Structure: identity → [task_a, task_b] → merge
        node_start = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="transformation",
            node_id="identity",
            is_start_node=True,
            task=None,
        )

        node_a = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="task",
            node_id="na",
            is_start_node=False,
            task=Mock(component=Mock(cy_name="task_a")),
        )

        node_b = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="task",
            node_id="nb",
            is_start_node=False,
            task=Mock(component=Mock(cy_name="task_b")),
        )

        node_merge = Mock(
            spec=WorkflowNode,
            id=uuid4(),
            kind="transformation",
            node_id="merge",
            is_start_node=False,
            task=None,
        )

        workflow.nodes = [node_start, node_a, node_b, node_merge]

        # Edges: start → [a, b] → merge
        workflow.edges = [
            Mock(from_node_uuid=node_start.id, to_node_uuid=node_a.id),
            Mock(from_node_uuid=node_start.id, to_node_uuid=node_b.id),
            Mock(from_node_uuid=node_a.id, to_node_uuid=node_merge.id),
            Mock(from_node_uuid=node_b.id, to_node_uuid=node_merge.id),
        ]

        composition = _reconstruct_composition_with_parallel(workflow)

        # Should have nested array for parallel section
        assert len(composition) == 3, (
            f"Expected 3 elements, got {len(composition)}: {composition}"
        )
        assert composition[0] == "identity"
        assert composition[2] == "merge"

        # Middle element should be nested array
        parallel_section = composition[1]
        assert isinstance(parallel_section, list), (
            f"Expected nested array for parallel section, got {type(parallel_section)}: {parallel_section}"
        )
        assert set(parallel_section) == {"task_a", "task_b"}


class TestGetNodeIdentifier:
    """Unit tests for _get_node_identifier helper function."""

    def test_get_identifier_for_task_node(self):
        """Test identifier extraction for task nodes."""
        from analysi.mcp.tools.workflow_tools import _get_node_identifier

        node = Mock(
            spec=WorkflowNode,
            kind="task",
            node_id="n1",
            task=Mock(component=Mock(cy_name="my_task")),
        )

        identifier = _get_node_identifier(node)

        assert identifier == "my_task", (
            f"Expected cy_name 'my_task', got '{identifier}'"
        )

    def test_get_identifier_for_template_node(self):
        """Test identifier extraction for template nodes."""
        from analysi.mcp.tools.workflow_tools import _get_node_identifier

        node = Mock(
            spec=WorkflowNode,
            kind="transformation",
            node_id="identity",
            task=None,
        )

        identifier = _get_node_identifier(node)

        assert identifier == "identity", (
            f"Expected node_id 'identity', got '{identifier}'"
        )

    def test_get_identifier_for_node_without_task(self):
        """Test identifier when task is None."""
        from analysi.mcp.tools.workflow_tools import _get_node_identifier

        node = Mock(
            spec=WorkflowNode,
            kind="task",
            node_id="n2",
            task=None,
        )

        identifier = _get_node_identifier(node)

        # Should fall back to node_id
        assert identifier == "n2"
