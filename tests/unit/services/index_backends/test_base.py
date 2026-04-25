"""
Unit tests for IndexBackend dataclasses and pad_vector helper.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analysi.services.index_backends.base import (
    IndexEntry,
    SearchResult,
    StoredEntry,
)
from analysi.services.index_backends.pgvector_backend import pad_vector


@pytest.mark.unit
class TestIndexEntryDataclass:
    """Test IndexEntry dataclass."""

    def test_index_entry_dataclass(self):
        """Create IndexEntry with all fields, verify values."""
        entry_id = uuid4()
        entry = IndexEntry(
            content="APT29 uses spearphishing",
            embedding=[0.1, 0.2, 0.3],
            metadata={"source": "mitre"},
            source_ref="document:abc",
            entry_id=entry_id,
        )
        assert entry.content == "APT29 uses spearphishing"
        assert entry.embedding == [0.1, 0.2, 0.3]
        assert entry.metadata == {"source": "mitre"}
        assert entry.source_ref == "document:abc"
        assert entry.entry_id == entry_id

    def test_index_entry_defaults(self):
        """IndexEntry defaults: empty metadata, None source_ref and entry_id."""
        entry = IndexEntry(content="test", embedding=[1.0])
        assert entry.metadata == {}
        assert entry.source_ref is None
        assert entry.entry_id is None


@pytest.mark.unit
class TestSearchResultDataclass:
    """Test SearchResult dataclass."""

    def test_search_result_dataclass(self):
        """Create SearchResult, verify all fields."""
        eid = uuid4()
        result = SearchResult(
            entry_id=eid,
            content="lateral movement techniques",
            score=0.87,
            metadata={"technique": "T1021"},
            source_ref="alert:xyz",
        )
        assert result.entry_id == eid
        assert result.content == "lateral movement techniques"
        assert result.score == 0.87
        assert result.metadata == {"technique": "T1021"}
        assert result.source_ref == "alert:xyz"

    def test_search_result_score_range(self):
        """Score is a float — verify extreme values accepted."""
        result_low = SearchResult(
            entry_id=uuid4(), content="low", score=0.0, metadata={}
        )
        result_high = SearchResult(
            entry_id=uuid4(), content="high", score=1.0, metadata={}
        )
        assert result_low.score == 0.0
        assert result_high.score == 1.0


@pytest.mark.unit
class TestStoredEntryDataclass:
    """Test StoredEntry dataclass."""

    def test_stored_entry_dataclass(self):
        """Create StoredEntry, verify all fields."""
        eid = uuid4()
        now = datetime.now(UTC)
        entry = StoredEntry(
            entry_id=eid,
            content="stored text",
            metadata={"key": "value"},
            source_ref="doc:123",
            created_at=now,
        )
        assert entry.entry_id == eid
        assert entry.content == "stored text"
        assert entry.metadata == {"key": "value"}
        assert entry.source_ref == "doc:123"
        assert entry.created_at == now


@pytest.mark.unit
class TestPadVector:
    """Test pad_vector helper."""

    def test_pad_short_vector(self):
        """768-dim vector padded to 1536 with trailing zeros."""
        short = [0.5] * 768
        padded = pad_vector(short, 1536)
        assert len(padded) == 1536
        assert padded[:768] == short
        assert padded[768:] == [0.0] * 768

    def test_pad_exact_vector(self):
        """1536-dim vector returned unchanged."""
        exact = [0.1] * 1536
        padded = pad_vector(exact, 1536)
        assert len(padded) == 1536
        assert padded == exact

    def test_pad_empty_vector(self):
        """Empty list padded to all zeros."""
        padded = pad_vector([], 1536)
        assert len(padded) == 1536
        assert all(v == 0.0 for v in padded)

    def test_pad_longer_vector_raises(self):
        """Vector longer than target raises ValueError instead of truncating."""
        long_vec = [0.1] * 2000
        with pytest.raises(ValueError, match="2000 dimensions"):
            pad_vector(long_vec, 1536)
