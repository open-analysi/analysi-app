"""Content review database model.

Tracks content flowing into skills through the content review pipeline.
Each record represents one piece of content going through content gates + async LLM review.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.constants import ContentReviewConstants
from analysi.db.base import Base

ContentReviewStatus = ContentReviewConstants.Status


class ContentReview(Base):
    """Tracks a content review through the pipeline.

    Lifecycle: pending → approved/flagged → applied/rejected
    On pipeline error: pending → failed
    Owner bypass: pending → approved (content gates run, LLM skipped)
    """

    __tablename__ = "content_reviews"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Pipeline configuration
    pipeline_name: Mapped[str] = mapped_column(String(50), nullable=False)
    pipeline_mode: Mapped[str] = mapped_column(
        Enum(
            "review",
            "review_transform",
            name="content_review_pipeline_mode",
            create_type=False,
        ),
        nullable=False,
    )

    # Trigger source
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Content reference
    document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content gate result (Tier 1)
    content_gates_passed: Mapped[bool] = mapped_column(
        "sync_checks_passed", Boolean, nullable=False, default=False
    )
    content_gates_result: Mapped[dict | None] = mapped_column(
        "sync_checks_result", JSONB, nullable=True
    )

    # Pipeline result (Tier 2 — populated by worker)
    pipeline_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transformed_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "approved",
            "flagged",
            "applied",
            "rejected",
            "failed",
            name="content_review_status",
            create_type=False,
        ),
        nullable=False,
        default=ContentReviewStatus.PENDING.value,
    )
    applied_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Actor
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    # Bypass
    bypassed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_cr_tenant_skill", "tenant_id", "skill_id"),
        Index("idx_cr_tenant_status", "tenant_id", "status"),
        Index("idx_cr_tenant_created", "tenant_id", "created_at"),
        Index("idx_cr_document", "document_id"),
        Index("idx_cr_tenant_pipeline_status", "tenant_id", "pipeline_name", "status"),
        Index(
            "idx_cr_active_reviews",
            "tenant_id",
            "status",
            "created_at",
            postgresql_where="status IN ('pending', 'flagged', 'approved')",
        ),
    )
