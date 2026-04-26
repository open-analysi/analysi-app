"""
TaskRun Model

SQLAlchemy model for task execution runs with partitioning support.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Interval, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base

if TYPE_CHECKING:
    from .task import Task
    from .workflow_execution import WorkflowRun


class TaskRun(Base):
    """
    Task execution run model with partitioning support.

    Stores execution details for both saved tasks and ad-hoc Cy scripts.
    Table is partitioned by created_at (daily partitions).
    """

    __tablename__ = "task_runs"

    # Core execution fields
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.component_id"), nullable=True
    )  # Nullable for ad-hoc
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )  # Links task to workflow execution (no FK due to partitioning)
    workflow_node_instance_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )  # Links task to specific node instance (no FK due to partitioning)
    cy_script: Mapped[str | None] = mapped_column(Text)  # For ad-hoc executions
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running"
    )  # See TaskConstants.Status: pending, running, completed, failed, paused
    duration: Mapped[timedelta | None] = mapped_column(Interval)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Input/Output storage fields
    input_type: Mapped[str | None] = mapped_column(String(20))  # inline, s3, file
    input_location: Mapped[str | None] = mapped_column(Text)
    input_content_type: Mapped[str | None] = mapped_column(String(100))
    output_type: Mapped[str | None] = mapped_column(String(20))  # inline, s3, file
    output_location: Mapped[str | None] = mapped_column(Text)
    output_content_type: Mapped[str | None] = mapped_column(String(100))

    # Execution configuration
    executor_config: Mapped[dict | None] = mapped_column(JSONB)
    execution_context: Mapped[dict | None] = mapped_column(JSONB)

    # Project Symi: execution context — analysis | scheduled | ad_hoc
    run_context: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ad_hoc"
    )

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="task_runs")
    # Relationship to WorkflowRun - nullable since tasks can run without workflows
    workflow_run: Mapped["WorkflowRun | None"] = relationship(
        "WorkflowRun",
        back_populates="task_runs",
        foreign_keys=[workflow_run_id],
        primaryjoin="TaskRun.workflow_run_id == WorkflowRun.id",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRun(id={self.id}, tenant_id={self.tenant_id}, status={self.status})>"
        )
