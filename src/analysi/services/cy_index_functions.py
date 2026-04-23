"""
Cy Native Functions for Knowledge Index — Project Paros.

Provides index_add, index_search, index_delete for Cy scripts.
Embedding is automatic — callers pass text, not vectors.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.knowledge_index import KnowledgeIndexService

logger = get_logger(__name__)


class CyIndexFunctions:
    """Native functions for Knowledge Index access in Cy scripts."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: str,
        execution_context: dict[str, Any],
        integration_service: Any,
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.execution_context = execution_context
        self.index_service = KnowledgeIndexService(session, integration_service)
        self._ku_repo = KnowledgeUnitRepository(session)
        # Cache name → component_id within a single script execution
        self._collection_cache: dict[str, UUID] = {}

    async def _resolve_collection_id(self, name: str) -> UUID:
        """Resolve a collection's component_id by name. Cached per instance."""
        if name in self._collection_cache:
            return self._collection_cache[name]

        index = await self._ku_repo.get_index_by_name(self.tenant_id, name)
        if not index:
            raise ValueError(f"Index collection '{name}' not found")

        self._collection_cache[name] = index.component_id
        return index.component_id

    async def index_create(
        self,
        name: str,
        description: str = "",
    ) -> bool:
        """Create a named index collection if it doesn't exist (idempotent).

        If a collection with the given name already exists for this tenant,
        this is a no-op and returns True. Otherwise, creates a new index
        collection with default settings (vector type, pgvector backend).

        Args:
            name: Collection name.
            description: Optional description for the collection.

        Returns:
            True always (created or already existed).
        """
        existing = await self._ku_repo.get_index_by_name(self.tenant_id, name)
        if existing:
            self._collection_cache[name] = existing.component_id
            logger.info(
                "cy_index_create_exists",
                collection=name,
                tenant_id=self.tenant_id,
            )
            return True

        try:
            new_index = await self._ku_repo.create_index_ku(
                self.tenant_id,
                {
                    "name": name,
                    "description": description,
                    "index_type": "vector",
                    "backend_type": "pgvector",
                },
            )
            self._collection_cache[name] = new_index.component_id
            # No explicit commit needed — create_index_ku commits internally.

            logger.info(
                "cy_index_create_new",
                collection=name,
                tenant_id=self.tenant_id,
                collection_id=str(new_index.component_id),
            )
        except IntegrityError:
            # Race condition: another caller created the same collection concurrently.
            # Roll back the failed transaction and resolve the existing collection.
            await self.session.rollback()
            existing = await self._ku_repo.get_index_by_name(self.tenant_id, name)
            if existing:
                self._collection_cache[name] = existing.component_id
                logger.info(
                    "cy_index_create_race_resolved",
                    collection=name,
                    tenant_id=self.tenant_id,
                )
                return True
            raise

        return True

    async def index_add(
        self,
        name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        source_ref: str | None = None,
    ) -> bool:
        """Add a single text entry to a named index collection (idempotent).

        Embedding is automatic — uses the tenant's configured AI model.
        If the same content already exists in the collection, it is silently
        skipped (deduplication via content hash).

        Args:
            name: Collection name (resolved per-tenant).
            content: Text to embed and store.
            metadata: Optional key-value metadata for filtering.
            source_ref: Optional origin reference.

        Returns:
            True always (added or already existed).
        """
        collection_id = await self._resolve_collection_id(name)

        entry_ids = await self.index_service.add_entries(
            tenant_id=self.tenant_id,
            collection_id=collection_id,
            texts=[content],
            metadata_list=[metadata or {}],
            source_refs=[source_ref],
        )

        logger.info(
            "cy_index_add",
            collection=name,
            tenant_id=self.tenant_id,
            entry_id=str(entry_ids[0]) if entry_ids else None,
        )
        return True

    async def index_search(
        self,
        name: str,
        query: str,
        top_k: int = 10,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search a named index collection by semantic similarity.

        Args:
            name: Collection name (resolved per-tenant).
            query: Natural-language search query.
            top_k: Number of results to return.
            threshold: Minimum similarity score (0-1).

        Returns:
            List of result dicts with content, score, metadata, source_ref.
        """
        collection_id = await self._resolve_collection_id(name)

        results = await self.index_service.search(
            tenant_id=self.tenant_id,
            collection_id=collection_id,
            query=query,
            top_k=top_k,
            score_threshold=threshold,
        )

        return [
            {
                "entry_id": str(r.entry_id),
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
                "source_ref": r.source_ref,
            }
            for r in results
        ]

    async def index_delete(
        self,
        name: str,
        entry_id: str,
    ) -> bool:
        """Delete a single entry from a named index collection.

        Args:
            name: Collection name (resolved per-tenant).
            entry_id: UUID of the entry to delete.

        Returns:
            True if entry was deleted, False if not found.
        """
        collection_id = await self._resolve_collection_id(name)

        deleted = await self.index_service.delete_entries(
            tenant_id=self.tenant_id,
            collection_id=collection_id,
            entry_ids=[UUID(entry_id)],
        )

        return deleted > 0


def create_cy_index_functions(
    session: AsyncSession,
    tenant_id: str,
    execution_context: dict[str, Any],
    integration_service: Any,
) -> dict[str, Any]:
    """Create dictionary of index functions for Cy interpreter."""
    index_functions = CyIndexFunctions(
        session, tenant_id, execution_context, integration_service
    )

    async def index_create_wrapper(name: str, description: str = "") -> bool:
        """Create a named index collection if it doesn't exist (idempotent)."""
        return await index_functions.index_create(name=name, description=description)

    async def index_add_wrapper(name: str, content: str) -> bool:
        """Add text to a named index collection (auto-embeds)."""
        return await index_functions.index_add(name=name, content=content)

    async def index_add_with_metadata_wrapper(
        name: str, content: str, metadata: dict, source_ref: str
    ) -> bool:
        """Add text with metadata to a named index collection."""
        return await index_functions.index_add(
            name=name, content=content, metadata=metadata, source_ref=source_ref
        )

    async def index_search_wrapper(
        name: str, query: str, top_k: int = 10
    ) -> list[dict]:
        """Search a named index collection (auto-embeds query)."""
        return await index_functions.index_search(name=name, query=query, top_k=top_k)

    async def index_delete_wrapper(name: str, entry_id: str) -> bool:
        """Delete an entry from a named index collection."""
        return await index_functions.index_delete(name=name, entry_id=entry_id)

    return {
        "index_create": index_create_wrapper,
        "index_add": index_add_wrapper,
        "index_add_with_metadata": index_add_with_metadata_wrapper,
        "index_search": index_search_wrapper,
        "index_delete": index_delete_wrapper,
    }
