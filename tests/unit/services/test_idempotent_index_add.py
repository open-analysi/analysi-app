"""
Unit tests for idempotent index_add — content-hash based deduplication.

The PgvectorBackend.add method should skip entries whose content already
exists in the same (collection_id, tenant_id) scope, using ON CONFLICT DO NOTHING
with a content_hash column.
"""

import hashlib
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.models.index_entry import IndexEntry as IndexEntryModel
from analysi.services.index_backends.base import IndexEntry
from analysi.services.index_backends.pgvector_backend import PgvectorBackend

# Named tuple matching RETURNING (id, content_hash) from Core insert
_ReturningRow = namedtuple("_ReturningRow", ["id", "content_hash"])


@pytest.mark.unit
class TestContentHashOnModel:
    """IndexEntry model should have a content_hash column."""

    def test_index_entry_has_content_hash_attribute(self):
        """IndexEntry model exposes content_hash."""
        assert hasattr(IndexEntryModel, "content_hash")

    def test_index_entry_accepts_content_hash(self):
        """Can set content_hash when constructing an IndexEntry."""
        entry = IndexEntryModel(
            collection_id=uuid4(),
            tenant_id="test",
            content="hello world",
            content_hash=hashlib.sha256(b"hello world").hexdigest(),
        )
        assert entry.content_hash == hashlib.sha256(b"hello world").hexdigest()


@pytest.mark.unit
class TestIdempotentAdd:
    """PgvectorBackend.add should deduplicate on content within a collection."""

    @pytest.mark.asyncio
    async def test_add_computes_content_hash(self):
        """Backend computes SHA-256 hash of content and uses INSERT ON CONFLICT."""
        session = AsyncMock()
        backend = PgvectorBackend(session)

        content = "APT29 uses spearphishing"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        entry = IndexEntry(content=content, embedding=[0.1] * 1536)
        collection_id = uuid4()
        new_id = uuid4()

        # Mock: INSERT returns the new row (nothing was duplicate)
        mock_insert_result = MagicMock()
        mock_insert_result.all.return_value = [_ReturningRow(new_id, expected_hash)]
        session.execute.return_value = mock_insert_result

        ids = await backend.add(collection_id, "test-tenant", [entry])

        assert len(ids) == 1
        assert ids[0] == new_id
        # Verify execute was called with the INSERT statement
        assert session.execute.called

    @pytest.mark.asyncio
    async def test_add_duplicate_content_returns_existing_id(self):
        """Adding the same content twice returns the existing entry's ID."""
        session = AsyncMock()
        backend = PgvectorBackend(session)

        existing_id = uuid4()
        content = "duplicate content"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        entry = IndexEntry(content=content, embedding=[0.1] * 1536)

        # Mock: INSERT returns empty (all duplicates skipped)
        mock_insert_result = MagicMock()
        mock_insert_result.all.return_value = []

        # Mock: SELECT for skipped hashes returns the existing entry
        mock_select_result = MagicMock()
        mock_select_result.all.return_value = [_ReturningRow(existing_id, content_hash)]

        session.execute.side_effect = [mock_insert_result, mock_select_result]

        ids = await backend.add(uuid4(), "test-tenant", [entry])

        assert len(ids) == 1
        assert ids[0] == existing_id

    @pytest.mark.asyncio
    async def test_add_mixed_new_and_duplicate(self):
        """Batch with both new and existing content returns correct IDs for each."""
        session = AsyncMock()
        backend = PgvectorBackend(session)

        existing_id = uuid4()
        new_id = uuid4()

        entries = [
            IndexEntry(content="already exists", embedding=[0.1] * 1536),
            IndexEntry(content="brand new", embedding=[0.2] * 1536),
        ]

        existing_hash = hashlib.sha256(b"already exists").hexdigest()
        new_hash = hashlib.sha256(b"brand new").hexdigest()

        # Mock: INSERT returns only the new row
        mock_insert_result = MagicMock()
        mock_insert_result.all.return_value = [_ReturningRow(new_id, new_hash)]

        # Mock: SELECT for skipped hashes returns the existing one
        mock_select_result = MagicMock()
        mock_select_result.all.return_value = [
            _ReturningRow(existing_id, existing_hash)
        ]

        session.execute.side_effect = [mock_insert_result, mock_select_result]

        ids = await backend.add(uuid4(), "test-tenant", entries)

        # Should return 2 IDs in input order: existing first, new second
        assert len(ids) == 2
        assert ids[0] == existing_id
        assert ids[1] == new_id

    @pytest.mark.asyncio
    async def test_add_intra_batch_duplicates(self):
        """Same content twice in one batch: deduplicated, both get same ID."""
        session = AsyncMock()
        backend = PgvectorBackend(session)

        single_id = uuid4()
        content = "duplicate in batch"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        entries = [
            IndexEntry(content=content, embedding=[0.1] * 1536),
            IndexEntry(content=content, embedding=[0.1] * 1536),
        ]

        # Mock: INSERT sends only 1 row (deduplicated), returns it
        mock_insert_result = MagicMock()
        mock_insert_result.all.return_value = [_ReturningRow(single_id, content_hash)]
        session.execute.return_value = mock_insert_result

        ids = await backend.add(uuid4(), "test-tenant", entries)

        # Both entries map to the same ID
        assert len(ids) == 2
        assert ids[0] == single_id
        assert ids[1] == single_id
        # Only 1 execute call (no SELECT needed — no skipped hashes)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_empty_list_returns_empty(self):
        """Adding an empty list returns empty list without hitting DB."""
        session = AsyncMock()
        backend = PgvectorBackend(session)

        ids = await backend.add(uuid4(), "test-tenant", [])

        assert ids == []
        session.execute.assert_not_called()
