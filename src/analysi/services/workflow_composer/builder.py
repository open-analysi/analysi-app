"""
Composer Workflow Builder - Create database workflow objects from composition.

Converts validated ParsedComposition into workflow, nodes, and edges.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.workflow import Workflow, WorkflowEdge, WorkflowNode
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.audit_context import AuditContext

from .models import ParsedComposition, ResolvedTask, ResolvedTemplate


class ComposerWorkflowBuilder:
    """Build workflow database objects from composition graph."""

    def __init__(self, session: AsyncSession):
        """
        Initialize ComposerWorkflowBuilder.

        Args:
            session: Database session
        """
        self.session = session

    async def build_workflow(
        self,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        workflow_name: str,
        workflow_description: str,
        tenant_id: str,
        created_by: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        audit_context: AuditContext | None = None,
        data_samples: list[dict[str, Any]] | None = None,
    ) -> UUID:
        """
        Create workflow with nodes and edges in database.

        Args:
            composition: Parsed composition graph
            resolved_nodes: Resolved tasks/templates
            workflow_name: Workflow name
            workflow_description: Workflow description
            tenant_id: Tenant ID
            created_by: Creator username
            input_schema: Inferred workflow input schema
            output_schema: Inferred workflow output schema
            audit_context: Optional audit context for logging
            data_samples: Optional data samples for workflow testing.
                         If not provided, workflow starts with empty samples.
                         Caller should pass the triggering alert as a sample.

        Returns:
            Created workflow UUID
        """
        try:
            # Create workflow record
            # data_samples defaults to empty list if not provided by caller
            workflow_id = await self._create_workflow(
                workflow_name=workflow_name,
                workflow_description=workflow_description,
                tenant_id=tenant_id,
                created_by=created_by,
                input_schema=input_schema,
                output_schema=output_schema,
                data_samples=data_samples or [],
            )

            # Create nodes
            node_id_map = await self._create_nodes(
                workflow_id=workflow_id,
                composition=composition,
                resolved_nodes=resolved_nodes,
                tenant_id=tenant_id,
            )

            # Create edges
            await self._create_edges(
                workflow_id=workflow_id,
                composition=composition,
                node_id_map=node_id_map,
                tenant_id=tenant_id,
            )

            # Commit transaction
            await self.session.commit()

            # Log audit event
            await self._log_audit(
                tenant_id=tenant_id,
                action="workflow.create",
                resource_id=str(workflow_id),
                audit_context=audit_context,
                details={
                    "workflow_name": workflow_name,
                    "node_count": len(composition.nodes),
                    "source": "compose_workflow",
                },
            )

            return workflow_id

        except Exception:
            await self.session.rollback()
            raise

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

    async def _create_workflow(
        self,
        workflow_name: str,
        workflow_description: str,
        tenant_id: str,
        created_by: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        data_samples: list[dict[str, Any]] | None = None,
    ) -> UUID:
        """
        Create workflow record in database.

        Args:
            workflow_name: Workflow name
            workflow_description: Workflow description
            tenant_id: Tenant ID
            created_by: Creator username
            input_schema: Workflow input schema
            output_schema: Workflow output schema
            data_samples: Example input data from first task

        Returns:
            Created workflow UUID
        """
        # Generate workflow ID explicitly for testability
        workflow_id = uuid4()

        # Create workflow with io_schema containing input/output
        workflow = Workflow(
            id=workflow_id,
            tenant_id=tenant_id,
            name=workflow_name,
            description=workflow_description,
            is_dynamic=False,
            io_schema={"input": input_schema, "output": output_schema},
            data_samples=data_samples,
            created_by=created_by,
            status="draft",
        )
        self.session.add(workflow)
        await self.session.flush()  # Get workflow ID

        return workflow_id

    async def _create_nodes(
        self,
        workflow_id: UUID,
        composition: ParsedComposition,
        resolved_nodes: dict[str, ResolvedTask | ResolvedTemplate],
        tenant_id: str,
    ) -> dict[str, UUID]:
        """
        Create workflow nodes in database.

        Args:
            workflow_id: Parent workflow ID
            composition: Parsed composition graph
            resolved_nodes: Resolved tasks/templates
            tenant_id: Tenant ID

        Returns:
            Mapping of node_id to node UUID
        """
        node_id_map: dict[str, UUID] = {}

        # Find minimum layer to mark start node
        min_layer = min(node.layer for node in composition.nodes)

        for parsed_node in composition.nodes:
            # Get resolved task or template
            resolved = resolved_nodes[parsed_node.node_id]

            # Determine node kind and references
            if isinstance(resolved, ResolvedTask):
                kind = "task"
                task_id = resolved.task_id
                node_template_id = None
                name = resolved.name
            elif isinstance(resolved, ResolvedTemplate):
                kind = "transformation"
                task_id = None
                node_template_id = resolved.template_id
                name = resolved.name
            else:
                raise ValueError(f"Unknown resolved node type: {type(resolved)}")

            # Build schemas dict
            schemas = {
                "input": resolved.input_schema or {"type": "object"},
                "output": resolved.output_schema or {"type": "object"},
            }

            # Mark first layer nodes as start nodes
            is_start_node = parsed_node.layer == min_layer

            # Generate node UUID explicitly for testability
            node_uuid = uuid4()

            # Create workflow node
            node = WorkflowNode(
                id=node_uuid,
                workflow_id=workflow_id,
                node_id=parsed_node.node_id,
                kind=kind,
                name=name,
                task_id=task_id,
                node_template_id=node_template_id,
                schemas=schemas,
                is_start_node=is_start_node,
            )
            self.session.add(node)
            await self.session.flush()  # Get node UUID

            # Store mapping
            node_id_map[parsed_node.node_id] = node_uuid

        return node_id_map

    async def _create_edges(
        self,
        workflow_id: UUID,
        composition: ParsedComposition,
        node_id_map: dict[str, UUID],
        tenant_id: str,
    ) -> None:
        """
        Create workflow edges in database.

        Args:
            workflow_id: Parent workflow ID
            composition: Parsed composition graph
            node_id_map: Mapping of node_id to node UUID
            tenant_id: Tenant ID
        """
        for parsed_edge in composition.edges:
            # Look up node UUIDs from mapping
            from_uuid = node_id_map.get(parsed_edge.from_node_id)
            to_uuid = node_id_map.get(parsed_edge.to_node_id)

            if not from_uuid or not to_uuid:
                raise ValueError(
                    f"Invalid node reference in edge {parsed_edge.edge_id}: "
                    f"from={parsed_edge.from_node_id}, to={parsed_edge.to_node_id}"
                )

            # Create workflow edge
            edge = WorkflowEdge(
                workflow_id=workflow_id,
                edge_id=parsed_edge.edge_id,
                from_node_uuid=from_uuid,
                to_node_uuid=to_uuid,
                alias=None,
            )
            self.session.add(edge)
