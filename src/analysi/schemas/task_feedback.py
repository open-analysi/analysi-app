"""Pydantic schemas for Task Feedback API (Project Zakynthos)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskFeedbackCreate(BaseModel):
    """Request body for creating task feedback."""

    feedback: str = Field(..., min_length=1, description="The feedback text")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured metadata (priority, category, etc.)",
    )


class TaskFeedbackUpdate(BaseModel):
    """Request body for updating task feedback."""

    feedback: str | None = Field(
        None, min_length=1, description="Updated feedback text"
    )
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")


class TaskFeedbackResponse(BaseModel):
    """API response for a single feedback entry.

    Flattened view assembled from Component + KUDocument.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Feedback component ID")
    tenant_id: str
    task_component_id: UUID = Field(description="Target task's component ID")
    title: str = Field(description="Short LLM-generated title for the feedback")
    feedback: str = Field(description="The feedback text")
    metadata: dict[str, Any] = Field(description="Structured metadata")
    status: str = Field(description="enabled or disabled")
    created_by: UUID
    created_at: datetime
    updated_at: datetime
