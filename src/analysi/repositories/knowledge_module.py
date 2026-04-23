"""
Repository for Knowledge Module (Skill) database operations.

Handles CRUD for skill modules and content management via KDG edges.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind, ComponentStatus
from analysi.models.kdg_edge import EdgeType, KDGEdge
from analysi.models.knowledge_module import KnowledgeModule, ModuleType
from analysi.models.knowledge_unit import KUDocument, KUTable
from analysi.repositories.component import ComponentRepository, categories_contain

logger = get_logger(__name__)


class KnowledgeModuleRepository:
    """Repository for Knowledge Module (Skill) CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def create_skill(
        self,
        tenant_id: str,
        data: dict[str, Any],
    ) -> KnowledgeModule:
        """
        Create a skill module with its Component.

        Args:
            tenant_id: Tenant identifier
            data: Skill data including name, description, config, etc.

        Returns:
            Created KnowledgeModule with component relationship loaded
        """
        name = data.get("name", "")
        app = data.get("app", "default")

        # Handle cy_name - use provided or generate
        comp_repo = ComponentRepository(self.session)
        cy_name = data.pop("cy_name", None)
        if not cy_name:
            base_cy_name = comp_repo.generate_cy_name(name, "skill")
            cy_name = await comp_repo.ensure_unique_cy_name(
                base_cy_name, tenant_id, app
            )
            logger.debug("generated_cyname_for_skill", cy_name=cy_name, name=name)
        else:
            # Check if provided cy_name already exists
            stmt = select(Component).where(
                Component.tenant_id == tenant_id,
                Component.app == app,
                Component.cy_name == cy_name,
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=409,
                    detail=f"Component with cy_name '{cy_name}' already exists in app '{app}'",
                )

        # Create component
        component_fields = {
            "tenant_id": tenant_id,
            "kind": ComponentKind.MODULE,
            "name": data.pop("name", ""),
            "description": data.pop("description", ""),
            "version": data.pop("version", "1.0.0"),
            "status": data.pop("status", ComponentStatus.ENABLED),
            "visible": data.pop("visible", False),
            "system_only": data.pop("system_only", False),
            "app": app,
            "categories": data.pop("categories", []),
            "created_by": data.pop("created_by", SYSTEM_USER_ID),
            "cy_name": cy_name,
            "namespace": data.pop("namespace", "/"),
        }

        component = Component(**component_fields)
        self.session.add(component)

        try:
            await self.session.flush()
        except IntegrityError as e:
            if "duplicate key" in str(e):
                logger.warning(
                    "duplicate_key_error_for_skill",
                    name=name,
                )
                await self.session.rollback()

                # Try to fetch existing
                existing = await self.get_skill_by_cy_name(tenant_id, cy_name)
                if existing:
                    logger.info(
                        "retrieved_existing_skill_after_race_condition",
                        name=name,
                    )
                    return existing
                raise
            raise

        # Create knowledge module
        module = KnowledgeModule(
            component_id=component.id,
            module_type=data.get("module_type", ModuleType.SKILL),
            root_document_path=data.get("root_document_path", "SKILL.md"),
            config=data.get("config", {}),
        )
        self.session.add(module)

        await self.session.commit()
        await self.session.refresh(module, ["component"])
        return module

    async def get_skill_by_id(
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
        stmt = (
            select(KnowledgeModule)
            .join(Component, KnowledgeModule.component_id == Component.id)
            .where(
                Component.id == component_id,
                Component.tenant_id == tenant_id,
                Component.kind == ComponentKind.MODULE,
            )
        )
        result = await self.session.execute(stmt)
        module = result.scalar_one_or_none()
        if not module:
            return None

        await self.session.refresh(module, ["component"])
        return module

    async def get_skill_by_cy_name(
        self, tenant_id: str, cy_name: str, app: str | None = None
    ) -> KnowledgeModule | None:
        """
        Get a skill by its cy_name.

        Args:
            tenant_id: Tenant identifier
            cy_name: Script-friendly identifier
            app: Optional app filter. If None, matches any app.

        Returns:
            KnowledgeModule if found, None otherwise
        """
        conditions = [
            Component.tenant_id == tenant_id,
            Component.cy_name == cy_name,
            Component.kind == ComponentKind.MODULE,
        ]
        if app is not None:
            conditions.append(Component.app == app)

        stmt = (
            select(KnowledgeModule)
            .join(Component, KnowledgeModule.component_id == Component.id)
            .where(*conditions)
        )
        result = await self.session.execute(stmt)
        module = result.scalar_one_or_none()
        if not module:
            return None

        await self.session.refresh(module, ["component"])
        return module

    async def get_skill_by_name(
        self, tenant_id: str, name: str, app: str | None = None
    ) -> KnowledgeModule | None:
        """
        Get a skill by its human-readable name.

        Args:
            tenant_id: Tenant identifier
            name: Human-readable skill name (e.g., "runbooks-manager")
            app: Optional app filter. If None, matches any app.

        Returns:
            KnowledgeModule if found, None otherwise
        """
        conditions = [
            Component.tenant_id == tenant_id,
            Component.name == name,
            Component.kind == ComponentKind.MODULE,
        ]
        if app is not None:
            conditions.append(Component.app == app)

        stmt = (
            select(KnowledgeModule)
            .join(Component, KnowledgeModule.component_id == Component.id)
            .where(*conditions)
        )
        result = await self.session.execute(stmt)
        module = result.scalar_one_or_none()
        if not module:
            return None

        await self.session.refresh(module, ["component"])
        return module

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
        List skill modules with optional filters.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter
            search: Optional search query (name, description, categories)
            skip: Pagination offset
            limit: Pagination limit
            categories: Optional categories filter (AND semantics)

        Returns:
            Tuple of (list of modules, metadata with total count)
        """
        base_stmt = (
            select(KnowledgeModule)
            .join(Component, KnowledgeModule.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.kind == ComponentKind.MODULE,
            )
        )

        if status:
            base_stmt = base_stmt.where(Component.status == status)

        if search:
            search_filter = or_(
                Component.name.ilike(f"%{search}%"),
                Component.description.ilike(f"%{search}%"),
                func.array_to_string(Component.categories, ",").ilike(f"%{search}%"),
            )
            base_stmt = base_stmt.where(search_filter)

        if app is not None:
            base_stmt = base_stmt.where(Component.app == app)

        if categories:
            base_stmt = base_stmt.where(categories_contain(categories))

        # Count total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get paginated results
        stmt = base_stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        modules = result.scalars().all()

        # Load component relationships
        for module in modules:
            await self.session.refresh(module, ["component"])

        return list(modules), {"total": total}

    async def update_skill(
        self, module: KnowledgeModule, update_data: dict[str, Any]
    ) -> KnowledgeModule:
        """
        Update a skill module and its component.

        Args:
            module: The KnowledgeModule to update
            update_data: Dictionary of fields to update

        Returns:
            Updated KnowledgeModule
        """
        # Component fields
        component_fields = [
            "name",
            "description",
            "cy_name",
            "status",
            "visible",
            "categories",
            "namespace",
        ]
        for field in component_fields:
            if field in update_data:
                setattr(module.component, field, update_data[field])

        # Module-specific fields
        module_fields = ["root_document_path", "config"]
        for field in module_fields:
            if field in update_data:
                setattr(module, field, update_data[field])

        # Update timestamps
        module.component.updated_at = datetime.now(UTC)
        module.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(module, ["component"])
        return module

    async def delete_skill(self, component_id: UUID, tenant_id: str) -> bool:
        """
        Delete a skill by deleting its Component (cascades to module).

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier

        Returns:
            True if deleted, False if not found
        """
        stmt = select(Component).where(
            Component.id == component_id,
            Component.tenant_id == tenant_id,
            Component.kind == ComponentKind.MODULE,
        )
        result = await self.session.execute(stmt)
        component = result.scalar_one_or_none()

        if not component:
            return False

        await self.session.delete(component)
        await self.session.commit()
        self.session.expunge_all()
        return True

    async def check_skill_delete(
        self, component_id: UUID, tenant_id: str
    ) -> dict[str, Any]:
        """
        Check what would be affected by deleting a skill.

        Args:
            component_id: Component UUID
            tenant_id: Tenant identifier

        Returns:
            Dictionary with affected items (contained documents, including skills, etc.)
        """
        # Count contained documents
        doc_count_stmt = (
            select(func.count())
            .select_from(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == component_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
            )
        )
        doc_result = await self.session.execute(doc_count_stmt)
        doc_count = doc_result.scalar() or 0

        # Count skills that include this skill
        including_stmt = (
            select(func.count())
            .select_from(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.target_id == component_id,
                KDGEdge.relationship_type == EdgeType.INCLUDES,
            )
        )
        including_result = await self.session.execute(including_stmt)
        including_count = including_result.scalar() or 0

        # Count skills that depend on this skill
        depending_stmt = (
            select(func.count())
            .select_from(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.target_id == component_id,
                KDGEdge.relationship_type == EdgeType.DEPENDS_ON,
            )
        )
        depending_result = await self.session.execute(depending_stmt)
        depending_count = depending_result.scalar() or 0

        return {
            "contained_documents": doc_count,
            "skills_including_this": including_count,
            "skills_depending_on_this": depending_count,
            "can_delete": True,  # Always allowed, but warn user
            "warnings": []
            if (including_count == 0 and depending_count == 0)
            else [
                f"{including_count} skill(s) include this skill",
                f"{depending_count} skill(s) depend on this skill",
            ],
        }

    # --- Document Management ---

    async def add_document_to_skill(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
        namespace_path: str,
    ) -> KDGEdge:
        """
        Link a document to a skill with a namespace path.

        Idempotent: if edge already exists, returns existing edge.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            document_id: Document KU's component_id
            namespace_path: Path within the skill (e.g., "references/api.md")

        Returns:
            Created or existing KDGEdge

        Raises:
            ValueError: If path conflicts with a different document
        """
        # Check if edge already exists (idempotent)
        existing_edge = await self._find_edge(
            tenant_id, skill_id, document_id, EdgeType.CONTAINS
        )
        if existing_edge:
            return existing_edge

        # Check for path conflict with a different document
        existing = await self._get_document_at_path(tenant_id, skill_id, namespace_path)
        if existing and existing != document_id:
            raise ValueError(
                f"Path '{namespace_path}' already exists in skill (document_id: {existing})"
            )

        # Create 'contains' edge with namespace_path in metadata
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=skill_id,
            target_id=document_id,
            relationship_type=EdgeType.CONTAINS,
            edge_metadata={"namespace_path": namespace_path},
        )
        self.session.add(edge)
        await self.session.commit()
        await self.session.refresh(edge)
        return edge

    async def remove_document_from_skill(
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
        stmt = select(KDGEdge).where(
            KDGEdge.tenant_id == tenant_id,
            KDGEdge.source_id == skill_id,
            KDGEdge.target_id == document_id,
            KDGEdge.relationship_type == EdgeType.CONTAINS,
        )
        result = await self.session.execute(stmt)
        edge = result.scalar_one_or_none()

        if not edge:
            return False

        await self.session.delete(edge)
        await self.session.commit()
        return True

    async def stage_document_to_skill(
        self,
        tenant_id: str,
        skill_id: UUID,
        document_id: UUID,
        namespace_path: str,
    ) -> KDGEdge:
        """Stage a document for future extraction into a skill.

        Creates a STAGED_FOR edge. Raises ValueError if already staged or integrated.
        """
        # Check if already integrated
        existing_contains = await self._find_edge(
            tenant_id, skill_id, document_id, EdgeType.CONTAINS
        )
        if existing_contains:
            raise ValueError("Document is already integrated into this skill")

        # Check if already staged
        existing_staged = await self._find_edge(
            tenant_id, skill_id, document_id, EdgeType.STAGED_FOR
        )
        if existing_staged:
            raise ValueError("Document is already staged for this skill")

        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=skill_id,
            target_id=document_id,
            relationship_type=EdgeType.STAGED_FOR,
            edge_metadata={"namespace_path": namespace_path},
        )
        self.session.add(edge)
        await self.session.flush()
        return edge

    async def get_staged_documents(
        self, tenant_id: str, skill_id: UUID
    ) -> list[dict[str, Any]]:
        """Get all staged documents for a skill."""
        stmt = (
            select(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == skill_id,
                KDGEdge.relationship_type == EdgeType.STAGED_FOR,
            )
            .order_by(KDGEdge.edge_metadata["namespace_path"].astext)
        )
        result = await self.session.execute(stmt)
        edges = result.scalars().all()

        return [
            {
                "document_id": str(edge.target_id),
                "path": edge.edge_metadata.get("namespace_path", ""),
                "edge_id": str(edge.id),
            }
            for edge in edges
        ]

    async def remove_staged_edge(
        self, tenant_id: str, skill_id: UUID, document_id: UUID
    ) -> bool:
        """Remove a STAGED_FOR edge. Returns True if removed, False if not found."""
        stmt = select(KDGEdge).where(
            KDGEdge.tenant_id == tenant_id,
            KDGEdge.source_id == skill_id,
            KDGEdge.target_id == document_id,
            KDGEdge.relationship_type == EdgeType.STAGED_FOR,
        )
        result = await self.session.execute(stmt)
        edge = result.scalar_one_or_none()
        if not edge:
            return False
        await self.session.delete(edge)
        await self.session.flush()
        return True

    async def _find_edge(
        self, tenant_id: str, skill_id: UUID, document_id: UUID, edge_type: str
    ) -> KDGEdge | None:
        """Find an edge between a skill and document of a given type."""
        stmt = select(KDGEdge).where(
            KDGEdge.tenant_id == tenant_id,
            KDGEdge.source_id == skill_id,
            KDGEdge.target_id == document_id,
            KDGEdge.relationship_type == edge_type,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_skill_tree(
        self, tenant_id: str, skill_id: UUID
    ) -> list[dict[str, Any]]:
        """Get the file tree for a skill, including staged documents.

        Returns list of dicts with path, document_id, and staged flag.
        """
        stmt = (
            select(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == skill_id,
                KDGEdge.relationship_type.in_([EdgeType.CONTAINS, EdgeType.STAGED_FOR]),
            )
            .order_by(KDGEdge.edge_metadata["namespace_path"].astext)
        )
        result = await self.session.execute(stmt)
        edges = result.scalars().all()

        tree = []
        for edge in edges:
            tree.append(
                {
                    "path": edge.edge_metadata.get("namespace_path", ""),
                    "document_id": str(edge.target_id),
                    "staged": edge.relationship_type == EdgeType.STAGED_FOR,
                }
            )
        return tree

    async def read_skill_file(
        self, tenant_id: str, skill_id: UUID, path: str
    ) -> dict[str, Any] | None:
        """
        Read a document's content by its namespace path within a skill.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            path: Namespace path within the skill

        Returns:
            Dictionary with document metadata and content, or None if not found
        """
        # Find the edge with this path (use latest if duplicates exist)
        stmt = (
            select(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == skill_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
                KDGEdge.edge_metadata["namespace_path"].astext == path,
            )
            .order_by(KDGEdge.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        edge = result.scalar_one_or_none()

        if not edge:
            return None

        # Get the document
        doc_stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(
                Component.id == edge.target_id,
                Component.tenant_id == tenant_id,
            )
        )
        doc_result = await self.session.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            return None

        await self.session.refresh(document, ["component"])

        return {
            "path": path,
            "document_id": str(document.component_id),
            "name": document.component.name,
            "content": document.content,
            "markdown_content": document.markdown_content,
            "doc_format": document.doc_format,
            "document_type": document.document_type,
            "metadata": document.doc_metadata,
        }

    async def read_skill_table(
        self, tenant_id: str, skill_id: UUID, path: str
    ) -> dict[str, Any] | None:
        """Read a KUTable's content by its namespace path within a skill.

        Similar to read_skill_file() but joins to KUTable instead of KUDocument.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            path: Namespace path within the skill

        Returns:
            Dictionary with table metadata and content, or None if not found
        """
        # Find the edge with this path (use latest if duplicates exist)
        stmt = (
            select(KDGEdge)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == skill_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
                KDGEdge.edge_metadata["namespace_path"].astext == path,
            )
            .order_by(KDGEdge.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        edge = result.scalar_one_or_none()

        if not edge:
            return None

        # Get the table (not document)
        table_stmt = (
            select(KUTable)
            .join(Component, KUTable.component_id == Component.id)
            .where(
                Component.id == edge.target_id,
                Component.tenant_id == tenant_id,
            )
        )
        table_result = await self.session.execute(table_stmt)
        table = table_result.scalar_one_or_none()

        if not table:
            return None

        await self.session.refresh(table, ["component"])

        return {
            "path": path,
            "table_id": str(table.component_id),
            "name": table.component.name,
            "content": table.content,
            "schema": table.schema,
            "row_count": table.row_count,
            "column_count": table.column_count,
        }

    async def write_skill_file(
        self,
        tenant_id: str,
        skill_id: UUID,
        path: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        """Write a KUDocument to a skill's namespace, creating or updating.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            path: Namespace path within the skill
            content: Document content (markdown)
            metadata: Optional metadata dict

        Returns:
            Component ID of the created/updated document
        """
        from analysi.models.knowledge_unit import KnowledgeUnit, KUType
        from analysi.repositories.component import ComponentRepository

        # Check if document already exists at this path
        existing_id = await self._get_document_at_path(tenant_id, skill_id, path)
        if existing_id:
            # Update existing document
            doc_stmt = select(KUDocument).where(KUDocument.component_id == existing_id)
            doc_result = await self.session.execute(doc_stmt)
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.markdown_content = content
                if metadata:
                    doc.doc_metadata = metadata
                doc.updated_at = datetime.now(UTC)
                await self.session.commit()
                return existing_id

        # Get skill component for namespace
        skill_stmt = select(Component).where(
            Component.id == skill_id, Component.tenant_id == tenant_id
        )
        skill_result = await self.session.execute(skill_stmt)
        skill_comp = skill_result.scalar_one_or_none()
        ns = f"/{skill_comp.cy_name}/" if skill_comp else "/"

        # Create new document
        comp_repo = ComponentRepository(self.session)
        filename = path.split("/")[-1]
        base_cy_name = comp_repo.generate_cy_name(filename, "ku")
        cy_name = await comp_repo.ensure_unique_cy_name(
            base_cy_name, tenant_id, "default"
        )

        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name=filename,
            description="",
            version="1.0.0",
            status="enabled",
            visible=False,
            system_only=False,
            app="default",
            categories=[],
            created_by=SYSTEM_USER_ID,
            ku_type=KUType.DOCUMENT,
            cy_name=cy_name,
            namespace=ns,
        )
        self.session.add(component)
        await self.session.flush()

        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.DOCUMENT,
        )
        self.session.add(ku)
        await self.session.flush()

        doc_ku = KUDocument(
            component_id=component.id,
            doc_format="markdown",
            markdown_content=content,
            doc_metadata=metadata or {},
        )
        self.session.add(doc_ku)

        # Link to skill
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=skill_id,
            target_id=component.id,
            relationship_type=EdgeType.CONTAINS,
            edge_metadata={"namespace_path": path},
        )
        self.session.add(edge)

        await self.session.commit()
        return component.id

    async def write_skill_table(
        self,
        tenant_id: str,
        skill_id: UUID,
        path: str,
        content: dict[str, Any] | list,
        schema: dict[str, Any] | None = None,
    ) -> UUID:
        """Write a KUTable to a skill's namespace, creating or updating.

        Args:
            tenant_id: Tenant identifier
            skill_id: Skill's component_id
            path: Namespace path within the skill
            content: Table content (dict or list)
            schema: Optional JSON schema

        Returns:
            Component ID of the created/updated table
        """
        from analysi.models.knowledge_unit import KnowledgeUnit, KUType
        from analysi.repositories.component import ComponentRepository

        # Check if table already exists at this path
        existing_data = await self.read_skill_table(tenant_id, skill_id, path)
        if existing_data:
            table_id = UUID(existing_data["table_id"])
            table_stmt = select(KUTable).where(KUTable.component_id == table_id)
            table_result = await self.session.execute(table_stmt)
            table = table_result.scalar_one_or_none()
            if table:
                table.content = content
                if schema:
                    table.schema = schema
                row_count = len(content) if isinstance(content, list) else 0
                table.row_count = row_count
                table.updated_at = datetime.now(UTC)
                await self.session.commit()
                return table_id

        # Get skill component for namespace
        skill_stmt = select(Component).where(
            Component.id == skill_id, Component.tenant_id == tenant_id
        )
        skill_result = await self.session.execute(skill_stmt)
        skill_comp = skill_result.scalar_one_or_none()
        ns = f"/{skill_comp.cy_name}/" if skill_comp else "/"

        # Create new table
        comp_repo = ComponentRepository(self.session)
        filename = path.split("/")[-1]
        base_cy_name = comp_repo.generate_cy_name(filename, "ku")
        cy_name = await comp_repo.ensure_unique_cy_name(
            base_cy_name, tenant_id, "default"
        )

        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name=filename,
            description="",
            version="1.0.0",
            status="enabled",
            visible=False,
            system_only=False,
            app="default",
            categories=[],
            created_by=SYSTEM_USER_ID,
            ku_type=KUType.TABLE,
            cy_name=cy_name,
            namespace=ns,
        )
        self.session.add(component)
        await self.session.flush()

        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.TABLE,
        )
        self.session.add(ku)
        await self.session.flush()

        row_count = len(content) if isinstance(content, list) else 0
        table_ku = KUTable(
            component_id=component.id,
            schema=schema or {},
            content=content,
            row_count=row_count,
            column_count=0,
        )
        self.session.add(table_ku)

        # Link to skill
        edge = KDGEdge(
            tenant_id=tenant_id,
            source_id=skill_id,
            target_id=component.id,
            relationship_type=EdgeType.CONTAINS,
            edge_metadata={"namespace_path": path},
        )
        self.session.add(edge)

        await self.session.commit()
        return component.id

    async def _get_document_at_path(
        self, tenant_id: str, skill_id: UUID, path: str
    ) -> UUID | None:
        """
        Check if a document exists at the given path.

        Returns:
            Document's component_id if exists, None otherwise
        """
        stmt = (
            select(KDGEdge.target_id)
            .where(
                KDGEdge.tenant_id == tenant_id,
                KDGEdge.source_id == skill_id,
                KDGEdge.relationship_type == EdgeType.CONTAINS,
                KDGEdge.edge_metadata["namespace_path"].astext == path,
            )
            .order_by(KDGEdge.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        target_id = result.scalar_one_or_none()
        return target_id
