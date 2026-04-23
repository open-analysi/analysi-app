"""Kea Coordination database models."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base


class AnalysisGroup(Base):
    """Analysis Group model - groups alerts by rule_name for workflow generation."""

    __tablename__ = "analysis_groups"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Usually matches rule_name
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

    # Relationships
    workflow_generations: Mapped[list["WorkflowGeneration"]] = relationship(
        "WorkflowGeneration",
        back_populates="analysis_group",
        cascade="all, delete-orphan",
    )
    routing_rules: Mapped[list["AlertRoutingRule"]] = relationship(
        "AlertRoutingRule",
        back_populates="analysis_group",
        cascade="all, delete-orphan",
    )

    # Unique constraint: one group per title per tenant
    __table_args__ = (
        Index("idx_analysis_groups_tenant", "tenant_id"),
        Index("uq_analysis_groups_tenant_title", "tenant_id", "title", unique=True),
    )


class WorkflowGeneration(Base):
    """Workflow Generation model - tracks workflow generation lifecycle."""

    __tablename__ = "workflow_generations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    analysis_group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Workflow lifecycle tracking
    workflow_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )  # NULL until created
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Link to triggering alert (no FK due to partitioned alert_analysis table)
    triggering_alert_analysis_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # Progress tracking (incremental updates during execution)
    # Structure: {"phases": [{stage, status, started_at, completed_at?, tasks_count?}, ...]}
    # Note: DB column is still named current_phase, but stores incremental progress data
    current_phase: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Orchestration results (stored for audit trail)
    # Single JSONB field for all results: runbook, task_proposals, tasks_built,
    # workflow_composition, metrics, and error (if failed)
    orchestration_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Workspace path for cleanup
    workspace_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        server_default="/tmp/unknown",  # nosec B108
    )

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    analysis_group: Mapped["AnalysisGroup"] = relationship(
        "AnalysisGroup", back_populates="workflow_generations"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workflow_generations_tenant", "tenant_id"),
        Index("idx_workflow_generations_group", "analysis_group_id"),
        Index(
            "idx_workflow_generations_active",
            "tenant_id",
            "analysis_group_id",
            "is_active",
            postgresql_where=(is_active == True),  # noqa: E712
        ),
        Index("idx_workflow_generations_status", "status"),
        Index("idx_workflow_generations_status_created", "status", "created_at"),
    )


class AlertRoutingRule(Base):
    """Alert Routing Rule model - maps analysis groups to workflows."""

    __tablename__ = "alert_routing_rules"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    analysis_group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

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

    # Relationships
    analysis_group: Mapped["AnalysisGroup"] = relationship(
        "AnalysisGroup", back_populates="routing_rules"
    )

    # Indexes for routing queries
    __table_args__ = (
        Index("idx_alert_routing_rules_tenant", "tenant_id"),
        Index("idx_alert_routing_rules_group", "analysis_group_id"),
    )
