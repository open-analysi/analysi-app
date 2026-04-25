"""
Pydantic schemas for authentication & authorization API responses.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    """Response schema for a user record."""

    id: UUID
    email: str
    display_name: str | None
    created_at: datetime
    last_seen_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    """Response schema for a tenant member (membership + user fields)."""

    id: UUID
    user_id: UUID
    tenant_id: str
    role: str
    email: str  # joined from User at the service layer
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationResponse(BaseModel):
    """Response schema for an invitation (token_hash never returned)."""

    id: UUID
    tenant_id: str
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationWithTokenResponse(InvitationResponse):
    """Response for dev/test invite endpoint that includes the plaintext token."""

    token: str


class ApiKeyResponse(BaseModel):
    """Response schema for an API key (secret never returned after creation)."""

    id: UUID
    tenant_id: str
    user_id: UUID | None
    name: str
    key_prefix: str
    scopes: list
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreatedResponse(ApiKeyResponse):
    """One-time response on API key creation — includes the plaintext secret."""

    secret: str


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    """Request body for sending a member invitation."""

    email: str = Field(..., description="Email address of the person to invite")
    role: str = Field(..., description="Role to assign: viewer, analyst, admin, owner")


class AcceptInviteRequest(BaseModel):
    """Request body for accepting an invitation token."""

    token: str = Field(..., min_length=1)


class ChangeRoleRequest(BaseModel):
    """Request body for changing a member's role."""

    role: str = Field(..., description="New role: viewer, analyst, admin, owner")


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
