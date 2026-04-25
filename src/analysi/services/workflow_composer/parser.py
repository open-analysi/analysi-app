"""
Composition Parser - Parse array-based composition format.

Handles sequential and parallel execution patterns:
- Sequential: ["task1", "task2", "task3"]
- Parallel: ["task1", ["task2", "task3"], "merge", "task4"]
"""

from typing import Any

from .models import ParsedComposition, ParsedEdge, ParsedNode


class CompositionParser:
    """Parse array-based composition into graph structure."""

    def parse(self, composition: list[Any]) -> ParsedComposition:
        """
        Parse composition array into ParsedComposition.

        Args:
            composition: Array of task cy_names, template shortcuts, or nested arrays

        Returns:
            ParsedComposition with nodes and edges

        Raises:
            ValueError: If composition format is invalid

        Examples:
            >>> parser = CompositionParser()
            >>> result = parser.parse(["task1", "task2"])
            >>> result.nodes  # [ParsedNode("n1", "task1", 1), ParsedNode("n2", "task2", 2)]
        """
        # Validate composition
        if not composition:
            raise ValueError("Composition cannot be empty")

        # Validate nesting depth
        self._validate_nesting(composition)

        # Parse nodes and edges
        nodes: list[ParsedNode] = []
        edges: list[ParsedEdge] = []
        node_counter = 0
        edge_counter = 0
        layer = 0
        parallel_group_counter = 0
        previous_layer_nodes: list[str] = []

        for item in composition:
            layer += 1

            if isinstance(item, str):
                # Simple sequential node
                node_counter += 1
                node_id = self._generate_node_id(node_counter)
                nodes.append(
                    ParsedNode(
                        node_id=node_id,
                        reference=item,
                        layer=layer,
                        parallel_group=None,
                    )
                )

                # Connect to previous layer nodes
                for prev_node_id in previous_layer_nodes:
                    edge_counter += 1
                    edges.append(
                        ParsedEdge(
                            from_node_id=prev_node_id,
                            to_node_id=node_id,
                            edge_id=self._generate_edge_id(edge_counter),
                        )
                    )

                previous_layer_nodes = [node_id]

            elif isinstance(item, list):
                # Parallel block
                if not item:
                    raise ValueError("Parallel block cannot be empty")

                parallel_group_counter += 1
                current_parallel_nodes: list[str] = []

                for sub_item in item:
                    if isinstance(sub_item, str):
                        # Parallel node
                        node_counter += 1
                        node_id = self._generate_node_id(node_counter)
                        nodes.append(
                            ParsedNode(
                                node_id=node_id,
                                reference=sub_item,
                                layer=layer,
                                parallel_group=parallel_group_counter,
                            )
                        )

                        # Connect to previous layer nodes
                        for prev_node_id in previous_layer_nodes:
                            edge_counter += 1
                            edges.append(
                                ParsedEdge(
                                    from_node_id=prev_node_id,
                                    to_node_id=node_id,
                                    edge_id=self._generate_edge_id(edge_counter),
                                )
                            )

                        current_parallel_nodes.append(node_id)
                    elif isinstance(sub_item, list):
                        # Nested parallel - process recursively
                        for nested_item in sub_item:
                            if not isinstance(nested_item, str):
                                raise ValueError(
                                    "Invalid reference type: must be string"
                                )
                            node_counter += 1
                            node_id = self._generate_node_id(node_counter)
                            nodes.append(
                                ParsedNode(
                                    node_id=node_id,
                                    reference=nested_item,
                                    layer=layer,
                                    parallel_group=parallel_group_counter,
                                )
                            )

                            # Connect to previous layer nodes
                            for prev_node_id in previous_layer_nodes:
                                edge_counter += 1
                                edges.append(
                                    ParsedEdge(
                                        from_node_id=prev_node_id,
                                        to_node_id=node_id,
                                        edge_id=self._generate_edge_id(edge_counter),
                                    )
                                )

                            current_parallel_nodes.append(node_id)
                    else:
                        raise ValueError("Invalid reference type: must be string")

                previous_layer_nodes = current_parallel_nodes

            else:
                raise ValueError("Invalid reference type: must be string or list")

        max_layer = layer
        return ParsedComposition(nodes=nodes, edges=edges, max_layer=max_layer)

    def _validate_nesting(self, composition: list[Any], depth: int = 0) -> None:
        """
        Validate nesting depth (max 2 levels).

        Args:
            composition: Composition array
            depth: Current nesting depth

        Raises:
            ValueError: If nesting exceeds 2 levels
        """
        if depth > 2:
            raise ValueError("Maximum nesting depth of 2 levels exceeded")

        for item in composition:
            if isinstance(item, list):
                self._validate_nesting(item, depth + 1)

    def _generate_node_id(self, index: int) -> str:
        """
        Generate auto node ID.

        Args:
            index: Node index

        Returns:
            Node ID like "n1", "n2", etc.
        """
        return f"n{index}"

    def _generate_edge_id(self, index: int) -> str:
        """
        Generate auto edge ID.

        Args:
            index: Edge index

        Returns:
            Edge ID like "e1", "e2", etc.
        """
        return f"e{index}"
