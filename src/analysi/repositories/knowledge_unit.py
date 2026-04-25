"""Repository for Knowledge Unit database operations."""

from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind
from analysi.models.knowledge_unit import (
    KnowledgeUnit,
    KUDocument,
    KUIndex,
    KUTable,
    KUTool,
    KUType,
)
from analysi.repositories.component import (
    ComponentRepository,
    categories_contain,
    merge_classification_into_categories,
)


class KnowledgeUnitRepository:
    """Repository for Knowledge Unit CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def create_table_ku(
        self, tenant_id: str, data: dict[str, Any], namespace: str = "/"
    ) -> KUTable:
        """Create or update a Table Knowledge Unit with Component."""

        logger = get_logger(__name__)
        name = data.get("name", "")
        app = data.get("app", "default")

        # Log the lookup attempt
        logger.debug(
            "looking_for_existing_table_ku_tenantid_name",
            tenant_id=tenant_id,
            name=name,
        )

        # Check if table exists and update it
        existing = await self.get_table_by_name(tenant_id, name, namespace=namespace)
        if existing:
            # Update existing table
            from datetime import UTC, datetime

            logger.info("found_existing_table_ku_updating_it", name=name)

            # Update table fields
            for field in ["content", "schema", "row_count", "column_count"]:
                if field in data:
                    setattr(existing, field, data[field])

            # Update component fields
            for field in ["description", "system_only", "categories", "created_by"]:
                if field in data:
                    setattr(existing.component, field, data[field])

            # Update timestamps
            existing.updated_at = datetime.now(UTC)
            existing.component.updated_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(existing, ["component"])
            return existing

        # Create new table
        logger.info("creating_new_table_ku", name=name)

        # Handle cy_name - use provided or generate
        comp_repo = ComponentRepository(self.session)
        cy_name = data.pop("cy_name", None)
        if not cy_name:
            # Generate from name
            base_cy_name = comp_repo.generate_cy_name(name, "ku")
            cy_name = await comp_repo.ensure_unique_cy_name(
                base_cy_name, tenant_id, app
            )
            logger.debug("generated_cyname_for_ku", cy_name=cy_name, name=name)
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

            logger.debug("using_provided_cyname_for_ku", cy_name=cy_name, name=name)

        component_fields = {
            "tenant_id": tenant_id,
            "kind": ComponentKind.KU,
            "name": data.pop("name", ""),
            "description": data.pop("description", "") or "",
            "version": data.pop("version", "1.0.0"),
            "status": data.pop("status", "enabled"),
            "visible": data.pop("visible", False),
            "system_only": data.pop("system_only", False),
            "app": app,
            "categories": data.pop("categories", []),
            "created_by": data.pop("created_by", SYSTEM_USER_ID),
            "ku_type": KUType.TABLE,
            "cy_name": cy_name,
            "namespace": namespace,
        }

        component = Component(**component_fields)
        self.session.add(component)

        try:
            await self.session.flush()
        except Exception as e:
            # Handle race condition where another process created the same KU
            from sqlalchemy.exc import IntegrityError

            if isinstance(e, IntegrityError) and "duplicate key" in str(e):
                logger.warning(
                    "duplicate_key_error_for_ku_attempting_to_fetch_exi", name=name
                )
                await self.session.rollback()

                # Try to fetch the existing record that was just created
                existing = await self.get_table_by_name(
                    tenant_id, name, namespace=namespace
                )
                if existing:
                    logger.info(
                        "retrieved_existing_table_ku_after_race_condition", name=name
                    )
                    return existing
                # If we still can't find it, re-raise the error
                logger.error(
                    "could_not_find_table_ku_after_duplicate_key_error", name=name
                )
                raise
            raise

        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.TABLE,
        )
        self.session.add(ku)
        await self.session.flush()

        table_ku = KUTable(
            component_id=component.id,
            schema=data.get("schema", {}),
            content=data.get("content", {}),
            row_count=data.get("row_count", 0),
            column_count=data.get("column_count", 0),
            file_path=data.get("file_path"),
        )
        self.session.add(table_ku)

        await self.session.commit()
        await self.session.refresh(table_ku, ["component"])
        return table_ku

    async def create_document_ku(
        self, tenant_id: str, data: dict[str, Any], namespace: str = "/"
    ) -> KUDocument:
        """Create or update a Document Knowledge Unit with Component."""
        name = data.get("name", "")
        app = data.get("app", "default")

        # Check if document KU already exists
        existing = await self.get_document_by_name(tenant_id, name, namespace=namespace)
        if existing:
            # Update existing document KU
            from datetime import datetime

            existing.content = data.get("content", existing.content)
            existing.doc_metadata = data.get("metadata", existing.doc_metadata)
            existing.doc_format = data.get("doc_format", existing.doc_format)
            existing.file_path = data.get("file_path", existing.file_path)
            existing.markdown_content = data.get(
                "markdown_content", existing.markdown_content
            )
            existing.document_type = data.get("document_type", existing.document_type)
            existing.content_source = data.get(
                "content_source", existing.content_source
            )
            existing.source_url = data.get("source_url", existing.source_url)
            existing.language = data.get("language", existing.language)
            existing.word_count = data.get("word_count", existing.word_count)
            existing.character_count = data.get(
                "character_count", existing.character_count
            )
            existing.page_count = data.get("page_count", existing.page_count)
            existing.updated_at = datetime.now(UTC)

            # Update component fields if provided
            if "description" in data:
                existing.component.description = data["description"] or ""
            if "version" in data:
                existing.component.version = data["version"]
            if "visible" in data:
                existing.component.visible = data["visible"]
            if "categories" in data:
                existing.component.categories = data["categories"]

            # Additively merge only the classification fields being changed
            # in this request — avoids re-adding values the user explicitly removed.
            changed_fields = {
                k: data[k]
                for k in ("document_type", "doc_format", "content_source")
                if k in data
            }
            if changed_fields:
                existing.component.categories = merge_classification_into_categories(
                    existing.component.categories or [],
                    **changed_fields,
                )

            await self.session.flush()
            return existing

        # Handle cy_name - use provided or generate
        comp_repo = ComponentRepository(self.session)
        cy_name = data.pop("cy_name", None)
        if not cy_name:
            # Generate from name
            base_cy_name = comp_repo.generate_cy_name(name, "ku")
            cy_name = await comp_repo.ensure_unique_cy_name(
                base_cy_name, tenant_id, app
            )
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

        # Auto-populate categories from classification fields.
        # Use the same defaults as the model layer so categories stay consistent.
        # Fields may be explicitly None from Pydantic, so use `or` fallback.
        categories = data.pop("categories", [])
        categories = merge_classification_into_categories(
            categories,
            document_type=data.get("document_type"),
            doc_format=data.get("doc_format") or "raw",
            content_source=data.get("content_source"),
        )

        # Extract component fields
        component_fields = {
            "tenant_id": tenant_id,
            "kind": ComponentKind.KU,
            "name": data.pop("name", ""),
            "description": data.pop("description", "") or "",
            "version": data.pop("version", "1.0.0"),
            "status": data.pop("status", "enabled"),
            "visible": data.pop("visible", False),
            "system_only": data.pop("system_only", False),
            "app": app,
            "categories": categories,
            "created_by": data.pop("created_by", SYSTEM_USER_ID),
            "ku_type": KUType.DOCUMENT,
            "cy_name": cy_name,
            "namespace": namespace,
        }

        # Create component first
        component = Component(**component_fields)
        self.session.add(component)

        try:
            await self.session.flush()
        except Exception as e:
            # Handle race condition where another process created the same KU

            from sqlalchemy.exc import IntegrityError

            logger = get_logger(__name__)

            if isinstance(e, IntegrityError) and "duplicate key" in str(e):
                logger.warning(
                    "duplicate_key_error_for_document_ku_attempting_to", name=name
                )
                await self.session.rollback()

                # Try to fetch the existing record that was just created
                existing = await self.get_document_by_name(
                    tenant_id, name, namespace=namespace
                )
                if existing:
                    logger.info(
                        "retrieved_existing_document_ku_after_race_conditio", name=name
                    )
                    return existing
                # If we still can't find it, re-raise the error
                logger.error(
                    "could_not_find_document_ku_after_duplicate_key_err", name=name
                )
                raise
            raise

        # Create intermediate KU entry
        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.DOCUMENT,
        )
        self.session.add(ku)
        await self.session.flush()

        # Create Document KU
        doc_ku = KUDocument(
            component_id=component.id,
            doc_format=data.get("doc_format") or "raw",
            content=data.get("content"),
            file_path=data.get("file_path"),
            markdown_content=data.get("markdown_content"),
            document_type=data.get("document_type"),
            content_source=data.get("content_source"),
            source_url=data.get("source_url"),
            doc_metadata=data.get("metadata", {}),
            word_count=data.get("word_count", 0),
            character_count=data.get("character_count", 0),
            page_count=data.get("page_count", 0),
            language=data.get("language"),
        )
        self.session.add(doc_ku)

        await self.session.commit()
        await self.session.refresh(doc_ku)
        await self.session.refresh(component)

        # Load the component relationship
        await self.session.refresh(doc_ku, ["component"])
        return doc_ku

    async def create_index_ku(
        self, tenant_id: str, data: dict[str, Any], namespace: str = "/"
    ) -> KUIndex:
        """Create an Index Knowledge Unit with Component."""
        name = data.get("name", "")
        app = data.get("app", "default")

        # Handle cy_name - use provided or generate
        comp_repo = ComponentRepository(self.session)
        cy_name = data.pop("cy_name", None)
        if not cy_name:
            # Generate from name
            base_cy_name = comp_repo.generate_cy_name(name, "ku")
            cy_name = await comp_repo.ensure_unique_cy_name(
                base_cy_name, tenant_id, app
            )
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

        # Auto-populate categories from classification fields.
        # Use the same defaults as the model layer so categories stay consistent.
        categories = data.pop("categories", [])
        categories = merge_classification_into_categories(
            categories,
            index_type=data.get("index_type") or "vector",
        )

        # Extract component fields
        component_fields = {
            "tenant_id": tenant_id,
            "kind": ComponentKind.KU,
            "name": data.pop("name", ""),
            "description": data.pop("description", "") or "",
            "version": data.pop("version", "1.0.0"),
            "status": data.pop("status", "enabled"),
            "visible": data.pop("visible", False),
            "system_only": data.pop("system_only", False),
            "app": app,
            "categories": categories,
            "created_by": data.pop("created_by", SYSTEM_USER_ID),
            "ku_type": KUType.INDEX,
            "cy_name": cy_name,
            "namespace": namespace,
        }

        # Create component first
        component = Component(**component_fields)
        self.session.add(component)
        await self.session.flush()

        # Create intermediate KU entry
        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.INDEX,
        )
        self.session.add(ku)
        await self.session.flush()

        # Create Index KU
        index_ku = KUIndex(
            component_id=component.id,
            index_type=data.get("index_type", "vector"),
            vector_database=data.get("vector_database"),
            embedding_model=data.get("embedding_model"),
            embedding_dimensions=data.get("embedding_dimensions"),
            backend_type=data.get("backend_type", "pgvector"),
            chunking_config=data.get("chunking_config", {}),
            build_status="pending",  # Management only, not built yet
            index_stats=data.get("index_stats", {}),
        )
        self.session.add(index_ku)

        await self.session.commit()
        await self.session.refresh(index_ku)
        await self.session.refresh(component)

        # Load the component relationship
        await self.session.refresh(index_ku, ["component"])
        return index_ku

    async def get_ku_by_id(
        self, component_id: UUID, tenant_id: str, ku_type: str | None = None
    ) -> Any:
        """Get a Knowledge Unit by Component ID - returns the specific KU subtype."""
        # Try to find in each KU subtype table
        # First check KUTable
        table_result = await self.get_table_by_id(component_id, tenant_id)
        if table_result:
            return table_result

        # Then check KUDocument
        doc_result = await self.get_document_by_id(component_id, tenant_id)
        if doc_result:
            return doc_result

        # Finally check KUIndex
        index_result = await self.get_index_by_id(component_id, tenant_id)
        if index_result:
            return index_result

        return None

    async def get_table_by_id(
        self, component_id: UUID, tenant_id: str
    ) -> KUTable | None:
        """Get a Table KU by Component ID."""
        stmt = (
            select(KUTable)
            .join(Component, KUTable.component_id == Component.id)
            .where(Component.id == component_id, Component.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        table = result.scalar_one_or_none()
        if not table:
            return None

        await self.session.refresh(table, ["component"])
        return table

    async def get_document_by_id(
        self, component_id: UUID, tenant_id: str
    ) -> KUDocument | None:
        """Get a Document KU by Component ID."""
        stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(Component.id == component_id, Component.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            return None

        await self.session.refresh(doc, ["component"])
        return doc

    async def get_index_by_id(
        self, component_id: UUID, tenant_id: str
    ) -> KUIndex | None:
        """Get an Index KU by Component ID."""
        stmt = (
            select(KUIndex)
            .join(Component, KUIndex.component_id == Component.id)
            .where(Component.id == component_id, Component.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        index = result.scalar_one_or_none()
        if not index:
            return None

        await self.session.refresh(index, ["component"])
        return index

    async def update_ku(self, ku: Any, update_data: dict[str, Any]) -> Any:
        """Update a Knowledge Unit and its Component fields."""
        # Separate component fields from KU fields
        component_fields = {
            k: v
            for k, v in update_data.items()
            if k in ["name", "description", "cy_name", "namespace"]
        }

        # Update component fields if any
        if component_fields:
            component = ku.component
            for key, value in component_fields.items():
                setattr(component, key, value)

        # Update KU-specific fields (varies by type)
        ku_fields = {
            k: v
            for k, v in update_data.items()
            if k not in ["name", "description", "cy_name", "namespace"]
        }

        for key, value in ku_fields.items():
            if hasattr(ku, key):
                setattr(ku, key, value)

        await self.session.commit()
        await self.session.refresh(ku)
        # Load the component relationship
        await self.session.refresh(ku, ["component"])

        return ku

    async def delete_ku(self, component_id: UUID, tenant_id: str) -> bool:
        """Delete a Knowledge Unit by deleting its Component (cascades to KU and subtypes)."""
        # Find the Component to delete (this is the root of the hierarchy)
        stmt = select(Component).where(
            Component.id == component_id, Component.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        component = result.scalar_one_or_none()

        if not component:
            return False

        # Delete the Component - this will cascade to KnowledgeUnit and KUTable/Document/Index
        await self.session.delete(component)
        await self.session.commit()

        # Expunge any cached instances to avoid stale references
        self.session.expunge_all()

        return True

    async def list_kus(
        self,
        tenant_id: str,
        ku_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
        app: str | None = None,  # Project Delos: filter by content pack
    ) -> tuple[list[Any], dict[str, Any]]:
        """List Knowledge Units with optional type filter."""
        # Build query
        stmt = (
            select(KnowledgeUnit)
            .join(Component)
            .where(Component.tenant_id == tenant_id)
        )

        if ku_type:
            stmt = stmt.where(KnowledgeUnit.ku_type == ku_type)

        if status:
            stmt = stmt.where(Component.status == status)

        if app is not None:
            stmt = stmt.where(Component.app == app)

        if categories:
            stmt = stmt.where(categories_contain(categories))

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated results
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        kus = result.scalars().all()

        # Load component relationships
        for ku in kus:
            await self.session.refresh(ku, ["component"])

        return list(kus), {"total": total}

    async def search_kus(
        self,
        tenant_id: str,
        query: str,
        ku_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Search Knowledge Units by name, description, or tags."""
        # Search across component fields
        search_filter = or_(
            Component.name.ilike(f"%{query}%"),
            Component.description.ilike(f"%{query}%"),
            # Fix array operator - categories is text[] and we need proper casting
            func.array_to_string(Component.categories, ",").ilike(f"%{query}%"),
        )

        stmt = (
            select(KnowledgeUnit)
            .join(Component)
            .where(and_(Component.tenant_id == tenant_id, search_filter))
        )

        if ku_type:
            stmt = stmt.where(KnowledgeUnit.ku_type == ku_type)

        if status:
            stmt = stmt.where(Component.status == status)

        if categories:
            stmt = stmt.where(categories_contain(categories))

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated results
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        kus = result.scalars().all()

        # Load component relationships
        for ku in kus:
            await self.session.refresh(ku, ["component"])

        return list(kus), {"total": total}

    async def get_table_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUTable | None:
        """Get Table KU by name and namespace."""
        stmt = (
            select(KUTable)
            .join(Component, KUTable.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.namespace == namespace,
                Component.name == name,
                Component.ku_type == KUType.TABLE,
            )
        )
        result = await self.session.execute(stmt)
        table = result.scalar_one_or_none()
        if not table:
            return None

        await self.session.refresh(table, ["component"])
        return table

    async def get_document_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUDocument | None:
        """Get Document KU by name and namespace."""
        stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.namespace == namespace,
                Component.name == name,
                Component.ku_type == KUType.DOCUMENT,
            )
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if not document:
            return None

        await self.session.refresh(document, ["component"])
        return document

    async def list_tables_direct(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> tuple[list[KUTable], dict[str, Any]]:
        """List Table KUs directly with proper joins."""
        # Count total tables
        count_stmt = (
            select(func.count())
            .select_from(KUTable)
            .join(Component, KUTable.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated tables with components loaded
        stmt = (
            select(KUTable)
            .join(Component, KUTable.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        tables = result.scalars().all()

        # Load component relationships
        for table in tables:
            await self.session.refresh(table, ["component"])

        return list(tables), {"total": total}

    async def list_documents_direct(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> tuple[list[KUDocument], dict[str, Any]]:
        """List Document KUs directly with proper joins."""
        # Count total documents
        count_stmt = (
            select(func.count())
            .select_from(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated documents with components loaded
        stmt = (
            select(KUDocument)
            .join(Component, KUDocument.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        documents = result.scalars().all()

        # Load component relationships
        for doc in documents:
            await self.session.refresh(doc, ["component"])

        return list(documents), {"total": total}

    async def list_indexes_direct(
        self, tenant_id: str, skip: int = 0, limit: int = 100
    ) -> tuple[list[KUIndex], dict[str, Any]]:
        """List Index KUs directly with proper joins."""
        # Count total indexes
        count_stmt = (
            select(func.count())
            .select_from(KUIndex)
            .join(Component, KUIndex.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar()

        # Get paginated indexes with components loaded
        stmt = (
            select(KUIndex)
            .join(Component, KUIndex.component_id == Component.id)
            .where(Component.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        indexes = result.scalars().all()

        # Load component relationships
        for index in indexes:
            await self.session.refresh(index, ["component"])

        return list(indexes), {"total": total}

    async def get_index_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUIndex | None:
        """Get Index KU by name and namespace."""
        stmt = (
            select(KUIndex)
            .join(Component, KUIndex.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.namespace == namespace,
                Component.name == name,
                Component.ku_type == KUType.INDEX,
            )
        )
        result = await self.session.execute(stmt)
        index = result.scalar_one_or_none()
        if not index:
            return None

        await self.session.refresh(index, ["component"])
        return index

    async def get_tool_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUTool | None:
        """Get Tool KU by name and namespace."""
        stmt = (
            select(KUTool)
            .join(Component, KUTool.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.namespace == namespace,
                Component.name == name,
                Component.ku_type == KUType.TOOL,
            )
        )
        result = await self.session.execute(stmt)
        tool = result.scalar_one_or_none()
        if not tool:
            return None

        await self.session.refresh(tool, ["component"])
        return tool

    async def create_tool_ku(
        self,
        tenant_id: str,
        name: str,
        description: str,
        tool_type: str,
        categories: list[str] | None = None,
        integration_id: UUID | None = None,
        status: str = "enabled",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> KUTool:
        """Create a Tool Knowledge Unit."""

        logger = get_logger(__name__)

        # Check if tool exists
        existing = await self.get_tool_by_name(tenant_id, name)
        if existing:
            logger.info("tool_ku_already_exists_skipping_creation", name=name)
            return existing

        logger.info("creating_new_tool_ku_type", name=name, tool_type=tool_type)

        # Generate cy_name
        comp_repo = ComponentRepository(self.session)
        base_cy_name = comp_repo.generate_cy_name(name, "ku")
        cy_name = await comp_repo.ensure_unique_cy_name(
            base_cy_name, tenant_id, "default"
        )

        # Auto-populate categories from classification fields
        merged_categories = merge_classification_into_categories(
            categories or [],
            tool_type=tool_type,
        )

        # Create component
        component = Component(
            tenant_id=tenant_id,
            kind=ComponentKind.KU,
            name=name,
            description=description,
            version="1.0.0",
            status=status,
            visible=True,
            system_only=False,
            app="default",
            categories=merged_categories,
            created_by=SYSTEM_USER_ID,
            ku_type=KUType.TOOL,
            cy_name=cy_name,
        )
        self.session.add(component)
        await self.session.flush()

        # Create KU entry
        ku = KnowledgeUnit(
            component_id=component.id,
            ku_type=KUType.TOOL,
        )
        self.session.add(ku)
        await self.session.flush()

        # Create tool entry
        tool_ku = KUTool(
            component_id=component.id,
            tool_type=tool_type,
            integration_id=integration_id,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
        )
        self.session.add(tool_ku)

        await self.session.commit()
        await self.session.refresh(tool_ku, ["component"])

        logger.info("created_tool_ku_with_cyname", name=name, cy_name=cy_name)
        return tool_ku

    async def list_app_tools(self, tenant_id: str) -> list[KUTool]:
        """
        List all app-type Tool KUs for a tenant.

        Returns tools with tool_type="app" (framework integration tools).

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of KUTool objects with component relationship loaded
        """
        stmt = (
            select(KUTool)
            .join(Component, KUTool.component_id == Component.id)
            .where(
                Component.tenant_id == tenant_id,
                Component.ku_type == KUType.TOOL,
                KUTool.tool_type == "app",
                Component.status == "enabled",
            )
        )
        result = await self.session.execute(stmt)
        tools = result.scalars().all()

        # Load component relationships
        for tool in tools:
            await self.session.refresh(tool, ["component"])

        return list(tools)
