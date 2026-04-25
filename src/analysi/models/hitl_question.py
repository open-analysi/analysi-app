"""SQLAlchemy model for HITL question tracking."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class HITLQuestion(Base):
    """
    Tracks questions posed to humans during workflow execution.

    HITL — Project Kalymnos: When a Cy script calls a hi-latency tool (e.g.,
    app::slack::ask), the task pauses and a row is created here. When the human
    answers (via Slack button click), the answer is recorded and a
    ``human:responded`` control event is emitted to resume the paused workflow.

    Monthly-partitioned by ``created_at``.
    """

    __tablename__ = "hitl_questions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Multi-tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Question identification (Slack message_ts + channel)
    question_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(255), nullable=False)

    # Question content
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Status lifecycle: pending → answered | expired
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    # Answer (nullable until answered)
    answer: Mapped[str | None] = mapped_column(String(500))
    answered_by: Mapped[str | None] = mapped_column(String(255))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timeout
    timeout_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Links to paused execution (no FKs — partitioned tables)
    task_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    workflow_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    node_instance_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    analysis_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_hitl_questions_tenant_status", "tenant_id", "status", "created_at"),
        Index("idx_hitl_questions_ref_channel", "question_ref", "channel"),
        Index("idx_hitl_questions_task_run", "task_run_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )
