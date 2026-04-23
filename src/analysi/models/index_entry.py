"""
Index Entry model — vector-embedded entries stored in a knowledge index collection.

Project Paros: Knowledge Index feature.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class IndexEntry(Base):
    """
    A single text entry stored in a knowledge index collection.

    Each entry contains the original text, its vector embedding (for similarity search),
    arbitrary metadata, and an optional source reference for traceability.

    The collection_id FK points to component(id) so ON DELETE CASCADE from
    Component deletion cascades through to entries.
    """

    __tablename__ = "index_entries"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Which collection owns this entry (FK to component, not ku_index)
    collection_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalized for query performance and tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # The actual text content that was embedded
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 hash of content for idempotent deduplication.
    # Unique within (collection_id, tenant_id, content_hash).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Vector embedding — fixed 1536 dimensions (OpenAI text-embedding-3-small).
    # Shorter vectors (e.g., Gemini 768-dim) are zero-padded by the service layer.
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=True)

    # Arbitrary key-value metadata for filtering (JSONB with GIN index)
    # Python attr is 'entry_metadata' to avoid SQLAlchemy reserved name;
    # DB column is 'metadata' (same pattern as KUDocument.doc_metadata)
    entry_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict
    )

    # Origin reference (e.g., "document:abc123", "alert:xyz789")
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    def __repr__(self) -> str:
        return (
            f"<IndexEntry(id={self.id}, collection_id={self.collection_id}, "
            f"tenant_id={self.tenant_id})>"
        )
