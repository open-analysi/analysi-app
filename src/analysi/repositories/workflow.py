"""
Repository layer for workflow-related database operations.
Handles CRUD operations for workflows, nodes, edges, and templates.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.models.task import Task
from analysi.models.workflow import NodeTemplate, Workflow, WorkflowEdge, WorkflowNode
from analysi.schemas.workflow import NodeTemplateCreate, WorkflowCreate


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""

    pass


class WorkflowRepository:
    """Repository for workflow operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _validate_task_ownership(self, task_id: UUID, tenant_id: str) -> None:
        """Verify task belongs to tenant. Raises ValueError if not."""
        from analysi.models.component import Component

        stmt = select(Component.id).where(
            Component.id == task_id,
            Component.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ValueError(
                f"Task {task_id} not found or not accessible for this tenant"
            )

    async def create_workflow(
        self,
        tenant_id: str,
        workflow_data: WorkflowCreate,
        created_by: UUID | None = None,
    ) -> Workflow:
        """
        Create a complete workflow with nodes and edges atomically.

        Args:
            tenant_id: Tenant identifier
            workflow_data: Complete workflow definition

        Returns:
            Created workflow with all relationships

        Raises:
            ValueError: If validation fails
            IntegrityError: If database constraints violated
        """
        try:
            # Create workflow first
            workflow = Workflow(
                tenant_id=tenant_id,
                name=workflow_data.name,
                description=workflow_data.description,
                is_dynamic=workflow_data.is_dynamic,
                io_schema=workflow_data.io_schema,
                data_samples=workflow_data.data_samples,
                app=workflow_data.app,
                created_by=created_by,
                planner_id=None,
            )
            self.session.add(workflow)
            await self.session.flush()  # Get workflow ID

            # Create nodes
            node_id_to_uuid_map = {}  # Map node_id to actual UUID for edge creation
            for node_data in workflow_data.nodes:
                # Validate template ownership before binding
                if node_data.node_template_id:
                    tmpl = await NodeTemplateRepository(
                        self.session
                    ).get_template_by_id(node_data.node_template_id, tenant_id)
                    if not tmpl or not tmpl.enabled:
                        raise ValueError(
                            f"Node '{node_data.node_id}' references inaccessible "
                            f"or disabled template: {node_data.node_template_id}"
                        )

                # Validate task belongs to this tenant
                if node_data.task_id:
                    await self._validate_task_ownership(node_data.task_id, tenant_id)

                # Build node arguments, excluding None foreach_config to let it default to SQL NULL
                node_args = {
                    "workflow_id": workflow.id,
                    "node_id": node_data.node_id,
                    "kind": node_data.kind.value,
                    "name": node_data.name,
                    "task_id": node_data.task_id,
                    "node_template_id": node_data.node_template_id,
                    "schemas": node_data.schemas,
                    "is_start_node": node_data.is_start_node,
                }

                # Only set foreach_config if it's not None to avoid JSON 'null' string
                if node_data.foreach_config is not None:
                    node_args["foreach_config"] = node_data.foreach_config

                node = WorkflowNode(**node_args)
                self.session.add(node)
                await self.session.flush()  # Get node UUID
                node_id_to_uuid_map[node_data.node_id] = node.id

            # Create edges
            for edge_data in workflow_data.edges:
                # Look up the actual UUIDs from node_ids
                from_uuid = node_id_to_uuid_map.get(edge_data.from_node_id)
                to_uuid = node_id_to_uuid_map.get(edge_data.to_node_id)

                if not from_uuid or not to_uuid:
                    raise ValueError(
                        f"Invalid node reference in edge {edge_data.edge_id}"
                    )

                edge = WorkflowEdge(
                    workflow_id=workflow.id,
                    edge_id=edge_data.edge_id,
                    from_node_uuid=from_uuid,
                    to_node_uuid=to_uuid,
                    alias=edge_data.alias,
                )
                self.session.add(edge)

            await self.session.commit()

            # Return workflow with relationships loaded
            return await self.get_workflow_by_id(tenant_id, workflow.id)

        except Exception:
            await self.session.rollback()
            raise

    async def get_workflow_by_id(
        self, tenant_id: str, workflow_id: UUID
    ) -> Workflow | None:
        """
        Get workflow by ID with all relationships loaded.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID

        Returns:
            Workflow with nodes and edges, or None if not found
        """
        stmt = (
            select(Workflow)
            .options(
                selectinload(Workflow.nodes).selectinload(WorkflowNode.node_template),
                selectinload(Workflow.nodes)
                .selectinload(WorkflowNode.task)
                .selectinload(Task.component),
                selectinload(Workflow.edges),
            )
            .where(and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id))
            # Force refresh from DB; prevents stale identity-map entries after
            # node/edge mutations within the same session.
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        name_filter: str | None = None,
        app: str | None = None,  # Project Delos: filter by content pack
    ) -> tuple[list[Workflow], int]:
        """
        List workflows with pagination and filtering.

        Args:
            tenant_id: Tenant identifier
            skip: Number of records to skip
            limit: Maximum number of records
            name_filter: Optional name substring filter
            app: Optional content pack filter

        Returns:
            Tuple of (workflows_list, total_count)
        """
        # Build base query
        base_query = select(Workflow).where(Workflow.tenant_id == tenant_id)

        # Apply name filter if provided
        if name_filter:
            base_query = base_query.where(Workflow.name.ilike(f"%{name_filter}%"))

        if app is not None:
            base_query = base_query.where(Workflow.app == app)

        # Get total count
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated results with all relationships
        # Note: Eagerly load task.component for cy_name access in list_workflows MCP tool
        list_stmt = (
            base_query.options(
                selectinload(Workflow.nodes).selectinload(WorkflowNode.node_template),
                selectinload(Workflow.nodes)
                .selectinload(WorkflowNode.task)
                .selectinload(Task.component),
                selectinload(Workflow.edges),
            )
            .order_by(Workflow.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(list_stmt)
        workflows = result.scalars().all()

        return list(workflows), total

    async def delete_workflow(self, tenant_id: str, workflow_id: UUID) -> bool:
        """
        Delete workflow and all related nodes/edges.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID

        Returns:
            True if deleted, False if not found
        """
        # Check if workflow exists first
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return False

        # Delete workflow (CASCADE will handle nodes and edges)
        stmt = delete(Workflow).where(
            and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount > 0

    async def get_workflow_with_enriched_data(
        self, tenant_id: str, workflow_id: UUID
    ) -> dict[str, Any] | None:
        """
        Get workflow with enriched node data (template code, task details).

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID

        Returns:
            Enriched workflow dictionary or None if not found
        """
        raise NotImplementedError("Workflow enrichment with JOINs to be implemented")

    async def get_workflows_using_task(
        self, tenant_id: str, task_component_id: UUID
    ) -> list[dict[str, Any]]:
        """
        Get workflows that have nodes referencing a specific task.

        Args:
            tenant_id: Tenant identifier
            task_component_id: The component ID of the task (task.component_id)

        Returns:
            List of workflows (id, name) that use the task
        """
        stmt = (
            select(Workflow.id, Workflow.name)
            .join(WorkflowNode, WorkflowNode.workflow_id == Workflow.id)
            .where(
                and_(
                    Workflow.tenant_id == tenant_id,
                    WorkflowNode.task_id == task_component_id,
                )
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return [{"id": str(row.id), "name": row.name} for row in rows]

    # ========== Mutation Methods ==========

    async def replace_workflow(
        self, tenant_id: str, workflow_id: UUID, workflow_data: WorkflowCreate
    ) -> Workflow:
        """
        Replace an existing workflow's nodes and edges while preserving the workflow ID.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID to replace
            workflow_data: New workflow definition

        Returns:
            Updated workflow with new nodes and edges

        Raises:
            NotFoundError: If workflow not found
        """
        # Check if workflow exists and get its ID
        existing = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not existing:
            raise NotFoundError(f"Workflow {workflow_id} not found")

        try:
            # Delete all existing edges first (they reference nodes via FK)
            delete_edges_stmt = delete(WorkflowEdge).where(
                WorkflowEdge.workflow_id == workflow_id
            )
            await self.session.execute(delete_edges_stmt)

            # Then delete all existing nodes
            delete_nodes_stmt = delete(WorkflowNode).where(
                WorkflowNode.workflow_id == workflow_id
            )
            await self.session.execute(delete_nodes_stmt)

            # Update workflow metadata using direct UPDATE statement to avoid
            # session caching issues
            update_stmt = (
                update(Workflow)
                .where(
                    and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
                )
                .values(
                    name=workflow_data.name,
                    description=workflow_data.description,
                    is_dynamic=workflow_data.is_dynamic,
                    io_schema=workflow_data.io_schema,
                    data_samples=workflow_data.data_samples,
                )
            )
            await self.session.execute(update_stmt)

            # Create new nodes
            node_id_to_uuid_map = {}  # Map node_id to actual UUID for edge creation
            for node_data in workflow_data.nodes:
                # Validate task belongs to this tenant
                if node_data.task_id:
                    await self._validate_task_ownership(node_data.task_id, tenant_id)

                # Build node arguments, excluding None foreach_config
                node_args = {
                    "workflow_id": workflow_id,
                    "node_id": node_data.node_id,
                    "kind": node_data.kind.value,
                    "name": node_data.name,
                    "task_id": node_data.task_id,
                    "node_template_id": node_data.node_template_id,
                    "schemas": node_data.schemas,
                    "is_start_node": node_data.is_start_node,
                }

                if node_data.foreach_config is not None:
                    node_args["foreach_config"] = node_data.foreach_config

                node = WorkflowNode(**node_args)
                self.session.add(node)
                await self.session.flush()
                node_id_to_uuid_map[node_data.node_id] = node.id

            # Create new edges
            for edge_data in workflow_data.edges:
                from_uuid = node_id_to_uuid_map.get(edge_data.from_node_id)
                to_uuid = node_id_to_uuid_map.get(edge_data.to_node_id)

                if not from_uuid or not to_uuid:
                    raise ValueError(
                        f"Invalid node reference in edge {edge_data.edge_id}"
                    )

                edge = WorkflowEdge(
                    workflow_id=workflow_id,
                    edge_id=edge_data.edge_id,
                    from_node_uuid=from_uuid,
                    to_node_uuid=to_uuid,
                    alias=edge_data.alias,
                )
                self.session.add(edge)

            await self.session.commit()

            # Fetch fresh data using a new query without any cached state
            # Using execution_options to bypass identity map cache
            stmt = (
                select(Workflow)
                .options(
                    selectinload(Workflow.nodes).selectinload(
                        WorkflowNode.node_template
                    ),
                    selectinload(Workflow.nodes)
                    .selectinload(WorkflowNode.task)
                    .selectinload(Task.component),
                    selectinload(Workflow.edges),
                )
                .where(
                    and_(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
                )
                .execution_options(populate_existing=True)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        except Exception:
            await self.session.rollback()
            raise

    async def update_workflow_metadata(
        self, tenant_id: str, workflow_id: UUID, update_data: dict[str, Any]
    ) -> Workflow | None:
        """
        Update workflow metadata (name, description, io_schema, data_samples).

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            update_data: Dict of fields to update (only non-None values applied)

        Returns:
            Updated workflow or None if not found
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return None

        # Apply updates for allowed fields
        allowed_fields = {"name", "description", "io_schema", "data_samples"}
        for field, value in update_data.items():
            if field in allowed_fields and value is not None:
                setattr(workflow, field, value)

        await self.session.commit()
        await self.session.refresh(workflow)
        return workflow

    async def add_node(
        self, tenant_id: str, workflow_id: UUID, node_data: dict[str, Any]
    ) -> WorkflowNode:
        """
        Add a node to an existing workflow.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_data: Node definition (node_id, kind, name, schemas, etc.)

        Returns:
            Created WorkflowNode

        Raises:
            ValueError: If workflow not found
            IntegrityError: If node_id already exists
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found for tenant {tenant_id}")

        # Validate template ownership before binding
        template_id = node_data.get("node_template_id")
        if template_id:
            tmpl = await NodeTemplateRepository(self.session).get_template_by_id(
                template_id, tenant_id
            )
            if not tmpl or not tmpl.enabled:
                raise ValueError(
                    f"Node references inaccessible or disabled template: {template_id}"
                )

        # Validate task belongs to this tenant
        if task_id := node_data.get("task_id"):
            await self._validate_task_ownership(task_id, tenant_id)

        # Handle kind as string or enum
        kind = node_data.get("kind")
        if hasattr(kind, "value"):
            kind = kind.value

        # Build node arguments - match create_workflow pattern
        node_args = {
            "workflow_id": workflow_id,
            "node_id": node_data["node_id"],
            "kind": kind,
            "name": node_data["name"],
            "is_start_node": node_data.get("is_start_node", False),
            "task_id": node_data.get("task_id"),
            "node_template_id": template_id,
            "schemas": node_data.get("schemas", {}),
        }
        # Only set foreach_config if not None (avoid JSON 'null' string issue)
        if node_data.get("foreach_config") is not None:
            node_args["foreach_config"] = node_data.get("foreach_config")

        node = WorkflowNode(**node_args)
        self.session.add(node)
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def update_node(
        self,
        tenant_id: str,
        workflow_id: UUID,
        node_id: str,
        update_data: dict[str, Any],
    ) -> WorkflowNode | None:
        """
        Update a workflow node's properties.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_id: Logical node ID within workflow
            update_data: Dict of fields to update

        Returns:
            Updated node or None if not found
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return None

        # Find the node by logical node_id
        node = None
        for n in workflow.nodes:
            if n.node_id == node_id:
                node = n
                break

        if not node:
            return None

        # Apply updates for allowed fields
        allowed_fields = {"name", "schemas", "task_id", "node_template_id"}
        for field, value in update_data.items():
            if field in allowed_fields and value is not None:
                # Validate task belongs to this tenant before binding
                if field == "task_id":
                    await self._validate_task_ownership(value, tenant_id)
                setattr(node, field, value)

        await self.session.commit()
        await self.session.refresh(node)
        return node

    async def remove_node(
        self, tenant_id: str, workflow_id: UUID, node_id: str
    ) -> bool:
        """
        Remove a node from workflow. Connected edges are cascade deleted.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            node_id: Logical node ID to remove

        Returns:
            True if deleted, False if not found
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return False

        # Find the node by logical node_id
        node = None
        for n in workflow.nodes:
            if n.node_id == node_id:
                node = n
                break

        if not node:
            return False

        # Get and delete connected edges first
        connected_edges = await self.get_edges_for_node(workflow_id, node.id)
        for edge in connected_edges:
            await self.session.delete(edge)

        # Delete the node
        await self.session.delete(node)
        await self.session.commit()
        return True

    async def add_edge(
        self, tenant_id: str, workflow_id: UUID, edge_data: dict[str, Any]
    ) -> WorkflowEdge:
        """
        Add an edge between two nodes in a workflow.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            edge_data: Edge definition (edge_id, from_node_id, to_node_id, alias)

        Returns:
            Created WorkflowEdge

        Raises:
            ValueError: If workflow or nodes not found
            IntegrityError: If edge_id already exists
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found for tenant {tenant_id}")

        # Build node_id to UUID mapping
        node_id_to_uuid = {n.node_id: n.id for n in workflow.nodes}

        from_node_id = edge_data["from_node_id"]
        to_node_id = edge_data["to_node_id"]

        if from_node_id not in node_id_to_uuid:
            raise ValueError(f"Source node '{from_node_id}' not found in workflow")
        if to_node_id not in node_id_to_uuid:
            raise ValueError(f"Target node '{to_node_id}' not found in workflow")

        edge = WorkflowEdge(
            workflow_id=workflow_id,
            edge_id=edge_data["edge_id"],
            from_node_uuid=node_id_to_uuid[from_node_id],
            to_node_uuid=node_id_to_uuid[to_node_id],
            alias=edge_data.get("alias"),
        )
        self.session.add(edge)
        await self.session.flush()
        await self.session.refresh(edge)
        return edge

    async def remove_edge(
        self, tenant_id: str, workflow_id: UUID, edge_id: str
    ) -> bool:
        """
        Remove an edge from workflow.

        Args:
            tenant_id: Tenant identifier
            workflow_id: Workflow ID
            edge_id: Logical edge ID to remove

        Returns:
            True if deleted, False if not found
        """
        workflow = await self.get_workflow_by_id(tenant_id, workflow_id)
        if not workflow:
            return False

        # Find the edge by logical edge_id
        edge = None
        for e in workflow.edges:
            if e.edge_id == edge_id:
                edge = e
                break

        if not edge:
            return False

        await self.session.delete(edge)
        await self.session.commit()
        return True

    async def get_edges_for_node(
        self, workflow_id: UUID, node_uuid: UUID
    ) -> list[WorkflowEdge]:
        """
        Get all edges connected to a node (as source or target).

        Args:
            workflow_id: Workflow ID
            node_uuid: Node UUID (not logical node_id)

        Returns:
            List of connected edges
        """
        from sqlalchemy import or_

        stmt = select(WorkflowEdge).where(
            and_(
                WorkflowEdge.workflow_id == workflow_id,
                or_(
                    WorkflowEdge.from_node_uuid == node_uuid,
                    WorkflowEdge.to_node_uuid == node_uuid,
                ),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class NodeTemplateRepository:
    """Repository for node template operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_template(
        self, template_data: NodeTemplateCreate, tenant_id: str
    ) -> NodeTemplate:
        """
        Create a new node template.

        Args:
            template_data: Template definition
            tenant_id: Tenant identifier (for tenant-specific templates)

        Returns:
            Created template

        Raises:
            IntegrityError: If constraints violated (e.g., multiple enabled versions)
        """
        from uuid import uuid4

        template = NodeTemplate(
            resource_id=uuid4(),  # New resource_id for new template
            tenant_id=tenant_id,
            name=template_data.name,
            description=template_data.description,
            input_schema=template_data.input_schema,
            output_schema=template_data.output_schema,
            code=template_data.code,
            language=template_data.language,
            type=template_data.type.value,
            kind=template_data.kind,
            enabled=True,
            revision_num=1,
        )

        self.session.add(template)

        # Integration tests control the transaction lifecycle via _is_test_session marker.
        # In test mode, flush without committing so the template is visible within the same
        # transaction (needed when create_workflow immediately looks up the template).
        is_integration_test_session = (
            hasattr(self.session, "_is_test_session")
            and self.session._is_test_session is True
        )
        if is_integration_test_session:
            await self.session.flush()
        else:
            await self.session.commit()

        return template

    async def get_template_by_id(
        self, template_id: UUID, tenant_id: str | None = None
    ) -> NodeTemplate | None:
        """
        Get template by ID, scoped to tenant.

        When tenant_id is provided, only returns the template if it belongs
        to that tenant OR is a system template (tenant_id IS NULL).

        Args:
            template_id: Template ID
            tenant_id: Optional tenant scope for isolation

        Returns:
            Template or None if not found / not accessible
        """
        from sqlalchemy import or_

        stmt = select(NodeTemplate).where(NodeTemplate.id == template_id)
        if tenant_id is not None:
            stmt = stmt.where(
                or_(
                    NodeTemplate.tenant_id == tenant_id,
                    NodeTemplate.tenant_id.is_(None),
                )
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        enabled_only: bool = False,
        name_filter: str | None = None,
    ) -> tuple[list[NodeTemplate], int]:
        """
        List templates with pagination and filtering.
        Includes both tenant-specific templates and system templates (tenant_id=NULL).

        Args:
            tenant_id: Tenant identifier
            skip: Number of records to skip
            limit: Maximum number of records
            enabled_only: Only return enabled templates
            name_filter: Optional name substring filter

        Returns:
            Tuple of (templates_list, total_count)
        """
        from sqlalchemy import or_

        # Build base query - include tenant-specific AND system templates
        base_query = select(NodeTemplate).where(
            or_(
                NodeTemplate.tenant_id == tenant_id,
                NodeTemplate.tenant_id.is_(None),  # System templates
            )
        )

        # Apply filters
        if enabled_only:
            base_query = base_query.where(NodeTemplate.enabled)

        if name_filter:
            base_query = base_query.where(NodeTemplate.name.ilike(f"%{name_filter}%"))

        # Get total count
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated results
        list_stmt = (
            base_query.order_by(NodeTemplate.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(list_stmt)
        templates = result.scalars().all()

        return list(templates), total

    async def delete_template(
        self, template_id: UUID, tenant_id: str | None = None
    ) -> bool:
        """
        Delete template, scoped to tenant.

        System templates (tenant_id IS NULL) cannot be deleted via
        tenant-scoped requests — only platform admins (tenant_id=None) can.

        Args:
            template_id: Template ID
            tenant_id: Tenant scope. None = platform admin (unrestricted).

        Returns:
            True if deleted, False if not found
        """
        template = await self.get_template_by_id(template_id, tenant_id)
        if not template:
            return False

        # Block tenant users from deleting system templates
        if tenant_id is not None and template.tenant_id is None:
            return False

        stmt = delete(NodeTemplate).where(NodeTemplate.id == template_id)
        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount > 0

    async def get_enabled_template_by_resource_id(
        self, resource_id: UUID
    ) -> NodeTemplate | None:
        """
        Get the currently enabled template for a resource_id.

        Args:
            resource_id: Resource ID (groups template versions)

        Returns:
            Enabled template or None if not found
        """
        raise NotImplementedError("Enabled template retrieval to be implemented")

    async def create_new_version(
        self, resource_id: UUID, template_data: NodeTemplateCreate
    ) -> NodeTemplate:
        """
        Create a new version of an existing template.

        Args:
            resource_id: Existing resource ID
            template_data: New template definition

        Returns:
            Created template with incremented revision_num
        """
        raise NotImplementedError("Template versioning to be implemented")


# Validation helper functions for workflow integrity


async def validate_node_template_references(
    session: AsyncSession, nodes: list[dict[str, Any]]
) -> bool:
    """
    Validate that all node template references exist and are enabled.

    Args:
        session: Database session
        nodes: List of node definitions

    Returns:
        True if all references are valid

    Raises:
        ValueError: If invalid references found
    """
    template_repo = NodeTemplateRepository(session)

    for node in nodes:
        if node.get("kind") == "transformation" and node.get("node_template_id"):
            template_id = node["node_template_id"]
            template = await template_repo.get_template_by_id(template_id)

            if not template:
                raise ValueError(
                    f"Node '{node.get('node_id')}' references non-existent template: {template_id}"
                )

            if not template.enabled:
                raise ValueError(
                    f"Node '{node.get('node_id')}' references disabled template: {template_id}"
                )

    return True


async def validate_task_references(
    session: AsyncSession, nodes: list[dict[str, Any]]
) -> bool:
    """
    Validate that all task references exist and are enabled.

    Args:
        session: Database session
        nodes: List of node definitions

    Returns:
        True if all references are valid

    Raises:
        ValueError: If invalid references found
    """
    # Basic validation to prevent workflow creation with invalid task references

    for node in nodes:
        if node.get("kind") == "task" and node.get("task_id"):
            # Placeholder validation — TODO: validate against actual Task table
            task_id = node["task_id"]
            if not isinstance(task_id, str | UUID):
                raise ValueError(
                    f"Node '{node.get('node_id')}' has invalid task_id format: {task_id}"
                )

    return True
