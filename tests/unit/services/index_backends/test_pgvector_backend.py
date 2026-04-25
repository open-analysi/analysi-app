"""
Unit tests for PgvectorBackend.

These test the backend with mocked AsyncSession — no real database.
"""

import hashlib
from collections import namedtuple
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.services.index_backends.base import IndexEntry
from analysi.services.index_backends.pgvector_backend import PgvectorBackend

# Named tuple matching RETURNING (id, content_hash) from Core insert
_ReturningRow = namedtuple("_ReturningRow", ["id", "content_hash"])


@pytest.mark.unit
class TestPgvectorBackendAdd:
    """Test PgvectorBackend.add()."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        return session

    @pytest.fixture
    def backend(self, mock_session):
        return PgvectorBackend(session=mock_session)

    @pytest.mark.asyncio
    async def test_add_entries(self, backend, mock_session):
        """add() uses INSERT ON CONFLICT DO NOTHING, no commit (service owns tx)."""
        collection_id = uuid4()
        entries = [
            IndexEntry(content="text one", embedding=[0.1] * 1536),
            IndexEntry(
                content="text two",
                embedding=[0.2] * 768,
                metadata={"source": "test"},
                source_ref="doc:123",
            ),
        ]

        id1, id2 = uuid4(), uuid4()
        hash1 = hashlib.sha256(b"text one").hexdigest()
        hash2 = hashlib.sha256(b"text two").hexdigest()

        # Mock: INSERT returns both rows (no duplicates)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            _ReturningRow(id1, hash1),
            _ReturningRow(id2, hash2),
        ]
        mock_session.execute.return_value = mock_result

        result = await backend.add(collection_id, "tenant-a", entries)

        assert len(result) == 2
        assert result[0] == id1
        assert result[1] == id2
        mock_session.execute.assert_called_once()
        # Backend should NOT commit — service owns transaction
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_pads_short_vectors(self, backend, mock_session):
        """add() pads 768-dim vectors to 1536 in the values dict."""
        collection_id = uuid4()
        short_embedding = [0.5] * 768
        entries = [IndexEntry(content="short vec", embedding=short_embedding)]

        new_id = uuid4()
        content_hash = hashlib.sha256(b"short vec").hexdigest()

        mock_result = MagicMock()
        mock_result.all.return_value = [_ReturningRow(new_id, content_hash)]
        mock_session.execute.return_value = mock_result

        ids = await backend.add(collection_id, "tenant-a", entries)

        assert len(ids) == 1
        # The test would have raised ValueError if embedding > 1536 dims
        mock_session.execute.assert_called_once()


@pytest.mark.unit
class TestPgvectorBackendSearch:
    """Test PgvectorBackend.search()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def backend(self, mock_session):
        return PgvectorBackend(session=mock_session)

    @pytest.mark.asyncio
    async def test_search_executes_query(self, backend, mock_session):
        """search() executes a SELECT and returns SearchResult list."""
        collection_id = uuid4()
        entry_id = uuid4()

        # Mock a result row
        mock_entry = MagicMock()
        mock_entry.id = entry_id
        mock_entry.content = "matching content"
        mock_entry.entry_metadata = {"key": "val"}
        mock_entry.source_ref = "doc:1"

        mock_row = MagicMock()
        mock_row.IndexEntry = mock_entry
        mock_row.score = 0.92

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        results = await backend.search(collection_id, "tenant-a", [0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0].entry_id == entry_id
        assert results[0].content == "matching content"
        assert results[0].score == 0.92
        assert results[0].metadata == {"key": "val"}
        mock_session.execute.assert_awaited_once()


@pytest.mark.unit
class TestPgvectorBackendDelete:
    """Test PgvectorBackend.delete() and delete_all()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def backend(self, mock_session):
        return PgvectorBackend(session=mock_session)

    @pytest.mark.asyncio
    async def test_delete_entries(self, backend, mock_session):
        """delete() executes DELETE returning count."""
        collection_id = uuid4()
        entry_ids = [uuid4(), uuid4()]

        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock(), MagicMock()]
        mock_session.execute.return_value = mock_result

        deleted = await backend.delete(collection_id, "tenant-a", entry_ids)

        assert deleted == 2
        mock_session.execute.assert_awaited_once()
        # Backend should NOT commit — service owns transaction
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_empty_list(self, backend, mock_session):
        """delete() with empty list returns 0 without hitting DB."""
        deleted = await backend.delete(uuid4(), "tenant-a", [])
        assert deleted == 0
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_all(self, backend, mock_session):
        """delete_all() deletes all entries for the collection."""
        collection_id = uuid4()

        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock()] * 5
        mock_session.execute.return_value = mock_result

        deleted = await backend.delete_all(collection_id, "tenant-a")

        assert deleted == 5
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_not_awaited()


@pytest.mark.unit
class TestPgvectorBackendCount:
    """Test PgvectorBackend.count()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def backend(self, mock_session):
        return PgvectorBackend(session=mock_session)

    @pytest.mark.asyncio
    async def test_count(self, backend, mock_session):
        """count() returns scalar from COUNT query."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        result = await backend.count(uuid4(), "tenant-a")

        assert result == 42
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_count_empty(self, backend, mock_session):
        """count() returns 0 when no entries."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await backend.count(uuid4(), "tenant-a")
        assert result == 0


@pytest.mark.unit
class TestPgvectorBackendListEntries:
    """Test PgvectorBackend.list_entries()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def backend(self, mock_session):
        return PgvectorBackend(session=mock_session)

    @pytest.mark.asyncio
    async def test_list_entries(self, backend, mock_session):
        """list_entries() returns paginated entries + total count."""
        entry_id = uuid4()
        now = datetime.now(UTC)

        mock_entry = MagicMock()
        mock_entry.id = entry_id
        mock_entry.content = "entry content"
        mock_entry.entry_metadata = {"key": "val"}
        mock_entry.source_ref = "doc:1"
        mock_entry.created_at = now

        # First call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 10

        # Second call: data query
        mock_data_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_entry]
        mock_data_result.scalars.return_value = mock_scalars

        mock_session.execute.side_effect = [mock_count_result, mock_data_result]

        entries, total = await backend.list_entries(
            uuid4(), "tenant-a", offset=0, limit=50
        )

        assert total == 10
        assert len(entries) == 1
        assert entries[0].entry_id == entry_id
        assert entries[0].content == "entry content"
        assert entries[0].metadata == {"key": "val"}
        assert entries[0].created_at == now
        assert mock_session.execute.await_count == 2
