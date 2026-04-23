"""
Type propagation algorithm for workflows.

Implements the core type propagation engine that traverses workflow DAG,
infers types for each node, and reports errors/warnings.
"""

from dataclasses import dataclass
from typing import Any, Literal

from analysi.models.workflow import Workflow, WorkflowNode
from analysi.services.type_propagation.errors import TypePropagationError


@dataclass
class NodeTypeInfo:
    """Type information for a single node."""

    node_id: str
    kind: str
    inferred_input: dict[str, Any] | list[dict[str, Any]]
    inferred_output: dict[str, Any]
    template_kind: str | None = None


@dataclass
class PropagationResult:
    """Result of type propagation."""

    status: Literal["valid", "invalid", "valid_with_warnings"]
    nodes: list[NodeTypeInfo]
    workflow_output_schema: dict[str, Any] | None
    errors: list[TypePropagationError]
    warnings: list[TypePropagationError]


class WorkflowTypePropagator:
    """Type propagation engine for workflows."""

    async def propagate_types(
        self,
        workflow: Workflow,
        initial_input_schema: dict[str, Any],
        strict_input: bool = True,
        session: Any = None,
        tenant_id: str | None = None,
    ) -> PropagationResult:
        """
        Propagate types through workflow DAG.

        Args:
            workflow: Workflow to analyze
            initial_input_schema: Input schema for start nodes
            strict_input: If True (default), enforce strict input field validation when
                         inferring task output schemas. Set to False for workflows with
                         dynamic/unknown input schemas (e.g., external APIs).

        Returns:
            PropagationResult with inferred schemas and errors/warnings
        """
        errors: list[TypePropagationError] = []
        warnings: list[TypePropagationError] = []
        inferred_schemas: dict[str, dict] = {}
        nodes_info: list[NodeTypeInfo] = []

        try:
            # Step 1: Identify start nodes (validates workflow has start nodes)
            self._identify_start_nodes(workflow)

            # Step 2: Topologically sort nodes
            sorted_nodes = self._topological_sort(workflow)

            # Step 3: Traverse nodes in topological order
            for node in sorted_nodes:
                # Use node_id (human-readable) as key for inferred_schemas
                node_key = node.node_id

                # Get predecessors
                predecessors = self._get_predecessors(node, workflow)

                # Compute input schema (can be single dict or list of dicts for multi-input)
                input_schema: dict[str, Any] | list[dict[str, Any]]
                if node.is_start_node:
                    # Start node: use initial input schema
                    input_schema = initial_input_schema
                else:
                    # Non-start node: compute from predecessors
                    input_schema = self._compute_node_input_schema(
                        node, predecessors, inferred_schemas
                    )

                # Validate multi-input pattern
                multi_input_warning = self._validate_multi_input(
                    node, len(predecessors)
                )
                if multi_input_warning:
                    warnings.append(multi_input_warning)

                # Validate schema compatibility (if node declares input schema)
                compatibility_error = self._validate_node_input_compatibility(
                    node, input_schema
                )
                if compatibility_error:
                    errors.append(compatibility_error)

                # Infer output schema
                output_result = await self._infer_node_output(
                    node, input_schema, strict_input, session, tenant_id
                )

                if isinstance(output_result, TypePropagationError):
                    # Inference failed - record error
                    errors.append(output_result)
                    # Use empty object as fallback to allow propagation to continue
                    output_schema = {"type": "object"}
                else:
                    output_schema = output_result

                # Store inferred output schema (keyed by node_id for helper methods)
                inferred_schemas[node_key] = output_schema

                # Create NodeTypeInfo
                template_kind = None
                if node.kind == "transformation" and node.node_template:
                    template_kind = node.node_template.kind

                nodes_info.append(
                    NodeTypeInfo(
                        node_id=node_key,
                        kind=node.kind,
                        inferred_input=input_schema,
                        inferred_output=output_schema,
                        template_kind=template_kind,
                    )
                )

            # Step 4: Compute workflow output schema
            workflow_output_schema = self._compute_workflow_output(
                workflow, inferred_schemas
            )

            # Determine status
            status: Literal["valid", "invalid", "valid_with_warnings"]
            if errors:
                status = "invalid"
            elif warnings:
                status = "valid_with_warnings"
            else:
                status = "valid"

            return PropagationResult(
                status=status,
                nodes=nodes_info,
                workflow_output_schema=workflow_output_schema,
                errors=errors,
                warnings=warnings,
            )

        except ValueError as e:
            # Catch validation errors (e.g., no start nodes, cycle detected)
            error = TypePropagationError(
                node_id="workflow",
                error_type="workflow_validation_error",
                message=str(e),
                suggestion="Fix workflow structure",
            )
            return PropagationResult(
                status="invalid",
                nodes=nodes_info,
                workflow_output_schema=None,
                errors=[error],
                warnings=[],
            )

    def _identify_start_nodes(self, workflow: Workflow) -> list[WorkflowNode]:
        """
        Find all nodes with is_start_node = True.

        Args:
            workflow: Workflow to analyze

        Returns:
            List of start nodes

        Raises:
            ValueError: If no start nodes found
        """
        start_nodes = [node for node in workflow.nodes if node.is_start_node]

        if not start_nodes:
            raise ValueError("Workflow must have at least one start node")

        return start_nodes

    def _topological_sort(self, workflow: Workflow) -> list[WorkflowNode]:
        """
        Topologically sort workflow DAG.

        Args:
            workflow: Workflow to sort

        Returns:
            Nodes in topological order

        Raises:
            ValueError: If cycle detected
        """
        # Build adjacency list from edges
        graph: dict[str, list[str]] = {str(node.id): [] for node in workflow.nodes}
        for edge in workflow.edges:
            from_id = str(edge.from_node_uuid)
            to_id = str(edge.to_node_uuid)
            graph[from_id].append(to_id)

        # DFS to detect cycles and build topological order
        visited: set[str] = set()
        rec_stack: set[str] = set()
        topo_order: list[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)

            for neighbor in graph[node_id]:
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    raise ValueError(f"cycle detected in workflow at node {node_id}")

            rec_stack.remove(node_id)
            topo_order.append(node_id)

        # Visit all nodes
        for node in workflow.nodes:
            node_id = str(node.id)
            if node_id not in visited:
                dfs(node_id)

        # Reverse to get correct topological order (dependencies first)
        topo_order.reverse()

        # Map node IDs back to WorkflowNode objects
        node_map = {str(node.id): node for node in workflow.nodes}
        return [node_map[node_id] for node_id in topo_order]

    def _get_predecessors(
        self, node: WorkflowNode, workflow: Workflow
    ) -> list[WorkflowNode]:
        """
        Get predecessor nodes for a given node.

        Args:
            node: Node to find predecessors for
            workflow: Workflow containing the node

        Returns:
            List of predecessor nodes
        """
        # Find all edges that point to this node
        predecessor_ids = [
            edge.from_node_uuid
            for edge in workflow.edges
            if edge.to_node_uuid == node.id
        ]

        # Map IDs to WorkflowNode objects
        node_map = {node.id: node for node in workflow.nodes}
        return [node_map[node_id] for node_id in predecessor_ids]

    def _compute_node_input_schema(
        self,
        node: WorkflowNode,
        predecessors: list[WorkflowNode],
        inferred_schemas: dict[str, dict],
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Compute input schema for a node based on predecessors.

        Single predecessor: returns predecessor output schema
        Multiple predecessors: returns list of predecessor output schemas

        Args:
            node: Node to compute input for
            predecessors: List of predecessor nodes
            inferred_schemas: Dictionary of already inferred schemas

        Returns:
            Input schema (single dict or list of dicts)
        """
        # No predecessors: start node uses initial input schema
        if not predecessors:
            # This shouldn't happen for non-start nodes
            # Start nodes are handled separately in propagate_types()
            return {}

        # Single predecessor: return its output schema
        if len(predecessors) == 1:
            pred_key = predecessors[0].node_id
            return inferred_schemas[pred_key]

        # Multiple predecessors: return list of output schemas
        return [inferred_schemas[pred.node_id] for pred in predecessors]

    def _validate_multi_input(
        self, node: WorkflowNode, predecessor_count: int
    ) -> TypePropagationError | None:
        """
        Validate multi-input constraints.

        Emit deprecation warning for v5 multi-input pattern (non-Merge/Collect with multiple inputs).

        Args:
            node: Node to validate
            predecessor_count: Number of predecessors

        Returns:
            DeprecatedMultiInputWarning if deprecated pattern, None otherwise
        """
        from analysi.services.type_propagation.errors import (
            DeprecatedMultiInputWarning,
        )

        # Only check if multiple predecessors
        if predecessor_count <= 1:
            return None

        # Check if node is transformation with Merge or Collect template
        if node.kind == "transformation" and node.node_template:
            template_kind = node.node_template.kind
            if template_kind in ["merge", "collect"]:
                # Valid multi-input pattern
                return None

        # Deprecated v5 multi-input pattern detected
        return DeprecatedMultiInputWarning(
            node_id=str(node.id),
            error_type="deprecated_multi_input",
            message=f"Node {node.id} has {predecessor_count} inputs but is not a Merge/Collect node",
            suggestion="Use Merge or Collect node for multi-input patterns",
            predecessor_count=predecessor_count,
            current_behavior="Receives list of predecessor outputs",
            migration_suggestion="Add Merge node before this node to combine inputs",
        )

    def _validate_node_input_compatibility(
        self, node: WorkflowNode, input_schema: dict[str, Any] | list[dict[str, Any]]
    ) -> TypePropagationError | None:
        """
        Validate that propagated input schema is compatible with node's declared input schema.

        Uses duck typing: actual schema must have all required fields from declared schema.

        Args:
            node: Node to validate
            input_schema: Propagated input schema (single dict or list for multi-input)

        Returns:
            TypeMismatchError if incompatible, None if compatible or no declared schema
        """
        from analysi.services.type_propagation.schema_validation import (
            validate_schema_compatibility,
        )

        # Get declared input schema from node.schemas JSONB field
        if not node.schemas:
            # No declared schema - skip validation
            return None

        declared_input_schema = node.schemas.get("input")
        if not declared_input_schema:
            # No declared input schema - skip validation
            return None

        # For multi-input nodes (Merge/Collect), skip schema validation
        # They receive list of schemas and handle validation internally
        if isinstance(input_schema, list):
            return None

        # Validate compatibility using duck typing
        return validate_schema_compatibility(
            node_id=node.node_id,
            required_schema=declared_input_schema,
            actual_schema=input_schema,
        )

    async def _infer_node_output(
        self,
        node: WorkflowNode,
        input_schema: dict[str, Any] | list[dict[str, Any]],
        strict_input: bool = True,
        session: Any = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any] | TypePropagationError:
        """
        Infer output schema for a node.

        Dispatches to appropriate handler based on node kind:
        - kind='task': Call infer_task_output_schema()
        - kind='transformation': Dispatch based on node_template.kind

        Args:
            node: Node to infer output for
            input_schema: Input schema (single dict or list for multi-input)
            strict_input: If True, enforce strict input field validation for task nodes

        Returns:
            Inferred output schema, or TypePropagationError
        """
        from analysi.services.type_propagation.task_inference import (
            infer_task_output_schema,
        )
        from analysi.services.type_propagation.template_handlers import (
            handle_collect_template,
            handle_identity_template,
            handle_merge_template,
        )

        # Handle task nodes
        if node.kind == "task":
            # Task input must be single schema (not list)
            if isinstance(input_schema, list):
                return TypePropagationError(
                    node_id=str(node.id),
                    error_type="invalid_task_input",
                    message="Task nodes cannot receive list input (multi-input)",
                    suggestion="Add Merge node before task to combine inputs",
                )

            # Check if task is loaded (for integration tests with database)
            # or if we need to create a placeholder (for unit tests)
            if hasattr(node, "task") and node.task:
                return await infer_task_output_schema(
                    node.task, input_schema, strict_input, session, tenant_id
                )
            if node.task_id:
                # Task ID exists but task not loaded
                # For unit tests: create placeholder Task with minimal info
                # For production: this would trigger a database load
                from analysi.models.task import Task, TaskFunction

                placeholder_task = Task(
                    component_id=node.task_id,
                    directive="Placeholder task for type inference",
                    script="return input",  # Generic pass-through
                    function=TaskFunction.EXTRACTION,
                )
                placeholder_task.id = node.task_id
                return await infer_task_output_schema(
                    placeholder_task, input_schema, strict_input, session, tenant_id
                )
            return TypePropagationError(
                node_id=str(node.id),
                error_type="missing_task",
                message="Task node missing task_id",
                suggestion="Ensure node.task_id is set",
            )

        # Handle transformation nodes
        if node.kind == "transformation":
            if not node.node_template:
                return TypePropagationError(
                    node_id=str(node.id),
                    error_type="missing_template",
                    message="Transformation node missing template",
                    suggestion="Ensure node.node_template is set",
                )

            template_kind = node.node_template.kind

            # Identity template: T => T
            if template_kind == "identity":
                if isinstance(input_schema, list):
                    return TypePropagationError(
                        node_id=str(node.id),
                        error_type="invalid_template_input",
                        message="Identity template requires single input",
                        suggestion="Identity nodes cannot have multiple predecessors",
                    )
                return handle_identity_template(input_schema)

            # Merge template: [T1, T2] => {...T1, ...T2}
            if template_kind == "merge":
                if not isinstance(input_schema, list):
                    # Single input to Merge: treat as single-element list
                    input_schema = [input_schema]
                return handle_merge_template(input_schema)

            # Collect template: [T1, T2] => [T1 | T2]
            if template_kind == "collect":
                if not isinstance(input_schema, list):
                    # Single input to Collect: treat as single-element list
                    input_schema = [input_schema]
                return handle_collect_template(input_schema)

            # Unknown template kind
            return TypePropagationError(
                node_id=str(node.id),
                error_type="unknown_template",
                message=f"Unknown template kind: {template_kind}",
                suggestion="Use identity, merge, or collect template",
            )

        # Unknown node kind
        return TypePropagationError(
            node_id=str(node.id),
            error_type="unknown_node_kind",
            message=f"Unknown node kind: {node.kind}",
            suggestion="Node kind must be 'task' or 'transformation'",
        )

    def _compute_workflow_output(
        self, workflow: Workflow, inferred_schemas: dict[str, dict]
    ) -> dict[str, Any]:
        """
        Compute workflow output schema from terminal nodes.

        Single terminal node: returns that node's output schema
        Multiple terminal nodes: returns object with node_id keys

        Args:
            workflow: Workflow to compute output for
            inferred_schemas: Dictionary of inferred schemas

        Returns:
            Workflow output schema
        """
        # Find terminal nodes (nodes with no outgoing edges)
        outgoing_node_ids = {str(edge.from_node_uuid) for edge in workflow.edges}
        terminal_nodes = [
            node for node in workflow.nodes if str(node.id) not in outgoing_node_ids
        ]

        # No terminal nodes - shouldn't happen in valid workflow
        if not terminal_nodes:
            return {}

        # Single terminal node: return its output schema
        if len(terminal_nodes) == 1:
            node_key = terminal_nodes[0].node_id
            return inferred_schemas[node_key]

        # Multiple terminal nodes: return object with node_id keys and properties
        # Format: {"type": "object", "properties": {node_id: schema, ...}}
        return {
            "type": "object",
            "properties": {
                node.node_id: inferred_schemas[node.node_id] for node in terminal_nodes
            },
        }
