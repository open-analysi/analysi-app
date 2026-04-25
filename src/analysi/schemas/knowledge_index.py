"""
Knowledge Index entry and search schemas for API requests and responses.

Project Paros: Knowledge Index feature.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ─── Request schemas ────────────────────────────────────────────────


class EntryInput(BaseModel):
    """A single entry to add to an index collection."""

    content: str = Field(
        ..., min_length=1, description="Text content to embed and store"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key-value metadata for filtering"
    )
    source_ref: str | None = Field(
        None, description="Origin reference (e.g., 'document:abc123')"
    )


class AddEntriesRequest(BaseModel):
    """Request to add entries to a knowledge index collection."""

    entries: list[EntryInput] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Entries to add (max 100 per request)",
    )


class SearchRequest(BaseModel):
    """Request to search a knowledge index collection."""

    query: str = Field(..., min_length=1, description="Natural-language search query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    score_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity score (0-1)"
    )
    metadata_filter: dict[str, Any] | None = Field(
        None, description="JSONB containment filter on entry metadata"
    )


# ─── Response schemas ───────────────────────────────────────────────


class AddEntriesResponse(BaseModel):
    """Response after adding entries to a collection."""

    entry_ids: list[UUID]
    collection_id: UUID
    entries_added: int
    embedding_model: str | None

    model_config = ConfigDict(from_attributes=True)


class SearchResultItem(BaseModel):
    """A single search result."""

    entry_id: UUID
    content: str
    score: float = Field(description="Similarity score 0-1 (higher = more similar)")
    metadata: dict[str, Any]
    source_ref: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Response from a search query."""

    results: list[SearchResultItem]
    query: str
    collection_id: UUID
    total_results: int

    model_config = ConfigDict(from_attributes=True)


class EntryResponse(BaseModel):
    """A stored entry returned from list operations."""

    entry_id: UUID
    content: str
    metadata: dict[str, Any]
    source_ref: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
