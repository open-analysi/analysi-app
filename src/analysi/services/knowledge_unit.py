"""Knowledge Unit service for business logic."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.knowledge_unit import KUDocument, KUIndex, KUTable
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.schemas.knowledge_unit import (
    DocumentKUCreate,
    DocumentKUUpdate,
    IndexKUCreate,
    IndexKUUpdate,
    TableKUCreate,
    TableKUUpdate,
)


class KnowledgeUnitService:
    """Service for Knowledge Unit business logic."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session."""
        self.repository = KnowledgeUnitRepository(session)
        self.session = session

    async def create_table(
        self, tenant_id: str, table_data: TableKUCreate, created_by: UUID | None = None
    ) -> KUTable:
        """Create a new Table Knowledge Unit."""
        # Convert Pydantic model to dict
        table_dict = table_data.model_dump()
        namespace = table_dict.pop("namespace", "/")
        # Inject server-derived created_by (prevent client impersonation)
        if created_by is not None:
            table_dict["created_by"] = created_by

        return await self.repository.create_table_ku(
            tenant_id, table_dict, namespace=namespace
        )

    async def create_document(
        self, tenant_id: str, doc_data: DocumentKUCreate, created_by: UUID | None = None
    ) -> KUDocument:
        """Create a new Document Knowledge Unit."""
        # Convert Pydantic model to dict
        doc_dict = doc_data.model_dump()
        namespace = doc_dict.pop("namespace", "/")
        # Inject server-derived created_by (prevent client impersonation)
        if created_by is not None:
            doc_dict["created_by"] = created_by

        return await self.repository.create_document_ku(
            tenant_id, doc_dict, namespace=namespace
        )

    async def create_index(
        self, tenant_id: str, index_data: IndexKUCreate, created_by: UUID | None = None
    ) -> KUIndex:
        """Create a new Index Knowledge Unit (management only)."""
        # Convert Pydantic model to dict
        index_dict = index_data.model_dump()
        namespace = index_dict.pop("namespace", "/")
        # Inject server-derived created_by (prevent client impersonation)
        if created_by is not None:
            index_dict["created_by"] = created_by

        return await self.repository.create_index_ku(
            tenant_id, index_dict, namespace=namespace
        )

    async def get_table(self, component_id: UUID, tenant_id: str) -> KUTable | None:
        """Get a Table KU by ID."""
        return await self.repository.get_table_by_id(component_id, tenant_id)

    async def get_document(
        self, component_id: UUID, tenant_id: str
    ) -> KUDocument | None:
        """Get a Document KU by ID."""
        return await self.repository.get_document_by_id(component_id, tenant_id)

    async def get_index(self, component_id: UUID, tenant_id: str) -> KUIndex | None:
        """Get an Index KU by ID."""
        return await self.repository.get_index_by_id(component_id, tenant_id)

    async def update_table(
        self, component_id: UUID, tenant_id: str, update_data: TableKUUpdate
    ) -> KUTable | None:
        """Update an existing Table KU."""
        # First get the existing table
        table = await self.repository.get_table_by_id(component_id, tenant_id)
        if not table:
            return None

        # Convert update data to dict, excluding None values
        update_dict = update_data.model_dump(exclude_unset=True)

        return await self.repository.update_ku(table, update_dict)

    async def update_document(
        self, component_id: UUID, tenant_id: str, update_data: DocumentKUUpdate
    ) -> KUDocument | None:
        """Update an existing Document KU."""
        # First get the existing document
        doc = await self.repository.get_document_by_id(component_id, tenant_id)
        if not doc:
            return None

        # Convert update data to dict, excluding None values
        update_dict = update_data.model_dump(exclude_unset=True)

        return await self.repository.update_ku(doc, update_dict)

    async def update_index(
        self, component_id: UUID, tenant_id: str, update_data: IndexKUUpdate
    ) -> KUIndex | None:
        """Update an existing Index KU."""
        # First get the existing index
        index = await self.repository.get_index_by_id(component_id, tenant_id)
        if not index:
            return None

        # Convert update data to dict, excluding None values
        update_dict = update_data.model_dump(exclude_unset=True)

        return await self.repository.update_ku(index, update_dict)

    async def get_table_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUTable | None:
        """Get table by name and namespace."""
        return await self.repository.get_table_by_name(
            tenant_id, name, namespace=namespace
        )

    async def get_document_by_name(
        self, tenant_id: str, name: str, namespace: str = "/"
    ) -> KUDocument | None:
        """Get document by name and namespace."""
        return await self.repository.get_document_by_name(
            tenant_id, name, namespace=namespace
        )

    async def get_table_by_name_or_id(
        self, tenant_id: str, name: str = None, id: str = None
    ) -> KUTable | None:
        """Get table by name (priority) or UUID."""
        # Name takes priority
        if name:
            return await self.get_table_by_name(tenant_id, name)
        # Fallback to UUID
        if id:
            return await self.get_table(UUID(id), tenant_id)
        return None

    async def get_document_by_name_or_id(
        self, tenant_id: str, name: str = None, id: str = None
    ) -> KUDocument | None:
        """Get document by name (priority) or UUID."""
        # Name takes priority
        if name:
            return await self.get_document_by_name(tenant_id, name)
        # Fallback to UUID
        if id:
            return await self.get_document(UUID(id), tenant_id)
        return None

    async def delete_ku(self, component_id: UUID, tenant_id: str) -> bool:
        """Delete a Knowledge Unit."""
        return await self.repository.delete_ku(component_id, tenant_id)

    async def list_tables(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        app: str | None = None,
    ) -> tuple[list[KUTable], dict[str, Any]]:
        """List Table KUs with pagination."""
        kus, meta = await self.repository.list_kus(
            tenant_id=tenant_id,
            ku_type="table",
            skip=skip,
            limit=limit,
            app=app,
        )

        # Get the actual table objects for each KU
        tables = []
        for ku in kus:
            # Get the KUTable that has this component_id
            from sqlalchemy import select

            from analysi.models.knowledge_unit import KUTable

            stmt = select(KUTable).where(KUTable.component_id == ku.component_id)
            result = await self.session.execute(stmt)
            table = result.scalar_one_or_none()
            if table:
                await self.session.refresh(table, ["component"])
                tables.append(table)

        return tables, {"total": meta["total"]}

    async def list_documents(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        app: str | None = None,
    ) -> tuple[list[KUDocument], dict[str, Any]]:
        """List Document KUs with pagination."""
        kus, meta = await self.repository.list_kus(
            tenant_id=tenant_id,
            ku_type="document",
            skip=skip,
            limit=limit,
            app=app,
        )

        # Get the actual document objects for each KU
        documents = []
        for ku in kus:
            # Get the KUDocument that has this component_id
            from sqlalchemy import select

            from analysi.models.knowledge_unit import KUDocument

            stmt = select(KUDocument).where(KUDocument.component_id == ku.component_id)
            result = await self.session.execute(stmt)
            doc = result.scalar_one_or_none()
            if doc:
                await self.session.refresh(doc, ["component"])
                documents.append(doc)

        return documents, {"total": meta["total"]}

    async def list_indexes(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 100,
        app: str | None = None,
    ) -> tuple[list[KUIndex], dict[str, Any]]:
        """List Index KUs with pagination."""
        kus, meta = await self.repository.list_kus(
            tenant_id=tenant_id,
            ku_type="index",
            skip=skip,
            limit=limit,
            app=app,
        )

        # Get the actual index objects for each KU
        indexes = []
        for ku in kus:
            # Get the KUIndex that has this component_id
            from sqlalchemy import select

            from analysi.models.knowledge_unit import KUIndex

            stmt = select(KUIndex).where(KUIndex.component_id == ku.component_id)
            result = await self.session.execute(stmt)
            index = result.scalar_one_or_none()
            if index:
                await self.session.refresh(index, ["component"])
                indexes.append(index)

        return indexes, {"total": meta["total"]}

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
        """Search across all Knowledge Units."""
        kus, meta = await self.repository.search_kus(
            tenant_id=tenant_id,
            query=query,
            ku_type=ku_type,
            status=status,
            skip=skip,
            limit=limit,
            categories=categories,
        )

        # Return pagination metadata
        return kus, {
            "total": meta["total"],
            "skip": skip,
            "limit": limit,
        }

    async def list_all_kus(
        self,
        tenant_id: str,
        ku_type: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        categories: list[str] | None = None,
    ) -> tuple[list[Any], dict[str, Any]]:
        """List all Knowledge Units with optional type filter."""
        kus, meta = await self.repository.list_kus(
            tenant_id=tenant_id,
            ku_type=ku_type,
            status=status,
            skip=skip,
            limit=limit,
            categories=categories,
        )

        # Return pagination metadata
        return kus, {
            "total": meta["total"],
            "skip": skip,
            "limit": limit,
        }
