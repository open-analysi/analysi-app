"""Pydantic schemas for the Schedules REST API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScheduleCreate(BaseModel):
    """Create a generic schedule."""

    target_type: str = Field(..., description="'task' or 'workflow'")
    target_id: UUID = Field(..., description="Component ID (task) or workflow ID")
    schedule_type: str = Field(
        "every", description="Schedule type (only 'every' in v1)"
    )
    schedule_value: str = Field(
        ..., description="Interval string, e.g. '60s', '5m', '1h'"
    )
    timezone: str = Field("UTC", description="IANA timezone")
    enabled: bool = Field(False, description="Whether the schedule is active")
    params: dict[str, Any] | None = Field(
        None, description="Parameters passed to the target"
    )
    origin_type: str = Field("user", description="'system', 'user', or 'pack'")
    integration_id: str | None = Field(
        None, description="Integration ID for system-managed schedules"
    )


class ScheduleUpdate(BaseModel):
    """Partial update for a schedule."""

    schedule_value: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    params: dict[str, Any] | None = None


class ScheduleResponse(BaseModel):
    """Full schedule in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    target_type: str
    target_id: UUID
    schedule_type: str
    schedule_value: str
    timezone: str
    enabled: bool
    params: dict[str, Any] | None = None
    origin_type: str
    integration_id: str | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TargetScheduleCreate(BaseModel):
    """Create a schedule via convenience endpoint (target inferred from URL)."""

    schedule_type: str = Field(
        "every", description="Schedule type (only 'every' in v1)"
    )
    schedule_value: str = Field(
        ..., description="Interval string, e.g. '60s', '5m', '1h'"
    )
    timezone: str = Field("UTC", description="IANA timezone")
    enabled: bool = Field(False, description="Whether the schedule is active")
    params: dict[str, Any] | None = Field(
        None, description="Parameters passed to the target"
    )
