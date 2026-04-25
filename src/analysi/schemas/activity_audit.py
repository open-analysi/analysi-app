"""Pydantic schemas for Activity Audit Trail API."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActorType(StrEnum):
    """Types of actors that can perform actions."""

    USER = "user"
    SYSTEM = "system"
    API_KEY = "api_key"
    WORKFLOW = "workflow"
    EXTERNAL_USER = "external_user"


class AuditSource(StrEnum):
    """Subsystems that can generate audit logs."""

    REST_API = "rest_api"
    MCP = "mcp"
    UI = "ui"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class ActivityAuditBase(BaseModel):
    """Base schema for activity audit events."""

    actor_id: UUID = Field(
        ...,
        description="UUID reference to users table",
    )
    actor_type: ActorType = Field(
        default=ActorType.USER,
        description="Type of actor performing the action",
    )
    source: AuditSource = Field(
        default=AuditSource.UNKNOWN,
        description="Subsystem that generated the audit log (rest_api, mcp, ui, internal)",
    )
    action: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Action performed (e.g., 'workflow.execute', 'alert.view')",
    )
    resource_type: str | None = Field(
        None,
        max_length=100,
        description="Type of resource acted upon (e.g., 'workflow', 'alert')",
    )
    resource_id: str | None = Field(
        None,
        max_length=255,
        description="ID of the resource acted upon",
    )
    details: dict[str, Any] | None = Field(
        None,
        description="Additional structured data about the action",
    )
    ip_address: str | None = Field(
        None,
        max_length=45,
        description="Client IP address (IPv4 or IPv6)",
    )
    user_agent: str | None = Field(
        None,
        description="Browser/client user agent string",
    )
    request_id: str | None = Field(
        None,
        max_length=100,
        description="Request correlation ID for tracing",
    )


class ActivityAuditCreate(ActivityAuditBase):
    """Schema for creating an activity audit event.

    actor_id is optional in the request body — the server always overrides it
    with the authenticated user's UUID from the auth token.
    """

    actor_id: UUID | None = Field(  # type: ignore[assignment]
        default=None,
        description="Ignored — server uses authenticated user's UUID",
    )


class ActivityAuditResponse(ActivityAuditBase):
    """Schema for activity audit event response."""

    model_config = ConfigDict(from_attributes=True)

    actor_id: UUID = Field(
        ...,
        description="UUID reference to users table",
    )

    id: UUID = Field(..., description="Unique event ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    created_at: datetime = Field(..., description="When the event occurred")


class ActivityAuditFilters(BaseModel):
    """Query parameters for filtering activity audit events."""

    actor_id: UUID | None = Field(None, description="Filter by actor UUID")
    source: AuditSource | None = Field(None, description="Filter by source subsystem")
    action: str | None = Field(
        None, description="Filter by action (supports prefix match with %)"
    )
    resource_type: str | None = Field(None, description="Filter by resource type")
    resource_id: str | None = Field(None, description="Filter by resource ID")
    from_date: datetime | None = Field(
        None, description="Start of date range (inclusive)"
    )
    to_date: datetime | None = Field(None, description="End of date range (exclusive)")
    limit: int = Field(50, ge=1, le=500, description="Page size (max 500)")
    offset: int = Field(0, ge=0, description="Starting position")
