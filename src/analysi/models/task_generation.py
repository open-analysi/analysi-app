"""Task Generation database model.

Tracks individual task generation runs. Supports two creation sources:
- 'workflow_generation': Created by Kea during parallel task building (Stage 3).
  Has workflow_generation_id set; description is NULL.
- 'api': Created via POST /v1/{tenant}/task-generations REST API.
  Has description set; workflow_generation_id may be NULL.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base

if TYPE_CHECKING:
    from .kea_coordination import WorkflowGeneration


class TaskGeneration(Base):
    """Task Generation model - tracks individual task generation.

    Used by both:
    1. Kea workflow generation (Stage 3 parallel task building)
    2. Standalone task generation API (POST /v1/{tenant}/task-generations)

    Each record captures:
    - Input context (proposal, alert, runbook) for restart capability
    - Real-time progress messages from agent execution
    - Result on completion (task_id, cy_name or error details)
    """

    __tablename__ = "task_generations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Nullable: NULL for standalone API builds, set for Kea builds
    workflow_generation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_generations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Source of the build: 'workflow_generation' (Kea) or 'api' (standalone REST API)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="workflow_generation"
    )

    # Human-provided description for standalone API builds (NULL for Kea builds)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional reference alert for standalone builds (no FK; alerts are partitioned)
    alert_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Status tracking: pending, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    # Input context for restart capability
    # Contains: {proposal: {...}, alert: {...}, runbook: "..."}
    input_context: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Result on completion
    # Success: {task_id: "...", cy_name: "...", recovered: bool}
    # Failure: {error: "...", error_type: "...", recovered: bool}
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Real-time progress messages (FIFO, max 100 enforced by application)
    # Each message: {timestamp, message, level, details}
    progress_messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    # Metadata (UUID FK to users table)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        default=UUID("00000000-0000-0000-0000-000000000001"),
    )
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
        server_default=func.current_timestamp(),
    )

    # Relationships
    workflow_generation: Mapped["WorkflowGeneration | None"] = relationship(
        "WorkflowGeneration"
    )

    # Indexes — names kept for backward compatibility with existing DB indexes
    __table_args__ = (
        Index("idx_task_building_runs_tenant", "tenant_id"),
        Index("idx_task_building_runs_generation", "workflow_generation_id"),
        Index("idx_task_building_runs_status", "status"),
        Index("idx_task_building_runs_source", "source"),
        Index(
            "idx_task_building_runs_alert",
            "alert_id",
            postgresql_where=(alert_id.isnot(None)),
        ),
    )
