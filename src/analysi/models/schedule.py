"""
Schedule model — generic scheduler for Tasks and Workflows.

Project Symi: Replaces IntegrationSchedule with a generic schedule
that can target any Task or Workflow.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class Schedule(Base):
    """Generic schedule that fires a Task or Workflow on a recurring interval."""

    __tablename__ = "schedules"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # What to run
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # When to run
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    schedule_value: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Parameters passed to the target as input
    params: Mapped[dict | None] = mapped_column(JSONB)

    # Provenance
    origin_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    integration_id: Mapped[str | None] = mapped_column(String(255))

    # Scheduling state
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        Index(
            "idx_schedules_tenant_enabled",
            "tenant_id",
            "enabled",
            postgresql_where=(enabled == True),  # noqa: E712
        ),
        Index(
            "idx_schedules_next_run",
            "next_run_at",
            postgresql_where=(enabled == True),  # noqa: E712
        ),
        Index(
            "idx_schedules_integration",
            "tenant_id",
            "integration_id",
            postgresql_where=(integration_id != None),  # noqa: E711
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Schedule(id={self.id}, target_type={self.target_type}, "
            f"target_id={self.target_id}, enabled={self.enabled})>"
        )
