"""
IndexBackend protocol and data types for pluggable index backends.

Project Paros: Knowledge Index feature.

The IndexBackend protocol defines the contract that all index backend
implementations must satisfy. Backends handle storage and retrieval of
embedded entries. They do NOT handle embedding generation — the service does that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass
class IndexEntry:
    """An entry to add to an index.

    The service layer generates the embedding from the text content
    and passes it here. Backends receive ready-to-store vectors.
    """

    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    source_ref: str | None = None
    entry_id: UUID | None = None  # Assigned by backend if None


@dataclass
class SearchResult:
    """A single search result returned from the index.

    Score is in [0, 1] range — higher means more similar.
    Computed as 1 - cosine_distance for pgvector backend.
    """

    entry_id: UUID
    content: str
    score: float
    metadata: dict[str, Any]
    source_ref: str | None = None


@dataclass
class StoredEntry:
    """A stored entry returned from list/get operations."""

    entry_id: UUID
    content: str
    metadata: dict[str, Any]
    source_ref: str | None
    created_at: datetime


class IndexBackend(Protocol):
    """Protocol that all index backend implementations must satisfy.

    Backends handle storage and retrieval of embedded entries.
    They do NOT handle embedding generation — the service does that.

    Thread/session safety: DB-backed backends receive an AsyncSession.
    Non-DB backends (e.g., ChromaDB client) manage their own connections.
    """

    async def add(
        self,
        collection_id: UUID,
        tenant_id: str,
        entries: list[IndexEntry],
    ) -> list[UUID]:
        """Add entries to a collection. Returns assigned entry IDs."""
        ...

    async def search(
        self,
        collection_id: UUID,
        tenant_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar entries by cosine similarity.

        Returns results ordered by score descending (most similar first).
        If score_threshold is set, only results above that score are returned.
        metadata_filter uses JSONB containment (@>) for filtering.
        """
        ...

    async def delete(
        self,
        collection_id: UUID,
        tenant_id: str,
        entry_ids: list[UUID],
    ) -> int:
        """Delete specific entries. Returns count of deleted entries."""
        ...

    async def delete_all(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Delete all entries in a collection. Returns count deleted."""
        ...

    async def count(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Count entries in a collection."""
        ...

    async def list_entries(
        self,
        collection_id: UUID,
        tenant_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[StoredEntry], int]:
        """List entries with pagination. Returns (entries, total_count)."""
        ...
