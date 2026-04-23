"""
PgvectorBackend — pgvector-backed index using PostgreSQL.

Project Paros: Knowledge Index feature.

This is the v1 built-in backend. It stores vectors in a vector(1536) column
and uses HNSW indexes for approximate nearest neighbor search via cosine distance.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.index_entry import IndexEntry as IndexEntryModel
from analysi.services.index_backends.base import (
    IndexEntry,
    SearchResult,
    StoredEntry,
)

logger = get_logger(__name__)

# Maximum vector dimension for the fixed-size column
MAX_VECTOR_DIM = 1536


def pad_vector(embedding: list[float], target_dim: int = MAX_VECTOR_DIM) -> list[float]:
    """Pad a vector with trailing zeros to reach target dimension.

    Cosine similarity is unaffected by zero-padding because
    the angle between vectors is preserved.

    Vectors that already match the target dimension are returned as-is.
    Vectors longer than the target are rejected — silent truncation would
    degrade retrieval quality without any visible signal.

    Args:
        embedding: Original embedding vector.
        target_dim: Target dimension (default 1536).

    Returns:
        Padded vector of exactly target_dim dimensions.

    Raises:
        ValueError: If embedding exceeds target_dim.
    """
    current_dim = len(embedding)
    if current_dim > target_dim:
        raise ValueError(
            f"Embedding has {current_dim} dimensions but the maximum "
            f"supported is {target_dim}. Use a smaller embedding model "
            f"or increase the vector column size."
        )
    if current_dim == target_dim:
        return embedding
    return embedding + [0.0] * (target_dim - current_dim)


class PgvectorBackend:
    """pgvector-backed index using PostgreSQL.

    All queries include tenant_id and collection_id filters
    for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        collection_id: UUID,
        tenant_id: str,
        entries: list[IndexEntry],
    ) -> list[UUID]:
        """Add entries with vector embeddings, idempotent on content.

        Vectors are zero-padded to MAX_VECTOR_DIM if shorter.
        Duplicate content (same collection_id + tenant_id + content SHA-256)
        is silently skipped via ON CONFLICT DO NOTHING.

        Returns list of entry UUIDs — newly inserted entries get fresh IDs,
        duplicate entries return their existing IDs.
        """
        if not entries:
            return []

        # Build rows for INSERT with content hashes.
        # Deduplicate within the batch — only the first occurrence of each
        # content hash is sent to the INSERT; all duplicates map to the same ID.
        values = []
        hashes = []
        seen_hashes: set[str] = set()
        for entry in entries:
            padded = pad_vector(entry.embedding)
            content_hash = hashlib.sha256(entry.content.encode("utf-8")).hexdigest()
            hashes.append(content_hash)
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                values.append(
                    {
                        "collection_id": collection_id,
                        "tenant_id": tenant_id,
                        "content": entry.content,
                        "content_hash": content_hash,
                        "embedding": padded,
                        "metadata": entry.metadata,
                        "source_ref": entry.source_ref,
                    }
                )

        # INSERT ... ON CONFLICT (collection_id, tenant_id, content_hash) DO NOTHING
        # RETURNING id, content_hash — so we know which rows were actually inserted.
        # Use __table__ (Core table) to avoid SQLAlchemy ORM 'metadata' attr conflict.
        table = IndexEntryModel.__table__
        stmt = (
            pg_insert(table)
            .values(values)
            .on_conflict_do_nothing(
                index_elements=["collection_id", "tenant_id", "content_hash"]
            )
            .returning(table.c.id, table.c.content_hash)
        )
        result = await self.session.execute(stmt)
        inserted_rows = result.all()
        inserted_by_hash = {row.content_hash: row.id for row in inserted_rows}

        # Find unique hashes that were skipped (already in DB)
        skipped_hashes = [h for h in seen_hashes if h not in inserted_by_hash]

        if skipped_hashes:
            # Fetch existing IDs for skipped content
            existing_stmt = select(
                IndexEntryModel.id, IndexEntryModel.content_hash
            ).where(
                IndexEntryModel.collection_id == collection_id,
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.content_hash.in_(skipped_hashes),
            )
            existing_result = await self.session.execute(existing_stmt)
            for row in existing_result.all():
                inserted_by_hash[row.content_hash] = row.id

        # Return IDs in the same order as the input entries
        ids = [inserted_by_hash[h] for h in hashes]

        new_count = len(inserted_rows)
        skip_count = len(entries) - new_count
        logger.info(
            "index_entries_added",
            collection_id=str(collection_id),
            tenant_id=tenant_id,
            count=new_count,
            skipped=skip_count,
        )
        return ids

    async def search(
        self,
        collection_id: UUID,
        tenant_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Cosine similarity search via pgvector <=> operator.

        Returns results ordered by score descending (most similar first).
        Score = 1 - cosine_distance, so range is [0, 1].
        """
        padded = pad_vector(query_embedding)

        # 1 - cosine_distance gives similarity in [0, 1]
        similarity = (1 - IndexEntryModel.embedding.cosine_distance(padded)).label(
            "score"
        )

        stmt = (
            select(IndexEntryModel, similarity)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
            .order_by(similarity.desc())
            .limit(top_k)
        )

        if metadata_filter:
            # JSONB containment: metadata @> filter
            stmt = stmt.where(IndexEntryModel.entry_metadata.op("@>")(metadata_filter))

        if score_threshold is not None:
            stmt = stmt.where(similarity >= score_threshold)

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            SearchResult(
                entry_id=row.IndexEntry.id,
                content=row.IndexEntry.content,
                score=float(row.score),
                metadata=row.IndexEntry.entry_metadata or {},
                source_ref=row.IndexEntry.source_ref,
            )
            for row in rows
        ]

    async def delete(
        self,
        collection_id: UUID,
        tenant_id: str,
        entry_ids: list[UUID],
    ) -> int:
        """Delete specific entries by ID. Returns count of deleted entries."""
        if not entry_ids:
            return 0

        stmt = (
            delete(IndexEntryModel)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
                IndexEntryModel.id.in_(entry_ids),
            )
            .returning(IndexEntryModel.id)
        )
        result = await self.session.execute(stmt)
        deleted = len(result.all())

        logger.info(
            "index_entries_deleted",
            collection_id=str(collection_id),
            tenant_id=tenant_id,
            count=deleted,
        )
        return deleted

    async def delete_all(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Delete all entries in a collection. Returns count deleted."""
        stmt = (
            delete(IndexEntryModel)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
            .returning(IndexEntryModel.id)
        )
        result = await self.session.execute(stmt)
        deleted = len(result.all())

        logger.info(
            "index_entries_deleted_all",
            collection_id=str(collection_id),
            tenant_id=tenant_id,
            count=deleted,
        )
        return deleted

    async def count(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Count entries in a collection."""
        stmt = (
            select(func.count())
            .select_from(IndexEntryModel)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_entries(
        self,
        collection_id: UUID,
        tenant_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[StoredEntry], int]:
        """List entries with pagination. Returns (entries, total_count)."""
        # Count total
        count_stmt = (
            select(func.count())
            .select_from(IndexEntryModel)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch page
        stmt = (
            select(IndexEntryModel)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
            .order_by(IndexEntryModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        entries = [
            StoredEntry(
                entry_id=row.id,
                content=row.content,
                metadata=row.entry_metadata or {},
                source_ref=row.source_ref,
                created_at=row.created_at,
            )
            for row in rows
        ]

        return entries, total
