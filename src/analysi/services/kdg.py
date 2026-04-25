"""
Service layer for Knowledge Dependency Graph operations.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.component import Component, ComponentKind
from analysi.models.kdg_edge import KDGEdge
from analysi.repositories.kdg import KDGRepository
from analysi.schemas.kdg import (
    EdgeCreate,
    EdgeDirection,
    EdgeResponse,
    EdgeType,
    EdgeUpdate,
    GraphResponse,
    NodeResponse,
    NodeType,
)

logger = get_logger(__name__)


class KDGService:
    """Service for managing KDG operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session."""
        self.repository = KDGRepository(session)
        self.session = session

    async def create_edge(self, edge_data: EdgeCreate, tenant_id: str) -> EdgeResponse:
        """
        Create a new edge with validation.
        - Validates nodes exist
        - Prevents self-loops
        - Checks for duplicates
        - Detects cycles
        """
        # Validate nodes exist
        node_existence = await self.repository.validate_nodes_exist(
            [edge_data.source_id, edge_data.target_id], tenant_id
        )

        if not node_existence.get(edge_data.source_id):
            raise ValueError(f"Source node {edge_data.source_id} not found")
        if not node_existence.get(edge_data.target_id):
            raise ValueError(f"Target node {edge_data.target_id} not found")

        # Prevent self-loops
        if edge_data.source_id == edge_data.target_id:
            raise ValueError("Self-loops are not allowed")

        # Check for cycles
        would_create_cycle = await self.repository.detect_cycles(
            edge_data.source_id, edge_data.target_id, tenant_id
        )
        if would_create_cycle:
            raise ValueError("Creating this edge would create a cycle")

        # Check for duplicates
        existing_edges, _ = await self.repository.list_edges(
            tenant_id=tenant_id,
            source_id=edge_data.source_id,
            target_id=edge_data.target_id,
            relationship_type=edge_data.relationship_type.value,
        )
        if existing_edges:
            raise ValueError("Duplicate edge already exists")

        # Create the edge
        edge = await self.repository.create_edge(
            tenant_id=tenant_id,
            source_id=edge_data.source_id,
            target_id=edge_data.target_id,
            relationship_type=edge_data.relationship_type.value,
            is_required=edge_data.is_required,
            execution_order=edge_data.execution_order,
            metadata=edge_data.metadata,
        )

        return await self._edge_to_response(edge)

    async def get_edge(self, edge_id: UUID, tenant_id: str) -> EdgeResponse | None:
        """Get edge with full node details."""
        edge = await self.repository.get_edge_by_id(edge_id, tenant_id)
        if not edge:
            return None
        return await self._edge_to_response(edge)

    async def delete_edge(self, edge_id: UUID, tenant_id: str) -> bool:
        """Delete an edge."""
        edge = await self.repository.get_edge_by_id(edge_id, tenant_id)
        if not edge:
            return False
        await self.repository.delete_edge(edge)
        return True

    async def update_edge(
        self, edge_id: UUID, update_data: EdgeUpdate, tenant_id: str
    ) -> EdgeResponse | None:
        """Update edge metadata."""
        edge = await self.repository.get_edge_by_id(edge_id, tenant_id)
        if not edge:
            return None

        # Update fields if provided
        if update_data.is_required is not None:
            edge.is_required = update_data.is_required
        if update_data.execution_order is not None:
            edge.execution_order = update_data.execution_order
        if update_data.metadata is not None:
            edge.edge_metadata = update_data.metadata

        await self.session.commit()
        await self.session.refresh(edge)
        return await self._edge_to_response(edge)

    async def get_node(self, node_id: UUID, tenant_id: str) -> NodeResponse | None:
        """Get node details (Task or KU)."""
        component = await self.repository.get_node_by_id(node_id, tenant_id)
        if not component:
            return None
        return self._component_to_node_response(component)

    async def list_nodes(
        self,
        tenant_id: str,
        node_type: NodeType | None = None,
        search_query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[NodeResponse], int]:
        """List and search nodes."""
        # Convert NodeType enum to string for repository
        node_type_str = node_type.value if node_type else None

        components, total = await self.repository.list_nodes(
            tenant_id=tenant_id,
            node_type=node_type_str,
            search_query=search_query,
            limit=limit,
            offset=offset,
        )

        nodes = [self._component_to_node_response(comp) for comp in components]
        return nodes, total

    async def get_node_edges(
        self,
        node_id: UUID,
        tenant_id: str,
        direction: EdgeDirection = EdgeDirection.BOTH,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[EdgeResponse], int]:
        """Get edges connected to a node with direction filter."""
        edges, total = await self.repository.get_node_edges(
            node_id=node_id,
            tenant_id=tenant_id,
            direction=direction,
            limit=limit,
            offset=offset,
        )

        edge_responses = []
        for edge in edges:
            try:
                edge_response = await self._edge_to_response(edge)
                edge_responses.append(edge_response)
            except ValueError:
                # Skip edges with invalid nodes
                continue

        return edge_responses, total

    async def get_node_graph(
        self, node_id: UUID, tenant_id: str, depth: int = 2
    ) -> GraphResponse:
        """
        Get subgraph starting from node using BFS traversal.
        Default depth is 2, max depth is 5 for performance.
        """
        # Enforce max depth limit
        if depth > 5:
            depth = 5
        if depth < 0:
            depth = 0

        components, edges = await self.repository.get_subgraph(
            start_node_id=node_id,
            tenant_id=tenant_id,
            max_depth=depth,
        )

        # Convert components to node responses
        nodes = [self._component_to_node_response(comp) for comp in components]

        # Convert edges to edge responses
        edge_responses = []
        for edge in edges:
            try:
                edge_response = await self._edge_to_response(edge)
                edge_responses.append(edge_response)
            except ValueError:
                # Skip edges with invalid nodes
                continue

        return GraphResponse(
            nodes=nodes,
            edges=edge_responses,
            traversal_depth=depth,
            total_nodes=len(nodes),
            total_edges=len(edge_responses),
        )

    async def validate_no_cycles(
        self, source_id: UUID, target_id: UUID, tenant_id: str
    ) -> bool:
        """
        Validate that adding an edge won't create a cycle.
        Returns True if safe, False if cycle would be created.
        """
        would_create_cycle = await self.repository.detect_cycles(
            source_id, target_id, tenant_id
        )
        return not would_create_cycle

    def _component_to_node_response(self, component: Component) -> NodeResponse:  # noqa: C901
        """Convert Component model to NodeResponse schema."""
        # Determine node type based on component kind and KU type
        if component.kind == ComponentKind.TASK:
            node_type = NodeType.TASK
            ku_type = None
        elif component.kind == ComponentKind.MODULE:
            # It's a knowledge module (skill)
            node_type = NodeType.SKILL
            ku_type = None
        else:
            # It's a knowledge unit - determine the specific KU type
            if component.knowledge_unit:
                ku_type = component.knowledge_unit.ku_type
                if ku_type == "document":
                    node_type = NodeType.DOCUMENT
                elif ku_type == "table":
                    node_type = NodeType.TABLE
                elif ku_type == "index":
                    node_type = NodeType.INDEX
                elif ku_type == "tool":
                    node_type = NodeType.TOOL
                else:
                    node_type = NodeType.DOCUMENT  # Default fallback
            else:
                node_type = NodeType.DOCUMENT
                ku_type = "document"

        # Build base node response
        node_data = {
            "id": component.id,
            "type": node_type,
            "name": component.name,
            "description": component.description,
            "version": component.version,
            "status": component.status,
            "categories": component.categories or [],
            "created_at": component.created_at,
            "updated_at": component.updated_at,
            "created_by": component.created_by
            if isinstance(component.created_by, UUID)
            else None,
        }

        # Add type-specific fields
        if node_type == NodeType.TASK:
            # Task-specific fields
            if hasattr(component, "task") and component.task:
                node_data.update(
                    {
                        "function": component.task.function,
                        "scope": component.task.scope,
                    }
                )
        else:
            # KU-specific fields
            node_data["ku_type"] = ku_type
            if component.knowledge_unit:
                ku = component.knowledge_unit
                if ku_type == "document" and hasattr(ku, "document"):
                    if ku.document:
                        node_data["document_type"] = ku.document.doc_format
                elif ku_type == "table" and hasattr(ku, "table"):
                    if ku.table:
                        node_data["row_count"] = ku.table.row_count
                        node_data["column_count"] = ku.table.column_count
                elif ku_type == "index" and hasattr(ku, "index") and ku.index:
                    node_data["index_type"] = ku.index.index_type
                    node_data["build_status"] = ku.index.build_status

        return NodeResponse(**node_data)

    async def _edge_to_response(self, edge: KDGEdge) -> EdgeResponse:
        """Convert KDGEdge model to EdgeResponse schema."""
        # Get source and target nodes
        source_component = await self.repository.get_node_by_id(
            edge.source_id, edge.tenant_id
        )
        target_component = await self.repository.get_node_by_id(
            edge.target_id, edge.tenant_id
        )

        if not source_component or not target_component:
            raise ValueError(f"Edge {edge.id} has invalid source or target node")

        source_node = self._component_to_node_response(source_component)
        target_node = self._component_to_node_response(target_component)

        return EdgeResponse(
            id=edge.id,
            source_node=source_node,
            target_node=target_node,
            relationship_type=EdgeType(edge.relationship_type),
            is_required=edge.is_required,
            execution_order=edge.execution_order,
            metadata=edge.edge_metadata or {},
            created_at=edge.created_at,
            updated_at=edge.updated_at,
        )

    async def get_global_graph(  # noqa: C901
        self,
        tenant_id: str,
        include_tasks: bool = True,
        include_knowledge_units: bool = True,
        include_tools: bool = True,
        include_skills: bool = True,
        depth: int | None = None,
        max_nodes: int | None = None,
    ) -> dict[str, Any]:
        """
        Get global knowledge graph with filtering options.
        """
        # Get all nodes based on filtering
        nodes = []
        node_ids = set()
        limit = max_nodes if max_nodes else 1000

        if include_tasks:
            tasks, _ = await self.list_nodes(
                tenant_id=tenant_id,
                node_type=NodeType.TASK,
                limit=limit,
                offset=0,
            )
            for task in tasks:
                if len(nodes) < limit:
                    nodes.append(self._node_to_web_format(task))
                    node_ids.add(task.id)

        if include_knowledge_units:
            # Get all KU types (document, table, index)
            for ku_type in [NodeType.DOCUMENT, NodeType.TABLE, NodeType.INDEX]:
                kus, _ = await self.list_nodes(
                    tenant_id=tenant_id,
                    node_type=ku_type,
                    limit=limit,
                    offset=0,
                )
                for ku in kus:
                    if len(nodes) < limit:
                        nodes.append(self._node_to_web_format(ku))
                        node_ids.add(ku.id)

        if include_tools:
            tools, _ = await self.list_nodes(
                tenant_id=tenant_id,
                node_type=NodeType.TOOL,
                limit=limit,
                offset=0,
            )
            for tool in tools:
                if len(nodes) < limit:
                    nodes.append(self._node_to_web_format(tool))
                    node_ids.add(tool.id)

        if include_skills:
            skills, _ = await self.list_nodes(
                tenant_id=tenant_id,
                node_type=NodeType.SKILL,
                limit=limit,
                offset=0,
            )
            for skill in skills:
                if len(nodes) < limit:
                    nodes.append(self._node_to_web_format(skill))
                    node_ids.add(skill.id)

        # Get edges connecting the included nodes
        edges = []
        all_edges = await self.repository.get_all_edges(tenant_id)

        logger.debug(
            "getglobalgraph_found_total_edges_nodeids",
            all_edges_count=len(all_edges),
            node_ids_count=len(node_ids),
        )

        unmatched_sources = set()
        unmatched_targets = set()

        for edge in all_edges:
            source_match = edge.source_id in node_ids
            target_match = edge.target_id in node_ids
            if source_match and target_match:
                edges.append(self._edge_to_web_format(edge))
            else:
                if not source_match:
                    unmatched_sources.add(edge.source_id)
                if not target_match:
                    unmatched_targets.add(edge.target_id)

        if unmatched_sources or unmatched_targets:
            logger.debug(
                "get_global_graph_unmatched_ids",
                unmatched_source_count=len(unmatched_sources),
                unmatched_target_count=len(unmatched_targets),
                sample_unmatched_sources=[str(s) for s in list(unmatched_sources)[:3]],
                sample_unmatched_targets=[str(t) for t in list(unmatched_targets)[:3]],
            )

        return {"nodes": nodes, "edges": edges}

    def _node_to_web_format(self, node: NodeResponse) -> dict[str, Any]:
        """Convert NodeResponse to web app format."""
        return {
            "id": str(node.id),
            "type": node.type,
            "label": node.name,
            "data": {
                "name": node.name,
                "description": node.description,
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "updated_at": node.updated_at.isoformat() if node.updated_at else None,
                "created_by": str(node.created_by) if node.created_by else None,
            },
        }

    def _edge_to_web_format(self, edge) -> dict[str, Any]:
        """Convert edge to web app format."""
        return {
            "source": str(edge.source_id),
            "target": str(edge.target_id),
            "type": edge.relationship_type,
            "data": edge.edge_metadata or {},
        }
