"""
Service layer for workflow business logic.
Handles validation, enrichment, and coordination between repositories.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.workflow import (
    Workflow,
    enrich_workflow_json,
    validate_workflow_dag,
    validate_workflow_schema,
)
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.workflow import NodeTemplateRepository, WorkflowRepository
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.workflow import (
    AddEdgeRequest,
    AddNodeRequest,
    NodeTemplateCreate,
    NodeTemplateResponse,
    ValidationResult,
    WorkflowCreate,
    WorkflowNodeUpdate,
    WorkflowResponse,
    WorkflowUpdate,
)


class WorkflowService:
    """Service for workflow business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workflow_repo = WorkflowRepository(session)
        self.template_repo = NodeTemplateRepository(session)

    async def _log_audit(
        self,
        tenant_id: str,
        action: str,
        resource_id: str,
        audit_context: AuditContext | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an audit event if audit_context is provided."""
        if audit_context is None:
            return  # Skip logging if no context provided

        repo = ActivityAuditRepository(self.session)
        await repo.create(
            tenant_id=tenant_id,
            actor_id=audit_context.actor_user_id,
            actor_type=audit_context.actor_type,
            source=audit_context.source,
            action=action,
            resource_type="workflow",
            resource_id=resource_id,
            details=details,
            ip_address=audit_context.ip_address,
            user_agent=audit_context.user_agent,
            request_id=audit_context.request_id,
        )

    async def create_workflow(
        self,
        tenant_id: str,
        workflow_data: WorkflowCreate,
        audit_context: AuditContext | None = None,
        validate: bool = False,
        created_by: UUID | None = None,
    ) -> WorkflowResponse:
        """
        Create a complete workflow.

        Args:
            tenant_id: Tenant identifier
            workflow_data: Complete workflow definition
            audit_context: Optional audit context for logging
            validate: If True, validate workflow before creation (default: False)

        Returns:
            Created workflow with enriched data

        Raises:
            ValueError: If validation fails (when validate=True)
            HTTPException: If business rules violated
        """
        # Only validate if explicitly requested
        if validate:
            await self.validate_workflow_definition(workflow_data, tenant_id)

        # Derive created_by: audit_context (REST) takes priority, then explicit param (MCP/workers)
        if audit_context:
            created_by = audit_context.actor_user_id

        # Create workflow in database
        workflow = await self.workflow_repo.create_workflow(
            tenant_id, workflow_data, created_by=created_by
        )

        # Convert to response format
        enriched_data = enrich_workflow_json(workflow)

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.create",
            resource_id=str(workflow.id),
            audit_context=audit_context,
            details={
                "workflow_name": workflow.name,
                "node_count": len(workflow.nodes) if workflow.nodes else 0,
            },
        )

        return WorkflowResponse(**enriched_data)

    async def get_workflow(
        self, tenant_id: str, workflow_id: UUID, slim: bool = False
    ) -> WorkflowResponse | dict | None:
        """
        Get workflow with enriched data.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            slim: If True, return minimal verbosity response (no timestamps, UUIDs, template code)

        Returns:
            Enriched workflow or None if not found
            If slim=True, returns dict instead of WorkflowResponse
        """
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return None

        # Enrich and convert to response format
        if slim:
            from analysi.models.workflow import enrich_workflow_json_slim

            return enrich_workflow_json_slim(workflow)
        enriched_data = enrich_workflow_json(workflow)
        return WorkflowResponse(**enriched_data)

    async def list_workflows(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        name_filter: str | None = None,
        app: str | None = None,
    ) -> tuple[list[Workflow], dict[str, Any]]:
        """
        List workflows with pagination.

        Args:
            tenant_id: Tenant identifier
            skip: Number of records to skip
            limit: Maximum number of records
            name_filter: Optional name filter
            app: Optional content pack filter

        Returns:
            Tuple of (workflows, metadata_dict)
        """
        workflows, total = await self.workflow_repo.list_workflows(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            name_filter=name_filter,
            app=app,
        )

        # Return pagination metadata (same pattern as tasks)
        return workflows, {
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def delete_workflow(
        self,
        tenant_id: str,
        workflow_id: UUID,
        audit_context: AuditContext | None = None,
    ) -> bool:
        """
        Delete workflow with validation.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            audit_context: Optional audit context for logging

        Returns:
            True if deleted, False if not found
        """
        # Get workflow info before deletion for audit logging
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return False

        workflow_name = workflow.name

        deleted = await self.workflow_repo.delete_workflow(tenant_id, workflow_id)

        if deleted:
            # Log audit event
            await self._log_audit(
                tenant_id=tenant_id,
                action="workflow.delete",
                resource_id=str(workflow_id),
                audit_context=audit_context,
                details={"workflow_name": workflow_name},
            )

        return deleted

    async def replace_workflow(
        self,
        tenant_id: str,
        workflow_id: UUID,
        workflow_data: WorkflowCreate,
        audit_context: AuditContext | None = None,
    ) -> Workflow:
        """
        Replace an existing workflow with new data.

        This method preserves the workflow ID but replaces all nodes and edges.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID to replace
            workflow_data: New workflow definition
            audit_context: Optional audit context for logging

        Returns:
            Updated workflow with new nodes and edges

        Raises:
            NotFoundError: If workflow not found
            ValueError: If validation fails
        """
        from analysi.repositories.workflow import NotFoundError

        # Verify workflow exists
        existing = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not existing:
            raise NotFoundError(
                f"Workflow {workflow_id} not found for tenant {tenant_id}"
            )

        # Replace workflow data (delete existing nodes/edges and create new ones)
        workflow = await self.workflow_repo.replace_workflow(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            workflow_data=workflow_data,
        )

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.replace",
            resource_id=str(workflow_id),
            audit_context=audit_context,
            details={
                "workflow_name": workflow.name,
                "node_count": len(workflow.nodes) if workflow.nodes else 0,
            },
        )

        return workflow

    async def validate_workflow_definition(
        self, workflow_data: WorkflowCreate, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """
        Comprehensive workflow validation.

        Args:
            workflow_data: Workflow definition to validate
            tenant_id: Tenant scope for template ownership checks

        Returns:
            Validation result with details

        Raises:
            ValueError: If validation fails
        """
        # Convert to dict for validation functions
        workflow_dict = workflow_data.model_dump()

        # Validate basic schema
        validate_workflow_schema(workflow_dict)

        # Validate DAG structure
        nodes_dict = [node.model_dump() for node in workflow_data.nodes]
        edges_dict = [edge.model_dump() for edge in workflow_data.edges]

        if not validate_workflow_dag(nodes_dict, edges_dict):
            raise ValueError("Workflow contains cycles - must be a DAG")

        # Validate template references for transformation nodes
        for node in workflow_data.nodes:
            if node.kind == "transformation" and node.node_template_id:
                template = await self.template_repo.get_template_by_id(
                    node.node_template_id, tenant_id
                )
                if not template:
                    raise ValueError(
                        f"Node '{node.node_id}' references non-existent template: {node.node_template_id}"
                    )
                if not template.enabled:
                    raise ValueError(
                        f"Node '{node.node_id}' references disabled template: {node.node_template_id}"
                    )

        # Note: Task reference validation not yet implemented

        return {
            "valid": True,
            "node_count": len(workflow_data.nodes),
            "edge_count": len(workflow_data.edges),
            "has_cycles": False,
        }

    # Type Validation Methods (STUBBED)
    async def validate_workflow_types(
        self,
        tenant_id: str,
        workflow_id: UUID,
        initial_input_schema: dict[str, Any],
        strict_input: bool = True,
    ) -> dict[str, Any]:
        """
        Validate workflow type safety using type propagation.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to validate
            initial_input_schema: JSON Schema for workflow input
            strict_input: If True (default), enforce strict input field validation.
                         Set to False for workflows with dynamic/unknown schemas.

        Returns:
            WorkflowTypeValidationResponse as dict

        Raises:
            ValueError: If workflow not found or invalid input schema
        """
        # 1. Fetch workflow with relationships (nodes, edges, templates, tasks)
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # 1.5. Compute start nodes (nodes with no incoming edges)
        # Necessary for workflows created before is_start_node tracking was added
        incoming_node_ids = {str(edge.to_node_uuid) for edge in workflow.edges}
        for node in workflow.nodes:
            node.is_start_node = str(node.id) not in incoming_node_ids

        # 2. Call WorkflowTypePropagator.propagate_types()
        from analysi.services.type_propagation import WorkflowTypePropagator

        propagator = WorkflowTypePropagator()
        result = await propagator.propagate_types(
            workflow,
            initial_input_schema,
            strict_input,
            self.workflow_repo.session,
            tenant_id,
        )

        # 3. Convert PropagationResult to WorkflowTypeValidationResponse dict
        return {
            "status": result.status,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "kind": node.kind,
                    "template_kind": node.template_kind,
                    "inferred_input": node.inferred_input,
                    "inferred_output": node.inferred_output,
                }
                for node in result.nodes
            ],
            "workflow_output_schema": result.workflow_output_schema,
            "errors": [
                {
                    "node_id": error.node_id,
                    "error_type": error.error_type,
                    "message": error.message,
                    "suggestion": error.suggestion,
                    "severity": "error",
                    "expected_schema": getattr(error, "expected_schema", None),
                    "actual_schema": getattr(error, "actual_schema", None),
                }
                for error in result.errors
            ],
            "warnings": [
                {
                    "node_id": warning.node_id,
                    "error_type": warning.error_type,
                    "message": warning.message,
                    "suggestion": warning.suggestion,
                    "severity": "warning",
                    "expected_schema": getattr(warning, "expected_schema", None),
                    "actual_schema": getattr(warning, "actual_schema", None),
                }
                for warning in result.warnings
            ],
        }

    async def apply_workflow_types(
        self,
        tenant_id: str,
        workflow_id: UUID,
        initial_input_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate workflow types AND persist to database.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to validate and update
            initial_input_schema: JSON Schema for workflow input

        Returns:
            WorkflowTypeApplyResponse as dict

        Raises:
            ValueError: If workflow not found, invalid input, or validation fails
        """
        from datetime import UTC, datetime

        # 1. Call validate_workflow_types()
        validation_result = await self.validate_workflow_types(
            tenant_id, workflow_id, initial_input_schema
        )

        # 2. Check if status is "valid" or "valid_with_warnings"
        if validation_result["status"] not in ["valid", "valid_with_warnings"]:
            raise ValueError(
                f"Cannot apply types: workflow validation status is '{validation_result['status']}'"
            )

        # 3. Persist to database atomically
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Create node_id to inferred_schemas mapping
        node_type_info = {
            node["node_id"]: {
                "inferred_input": node["inferred_input"],
                "inferred_output": node["inferred_output"],
            }
            for node in validation_result["nodes"]
        }

        # Update each node's schemas JSONB field
        nodes_updated = 0
        for node in workflow.nodes:
            if node.node_id in node_type_info:
                # Update the schemas JSONB field with inferred types and metadata
                node.schemas = {
                    **node.schemas,  # Preserve existing fields (input, output, etc.)
                    "inferred_input": node_type_info[node.node_id]["inferred_input"],
                    "inferred_output": node_type_info[node.node_id]["inferred_output"],
                    "type_checked": True,
                    "validated_at": datetime.now(UTC).isoformat(),
                }
                nodes_updated += 1

        # Update workflow output schema if available
        if validation_result["workflow_output_schema"] is not None:
            workflow.io_schema = {
                **workflow.io_schema,
                "output": validation_result["workflow_output_schema"],
            }

        # Update workflow status to "validated" (two-tier validation)
        workflow.status = "validated"

        # Commit all changes atomically
        await self.session.commit()

        # 4. Return WorkflowTypeApplyResponse with applied=True
        return {
            **validation_result,  # Include all validation fields
            "applied": True,
            "nodes_updated": nodes_updated,
            "updated_at": datetime.now(UTC),
        }

    async def clear_workflow_types(
        self,
        tenant_id: str,
        workflow_id: UUID,
    ) -> dict[str, Any]:
        """
        Clear type annotations from workflow.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow to clear annotations from

        Returns:
            Dict with success status and nodes_updated count

        Raises:
            ValueError: If workflow not found
        """
        # 1. Fetch workflow with nodes
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # 2. Remove type annotations from each node
        nodes_updated = 0
        for node in workflow.nodes:
            # Remove inferred_input, inferred_output, type_checked, validated_at from schemas
            cleaned_schemas = {
                k: v
                for k, v in node.schemas.items()
                if k
                not in [
                    "inferred_input",
                    "inferred_output",
                    "type_checked",
                    "validated_at",
                ]
            }

            # Only update if there were changes
            if cleaned_schemas != node.schemas:
                node.schemas = cleaned_schemas
                nodes_updated += 1

        # Reset workflow status to draft (two-tier validation)
        workflow.status = "draft"

        # Commit changes
        await self.session.commit()

        # 3. Return summary
        return {
            "success": True,
            "nodes_updated": nodes_updated,
            "workflow_id": str(workflow_id),
        }

    # ========== Mutation Methods (Stubs) ==========

    async def update_workflow_metadata(
        self,
        tenant_id: str,
        workflow_id: UUID,
        update_data: WorkflowUpdate,
        audit_context: AuditContext | None = None,
    ) -> Workflow:
        """
        Update workflow metadata with audit logging.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            update_data: WorkflowUpdate schema with fields to update
            audit_context: Audit context for logging

        Returns:
            Updated workflow

        Raises:
            NotFoundError: If workflow not found
        """
        from analysi.repositories.workflow import NotFoundError

        workflow = await self.workflow_repo.update_workflow_metadata(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            update_data=update_data.model_dump(exclude_unset=True),
        )

        if workflow is None:
            raise NotFoundError(
                f"Workflow {workflow_id} not found for tenant {tenant_id}"
            )

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.update",
            resource_id=str(workflow_id),
            audit_context=audit_context,
            details={"updated_fields": update_data.model_dump(exclude_unset=True)},
        )

        return workflow

    async def add_node(
        self,
        tenant_id: str,
        workflow_id: UUID,
        node_request: AddNodeRequest,
        audit_context: AuditContext | None = None,
    ) -> Any:
        """
        Add node to workflow with audit logging. No validation (supports UI building).

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_request: AddNodeRequest schema
            audit_context: Audit context for logging

        Returns:
            Created WorkflowNode
        """
        from analysi.repositories.workflow import NotFoundError

        node_data = node_request.model_dump()
        node_data["kind"] = node_request.kind.value  # Convert enum to string
        try:
            node = await self.workflow_repo.add_node(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                node_data=node_data,
            )
        except ValueError as e:
            msg = str(e).lower()
            if "workflow" in msg and "not found" in msg:
                raise NotFoundError(str(e)) from e
            raise

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.node.add",
            resource_id=str(workflow_id),
            audit_context=audit_context,
            details={"node_id": node_request.node_id, "kind": node_request.kind.value},
        )

        return node

    async def update_node(
        self,
        tenant_id: str,
        workflow_id: UUID,
        node_id: str,
        update_data: WorkflowNodeUpdate,
        audit_context: AuditContext | None = None,
    ) -> Any:
        """
        Update workflow node with audit logging.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_id: Logical node ID
            update_data: WorkflowNodeUpdate schema
            audit_context: Audit context for logging

        Returns:
            Updated node
        """
        from analysi.repositories.workflow import NotFoundError

        node = await self.workflow_repo.update_node(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            node_id=node_id,
            update_data=update_data.model_dump(exclude_unset=True),
        )

        if node is None:
            raise NotFoundError(f"Node {node_id} not found in workflow {workflow_id}")

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.node.update",
            resource_id=str(workflow_id),
            audit_context=audit_context,
            details={
                "node_id": node_id,
                "updated_fields": update_data.model_dump(exclude_unset=True),
            },
        )

        return node

    async def remove_node(
        self,
        tenant_id: str,
        workflow_id: UUID,
        node_id: str,
        audit_context: AuditContext | None = None,
    ) -> bool:
        """
        Remove node (cascades edges) with audit logging.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_id: Logical node ID to remove
            audit_context: Audit context for logging

        Returns:
            True if deleted
        """
        from analysi.repositories.workflow import NotFoundError

        # First get the workflow to find the node's UUID
        workflow = await self.workflow_repo.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise NotFoundError(
                f"Workflow {workflow_id} not found for tenant {tenant_id}"
            )

        # Find the node to get its UUID
        node = next((n for n in workflow.nodes if n.node_id == node_id), None)
        if not node:
            raise NotFoundError(f"Node {node_id} not found in workflow {workflow_id}")

        # Get all edges connected to this node for cascade delete
        connected_edges = await self.workflow_repo.get_edges_for_node(
            workflow_id=workflow_id,
            node_uuid=node.id,
        )

        # Remove connected edges first (cascade)
        removed_edge_ids = []
        for edge in connected_edges:
            await self.workflow_repo.remove_edge(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                edge_id=edge.edge_id,
            )
            removed_edge_ids.append(edge.edge_id)

        # Remove the node
        deleted = await self.workflow_repo.remove_node(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            node_id=node_id,
        )

        if deleted:
            # Log audit event
            await self._log_audit(
                tenant_id=tenant_id,
                action="workflow.node.remove",
                resource_id=str(workflow_id),
                audit_context=audit_context,
                details={
                    "node_id": node_id,
                    "cascaded_edges": removed_edge_ids,
                },
            )

        return deleted

    async def add_edge(
        self,
        tenant_id: str,
        workflow_id: UUID,
        edge_request: AddEdgeRequest,
        audit_context: AuditContext | None = None,
    ) -> Any:
        """
        Add edge to workflow with audit logging. No validation (supports UI building).

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            edge_request: AddEdgeRequest schema
            audit_context: Audit context for logging

        Returns:
            Created WorkflowEdge
        """
        edge = await self.workflow_repo.add_edge(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            edge_data=edge_request.model_dump(),
        )

        # Log audit event
        await self._log_audit(
            tenant_id=tenant_id,
            action="workflow.edge.add",
            resource_id=str(workflow_id),
            audit_context=audit_context,
            details={
                "edge_id": edge_request.edge_id,
                "from_node_id": edge_request.from_node_id,
                "to_node_id": edge_request.to_node_id,
            },
        )

        return edge

    async def remove_edge(
        self,
        tenant_id: str,
        workflow_id: UUID,
        edge_id: str,
        audit_context: AuditContext | None = None,
    ) -> bool:
        """
        Remove edge with audit logging.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            edge_id: Logical edge ID to remove
            audit_context: Audit context for logging

        Returns:
            True if deleted
        """
        deleted = await self.workflow_repo.remove_edge(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            edge_id=edge_id,
        )

        if deleted:
            # Log audit event
            await self._log_audit(
                tenant_id=tenant_id,
                action="workflow.edge.remove",
                resource_id=str(workflow_id),
                audit_context=audit_context,
                details={"edge_id": edge_id},
            )

        return deleted

    async def validate_workflow_on_demand(
        self,
        tenant_id: str,
        workflow_id: UUID,
    ) -> ValidationResult:
        """
        On-demand validation: DAG structure + type propagation.

        Updates workflow status to 'validated' or 'invalid'.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID

        Returns:
            ValidationResult with valid, workflow_status, dag_errors, type_errors, warnings
        """
        from analysi.repositories.workflow import NotFoundError

        # Get workflow with nodes and edges
        workflow = await self.workflow_repo.get_workflow_by_id(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
        )

        if workflow is None:
            raise NotFoundError(
                f"Workflow {workflow_id} not found for tenant {tenant_id}"
            )

        dag_errors: list[str] = []
        type_errors: list[str] = []
        warnings: list[str] = []

        # Build node UUID to node_id map for edge lookup
        node_uuid_to_id = {n.id: n.node_id for n in workflow.nodes}

        # Convert nodes and edges to dicts for validation
        nodes = [
            {"node_id": n.node_id, "is_start_node": n.is_start_node}
            for n in workflow.nodes
        ]
        edges = [
            {
                "edge_id": e.edge_id,
                "from_node_id": node_uuid_to_id.get(e.from_node_uuid, "unknown"),
                "to_node_id": node_uuid_to_id.get(e.to_node_uuid, "unknown"),
            }
            for e in workflow.edges
        ]

        # DAG validation (cycle detection)
        try:
            is_dag = validate_workflow_dag(nodes, edges)
            if not is_dag:
                dag_errors.append("Cycle detected in workflow graph")
        except ValueError as e:
            dag_errors.append(str(e))

        # Check for disconnected nodes (nodes with no edges)
        if nodes and edges:
            connected_nodes = set()
            for edge in edges:
                connected_nodes.add(edge["from_node_id"])
                connected_nodes.add(edge["to_node_id"])
            for node in nodes:
                if node["node_id"] not in connected_nodes:
                    warnings.append(
                        f"Node '{node['node_id']}' is not connected to any edges"
                    )

        # Check for exactly one start node
        start_nodes = [n for n in nodes if n.get("is_start_node")]
        if len(start_nodes) == 0:
            warnings.append("No start node defined")
        elif len(start_nodes) > 1:
            dag_errors.append("Multiple start nodes defined")

        # Determine validity and status
        is_valid = len(dag_errors) == 0 and len(type_errors) == 0
        new_status = "validated" if is_valid else "invalid"

        # Update workflow status
        workflow.status = new_status
        await self.session.commit()

        return ValidationResult(
            valid=is_valid,
            workflow_status=new_status,
            dag_errors=dag_errors,
            type_errors=type_errors,
            warnings=warnings,
        )


class NodeTemplateService:
    """Service for node template business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.template_repo = NodeTemplateRepository(session)

    async def create_template(
        self, template_data: NodeTemplateCreate, tenant_id: str
    ) -> NodeTemplateResponse:
        """
        Create node template with validation.

        Args:
            template_data: Template definition
            tenant_id: Tenant identifier

        Returns:
            Created template

        Raises:
            ValueError: If validation fails
        """
        await self.validate_template_code(template_data.code)

        # Create template
        template = await self.template_repo.create_template(template_data, tenant_id)

        # Convert to response format
        return NodeTemplateResponse(
            id=template.id,
            resource_id=template.resource_id,
            tenant_id=template.tenant_id,
            name=template.name,
            description=template.description,
            input_schema=template.input_schema,
            output_schema=template.output_schema,
            code=template.code,
            language=template.language,
            type=template.type,
            kind=template.kind,
            enabled=template.enabled,
            revision_num=template.revision_num,
            created_at=template.created_at,
        )

    async def get_template(
        self, template_id: UUID, tenant_id: str | None = None
    ) -> NodeTemplateResponse | None:
        """
        Get template by ID, scoped to tenant.

        Args:
            template_id: Template ID
            tenant_id: Tenant scope for isolation

        Returns:
            Template or None if not found / not accessible
        """
        template = await self.template_repo.get_template_by_id(template_id, tenant_id)
        if not template:
            return None

        return NodeTemplateResponse(
            id=template.id,
            resource_id=template.resource_id,
            tenant_id=template.tenant_id,
            name=template.name,
            description=template.description,
            input_schema=template.input_schema,
            output_schema=template.output_schema,
            code=template.code,
            language=template.language,
            type=template.type,
            kind=template.kind,
            enabled=template.enabled,
            revision_num=template.revision_num,
            created_at=template.created_at,
        )

    async def list_templates(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        enabled_only: bool = False,
        name_filter: str | None = None,
    ) -> tuple[list[NodeTemplateResponse], dict[str, Any]]:
        """
        List templates with pagination.
        Includes both tenant-specific and system templates.

        Args:
            tenant_id: Tenant identifier
            skip: Number of records to skip
            limit: Maximum number of records
            enabled_only: Only return enabled templates
            name_filter: Optional name filter

        Returns:
            Tuple of (template_responses, metadata_dict) - consistent with other services
        """
        templates, total = await self.template_repo.list_templates(
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
            enabled_only=enabled_only,
            name_filter=name_filter,
        )

        # Convert to response format
        template_responses = []
        for template in templates:
            template_responses.append(
                NodeTemplateResponse(
                    id=template.id,
                    resource_id=template.resource_id,
                    tenant_id=template.tenant_id,
                    name=template.name,
                    description=template.description,
                    input_schema=template.input_schema,
                    output_schema=template.output_schema,
                    code=template.code,
                    language=template.language,
                    type=template.type,
                    kind=template.kind,
                    enabled=template.enabled,
                    revision_num=template.revision_num,
                    created_at=template.created_at,
                )
            )

        # Return pagination metadata (same pattern as other services)
        return template_responses, {
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def delete_template(
        self, template_id: UUID, tenant_id: str | None = None
    ) -> bool:
        """
        Delete template with validation, scoped to tenant.

        Args:
            template_id: Template ID
            tenant_id: Tenant scope. None = platform admin (unrestricted).

        Returns:
            True if deleted, False if not found
        """
        return await self.template_repo.delete_template(template_id, tenant_id)

    async def create_template_version(
        self, resource_id: UUID, template_data: NodeTemplateCreate
    ) -> NodeTemplateResponse:
        """
        Create new version of existing template.

        Args:
            resource_id: Existing resource ID
            template_data: New template definition

        Returns:
            Created template version
        """
        raise NotImplementedError("Template versioning to be implemented")

    async def validate_template_code(
        self, code: str, language: str = "python"
    ) -> dict[str, Any]:
        """
        Validate template code syntax and safety.

        Args:
            code: Template code to validate
            language: Programming language

        Returns:
            Validation result with details

        Raises:
            ValueError: If code validation fails
        """
        if not code or not code.strip():
            raise ValueError("Template code cannot be empty")

        # Basic Python syntax validation
        if language == "python":
            try:
                import ast

                ast.parse(code)
            except SyntaxError as e:
                raise ValueError(f"Python syntax error: {e}")

        return {
            "valid": True,
            "language": language,
            "line_count": len(code.split("\n")),
        }


def validate_dag_structure(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Validate workflow DAG structure and properties.

    Args:
        nodes: List of node definitions
        edges: List of edge definitions

    Returns:
        Validation result with cycle detection, connectivity analysis

    Raises:
        ValueError: If DAG validation fails
    """
    # Use the model validation function
    is_valid_dag = validate_workflow_dag(nodes, edges)

    # Additional analysis
    node_count = len(nodes)
    edge_count = len(edges)

    # Find connected components
    if node_count == 0:
        return {
            "valid": True,
            "has_cycles": False,
            "node_count": 0,
            "edge_count": 0,
            "connected_components": 0,
        }

    # Simple connectivity check
    node_ids = {node.get("node_id") for node in nodes}
    connected_nodes = set()

    for edge in edges:
        connected_nodes.add(edge.get("from_node_id"))
        connected_nodes.add(edge.get("to_node_id"))

    isolated_nodes = node_ids - connected_nodes

    return {
        "valid": is_valid_dag,
        "has_cycles": not is_valid_dag,
        "node_count": node_count,
        "edge_count": edge_count,
        "isolated_nodes": len(isolated_nodes),
        "connected_nodes": len(connected_nodes),
    }


def enrich_workflow_response(
    workflow: dict[str, Any],
    template_code: dict[UUID, str],
    task_details: dict[UUID, dict],
) -> dict[str, Any]:
    """
    Enrich workflow response with template code and task details.

    Args:
        workflow: Base workflow data
        template_code: Mapping of template_id to code
        task_details: Mapping of task_id to task details

    Returns:
        Enriched workflow response
    """
    # Make a copy to avoid modifying original
    enriched = workflow.copy()

    # Enrich nodes
    if "nodes" in enriched:
        for node in enriched["nodes"]:
            # Add template code if node has template_id
            template_id = node.get("node_template_id")
            if template_id and template_id in template_code:
                node["template_code"] = template_code[template_id]

            # Add task details if node has task_id
            task_id = node.get("task_id")
            if task_id and task_id in task_details:
                node["task_details"] = task_details[task_id]

    return enriched


def validate_node_schemas(nodes: list[dict[str, Any]]) -> bool:
    """
    Validate node schema definitions.

    Args:
        nodes: List of node definitions

    Returns:
        True if all schemas are valid

    Raises:
        ValueError: If schema validation fails
    """
    for i, node in enumerate(nodes):
        schemas = node.get("schemas", {})

        if not isinstance(schemas, dict):
            raise ValueError(f"Node {i} schemas must be a dictionary")

        # Validate required schemas based on node kind
        kind = node.get("kind")

        if kind == "task":
            required_schemas = ["input", "output"]
        elif kind == "transformation":
            required_schemas = ["input", "output_envelope", "output_result"]
        elif kind == "foreach":
            required_schemas = ["input", "output"]
        else:
            raise ValueError(f"Node {i} has invalid kind: {kind}")

        for schema_name in required_schemas:
            if schema_name not in schemas:
                raise ValueError(f"Node {i} missing required schema: {schema_name}")

            schema = schemas[schema_name]
            if not isinstance(schema, dict):
                raise ValueError(
                    f"Node {i} schema '{schema_name}' must be a dictionary"
                )

            # Basic JSON Schema validation
            if "type" not in schema:
                raise ValueError(
                    f"Node {i} schema '{schema_name}' missing 'type' field"
                )

    return True
