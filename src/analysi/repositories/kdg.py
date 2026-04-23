"""
Repository for Knowledge Dependency Graph operations.
"""

from collections import deque
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.config.logging import get_logger
from analysi.models.component import Component, ComponentKind
from analysi.models.kdg_edge import KDGEdge
from analysi.models.knowledge_unit import KnowledgeUnit
from analysi.schemas.kdg import EdgeDirection

logger = get_logger(__name__)


class KDGRepository:
    """Repository for managing KDG edges and graph operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def create_edge(
        self,
        tenant_id: str,
        source_id: UUID,
        target_id: UUID,
        relationship_type: str,
        is_required: bool = False,
        execution_order: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> KDGEdge:
        """Create a new edge between nodes."""
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            is_required=is_required,
            execution_order=execution_order,
            edge_metadata=metadata or {},
        )
        self.session.add(edge)
        await self.session.commit()
        await self.session.refresh(edge)
        return edge

    async def get_edge_by_id(self, edge_id: UUID, tenant_id: str) -> KDGEdge | None:
        """Get a single edge by ID."""
        query = select(KDGEdge).where(
            and_(KDGEdge.id == edge_id, KDGEdge.tenant_id == tenant_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_edge(self, edge: KDGEdge) -> None:
        """Delete an edge."""
        await self.session.delete(edge)
        await self.session.commit()

    async def list_edges(
        self,
        tenant_id: str,
        source_id: UUID | None = None,
        target_id: UUID | None = None,
        relationship_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[KDGEdge], int]:
        """List edges with optional filters."""
        conditions = [KDGEdge.tenant_id == tenant_id]

        if source_id:
            conditions.append(KDGEdge.source_id == source_id)
        if target_id:
            conditions.append(KDGEdge.target_id == target_id)
        if relationship_type:
            conditions.append(KDGEdge.relationship_type == relationship_type)

        # Get total count
        count_query = select(KDGEdge).where(and_(*conditions))
        count_result = await self.session.execute(count_query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = select(KDGEdge).where(and_(*conditions)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        edges = list(result.scalars().all())

        return edges, total

    async def get_node_edges(
        self,
        node_id: UUID,
        tenant_id: str,
        direction: EdgeDirection = EdgeDirection.BOTH,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[KDGEdge], int]:
        """Get edges for a specific node with direction filter."""
        conditions = [KDGEdge.tenant_id == tenant_id]

        if direction == EdgeDirection.IN:
            conditions.append(KDGEdge.target_id == node_id)
        elif direction == EdgeDirection.OUT:
            conditions.append(KDGEdge.source_id == node_id)
        elif direction == EdgeDirection.BOTH:
            conditions.append(
                or_(KDGEdge.source_id == node_id, KDGEdge.target_id == node_id)
            )

        # Get total count
        count_query = select(KDGEdge).where(and_(*conditions))
        count_result = await self.session.execute(count_query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = select(KDGEdge).where(and_(*conditions)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        edges = list(result.scalars().all())

        logger.debug(
            "get_node_edges",
            node_id=str(node_id),
            direction=str(direction),
            edges_found=len(edges),
            total=total,
        )

        return edges, total

    async def get_node_by_id(self, node_id: UUID, tenant_id: str) -> Component | None:
        """Get a node (Task or KU) by Component ID."""
        query = (
            select(Component)
            .options(
                selectinload(Component.task), selectinload(Component.knowledge_unit)
            )
            .where(and_(Component.id == node_id, Component.tenant_id == tenant_id))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_nodes(
        self,
        tenant_id: str,
        node_type: str | None = None,
        search_query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Component], int]:
        """List nodes with optional type and search filters."""
        conditions = [Component.tenant_id == tenant_id]

        # Filter by node type
        if node_type:
            if node_type == "task":
                conditions.append(Component.kind == ComponentKind.TASK)
            elif node_type == "skill":
                # Skills are stored as knowledge modules
                conditions.append(Component.kind == ComponentKind.MODULE)
            else:
                # For KU types, filter by kind=KU and then ku_type
                conditions.append(Component.kind == ComponentKind.KU)
                conditions.append(KnowledgeUnit.ku_type == node_type)

        # Search filter
        if search_query:
            search_conditions = []
            search_terms = search_query.lower().split()
            for term in search_terms:
                search_conditions.append(Component.name.ilike(f"%{term}%"))
                search_conditions.append(Component.description.ilike(f"%{term}%"))
            conditions.append(or_(*search_conditions))

        # Build base query with joins and eager loading
        query_base = select(Component).options(
            selectinload(Component.knowledge_unit),
            selectinload(Component.task),
            selectinload(Component.knowledge_module),
        )
        # Only join KnowledgeUnit for KU types (not task, not skill)
        if node_type and node_type not in ("task", "skill"):
            query_base = query_base.join(
                KnowledgeUnit, Component.id == KnowledgeUnit.component_id
            )

        # Get total count
        count_query = query_base.where(and_(*conditions))
        count_result = await self.session.execute(count_query)
        total = len(list(count_result.scalars().all()))

        # Get paginated results
        query = query_base.where(and_(*conditions)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        nodes = list(result.scalars().all())

        return nodes, total

    async def get_subgraph(
        self, start_node_id: UUID, tenant_id: str, max_depth: int = 2
    ) -> tuple[list[Component], list[KDGEdge]]:
        """
        Perform BFS traversal from start node up to max_depth.
        Returns (nodes, edges) found during traversal.
        """
        visited_nodes = set()
        visited_edges = set()
        nodes_to_return = []
        edges_to_return = []

        # BFS queue: (node_id, current_depth)
        queue = deque([(start_node_id, 0)])
        visited_nodes.add(start_node_id)

        while queue:
            current_node_id, depth = queue.popleft()

            # Get current node
            node = await self.get_node_by_id(current_node_id, tenant_id)
            if node:
                nodes_to_return.append(node)

            # Don't traverse deeper if at max depth
            if depth >= max_depth:
                continue

            # Get all edges for this node (both directions)
            edges, _ = await self.get_node_edges(
                current_node_id, tenant_id, EdgeDirection.BOTH, limit=1000
            )

            for edge in edges:
                if edge.id not in visited_edges:
                    visited_edges.add(edge.id)
                    edges_to_return.append(edge)

                    # Find the other node in this edge
                    other_node_id = (
                        edge.target_id
                        if edge.source_id == current_node_id
                        else edge.source_id
                    )

                    # Add to queue if not visited
                    if other_node_id not in visited_nodes:
                        visited_nodes.add(other_node_id)
                        queue.append((other_node_id, depth + 1))

        return nodes_to_return, edges_to_return

    async def detect_cycles(
        self, source_id: UUID, target_id: UUID, tenant_id: str
    ) -> bool:
        """
        Check if adding an edge from source to target would create a cycle.
        Returns True if cycle would be created.
        """
        # If source equals target, it's a self-loop (cycle)
        if source_id == target_id:
            return True

        # Check if there's already a path from target to source
        # If yes, adding source->target would create a cycle
        visited = set()
        queue = deque([target_id])
        visited.add(target_id)

        while queue:
            current_node_id = queue.popleft()

            # If we can reach source from target, adding source->target creates cycle
            if current_node_id == source_id:
                return True

            # Get outgoing edges from current node
            edges, _ = await self.get_node_edges(
                current_node_id, tenant_id, EdgeDirection.OUT, limit=1000
            )

            for edge in edges:
                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append(edge.target_id)

        return False

    async def validate_nodes_exist(
        self, node_ids: list[UUID], tenant_id: str
    ) -> dict[UUID, bool]:
        """
        Check if Component nodes exist for the given tenant.
        Returns dict mapping Component ID to existence boolean.
        """
        if not node_ids:
            return {}

        # Simple Component ID lookup
        query = select(Component.id).where(
            and_(Component.id.in_(node_ids), Component.tenant_id == tenant_id)
        )
        result = await self.session.execute(query)
        existing_component_ids = set(result.scalars().all())

        # Return existence map
        return {node_id: node_id in existing_component_ids for node_id in node_ids}

    async def get_all_edges(self, tenant_id: str) -> list[KDGEdge]:
        """Get all edges for a tenant."""
        stmt = select(KDGEdge).where(KDGEdge.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        edges = list(result.scalars().all())
        logger.debug(
            "getalledges_tenant_found_edges",
            tenant_id=tenant_id,
            edges_count=len(edges),
        )
        if edges:
            sample = edges[0]
            logger.debug(
                "sample_edge",
                source_id=str(sample.source_id),
                target_id=str(sample.target_id),
                relationship_type=sample.relationship_type,
            )
        return edges
