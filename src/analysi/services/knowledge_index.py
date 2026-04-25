"""
KnowledgeIndexService — orchestrates knowledge index operations.

Project Paros: Knowledge Index feature.

Owns: embedding generation, model validation, backend routing.
Delegates: vector storage/retrieval to IndexBackend implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from analysi.config.logging import get_logger
from analysi.integrations.framework.base_ai import resolve_model_config
from analysi.integrations.framework.models import Archetype
from analysi.integrations.framework.registry import get_registry
from analysi.models.knowledge_unit import KUIndex
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.index_backends import get_backend
from analysi.services.index_backends.base import (
    IndexEntry,
    SearchResult,
    StoredEntry,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from analysi.services.integration_service import IntegrationService

logger = get_logger(__name__)


class CollectionNotFoundError(ValueError):
    """Raised when a collection is not found. Subclass of ValueError for backward compat."""


class EmbeddingModelMismatchError(Exception):
    """Raised when the tenant's embedding model differs from the collection's locked model."""


class NoEmbeddingProviderError(Exception):
    """Raised when the tenant has no AI integration that supports embeddings."""


class _ResolvedAIIntegration:
    """Cached result of AI integration resolution for a tenant."""

    __slots__ = (
        "credential_id",
        "embedding_model",
        "integration_id",
        "integration_type",
    )

    def __init__(
        self,
        integration_id: str,
        integration_type: str,
        credential_id: UUID | None,
        embedding_model: str,
    ):
        self.integration_id = integration_id
        self.integration_type = integration_type
        self.credential_id = credential_id
        self.embedding_model = embedding_model


class KnowledgeIndexService:
    """Orchestrates knowledge index operations.

    Owns: embedding generation, model validation, backend routing.
    Delegates: vector storage/retrieval to IndexBackend implementations.
    """

    def __init__(
        self,
        session: AsyncSession,
        integration_service: IntegrationService,
    ) -> None:
        self.session = session
        self.integration_service = integration_service
        self.ku_repo = KnowledgeUnitRepository(session)
        # Cache resolved AI integration per tenant (valid for this service instance's lifetime)
        self._ai_cache: dict[str, _ResolvedAIIntegration] = {}

    # ─── Entry operations ──────────────────────────────────────────────

    async def add_entries(
        self,
        tenant_id: str,
        collection_id: UUID,
        texts: list[str],
        metadata_list: list[dict[str, Any]] | None = None,
        source_refs: list[str | None] | None = None,
    ) -> list[UUID]:
        """Add text entries to a collection.

        Generates embeddings via the tenant's AI archetype,
        validates model compatibility, then delegates to the backend.

        Returns:
            List of assigned entry UUIDs.

        Raises:
            EmbeddingModelMismatchError: If embedding model doesn't match collection.
            NoEmbeddingProviderError: If tenant has no embedding-capable AI integration.
            ValueError: If collection not found.
        """
        collection = await self._get_collection_or_raise(collection_id, tenant_id)
        resolved = await self._resolve_ai_integration(tenant_id)

        await self._validate_and_lock_model(collection, resolved.embedding_model)

        embeddings = await self._embed_texts(tenant_id, texts, resolved)

        if collection.embedding_dimensions is None and embeddings:
            collection.embedding_dimensions = len(embeddings[0])

        entries = []
        for i, (text, embedding) in enumerate(zip(texts, embeddings, strict=True)):
            meta = metadata_list[i] if metadata_list and i < len(metadata_list) else {}
            src = source_refs[i] if source_refs and i < len(source_refs) else None
            entries.append(
                IndexEntry(
                    content=text, embedding=embedding, metadata=meta, source_ref=src
                )
            )

        backend = self._get_backend(collection)
        entry_ids = await backend.add(collection_id, tenant_id, entries)

        if collection.build_status == "pending":
            collection.build_status = "completed"
        await self.session.commit()

        logger.info(
            "knowledge_index_entries_added",
            collection_id=str(collection_id),
            tenant_id=tenant_id,
            count=len(entry_ids),
            embedding_model=collection.embedding_model,
        )
        return entry_ids

    async def search(
        self,
        tenant_id: str,
        collection_id: UUID,
        query: str,
        top_k: int = 10,
        score_threshold: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search a collection by semantic similarity.

        Returns:
            List of SearchResult ordered by score descending.
        """
        collection = await self._get_collection_or_raise(collection_id, tenant_id)
        resolved = await self._resolve_ai_integration(tenant_id)
        self._check_model_match(collection, resolved.embedding_model)

        query_embedding = await self._embed_single_with_resolved(
            tenant_id, query, resolved
        )

        backend = self._get_backend(collection)
        return await backend.search(
            collection_id,
            tenant_id,
            query_embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            metadata_filter=metadata_filter,
        )

    async def delete_entries(
        self,
        tenant_id: str,
        collection_id: UUID,
        entry_ids: list[UUID],
    ) -> int:
        """Delete specific entries from a collection."""
        collection = await self._get_collection_or_raise(collection_id, tenant_id)
        backend = self._get_backend(collection)
        deleted = await backend.delete(collection_id, tenant_id, entry_ids)
        await self.session.commit()
        return deleted

    async def list_entries(
        self,
        tenant_id: str,
        collection_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[StoredEntry], int]:
        """List entries in a collection with pagination."""
        collection = await self._get_collection_or_raise(collection_id, tenant_id)
        backend = self._get_backend(collection)
        return await backend.list_entries(collection_id, tenant_id, offset, limit)

    async def get_entry_count(
        self,
        tenant_id: str,
        collection_id: UUID,
    ) -> int:
        """Count entries in a collection."""
        collection = await self._get_collection_or_raise(collection_id, tenant_id)
        backend = self._get_backend(collection)
        return await backend.count(collection_id, tenant_id)

    # ─── Internal helpers ──────────────────────────────────────────────

    async def _get_collection_or_raise(
        self, collection_id: UUID, tenant_id: str
    ) -> KUIndex:
        """Load collection or raise CollectionNotFoundError."""
        collection = await self.ku_repo.get_index_by_id(collection_id, tenant_id)
        if not collection:
            raise CollectionNotFoundError(
                f"Collection '{collection_id}' not found for tenant '{tenant_id}'"
            )
        return collection

    async def _resolve_ai_integration(self, tenant_id: str) -> _ResolvedAIIntegration:
        """Resolve the tenant's primary AI integration with embedding capability.

        Results are cached per tenant for this service instance's lifetime.

        Raises:
            NoEmbeddingProviderError: If no embedding-capable integration found.
        """
        if tenant_id in self._ai_cache:
            return self._ai_cache[tenant_id]

        try:
            framework_registry = get_registry()
            ai_type_ids = {
                m.id for m in framework_registry.list_by_archetype(Archetype.AI)
            }

            integrations = await self.integration_service.list_integrations(tenant_id)

            # Find AI integration — prefer the one marked is_primary in settings
            # (same pattern as CyLLMFunctions._resolve_primary_ai_integration)
            ai_integration = None
            for integration in integrations:
                if integration.integration_type in ai_type_ids:
                    ai_integration = integration
                    settings = integration.settings or {}
                    if settings.get("is_primary", False):
                        break

            if not ai_integration:
                raise NoEmbeddingProviderError(
                    f"No AI integration configured for tenant '{tenant_id}'"
                )

            manifest = framework_registry.get_integration(
                ai_integration.integration_type
            )
            if not manifest:
                raise NoEmbeddingProviderError(
                    f"Manifest not found for '{ai_integration.integration_type}'"
                )

            model_config = resolve_model_config(
                manifest,
                capability="embedding",
                settings_overrides=ai_integration.settings,
            )
            model_name = model_config.get("model")
            if not model_name:
                raise NoEmbeddingProviderError(
                    f"Integration '{ai_integration.integration_id}' "
                    f"has no embedding model configured"
                )

            # Resolve credential via CredentialRepository
            # (same pattern as CyLLMFunctions._resolve_primary_ai_integration)
            credential_id = None
            try:
                from analysi.repositories.credential_repository import (
                    CredentialRepository,
                )

                cred_repo = CredentialRepository(self.session)
                int_creds = await cred_repo.list_by_integration(
                    tenant_id, ai_integration.integration_id
                )
                for ic in int_creds:
                    if ic.is_primary:
                        credential_id = ic.credential_id
                        break
                if not credential_id and int_creds:
                    credential_id = int_creds[0].credential_id
            except Exception:
                logger.warning(
                    "credential_resolution_failed",
                    integration_id=ai_integration.integration_id,
                    tenant_id=tenant_id,
                )

            resolved = _ResolvedAIIntegration(
                integration_id=ai_integration.integration_id,
                integration_type=ai_integration.integration_type,
                credential_id=credential_id,
                embedding_model=model_name,
            )
            self._ai_cache[tenant_id] = resolved
            return resolved

        except ValueError as e:
            # resolve_model_config raises ValueError for explicitly null capabilities
            # (e.g., Anthropic doesn't support embeddings)
            raise NoEmbeddingProviderError(str(e)) from e

    async def _validate_and_lock_model(
        self, collection: KUIndex, model_name: str
    ) -> None:
        """Lock embedding model on first use, validate on subsequent uses."""
        if collection.embedding_model is None:
            collection.embedding_model = model_name
            collection.vector_database = collection.vector_database or "pgvector"
            # Flush (not commit) — the model lock is part of the same transaction
            # as the entry inserts. If embedding fails, the lock rolls back too.
            await self.session.flush()
            logger.info(
                "embedding_model_locked",
                collection_id=str(collection.component_id),
                model=model_name,
            )
        else:
            self._check_model_match(collection, model_name)

    def _check_model_match(self, collection: KUIndex, model_name: str) -> None:
        """Check that model matches the collection's locked model."""
        if collection.embedding_model and collection.embedding_model != model_name:
            raise EmbeddingModelMismatchError(
                f"Collection '{collection.component_id}' uses model "
                f"'{collection.embedding_model}' but tenant's current embedding "
                f"model is '{model_name}'. Cannot mix embedding models "
                f"within a collection."
            )

    async def _embed_texts(
        self,
        tenant_id: str,
        texts: list[str],
        resolved: _ResolvedAIIntegration,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Uses the already-resolved AI integration to avoid N+1 lookups.
        """
        embeddings: list[list[float]] = []
        for text in texts:
            embedding = await self._embed_single_with_resolved(
                tenant_id, text, resolved
            )
            embeddings.append(embedding)
        return embeddings

    async def _embed_single_with_resolved(
        self,
        tenant_id: str,
        text: str,
        resolved: _ResolvedAIIntegration,
    ) -> list[float]:
        """Generate embedding for a single text using pre-resolved integration."""
        result = await self.integration_service.execute_action(
            tenant_id=tenant_id,
            integration_id=resolved.integration_id,
            integration_type=resolved.integration_type,
            action_id="llm_embed",
            credential_id=resolved.credential_id,
            params={"text": text},
            session=self.session,
        )

        if result.get("status") != "success":
            error_msg = result.get("error", "Unknown embedding error")
            raise RuntimeError(f"Embedding generation failed: {error_msg}")

        embedding = result.get("data", {}).get("embedding")
        if not embedding:
            raise RuntimeError("Embedding response missing 'embedding' field")

        return embedding

    def _get_backend(self, collection: KUIndex) -> Any:
        """Resolve backend from collection metadata."""
        backend_type = collection.backend_type or "pgvector"
        return get_backend(backend_type, session=self.session)
