"""
Question Generator - Generate user-facing questions for composition decisions.

Handles decision points like missing aggregation nodes after parallel blocks.
"""

from typing import Any

from .models import (
    Question,
    ResolvedTask,
    ResolvedTemplate,
)


class QuestionGenerator:
    """Generate actionable questions for composition decision points."""

    def generate_missing_aggregation_question(
        self,
        parallel_node_ids: list[str],
        layer: int,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> Question:
        """
        Generate question for missing aggregation after parallel block.

        Args:
            parallel_node_ids: List of parallel node IDs
            layer: Layer number where aggregation is missing
            resolved_nodes: Resolved task/template nodes

        Returns:
            Question object with options and suggested fix
        """
        # Get node names for context
        node_names = []
        for node_id in parallel_node_ids:
            resolved = resolved_nodes.get(node_id)
            if resolved:
                node_names.append(
                    resolved.name if hasattr(resolved, "name") else str(resolved)
                )

        # Suggest aggregation node type
        suggested = self._suggest_aggregation_node(parallel_node_ids, resolved_nodes)

        return Question(
            question_id=f"missing_agg_layer_{layer}",
            question_type="missing_aggregation",
            message=f"Parallel block at layer {layer} is missing an aggregation node. "
            f"Parallel nodes: {', '.join(node_names)}. "
            f"How should their outputs be combined?",
            options=["add merge", "add collect", "skip"],
            suggested=f"add {suggested}",
            context={
                "layer": layer,
                "parallel_node_ids": parallel_node_ids,
                "node_names": node_names,
                "suggested_type": suggested,
            },
        )

    def generate_ambiguous_resolution_question(
        self,
        reference: str,
        candidates: list[dict[str, Any]],
    ) -> Question:
        """
        Generate question for ambiguous task/template resolution.

        Args:
            reference: Ambiguous reference (cy_name or shortcut)
            candidates: List of possible matches

        Returns:
            Question object with candidate options
        """
        # Build options from candidates
        options = []
        for candidate in candidates:
            option_label = candidate.get("name", str(candidate.get("id", "unknown")))
            options.append(option_label)

        # Build context with descriptions
        candidate_details = []
        for candidate in candidates:
            candidate_details.append(
                {
                    "id": str(candidate.get("id")),
                    "name": candidate.get("name"),
                    "description": candidate.get("description"),
                }
            )

        return Question(
            question_id=f"ambiguous_{reference}",
            question_type="ambiguous_resolution",
            message=f"Multiple tasks/templates found matching '{reference}'. "
            f"Which one should be used?",
            options=options,
            suggested=options[0] if options else None,  # Suggest first option
            context={
                "reference": reference,
                "candidates": candidate_details,
            },
        )

    def _suggest_aggregation_node(
        self,
        parallel_node_ids: list[str],
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> str:
        """
        Suggest appropriate aggregation node (merge vs collect).

        Args:
            parallel_node_ids: List of parallel node IDs
            resolved_nodes: Resolved task/template nodes

        Returns:
            Suggested shortcut ("merge" or "collect")
        """
        # Get output schemas of parallel nodes
        output_schemas = []
        for node_id in parallel_node_ids:
            resolved = resolved_nodes.get(node_id)
            if resolved and resolved.output_schema:
                output_schemas.append(resolved.output_schema)

        # If we don't have enough information, suggest merge as default
        if len(output_schemas) < 2:
            return "merge"

        # Check if all output schemas are the same (or very similar)
        # If schemas are uniform, suggest "merge" (combines into single object)
        # If schemas are different, suggest "collect" (preserves all outputs as array)

        first_schema = output_schemas[0]
        all_same = all(schema == first_schema for schema in output_schemas)

        if all_same:
            return "merge"
        return "collect"
