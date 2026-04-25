"""Pydantic schemas for Task Generations.

Supports both:
- Kea workflow generation builds (workflow_generation_id set, source='workflow_generation')
- Standalone API builds (description set, source='api')
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskGenerationStatus(StrEnum):
    """Status of a task generation."""

    PENDING = "pending"  # Created, not yet started
    RUNNING = "running"  # Agent executing
    COMPLETED = "completed"  # Task created successfully
    FAILED = "failed"  # Agent or task creation failed
    CANCELLED = "cancelled"  # Manually cancelled


# Backward-compatible alias
TaskBuildingRunStatus = TaskGenerationStatus


class TaskGenerationSource(StrEnum):
    """Source of a task generation."""

    WORKFLOW_GENERATION = (
        "workflow_generation"  # Created by Kea during workflow generation
    )
    API = "api"  # Created via POST /v1/{tenant}/task-generations


# Backward-compatible alias
TaskBuildingRunSource = TaskGenerationSource


# Request Schemas
class TaskGenerationCreate(BaseModel):
    """Schema for creating a task generation (used by Kea internal API and standalone builds)."""

    workflow_generation_id: UUID | None = Field(
        None,
        description="ID of the parent workflow generation (None for standalone builds)",
    )
    input_context: dict[str, Any] = Field(
        ...,
        description="Full input context: {proposal: {...}, alert: {...}, runbook: '...'}",
    )


# Backward-compatible alias
TaskBuildingRunCreate = TaskGenerationCreate


class TaskBuildRequest(BaseModel):
    """Schema for the public task build API: POST /v1/{tenant}/task-generations.

    Supports two modes:
    - From scratch: Only provide description (and optionally alert_id).
    - With starting point: Provide task_id of an existing task to modify.
      The description then explains WHAT to change about the existing task.
    """

    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Description of the task to build, or what to change if task_id is provided.",
    )
    alert_id: UUID | None = Field(
        None,
        description="Optional alert ID to use as example context. "
        "The alert must exist and belong to the same tenant.",
    )
    task_id: UUID | None = Field(
        None,
        description="Optional existing task as starting point. "
        "When provided, the agent modifies this task instead of creating from scratch. "
        "The description field then describes what to change.",
    )


class TaskGenerationStatusUpdate(BaseModel):
    """Schema for updating task generation status."""

    status: TaskGenerationStatus = Field(..., description="New status")
    result: dict[str, Any] | None = Field(
        None,
        description="Result on completion. Success: {task_id, cy_name, recovered}. Failure: {error, error_type, recovered}",
    )


# Backward-compatible alias
TaskBuildingRunStatusUpdate = TaskGenerationStatusUpdate


class ProgressMessage(BaseModel):
    """A single progress message from agent execution."""

    timestamp: datetime = Field(..., description="When the message was created")
    message: str = Field(..., description="Progress message text")
    level: str = Field("info", description="Log level: info, warning, error")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional structured details"
    )


class TaskGenerationProgressAppend(BaseModel):
    """Schema for appending progress messages."""

    messages: list[ProgressMessage] = Field(
        ..., min_length=1, description="Progress messages to append"
    )


# Backward-compatible alias
TaskBuildingRunProgressAppend = TaskGenerationProgressAppend


# Response Schemas
class TaskGenerationResponse(BaseModel):
    """Schema for task generation response."""

    id: UUID
    tenant_id: str
    workflow_generation_id: UUID | None = None
    source: TaskGenerationSource = TaskGenerationSource.WORKFLOW_GENERATION
    description: str | None = None
    alert_id: UUID | None = None
    status: TaskGenerationStatus
    input_context: dict[str, Any]
    result: dict[str, Any] | None = None
    progress_messages: list[dict[str, Any]] = Field(default_factory=list)
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Backward-compatible alias
TaskBuildingRunResponse = TaskGenerationResponse


class TaskBuildResponse(BaseModel):
    """Accepted response for POST /v1/{tenant}/task-generations."""

    id: UUID = Field(..., description="Task generation ID for polling status")
    status: TaskGenerationStatus = Field(
        ..., description="Initial status (always 'pending')"
    )
    description: str = Field(..., description="Task description submitted")
    alert_id: UUID | None = Field(None, description="Alert ID if provided")
    task_id: UUID | None = Field(
        None, description="Existing task ID used as starting point, if provided"
    )
    created_at: datetime = Field(..., description="When the build was queued")

    model_config = ConfigDict(from_attributes=True)
