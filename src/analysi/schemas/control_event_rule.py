"""Schemas for Control Event Rule CRUD API (Project Tilos)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_VALID_TARGET_TYPES = {"task", "workflow"}


class ControlEventRuleCreate(BaseModel):
    """Request body for creating a control event rule."""

    name: str = Field(..., min_length=1, max_length=255)
    channel: str = Field(..., min_length=1, max_length=100)
    target_type: str = Field(..., description="'task' or 'workflow'")
    target_id: UUID
    enabled: bool = Field(default=True)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, v: str) -> str:
        if v not in _VALID_TARGET_TYPES:
            raise ValueError(
                f"target_type must be one of: {sorted(_VALID_TARGET_TYPES)}"
            )
        return v


class ControlEventRuleUpdate(BaseModel):
    """Request body for partially updating a control event rule."""

    name: str | None = Field(None, min_length=1, max_length=255)
    target_type: str | None = None
    target_id: UUID | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None

    @field_validator("target_type")
    @classmethod
    def validate_target_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_TARGET_TYPES:
            raise ValueError(
                f"target_type must be one of: {sorted(_VALID_TARGET_TYPES)}"
            )
        return v


class ControlEventRuleResponse(BaseModel):
    """API response for a single control event rule."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    name: str
    channel: str
    target_type: str
    target_id: UUID
    enabled: bool
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
