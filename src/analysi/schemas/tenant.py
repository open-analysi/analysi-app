"""Pydantic schemas for tenant management API."""

from datetime import datetime

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """Request body for POST /platform/v1/tenants."""

    id: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Human-readable tenant identifier (e.g., 'acme-corp')",
        examples=["acme-corp"],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name for the tenant",
        examples=["Acme Corporation"],
    )
    owner_email: str | None = Field(
        None,
        description="Email of the first owner. Creates user (JIT) and membership.",
        examples=["admin@acme-corp.com"],
    )


class TenantResponse(BaseModel):
    """Tenant summary for list responses."""

    id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantDetailResponse(TenantResponse):
    """Extended tenant info for describe endpoint."""

    member_count: int = Field(0, description="Number of members in the tenant")
    component_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Component counts by type (tasks, knowledge_units, skills, workflows)",
    )
    installed_packs: list[str] = Field(
        default_factory=list,
        description="List of installed content pack names",
    )


class CascadeDeleteResponse(BaseModel):
    """Response for tenant cascade delete."""

    tenant_id: str
    tables_affected: int
    total_rows_deleted: int
    details: dict[str, int] = Field(
        default_factory=dict,
        description="Rows deleted per table",
    )
