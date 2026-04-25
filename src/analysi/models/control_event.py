"""SQLAlchemy models for control event bus (Project Tilos)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class ControlEvent(Base):
    """
    Transactional outbox entry for the control event bus.

    Monthly-partitioned by created_at.  Producers INSERT a row in the same
    DB transaction as their business state change.  The consume_control_events
    cron claims pending rows and enqueues execute_control_event ARQ jobs.
    """

    __tablename__ = "control_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_control_events_status_channel", "status", "channel", "created_at"),
        Index("idx_control_events_tenant_status", "tenant_id", "status", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )


class ControlEventRule(Base):
    """
    Operator-configured rule that binds a (tenant, channel) pair to a Task or Workflow.

    The bus evaluates only channel match + enabled flag.  Fine-grained filtering
    lives inside the target Task/Workflow (two-layer model).
    """

    __tablename__ = "control_event_rules"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'task' | 'workflow'
    target_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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

    __table_args__ = (
        Index(
            "idx_control_event_rules_tenant_channel", "tenant_id", "channel", "enabled"
        ),
    )


class ControlEventDispatch(Base):
    """
    Per-rule idempotency record for a control event execution.

    UNIQUE(control_event_id, rule_id) prevents double-dispatch even under retries.
    Rows are deleted atomically when the event is marked completed; kept on failure
    so the next retry can check which rules already completed.
    """

    __tablename__ = "control_event_dispatches"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # No FK to control_events — it is partitioned and Postgres requires partition key in FK
    control_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    rule_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("control_event_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running"
    )  # running|completed|failed
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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

    __table_args__ = (
        UniqueConstraint(
            "control_event_id", "rule_id", name="uq_control_event_dispatches_event_rule"
        ),
        Index("idx_control_event_dispatches_event", "control_event_id"),
    )
