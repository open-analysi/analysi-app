"""Schemas for Control Events API (Project Tilos)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ControlEventCreate(BaseModel):
    """Request body for manually creating a control event."""

    channel: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class ControlEventResponse(BaseModel):
    """API response for a single control event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    channel: str
    status: str
    retry_count: int
    payload: dict[str, Any]
    created_at: datetime
    claimed_at: datetime | None
