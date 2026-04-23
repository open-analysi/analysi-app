"""
Pydantic schemas for credentials API.

Following CustomerCredentials spec for request/response structures.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CredentialCreate(BaseModel):
    """Request schema for creating credentials."""

    provider: str = Field(..., description="Integration type (splunk, echo_edr, etc.)")
    account: str | None = Field(None, description="Credential label/identifier")
    secret: dict[str, Any] = Field(..., description="Credential data to encrypt")
    credential_metadata: dict[str, Any] | None = Field(
        None, description="Unencrypted metadata"
    )


class CredentialResponse(BaseModel):
    """Response schema for credential (without secrets)."""

    id: UUID
    tenant_id: str
    provider: str
    account: str
    credential_metadata: dict[str, Any] | None
    key_version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CredentialMetadata(BaseModel):
    """Metadata-only response for listing."""

    id: UUID
    provider: str
    account: str
    credential_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CredentialDecrypted(BaseModel):
    """Response with decrypted credential (internal use only)."""

    id: UUID
    provider: str
    account: str
    secret: dict[str, Any]  # Decrypted content
    credential_metadata: dict[str, Any] | None
    key_version: int

    model_config = ConfigDict(from_attributes=True)


class CredentialRotateResponse(BaseModel):
    """Response for credential rotation."""

    id: UUID
    new_key_version: int
    rotated_at: datetime


class IntegrationCredentialAssociation(BaseModel):
    """Request to associate credential with integration."""

    credential_id: UUID
    is_primary: bool = False
    purpose: str | None = Field(None, pattern="^(read|write|admin)$")


class IntegrationCredentialResponse(BaseModel):
    """Response for integration-credential association."""

    credential_id: UUID
    provider: str
    account: str
    is_primary: bool
    purpose: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationCredentialCreateAndAssociate(BaseModel):
    """Create and associate credential with integration in one step."""

    provider: str = Field(..., description="Integration type (splunk, echo_edr, etc.)")
    account: str | None = Field(None, description="Credential label/identifier")
    secret: dict[str, Any] = Field(..., description="Credential data to encrypt")
    credential_metadata: dict[str, Any] | None = Field(
        None, description="Unencrypted metadata"
    )
    is_primary: bool = Field(True, description="Set as primary credential")
    purpose: str | None = Field(
        None, pattern="^(read|write|admin)$", description="Credential purpose"
    )
