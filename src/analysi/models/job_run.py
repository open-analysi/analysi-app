"""
JobRun model — audit record for scheduled executions.

Project Symi: Replaces IntegrationRun. Created each time a Schedule fires,
linking the schedule to the resulting TaskRun or WorkflowRun.
Partitioned monthly by created_at.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class JobRun(Base):
    """Audit record created each time a Schedule fires.

    Partitioned monthly by ``created_at`` (same pattern as integration_runs).
    """

    __tablename__ = "job_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("schedules.id", ondelete="SET NULL"),
    )

    # What was executed
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    task_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    workflow_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    # Integration context (nullable -- only for integration-related runs)
    integration_id: Mapped[str | None] = mapped_column(String(255))
    action_id: Mapped[str | None] = mapped_column(String(100))

    # Status (mirrors the target run status)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    # Timing
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Job tracking (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_job_runs_tenant", "tenant_id"),
        Index("idx_job_runs_schedule", "schedule_id"),
        Index("idx_job_runs_integration", "tenant_id", "integration_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    def __repr__(self) -> str:
        return (
            f"<JobRun(id={self.id}, schedule_id={self.schedule_id}, "
            f"status={self.status})>"
        )
