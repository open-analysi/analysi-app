"""
Unit tests for Knowledge Index entry and search schemas.

Tests Pydantic request/response schema validation.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from analysi.schemas.knowledge_index import (
    AddEntriesRequest,
    AddEntriesResponse,
    EntryInput,
    EntryResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


@pytest.mark.unit
class TestAddEntriesRequestSchema:
    """Test AddEntriesRequest Pydantic validation."""

    def test_valid_request(self):
        """Valid request with entries."""
        req = AddEntriesRequest(
            entries=[
                EntryInput(content="test text", metadata={"key": "val"}),
                EntryInput(content="another", source_ref="doc:1"),
            ]
        )
        assert len(req.entries) == 2
        assert req.entries[0].content == "test text"
        assert req.entries[1].source_ref == "doc:1"

    def test_empty_entries_rejected(self):
        """Empty entries list should fail validation."""
        with pytest.raises(ValidationError):
            AddEntriesRequest(entries=[])

    def test_empty_content_rejected(self):
        """Entry with empty content should fail validation."""
        with pytest.raises(ValidationError):
            AddEntriesRequest(entries=[EntryInput(content="")])


@pytest.mark.unit
class TestSearchRequestSchema:
    """Test SearchRequest Pydantic validation."""

    def test_valid_search(self):
        """Valid search request."""
        req = SearchRequest(
            query="lateral movement",
            top_k=5,
            score_threshold=0.7,
            metadata_filter={"source": "mitre"},
        )
        assert req.query == "lateral movement"
        assert req.top_k == 5
        assert req.score_threshold == 0.7

    def test_defaults(self):
        """Search with just query uses defaults."""
        req = SearchRequest(query="test")
        assert req.top_k == 10
        assert req.score_threshold is None
        assert req.metadata_filter is None

    def test_invalid_top_k(self):
        """top_k < 1 should fail validation."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_k=0)

    def test_invalid_threshold(self):
        """score_threshold > 1 should fail validation."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", score_threshold=1.5)


@pytest.mark.unit
class TestResponseSchemas:
    """Test response schema construction."""

    def test_add_entries_response(self):
        """AddEntriesResponse construction."""
        ids = [uuid4(), uuid4()]
        cid = uuid4()
        resp = AddEntriesResponse(
            entry_ids=ids,
            collection_id=cid,
            entries_added=2,
            embedding_model="text-embedding-3-small",
        )
        assert resp.entry_ids == ids
        assert resp.entries_added == 2

    def test_search_response(self):
        """SearchResponse construction."""
        result = SearchResultItem(
            entry_id=uuid4(),
            content="match",
            score=0.87,
            metadata={"key": "val"},
        )
        resp = SearchResponse(
            results=[result],
            query="test query",
            collection_id=uuid4(),
            total_results=1,
        )
        assert len(resp.results) == 1
        assert resp.results[0].score == 0.87

    def test_entry_response(self):
        """EntryResponse construction."""
        now = datetime.now(UTC)
        resp = EntryResponse(
            entry_id=uuid4(),
            content="stored text",
            metadata={"key": "val"},
            source_ref="doc:1",
            created_at=now,
        )
        assert resp.content == "stored text"
        assert resp.created_at == now
