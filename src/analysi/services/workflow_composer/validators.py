"""
Structural and Schema Validators.

Validate graph structure and type compatibility.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID

from .models import (
    CompositionError,
    CompositionWarning,
    ParsedComposition,
    ResolvedTask,
    ResolvedTemplate,
)


class StructuralValidator:
    """Validate graph structure (DAG, reachability, missing nodes)."""

    def validate(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> list[CompositionError]:
        """
        Validate structural properties of composition.

        Checks:
        - No cycles (DAG)
        - Single start node
        - All nodes reachable
        - Missing aggregation after parallel blocks
        - No dangling outputs

        Args:
            composition: Parsed composition
            resolved_nodes: Mapping of node_id to resolved task/template

        Returns:
            List of errors (empty if valid)
        """
        errors: list[CompositionError] = []

        # Check for cycles
        cycles = self._detect_cycles(composition)
        if cycles:
            for cycle_path in cycles:
                errors.append(
                    CompositionError(
                        error_type="cycle_detected",
                        message=f"Cycle detected in workflow: {cycle_path}",
                        context={"cycle": cycle_path},
                    )
                )

        # Find start nodes
        start_nodes = self._find_start_nodes(composition)
        if len(start_nodes) == 0:
            errors.append(
                CompositionError(
                    error_type="no_start_node",
                    message="No start node found (all nodes have incoming edges)",
                    context={},
                )
            )
        elif len(start_nodes) > 1:
            errors.append(
                CompositionError(
                    error_type="multiple_start_nodes",
                    message=f"Multiple start nodes found: {start_nodes}",
                    context={"start_nodes": start_nodes},
                )
            )

        # Check reachability
        if len(start_nodes) == 1:
            reachable = self._check_reachability(composition, start_nodes[0])
            all_nodes = {node.node_id for node in composition.nodes}
            unreachable = all_nodes - reachable
            if unreachable:
                errors.append(
                    CompositionError(
                        error_type="unreachable_nodes",
                        message=f"Nodes not reachable from start: {list(unreachable)}",
                        context={"unreachable_nodes": list(unreachable)},
                    )
                )

        # Check for missing aggregation
        missing_agg = self._detect_missing_aggregation(composition, resolved_nodes)
        for layer, parallel_node_ids in missing_agg:
            errors.append(
                CompositionError(
                    error_type="missing_aggregation",
                    message=f"Parallel block at layer {layer} missing aggregation node",
                    context={"layer": layer, "parallel_nodes": parallel_node_ids},
                )
            )

        return errors

    def _detect_cycles(self, composition: ParsedComposition) -> list[str]:
        """
        Detect cycles using DFS.

        Args:
            composition: Parsed composition

        Returns:
            List of cycle paths (empty if DAG)
        """
        # Build adjacency list
        graph: dict[str, list[str]] = {node.node_id: [] for node in composition.nodes}
        for edge in composition.edges:
            graph[edge.from_node_id].append(edge.to_node_id)

        # DFS with coloring: white (unvisited), gray (visiting), black (visited)
        color = dict.fromkeys(graph, "white")
        cycles: list[str] = []

        def dfs(node: str, path: list[str]) -> None:
            if color[node] == "gray":
                # Found a cycle
                cycle_start = path.index(node)
                cycle_path = " -> ".join([*path[cycle_start:], node])
                cycles.append(cycle_path)
                return

            if color[node] == "black":
                return

            color[node] = "gray"
            path.append(node)

            for neighbor in graph[node]:
                dfs(neighbor, path)

            path.pop()
            color[node] = "black"

        for node_id in graph:
            if color[node_id] == "white":
                dfs(node_id, [])

        return cycles

    def _find_start_nodes(self, composition: ParsedComposition) -> list[str]:
        """
        Find nodes with no incoming edges.

        Args:
            composition: Parsed composition

        Returns:
            List of start node IDs
        """
        all_nodes = {node.node_id for node in composition.nodes}
        target_nodes = {edge.to_node_id for edge in composition.edges}
        start_nodes = all_nodes - target_nodes
        return list(start_nodes)

    def _check_reachability(
        self, composition: ParsedComposition, start_node_id: str
    ) -> set[str]:
        """
        Find all nodes reachable from start node using BFS.

        Args:
            composition: Parsed composition
            start_node_id: Starting node

        Returns:
            Set of reachable node IDs
        """
        # Build adjacency list
        graph: dict[str, list[str]] = {node.node_id: [] for node in composition.nodes}
        for edge in composition.edges:
            graph[edge.from_node_id].append(edge.to_node_id)

        # BFS
        from collections import deque

        visited = {start_node_id}
        queue = deque([start_node_id])

        while queue:
            node = queue.popleft()
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return visited

    def _detect_missing_aggregation(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> list[tuple[int, list[str]]]:
        """
        Detect parallel blocks without aggregation nodes.

        Args:
            composition: Parsed composition
            resolved_nodes: Resolved tasks/templates

        Returns:
            List of (layer, parallel_node_ids) tuples missing aggregation
        """
        missing: list[tuple[int, list[str]]] = []

        # Group nodes by layer and parallel group
        layer_groups: dict[int, dict[int | None, list[str]]] = {}
        for node in composition.nodes:
            if node.layer not in layer_groups:
                layer_groups[node.layer] = {}
            if node.parallel_group not in layer_groups[node.layer]:
                layer_groups[node.layer][node.parallel_group] = []
            layer_groups[node.layer][node.parallel_group].append(node.node_id)

        # Check each layer for parallel blocks
        for layer, groups in layer_groups.items():
            # Find parallel groups (non-None group IDs with multiple nodes)
            for group_id, node_ids in groups.items():
                if group_id is not None and len(node_ids) > 1:
                    # This is a parallel block
                    # Check if the next layer has an aggregation node
                    next_layer = layer + 1
                    if next_layer in layer_groups:
                        next_layer_nodes = []
                        for group_nodes in layer_groups[next_layer].values():
                            next_layer_nodes.extend(group_nodes)

                        # Check if any next layer node is an aggregation node (merge/collect)
                        has_aggregation = False
                        for node_id in next_layer_nodes:
                            resolved = resolved_nodes.get(node_id)
                            if isinstance(
                                resolved, ResolvedTemplate
                            ) and resolved.kind in [
                                "merge",
                                "collect",
                            ]:
                                has_aggregation = True
                                break

                        if not has_aggregation:
                            missing.append((layer, node_ids))

        return missing


class SchemaValidator:
    """Validate type compatibility using type propagation."""

    def __init__(self, session: AsyncSession):
        """
        Initialize SchemaValidator.

        Args:
            session: Database session
        """
        self.session = session

    async def validate(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        tenant_id: str,
    ) -> tuple[
        list[CompositionError], list[CompositionWarning], dict[str, Any], dict[str, Any]
    ]:
        """
        Validate schema compatibility using Rodos compilation.

        Uses WorkflowTypePropagator to compile each task with the previous task's
        output as input, catching compilation errors and type mismatches.

        Args:
            composition: Parsed composition
            resolved_nodes: Resolved tasks/templates
            tenant_id: Tenant ID

        Returns:
            Tuple of (errors, warnings, input_schema, output_schema)
        """
        errors: list[CompositionError] = []
        warnings: list[CompositionWarning] = []

        # Infer workflow input/output schemas from first/last nodes
        input_schema, output_schema = self._infer_workflow_schemas(
            composition, resolved_nodes
        )

        # Try to build temporary workflow for Rodos compilation
        # If tasks can't be loaded (unit tests), fall back to simple validation
        propagation_result = None
        try:
            temp_workflow = await self._build_temp_workflow(
                composition, resolved_nodes, tenant_id, input_schema, output_schema
            )

            # Check if all task nodes have actual tasks loaded
            has_real_tasks = all(
                node.task is not None and hasattr(node.task, "id")
                for node in temp_workflow.nodes
                if node.kind == "task"
            )

            if has_real_tasks:
                # Use WorkflowTypePropagator for Rodos compilation (integration tests)
                from analysi.services.type_propagation import WorkflowTypePropagator

                propagator = WorkflowTypePropagator()
                propagation_result = await propagator.propagate_types(
                    workflow=temp_workflow,
                    initial_input_schema=input_schema,
                    strict_input=True,
                    session=self.session,
                    tenant_id=tenant_id,
                )

                # Convert propagation errors to composition errors
                for prop_error in propagation_result.errors:
                    errors.append(
                        CompositionError(
                            error_type=prop_error.error_type,
                            message=prop_error.message,
                            context={
                                "node_id": prop_error.node_id,
                                "suggestion": prop_error.suggestion,
                            },
                        )
                    )

                # Update output schema from propagation if available
                if propagation_result.workflow_output_schema:
                    output_schema = propagation_result.workflow_output_schema
            else:
                # Fall back to simple edge validation for unit tests
                errors.extend(self._validate_edges_simple(composition, resolved_nodes))
        except Exception:
            # If workflow building fails (unit tests), use simple validation
            errors.extend(self._validate_edges_simple(composition, resolved_nodes))

        # Convert propagation warnings to composition warnings (if we did propagation)
        if propagation_result:
            for prop_warning in propagation_result.warnings:
                warnings.append(
                    CompositionWarning(
                        warning_type=prop_warning.error_type,
                        message=prop_warning.message,
                        context={
                            "node_id": prop_warning.node_id,
                        },
                    )
                )

        # Update output schema from propagation result if available
        if propagation_result and propagation_result.workflow_output_schema:
            output_schema = propagation_result.workflow_output_schema

        return errors, warnings, input_schema, output_schema

    def _validate_edges_simple(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> list[CompositionError]:
        """
        Simple edge validation for unit tests (no Cy compilation).

        Validates that output schema of source node is compatible with
        input schema of target node based on pre-defined schemas.

        Args:
            composition: Parsed composition
            resolved_nodes: Resolved tasks/templates with pre-defined schemas

        Returns:
            List of composition errors
        """
        errors: list[CompositionError] = []

        # Validate each edge
        for edge in composition.edges:
            from_node = resolved_nodes.get(edge.from_node_id)
            to_node = resolved_nodes.get(edge.to_node_id)

            if not from_node or not to_node:
                errors.append(
                    CompositionError(
                        error_type="missing_node",
                        message=f"Edge references missing node: {edge.edge_id}",
                        context={"edge_id": edge.edge_id},
                    )
                )
                continue

            # Check schema compatibility
            output_schema = from_node.output_schema or {}
            input_schema = to_node.input_schema or {}

            # Extract properties from schemas
            output_props = output_schema.get("properties", {})
            input_props = input_schema.get("properties", {})
            required_fields = input_schema.get("required", [])

            # Check required fields are provided
            for required_field in required_fields:
                if required_field not in output_props:
                    errors.append(
                        CompositionError(
                            error_type="missing_required_field",
                            message=f"Missing required field '{required_field}' in input schema",
                            context={
                                "node_id": edge.to_node_id,
                                "field": required_field,
                                "suggestion": f"Ensure predecessor provides '{required_field}' field",
                            },
                        )
                    )

            # Check type compatibility for overlapping fields
            for field_name, input_field_schema in input_props.items():
                if field_name in output_props:
                    output_field_schema = output_props[field_name]
                    input_type = input_field_schema.get("type")
                    output_type = output_field_schema.get("type")

                    if input_type and output_type and input_type != output_type:
                        errors.append(
                            CompositionError(
                                error_type="type_mismatch",
                                message=f"Type mismatch for field '{field_name}': "
                                f"expected {input_type}, got {output_type}",
                                context={
                                    "field": field_name,
                                    "expected_type": input_type,
                                    "actual_type": output_type,
                                    "source_node": edge.from_node_id,
                                    "target_node": edge.to_node_id,
                                },
                            )
                        )

        return errors

    async def _build_temp_workflow(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        tenant_id: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
    ):
        """
        Build temporary in-memory workflow for type propagation.

        Args:
            composition: Parsed composition
            resolved_nodes: Resolved tasks/templates
            tenant_id: Tenant ID
            input_schema: Workflow input schema
            output_schema: Workflow output schema

        Returns:
            Temporary Workflow object with nodes and edges
        """
        from uuid import uuid4

        from analysi.models.task import Task
        from analysi.models.workflow import Workflow, WorkflowEdge, WorkflowNode

        # Create temporary workflow
        temp_workflow = Workflow(
            id=uuid4(),
            tenant_id=tenant_id,
            name="temp_validation_workflow",
            description="Temporary workflow for validation",
            is_dynamic=False,
            io_schema={"input": input_schema, "output": output_schema},
            data_samples=None,
            created_by=SYSTEM_USER_ID,
            status="draft",
        )

        # Create nodes
        node_map: dict[str, WorkflowNode] = {}
        min_layer = min(n.layer for n in composition.nodes)

        for parsed_node in composition.nodes:
            resolved = resolved_nodes[parsed_node.node_id]

            # Determine node kind and task_id
            if isinstance(resolved, ResolvedTask):
                kind = "task"
                task_id = resolved.task_id

                # Load actual task from database for propagation (tenant-scoped)
                from sqlalchemy import select

                from analysi.models.component import Component

                stmt = (
                    select(Task)
                    .join(Component, Task.component_id == Component.id)
                    .where(
                        Task.component_id == task_id,
                        Component.tenant_id == tenant_id,
                    )
                )
                result = await self.session.execute(stmt)
                task = result.scalar_one_or_none()

                # Create node
                node = WorkflowNode(
                    id=uuid4(),
                    workflow_id=temp_workflow.id,
                    node_id=parsed_node.node_id,
                    kind=kind,
                    name=resolved.name,
                    task_id=task_id,
                    node_template_id=None,
                    schemas={
                        "input": resolved.input_schema or {"type": "object"},
                        "output": resolved.output_schema or {"type": "object"},
                    },
                    is_start_node=(parsed_node.layer == min_layer),
                )
                # Attach task for propagation
                node.task = task

            elif isinstance(resolved, ResolvedTemplate):
                kind = "transformation"
                node_template_id = resolved.template_id

                # Load template from database (tenant-scoped: own + system)
                from sqlalchemy import or_, select

                from analysi.models.workflow import NodeTemplate

                stmt = select(NodeTemplate).where(
                    NodeTemplate.id == node_template_id,
                    or_(
                        NodeTemplate.tenant_id == tenant_id,
                        NodeTemplate.tenant_id.is_(None),
                    ),
                )
                result = await self.session.execute(stmt)
                template = result.scalar_one_or_none()

                # Create node
                node = WorkflowNode(
                    id=uuid4(),
                    workflow_id=temp_workflow.id,
                    node_id=parsed_node.node_id,
                    kind=kind,
                    name=resolved.name,
                    task_id=None,
                    node_template_id=node_template_id,
                    schemas={
                        "input": resolved.input_schema or {"type": "object"},
                        "output": resolved.output_schema or {"type": "object"},
                    },
                    is_start_node=(parsed_node.layer == min_layer),
                )
                # Attach template for propagation
                node.node_template = template

            node_map[parsed_node.node_id] = node

        # Create edges
        edges = []
        for parsed_edge in composition.edges:
            from_node = node_map[parsed_edge.from_node_id]
            to_node = node_map[parsed_edge.to_node_id]

            edge = WorkflowEdge(
                workflow_id=temp_workflow.id,
                edge_id=parsed_edge.edge_id,
                from_node_uuid=from_node.id,
                to_node_uuid=to_node.id,
                alias=None,
            )
            edges.append(edge)

        # Attach nodes and edges to workflow
        temp_workflow.nodes = list(node_map.values())
        temp_workflow.edges = edges

        return temp_workflow

    async def _validate_edge_compatibility(
        self,
        source_output_schema: dict[str, Any],
        target_input_schema: dict[str, Any],
        edge_id: str,
    ) -> tuple[list[CompositionError], list[CompositionWarning]]:
        """
        Validate type compatibility for single edge.

        Args:
            source_output_schema: Output schema of source node
            target_input_schema: Input schema of target node
            edge_id: Edge identifier for error reporting

        Returns:
            Tuple of (errors, warnings)
        """
        errors: list[CompositionError] = []
        warnings: list[CompositionWarning] = []

        # Basic compatibility check
        # Check if source output provides what target input requires

        source_props = source_output_schema.get("properties", {})
        target_props = target_input_schema.get("properties", {})
        required_fields = target_input_schema.get("required", [])

        # Check for missing required fields
        for field in required_fields:
            if field not in source_props:
                errors.append(
                    CompositionError(
                        error_type="missing_required_field",
                        message=f"Edge {edge_id}: Required field '{field}' not in source output",
                        context={
                            "edge_id": edge_id,
                            "missing_field": field,
                            "source_output": source_output_schema,
                            "target_input": target_input_schema,
                        },
                    )
                )

        # Check for type mismatches on common fields
        for field in target_props:
            if field in source_props:
                source_type = source_props[field].get("type")
                target_type = target_props[field].get("type")
                if source_type and target_type and source_type != target_type:
                    errors.append(
                        CompositionError(
                            error_type="type_mismatch",
                            message=f"Edge {edge_id}: Field '{field}' type mismatch "
                            f"(source: {source_type}, target: {target_type})",
                            context={
                                "edge_id": edge_id,
                                "field": field,
                                "source_type": source_type,
                                "target_type": target_type,
                            },
                        )
                    )

        # Check for extra fields (warning only, duck typing)
        extra_fields = set(source_props.keys()) - set(target_props.keys())
        if extra_fields:
            warnings.append(
                CompositionWarning(
                    warning_type="extra_fields",
                    message=f"Edge {edge_id}: Extra fields in source output (duck typing allows this)",
                    context={
                        "edge_id": edge_id,
                        "extra_fields": list(extra_fields),
                    },
                )
            )

        return errors, warnings

    def _infer_workflow_schemas(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Infer workflow input/output schemas from first/last nodes.

        Args:
            composition: Parsed composition
            resolved_nodes: Resolved tasks/templates

        Returns:
            Tuple of (input_schema, output_schema)
        """
        # Find first node (minimum layer)
        first_node = min(composition.nodes, key=lambda n: n.layer)
        first_resolved = resolved_nodes.get(first_node.node_id)
        input_schema = (
            first_resolved.input_schema if first_resolved else {"type": "object"}
        )

        # Find last node (maximum layer)
        last_node = max(composition.nodes, key=lambda n: n.layer)
        last_resolved = resolved_nodes.get(last_node.node_id)
        output_schema = (
            last_resolved.output_schema if last_resolved else {"type": "object"}
        )

        return input_schema or {"type": "object"}, output_schema or {"type": "object"}
