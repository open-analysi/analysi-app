"""Knowledge Extraction database model — Hydra project."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class KnowledgeExtraction(Base):
    """Tracks a knowledge extraction from a source KUDocument into a skill.

    Lifecycle: pending → completed → applied | rejected
    On failure: pending → failed
    """

    __tablename__ = "knowledge_extractions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Lifecycle status
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "completed",
            "rejected",
            "applied",
            "failed",
            name="extraction_status",
            create_type=False,
        ),
        nullable=False,
        default="pending",
    )

    # Pipeline node outputs
    classification: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    relevance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    placement: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transformed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    merge_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Apply result
    applied_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="SET NULL"),
        nullable=True,
    )

    # LLM-generated summary
    extraction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rejection / error
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )

    __table_args__ = (
        Index("idx_knowledge_extractions_tenant_skill", "tenant_id", "skill_id"),
        Index("idx_knowledge_extractions_tenant_status", "tenant_id", "status"),
        Index("idx_knowledge_extractions_document", "document_id"),
    )
