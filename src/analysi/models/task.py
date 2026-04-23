"""
Task model - AI agent tasks with Cy script execution capabilities.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from .task_run import TaskRun

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.constants import TaskFunctionType, TaskModeType, TaskScopeType
from analysi.db.base import Base

from .component import Component

TaskFunction = TaskFunctionType
TaskScope = TaskScopeType
TaskMode = TaskModeType


class Task(Base):
    """
    Task model for AI agent tasks with Cy script execution and LLM configuration.

    Links to Component via component_id foreign key.
    """

    __tablename__ = "tasks"

    # Own primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Foreign key to component table
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Task-specific fields
    directive: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str | None] = mapped_column(Text)
    function: Mapped[str | None] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(100), default="processing")
    schedule: Mapped[str | None] = mapped_column(String(255))  # Cron expression
    mode: Mapped[str] = mapped_column(
        String(50), nullable=False, default=TaskMode.SAVED
    )
    data_samples: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    # LLM configuration as JSON
    llm_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Project Symi: provenance and integration link
    integration_id: Mapped[str | None] = mapped_column(String(255))
    origin_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )  # "system" | "user" | "pack"
    managed_resource_key: Mapped[str | None] = mapped_column(
        String(50)
    )  # e.g. "health_check", "alert_ingestion", "sourcetype_discovery"

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
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    component: Mapped["Component"] = relationship("Component", back_populates="task")
    task_runs: Mapped[list["TaskRun"]] = relationship("TaskRun", back_populates="task")

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, component_id={self.component_id}, function={self.function})>"
