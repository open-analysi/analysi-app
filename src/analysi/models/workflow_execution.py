"""
SQLAlchemy models for workflow execution (dynamic/runtime).
These models represent workflow runs and their execution state.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base


class WorkflowRun(Base):
    """
    Workflow execution instance (partitioned by created_at).
    Represents a single execution of a workflow blueprint.
    """

    __tablename__ = "workflow_runs"

    # Primary identification (composite primary key for partitioning)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), default=uuid4, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Tenant and workflow reference
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    workflow_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Execution status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )  # See WorkflowConstants.Status: pending, running, completed, failed, cancelled, paused

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Input/Output storage (follows task_runs pattern)
    input_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # inline, s3
    input_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # inline, s3
    output_location: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution context (passed from caller, e.g., analysis_id for artifact linking).
    # Also stores aggregate LLM usage under key "_llm_usage" when the run terminates
    # (populated by WorkflowExecutor._aggregate_llm_usage at completion/failure).
    # _llm_usage schema: {"input_tokens": int, "output_tokens": int, "total_tokens": int, "cost_usd": float|null}
    execution_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Composite primary key required for partitioned table
    __table_args__ = (PrimaryKeyConstraint("id", "created_at"),)

    # Relationships
    # Relationship to TaskRun - uses workflow_run_id foreign key in TaskRun
    # Note: TaskRun.workflow_run_id is nullable since tasks can run without workflows
    task_runs = relationship(
        "TaskRun",
        back_populates="workflow_run",
        foreign_keys="TaskRun.workflow_run_id",
        primaryjoin="WorkflowRun.id == TaskRun.workflow_run_id",
    )

    def __repr__(self) -> str:
        return f"<WorkflowRun(id={self.id}, status='{self.status}')>"


class WorkflowNodeInstance(Base):
    """
    Node execution instance within a workflow run (partitioned).
    Represents the execution of a single node.
    """

    __tablename__ = "workflow_node_instances"

    # Primary identification (composite primary key for partitioning)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), default=uuid4, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Run and node references
    workflow_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # References static node_id
    node_uuid: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workflow_nodes.id"),
        nullable=False,
    )

    # Task execution reference (for task nodes)
    task_run_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )

    # Parent relationship (for foreach children)
    parent_instance_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True, index=True
    )
    loop_context: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # {item_index, item_key, total_items}

    # Execution status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )  # See WorkflowConstants.Status: pending, running, completed, failed, cancelled, paused

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Input/Output storage
    input_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # inline, s3
    input_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # inline, s3
    output_location: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Template reference (for transformation nodes)
    template_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("node_templates.id"),
        nullable=True,
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Composite primary key required for partitioned table
    __table_args__ = (PrimaryKeyConstraint("id", "created_at"),)

    def __repr__(self) -> str:
        return f"<WorkflowNodeInstance(id={self.id}, node_id='{self.node_id}', status='{self.status}')>"


class WorkflowEdgeInstance(Base):
    """
    Edge execution instance representing data flow (partitioned).
    Tracks when data was delivered between node instances.
    """

    __tablename__ = "workflow_edge_instances"

    # Primary identification (composite primary key for partitioning)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), default=uuid4, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    # Run and edge references
    workflow_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    edge_id: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # References static edge_id
    edge_uuid: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workflow_edges.id"),
        nullable=False,
    )

    # Instance connections
    from_instance_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )
    to_instance_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=False, index=True
    )

    # Delivery tracking
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Composite primary key required for partitioned table
    __table_args__ = (PrimaryKeyConstraint("id", "created_at"),)

    def __repr__(self) -> str:
        return f"<WorkflowEdgeInstance(id={self.id}, edge_id='{self.edge_id}')>"
