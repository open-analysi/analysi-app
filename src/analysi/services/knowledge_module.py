"""
Knowledge Module (Skill) service for business logic.

Handles skill management, document linking, and content retrieval.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.knowledge_module import KnowledgeModule
from analysi.repositories.knowledge_module import KnowledgeModuleRepository
from analysi.schemas.skill import SkillCreate, SkillUpdate


class KnowledgeModuleService:
    """Service for Knowledge Module (Skill) business logic."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session."""
        self.repository = KnowledgeModuleRepository(session)
        self.session = session

    async def create_skill(
        self, tenant_id: str, skill_data: SkillCreate, created_by: UUID | None = None
    ) -> KnowledgeModule:
        """
        Create a new skill module.

        Args:
            tenant_id: Tenant identifier
            skill_data: Skill creation data
            created_by: UUID of the authenticated user (from audit_context)

        Returns:
            Created KnowledgeModule
        """
        skill_dict = skill_data.model_dump()
        # Inject server-derived created_by (prevent client impersonation)
        if created_by is not None:
            skill_dict["created_by"] = created_by
        return await self.repository.create_skill(tenant_id, skill_dict)

    async def get_skill(
        self, component_id: UUID, tenant_id: str
    ) -> KnowledgeModule | None:
        """
        Get a skill by its component ID.

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier

        Returns:
            KnowledgeModule if found, None otherwise
        """
        return await self.repository.get_skill_by_id(component_id, tenant_id)

    async def get_skill_by_cy_name(
        self, tenant_id: str, cy_name: str, app: str = "default"
    ) -> KnowledgeModule | None:
        """
        Get a skill by its cy_name.

        Args:
            tenant_id: Tenant identifier
            cy_name: Script-friendly identifier
            app: Application context

        Returns:
            KnowledgeModule if found, None otherwise
        """
        return await self.repository.get_skill_by_cy_name(tenant_id, cy_name, app)

    async def list_skills(
        self,
        tenant_id: str,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
        app: str | None = None,  # Project Delos: filter by content pack
    ) -> tuple[list[KnowledgeModule], dict[str, Any]]:
        """
        List skills with optional filters.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter
            search: Optional search query
            skip: Pagination offset
            limit: Pagination limit
            categories: Optional categories filter (AND semantics)
            app: Optional content pack filter

        Returns:
            Tuple of (list of modules, metadata with total count)
        """
        return await self.repository.list_skills(
            tenant_id=tenant_id,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
            categories=categories,
            app=app,
        )

    async def update_skill(
        self,
        component_id: UUID,
        tenant_id: str,
        update_data: SkillUpdate,
    ) -> KnowledgeModule | None:
        """
        Update an existing skill.

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier
            update_data: Fields to update

        Returns:
            Updated KnowledgeModule if found, None otherwise
        """
        module = await self.repository.get_skill_by_id(component_id, tenant_id)
        if not module:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        return await self.repository.update_skill(module, update_dict)

    async def delete_skill(self, component_id: UUID, tenant_id: str) -> bool:
        """
        Delete a skill.

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier

        Returns:
            True if deleted, False if not found
        """
        return await self.repository.delete_skill(component_id, tenant_id)

    async def check_skill_delete(
        self, component_id: UUID, tenant_id: str
    ) -> dict[str, Any]:
        """
        Check what would be affected by deleting a skill.

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier

        Returns:
            Dictionary with affected items
        """
        return await self.repository.check_skill_delete(component_id, tenant_id)

    # --- Document Management ---

    async def add_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
        namespace_path: str,
    ) -> dict[str, Any]:
        """
        Link a document to a skill.

        After linking, auto-sets the document's component.namespace to /{skill_cy_name}/
        so the document is scoped to the skill.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            document_id: Document KU's component_id
            namespace_path: Path within the skill

        Returns:
            Edge details

        Raises:
            ValueError: If path conflicts with existing document
        """
        edge = await self.repository.add_document_to_skill(
            tenant_id, skill_id, document_id, namespace_path
        )

        # Auto-set namespace on the document's component to scope it to this skill
        skill = await self.repository.get_skill_by_id(skill_id, tenant_id)
        if skill and skill.component.cy_name:
            from sqlalchemy import select

            from analysi.models.component import Component

            target_namespace = f"/{skill.component.cy_name}/"

            stmt = select(Component).where(
                Component.id == document_id,
                Component.tenant_id == tenant_id,
            )
            result = await self.session.execute(stmt)
            doc_component = result.scalar_one_or_none()
            if doc_component:
                # Idempotent: if already in target namespace, skip
                if doc_component.namespace == target_namespace:
                    pass  # Already linked, nothing to do
                else:
                    # Check for conflict: another doc with same name in target namespace
                    conflict_stmt = select(Component).where(
                        Component.tenant_id == tenant_id,
                        Component.namespace == target_namespace,
                        Component.name == doc_component.name,
                        Component.ku_type == doc_component.ku_type,
                        Component.id != document_id,
                    )
                    conflict_result = await self.session.execute(conflict_stmt)
                    existing = conflict_result.scalar_one_or_none()
                    if existing:
                        # Document already exists in skill - skip this one
                        # (caller created a duplicate that should be cleaned up)
                        pass
                    else:
                        doc_component.namespace = target_namespace
                        await self.session.flush()

        return {
            "edge_id": str(edge.id),
            "skill_id": str(skill_id),
            "document_id": str(document_id),
            "namespace_path": namespace_path,
        }

    async def remove_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
    ) -> bool:
        """
        Unlink a document from a skill.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            document_id: Document KU's component_id

        Returns:
            True if removed, False if not found
        """
        return await self.repository.remove_document_from_skill(
            tenant_id, skill_id, document_id
        )

    async def stage_document(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
        namespace_path: str,
    ) -> dict[str, Any]:
        """Stage a document for future extraction into a skill."""
        # Validate document exists
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        ku_repo = KnowledgeUnitRepository(self.session)
        doc = await ku_repo.get_document_by_id(document_id, tenant_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")

        edge = await self.repository.stage_document_to_skill(
            tenant_id, skill_id, document_id, namespace_path
        )
        await self.session.commit()

        return {
            "edge_id": str(edge.id),
            "skill_id": str(skill_id),
            "document_id": str(document_id),
            "path": namespace_path,
        }

    async def get_staged_documents(
        self, tenant_id: str, skill_id: UUID
    ) -> list[dict[str, Any]]:
        """Get staged documents for a skill."""
        return await self.repository.get_staged_documents(tenant_id, skill_id)

    async def remove_staged_document(
        self, tenant_id: str, skill_id: UUID, document_id: UUID
    ) -> bool:
        """Remove a staged document from a skill."""
        result = await self.repository.remove_staged_edge(
            tenant_id, skill_id, document_id
        )
        if result:
            await self.session.commit()
        return result

    async def get_skill_tree(
        self, tenant_id: str, skill_id: UUID
    ) -> list[dict[str, Any]]:
        """
        Get the file tree for a skill.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id

        Returns:
            List of dictionaries with path and document_id
        """
        return await self.repository.get_skill_tree(tenant_id, skill_id)

    async def read_skill_file(
        self, tenant_id: str, skill_id: UUID, path: str
    ) -> dict[str, Any] | None:
        """
        Read a document's content by path.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            path: Namespace path within the skill

        Returns:
            Document metadata and content, or None if not found
        """
        return await self.repository.read_skill_file(tenant_id, skill_id, path)


class DocumentNotFoundError(Exception):
    """Raised when a document is not found."""

    pass


async def repair_missing_skill_edges(
    session: AsyncSession, tenant_id: str
) -> dict[str, Any]:
    """
    Repair missing CONTAINS edges between Skills and their documents.

    Finds documents with namespace=/{skill_cy_name}/ that don't have
    a CONTAINS edge from the skill and creates the missing edges.

    Args:
        session: Database session
        tenant_id: Tenant identifier

    Returns:
        Dictionary with repair results
    """

    from sqlalchemy import select

    from analysi.models.component import Component, ComponentKind
    from analysi.models.kdg_edge import EdgeType, KDGEdge
    from analysi.models.knowledge_module import KnowledgeModule

    logger = get_logger(__name__)
    results = {
        "skills_checked": 0,
        "documents_checked": 0,
        "edges_created": 0,
        "edges_skipped": 0,
        "errors": [],
    }

    # Get all skills
    skills_stmt = (
        select(KnowledgeModule)
        .join(Component, KnowledgeModule.component_id == Component.id)
        .where(
            Component.tenant_id == tenant_id,
            Component.kind == ComponentKind.MODULE,
        )
    )
    skills_result = await session.execute(skills_stmt)
    skills = list(skills_result.scalars().all())
    results["skills_checked"] = len(skills)

    for skill in skills:
        await session.refresh(skill, ["component"])
        skill_cy_name = skill.component.cy_name
        skill_id = skill.component_id
        skill_namespace = f"/{skill_cy_name}/"

        # Find all KUs in this skill's namespace
        docs_stmt = select(Component).where(
            Component.tenant_id == tenant_id,
            Component.kind == ComponentKind.KU,
            Component.namespace == skill_namespace,
        )
        docs_result = await session.execute(docs_stmt)
        docs = list(docs_result.scalars().all())

        for doc in docs:
            results["documents_checked"] += 1

            # Check if CONTAINS edge already exists
            edge_stmt = (
                select(KDGEdge)
                .where(
                    KDGEdge.tenant_id == tenant_id,
                    KDGEdge.source_id == skill_id,
                    KDGEdge.target_id == doc.id,
                    KDGEdge.relationship_type == EdgeType.CONTAINS,
                )
                .order_by(KDGEdge.created_at.desc())
                .limit(1)
            )
            edge_result = await session.execute(edge_stmt)
            existing_edge = edge_result.scalar_one_or_none()

            if existing_edge:
                results["edges_skipped"] += 1
                continue

            # Create missing edge
            # Derive namespace_path from doc name
            namespace_path = doc.name
            if not namespace_path.endswith(".md"):
                namespace_path = f"{namespace_path}.md"

            try:
                edge = KDGEdge(
                    tenant_id=tenant_id,
                    source_id=skill_id,
                    target_id=doc.id,
                    relationship_type=EdgeType.CONTAINS,
                    edge_metadata={"namespace_path": namespace_path},
                )
                session.add(edge)
                results["edges_created"] += 1
                logger.info(
                    "created_missing_edge",
                    skill_cy_name=skill_cy_name,
                    doc_name=doc.name,
                    namespace_path=namespace_path,
                )
            except Exception as e:
                results["errors"].append(
                    f"Failed to create edge {skill_cy_name} -> {doc.name}: {e!s}"
                )

    await session.commit()
    logger.info(
        "repair_complete",
        edges_created=results["edges_created"],
        edges_skipped=results["edges_skipped"],
    )
    return results
