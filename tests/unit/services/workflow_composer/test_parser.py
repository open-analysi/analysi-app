"""Unit tests for CompositionParser."""

import pytest

from analysi.services.workflow_composer.models import ParsedComposition
from analysi.services.workflow_composer.parser import CompositionParser


class TestCompositionParser:
    """Test CompositionParser business logic."""

    @pytest.fixture
    def parser(self):
        """Create a CompositionParser instance."""
        return CompositionParser()

    # ============================================================================
    # Positive Tests
    # ============================================================================

    def test_parse_simple_sequential(self, parser):
        """
        Verify parser handles simple sequential composition ["task1", "task2", "task3"].

        Expected:
        - 3 nodes with sequential layers (1, 2, 3)
        - 2 edges connecting them sequentially
        - All parallel_group = None
        """
        composition = ["task1", "task2", "task3"]

        result = parser.parse(composition)

        assert isinstance(result, ParsedComposition)
        assert len(result.nodes) == 3
        assert len(result.edges) == 2
        assert result.max_layer == 3

        # Check nodes
        assert result.nodes[0].reference == "task1"
        assert result.nodes[0].layer == 1
        assert result.nodes[0].parallel_group is None

        assert result.nodes[1].reference == "task2"
        assert result.nodes[1].layer == 2
        assert result.nodes[1].parallel_group is None

        assert result.nodes[2].reference == "task3"
        assert result.nodes[2].layer == 3
        assert result.nodes[2].parallel_group is None

        # Check edges
        assert result.edges[0].from_node_id == result.nodes[0].node_id
        assert result.edges[0].to_node_id == result.nodes[1].node_id

        assert result.edges[1].from_node_id == result.nodes[1].node_id
        assert result.edges[1].to_node_id == result.nodes[2].node_id

    def test_parse_parallel_composition(self, parser):
        """
        Verify parser handles parallel execution ["task1", ["task2", "task3"], "task4"].

        Expected:
        - 4 nodes total
        - task1 at layer 1, task2/task3 at layer 2 (same layer, different parallel_group), task4 at layer 3
        - Edges: task1→task2, task1→task3, task2→task4, task3→task4
        """
        composition = ["task1", ["task2", "task3"], "task4"]

        result = parser.parse(composition)

        assert isinstance(result, ParsedComposition)
        assert len(result.nodes) == 4
        assert len(result.edges) == 4
        assert result.max_layer == 3

        # Check task1 (layer 1, sequential)
        task1_node = next(n for n in result.nodes if n.reference == "task1")
        assert task1_node.layer == 1
        assert task1_node.parallel_group is None

        # Check task2 and task3 (layer 2, parallel)
        task2_node = next(n for n in result.nodes if n.reference == "task2")
        task3_node = next(n for n in result.nodes if n.reference == "task3")
        assert task2_node.layer == 2
        assert task3_node.layer == 2
        assert task2_node.parallel_group is not None
        assert task3_node.parallel_group is not None
        assert task2_node.parallel_group == task3_node.parallel_group

        # Check task4 (layer 3, sequential)
        task4_node = next(n for n in result.nodes if n.reference == "task4")
        assert task4_node.layer == 3
        assert task4_node.parallel_group is None

        # Check edges: task1 → task2, task1 → task3, task2 → task4, task3 → task4
        edge_pairs = [(e.from_node_id, e.to_node_id) for e in result.edges]
        assert (task1_node.node_id, task2_node.node_id) in edge_pairs
        assert (task1_node.node_id, task3_node.node_id) in edge_pairs
        assert (task2_node.node_id, task4_node.node_id) in edge_pairs
        assert (task3_node.node_id, task4_node.node_id) in edge_pairs

    def test_parse_template_shortcuts(self, parser):
        """
        Verify parser handles lowercase shortcuts like "identity", "merge", "collect".

        Expected:
        - Shortcuts treated as references like cy_names
        - Proper node generation
        """
        composition = ["identity", "task1", "merge"]

        result = parser.parse(composition)

        assert isinstance(result, ParsedComposition)
        assert len(result.nodes) == 3

        assert result.nodes[0].reference == "identity"
        assert result.nodes[1].reference == "task1"
        assert result.nodes[2].reference == "merge"

    def test_parse_complex_nested(self, parser):
        """
        Verify parser handles 2-level nesting ["t1", [["t2", "t3"], "t4"], "merge", "t5"].

        Expected:
        - Correct layer assignment
        - Proper parallel_group tracking
        - Valid edge generation
        """
        composition = ["t1", [["t2", "t3"], "t4"], "merge", "t5"]

        result = parser.parse(composition)

        assert isinstance(result, ParsedComposition)
        assert len(result.nodes) == 6  # t1, t2, t3, t4, merge, t5

        # t1 should be layer 1
        t1_node = next(n for n in result.nodes if n.reference == "t1")
        assert t1_node.layer == 1

        # t2, t3, t4 should be layer 2
        t2_node = next(n for n in result.nodes if n.reference == "t2")
        t3_node = next(n for n in result.nodes if n.reference == "t3")
        t4_node = next(n for n in result.nodes if n.reference == "t4")
        assert t2_node.layer == 2
        assert t3_node.layer == 2
        assert t4_node.layer == 2

        # merge and t5 should be later layers
        merge_node = next(n for n in result.nodes if n.reference == "merge")
        t5_node = next(n for n in result.nodes if n.reference == "t5")
        assert merge_node.layer > 2
        assert t5_node.layer > merge_node.layer

    def test_generate_node_ids(self, parser):
        """
        Verify auto-generated node IDs follow pattern n1, n2, n3...

        Expected:
        - Sequential numbering
        - Unique IDs
        """
        composition = ["task1", "task2", "task3"]

        result = parser.parse(composition)

        node_ids = [n.node_id for n in result.nodes]
        assert len(node_ids) == len(set(node_ids))  # All unique

        # Should follow pattern like "n1", "n2", "n3"
        for node_id in node_ids:
            assert node_id.startswith("n")
            assert node_id[1:].isdigit()

    def test_generate_edge_ids(self, parser):
        """
        Verify auto-generated edge IDs follow pattern e1, e2, e3...

        Expected:
        - Sequential numbering
        - Unique IDs
        """
        composition = ["task1", "task2", "task3"]

        result = parser.parse(composition)

        edge_ids = [e.edge_id for e in result.edges]
        assert len(edge_ids) == len(set(edge_ids))  # All unique

        # Should follow pattern like "e1", "e2"
        for edge_id in edge_ids:
            assert edge_id.startswith("e")
            assert edge_id[1:].isdigit()

    # ============================================================================
    # Negative Tests
    # ============================================================================

    def test_parse_empty_composition(self, parser):
        """
        Verify parser rejects empty array [].

        Expected:
        - ValueError with message about empty composition
        """
        composition = []

        with pytest.raises(ValueError, match="empty"):
            parser.parse(composition)

    def test_parse_excessive_nesting(self, parser):
        """
        Verify parser rejects nesting deeper than 2 levels ["t1", [[["t2"]]]].

        Expected:
        - ValueError with message about max nesting depth exceeded
        """
        composition = ["t1", [[["t2"]]]]

        with pytest.raises(ValueError, match="nesting|depth"):
            parser.parse(composition)

    def test_parse_invalid_reference_type(self, parser):
        """
        Verify parser rejects non-string references like [123, "task1"].

        Expected:
        - ValueError with message about invalid reference type
        """
        composition = [123, "task1"]

        with pytest.raises(ValueError, match="string|type"):
            parser.parse(composition)

    def test_parse_empty_parallel_block(self, parser):
        """
        Verify parser rejects empty parallel blocks ["t1", [], "t2"].

        Expected:
        - ValueError with message about empty parallel block
        """
        composition = ["t1", [], "t2"]

        with pytest.raises(ValueError, match="empty"):
            parser.parse(composition)
