"""
Unit tests for KnowledgeIndexService.

All dependencies (session, integration_service, backend, repository) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.knowledge_index import (
    CollectionNotFoundError,
    EmbeddingModelMismatchError,
    KnowledgeIndexService,
    _ResolvedAIIntegration,
)


def _make_mock_collection(
    embedding_model=None,
    embedding_dimensions=None,
    backend_type="pgvector",
    build_status="pending",
    component_id=None,
    vector_database=None,
):
    """Helper to create a mock KUIndex collection."""
    collection = MagicMock()
    collection.component_id = component_id or uuid4()
    collection.embedding_model = embedding_model
    collection.embedding_dimensions = embedding_dimensions
    collection.backend_type = backend_type
    collection.build_status = build_status
    collection.vector_database = vector_database
    return collection


def _make_resolved(model="text-embedding-3-small"):
    """Helper to create a _ResolvedAIIntegration."""
    return _ResolvedAIIntegration(
        integration_id="openai-1",
        integration_type="openai",
        credential_id=uuid4(),
        embedding_model=model,
    )


@pytest.mark.unit
class TestKnowledgeIndexServiceAddEntries:
    """Test add_entries orchestration."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_add_entries_calls_embed_and_backend(self, service):
        """add_entries resolves AI once, embeds, passes vectors to backend."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            component_id=collection_id,
            build_status="completed",
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)

        resolved = _make_resolved()
        service._resolve_ai_integration = AsyncMock(return_value=resolved)
        service._embed_texts = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        mock_backend = AsyncMock()
        entry_ids = [uuid4(), uuid4()]
        mock_backend.add.return_value = entry_ids
        service._get_backend = MagicMock(return_value=mock_backend)

        result = await service.add_entries(
            tenant_id="tenant-a",
            collection_id=collection_id,
            texts=["text one", "text two"],
            metadata_list=[{"key": "a"}, {"key": "b"}],
        )

        assert result == entry_ids
        # AI integration resolved once, not per text
        service._resolve_ai_integration.assert_awaited_once_with("tenant-a")
        # Embed called with resolved integration
        service._embed_texts.assert_awaited_once()
        call_args = service._embed_texts.call_args
        assert call_args[0][1] == ["text one", "text two"]
        assert call_args[0][2] is resolved

        # Backend receives 2 entries
        backend_entries = mock_backend.add.call_args[0][2]
        assert len(backend_entries) == 2
        assert backend_entries[0].content == "text one"
        assert backend_entries[1].metadata == {"key": "b"}

    @pytest.mark.asyncio
    async def test_first_add_locks_embedding_model(self, service):
        """First add_entries locks the embedding model on the collection."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model=None,
            component_id=collection_id,
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)
        service._resolve_ai_integration = AsyncMock(return_value=_make_resolved())
        service._embed_texts = AsyncMock(return_value=[[0.1] * 1536])

        mock_backend = AsyncMock()
        mock_backend.add.return_value = [uuid4()]
        service._get_backend = MagicMock(return_value=mock_backend)

        await service.add_entries("tenant-a", collection_id, ["test text"])

        assert collection.embedding_model == "text-embedding-3-small"
        assert collection.embedding_dimensions == 1536

    @pytest.mark.asyncio
    async def test_add_with_model_mismatch_raises(self, service):
        """add_entries raises EmbeddingModelMismatchError on model mismatch."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model="text-embedding-3-small",
            component_id=collection_id,
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)
        # Tenant now uses Gemini
        service._resolve_ai_integration = AsyncMock(
            return_value=_make_resolved("text-embedding-004")
        )

        with pytest.raises(EmbeddingModelMismatchError, match="text-embedding-3-small"):
            await service.add_entries("tenant-a", collection_id, ["test"])

    @pytest.mark.asyncio
    async def test_add_updates_build_status(self, service):
        """add_entries updates build_status from pending to completed."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            component_id=collection_id,
            build_status="pending",
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)
        service._resolve_ai_integration = AsyncMock(return_value=_make_resolved())
        service._embed_texts = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        mock_backend = AsyncMock()
        mock_backend.add.return_value = [uuid4(), uuid4()]
        service._get_backend = MagicMock(return_value=mock_backend)

        await service.add_entries("tenant-a", collection_id, ["a", "b"])

        assert collection.build_status == "completed"


@pytest.mark.unit
class TestKnowledgeIndexServiceSearch:
    """Test search orchestration."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_search_embeds_query_and_delegates(self, service):
        """search resolves AI once, embeds query, delegates to backend."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model="text-embedding-3-small",
            component_id=collection_id,
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)

        resolved = _make_resolved()
        service._resolve_ai_integration = AsyncMock(return_value=resolved)
        service._embed_single_with_resolved = AsyncMock(return_value=[0.3] * 1536)

        mock_backend = AsyncMock()
        mock_backend.search.return_value = []
        service._get_backend = MagicMock(return_value=mock_backend)

        await service.search("tenant-a", collection_id, "lateral movement", top_k=5)

        service._resolve_ai_integration.assert_awaited_once_with("tenant-a")
        service._embed_single_with_resolved.assert_awaited_once_with(
            "tenant-a", "lateral movement", resolved
        )
        assert mock_backend.search.call_args[1]["top_k"] == 5

    @pytest.mark.asyncio
    async def test_search_with_model_mismatch_raises(self, service):
        """search raises EmbeddingModelMismatchError on mismatch."""
        collection_id = uuid4()
        collection = _make_mock_collection(
            embedding_model="text-embedding-3-small",
            component_id=collection_id,
        )
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)
        service._resolve_ai_integration = AsyncMock(
            return_value=_make_resolved("text-embedding-004")
        )

        with pytest.raises(EmbeddingModelMismatchError):
            await service.search("tenant-a", collection_id, "query")


@pytest.mark.unit
class TestKnowledgeIndexServiceDelete:
    """Test delete orchestration."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_delete_entries(self, service):
        """delete_entries calls backend and commits."""
        collection_id = uuid4()
        collection = _make_mock_collection(component_id=collection_id)
        service.ku_repo.get_index_by_id = AsyncMock(return_value=collection)

        mock_backend = AsyncMock()
        mock_backend.delete.return_value = 3
        service._get_backend = MagicMock(return_value=mock_backend)

        deleted = await service.delete_entries(
            "tenant-a", collection_id, [uuid4(), uuid4(), uuid4()]
        )

        assert deleted == 3


@pytest.mark.unit
class TestKnowledgeIndexServiceCollectionNotFound:
    """Test collection not found handling."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        svc.ku_repo.get_index_by_id = AsyncMock(return_value=None)
        return svc

    @pytest.mark.asyncio
    async def test_add_to_missing_collection_raises(self, service):
        with pytest.raises(CollectionNotFoundError, match="not found"):
            await service.add_entries("tenant-a", uuid4(), ["test"])

    @pytest.mark.asyncio
    async def test_search_missing_collection_raises(self, service):
        with pytest.raises(CollectionNotFoundError, match="not found"):
            await service.search("tenant-a", uuid4(), "query")


@pytest.mark.unit
class TestKnowledgeIndexServiceBackendRouting:
    """Test backend routing from collection metadata."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        return svc

    def test_get_backend_uses_collection_type(self, service):
        collection = _make_mock_collection(backend_type="pgvector")
        with patch("analysi.services.knowledge_index.get_backend") as mock_get:
            mock_get.return_value = MagicMock()
            service._get_backend(collection)
            mock_get.assert_called_once_with("pgvector", session=service.session)

    def test_get_backend_defaults_to_pgvector(self, service):
        collection = _make_mock_collection(backend_type=None)
        with patch("analysi.services.knowledge_index.get_backend") as mock_get:
            mock_get.return_value = MagicMock()
            service._get_backend(collection)
            mock_get.assert_called_once_with("pgvector", session=service.session)


@pytest.mark.unit
class TestResolvedAIIntegrationCache:
    """Test that AI integration resolution is cached."""

    @pytest.fixture
    def service(self):
        svc = KnowledgeIndexService(AsyncMock(), AsyncMock())
        svc.ku_repo = AsyncMock()
        return svc

    def test_cache_hit(self, service):
        """Cached resolution returns immediately without DB call."""
        resolved = _make_resolved()
        service._ai_cache["tenant-a"] = resolved

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            service._resolve_ai_integration("tenant-a")
        )

        assert result is resolved
        # integration_service.list_integrations should NOT have been called
        service.integration_service.list_integrations.assert_not_awaited()
