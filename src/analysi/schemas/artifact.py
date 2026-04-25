"""
Artifact Pydantic schemas.

Request/response schemas for artifact API endpoints with validation.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArtifactCreate(BaseModel):
    """Schema for creating new artifacts."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable artifact name"
    )
    artifact_type: str | None = Field(
        None,
        max_length=100,
        description="Semantic type (timeline, activity_graph, etc.)",
    )
    mime_type: str | None = Field(
        None, description="MIME type of content (auto-detected if not provided)"
    )
    tags: list[str] | dict[str, Any] = Field(
        default_factory=list, description="Tags for categorization (list or dict)"
    )
    content: str | bytes = Field(
        ..., description="Artifact content (string or base64 for binary)"
    )
    content_encoding: str | None = Field(
        None, description="Content encoding (hex, base64, utf-8)"
    )

    # Relationship fields (optional - can be auto-populated from execution context)
    alert_id: UUID | None = Field(
        None, description="Direct link to alert (for manual attachments via REST API)"
    )
    task_run_id: UUID | None = Field(None, description="Associated task run ID")
    workflow_run_id: UUID | None = Field(None, description="Associated workflow run ID")
    workflow_node_instance_id: UUID | None = Field(
        None, description="Associated workflow node instance ID"
    )
    analysis_id: UUID | None = Field(None, description="Associated analysis ID")

    # Integration and provenance tracking
    integration_id: str | None = Field(
        None, description="Integration instance ID (e.g., 'virustotal-prod')"
    )
    source: str | None = Field(
        None, description="Provenance: auto_capture, cy_script, rest_api, mcp"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate artifact name."""
        if not v or not v.strip():
            raise ValueError("Artifact name cannot be empty")
        if len(v.strip()) > 255:
            raise ValueError("Artifact name cannot exceed 255 characters")
        return v.strip()

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v):
        """Validate MIME type format."""
        if v and "/" not in v:
            raise ValueError("MIME type must be in format 'type/subtype'")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        """Validate tags array."""
        if v is None:
            return []
        if isinstance(v, dict):
            # Convert dict to list format
            return [f"{k}:{val}" for k, val in v.items()]
        if isinstance(v, list):
            return [str(tag) for tag in v]
        return []


class ArtifactResponse(BaseModel):
    """Schema for artifact API responses."""

    id: UUID = Field(..., description="Artifact unique identifier")
    tenant_id: str = Field(..., description="Tenant identifier")

    # Core metadata
    name: str = Field(..., description="Artifact name")
    artifact_type: str | None = Field(None, description="Semantic artifact type")
    mime_type: str = Field(..., description="MIME type")
    tags: list[str] = Field(..., description="Tags array")

    # Content information
    size_bytes: int = Field(..., description="Content size in bytes")
    sha256: str = Field(..., description="SHA256 hash (base64)")
    md5: str | None = Field(None, description="MD5 hash (base64)")

    # Storage information
    storage_class: str = Field(..., description="Storage class (inline or object)")
    content: str | dict[str, Any] | None = Field(
        None, description="Inline content (only if storage_class=inline)"
    )
    download_url: str | None = Field(
        None, description="Presigned download URL (only if storage_class=object)"
    )
    bucket: str | None = Field(
        None, description="MinIO bucket name (only if storage_class=object)"
    )
    object_key: str | None = Field(
        None, description="MinIO object key (only if storage_class=object)"
    )

    # Relationships
    alert_id: UUID | None = Field(
        None, description="Direct link to alert (for manual attachments)"
    )
    task_run_id: UUID | None = Field(None, description="Associated task run ID")
    workflow_run_id: UUID | None = Field(None, description="Associated workflow run ID")
    workflow_node_instance_id: UUID | None = Field(
        None, description="Associated workflow node instance ID"
    )
    analysis_id: UUID | None = Field(None, description="Associated analysis ID")

    # Integration and provenance tracking
    integration_id: str | None = Field(
        None, description="Integration instance ID (e.g., 'virustotal-prod')"
    )
    source: str | None = Field(
        None, description="Provenance: auto_capture, cy_script, rest_api, mcp"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class ArtifactStats(BaseModel):
    """Schema for artifact storage statistics."""

    tenant_id: str = Field(..., description="Tenant identifier")
    total_artifacts: int = Field(..., description="Total artifact count")
    inline_artifacts: int = Field(..., description="Inline storage count")
    object_artifacts: int = Field(..., description="Object storage count")
    total_size_bytes: int = Field(..., description="Total storage used")
    inline_size_bytes: int = Field(..., description="Inline storage used")
    object_size_bytes: int = Field(..., description="Object storage used")
