"""Pydantic schemas for content review API."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContentGateResult(BaseModel):
    """Result from a single content gate."""

    check_name: str
    passed: bool
    errors: list[str] = Field(default_factory=list)


# Backwards compat alias
SyncCheckResult = ContentGateResult


class ContentReviewResponse(BaseModel):
    """Full content review response for REST API."""

    id: UUID
    tenant_id: str
    skill_id: UUID
    pipeline_name: str
    pipeline_mode: Literal["review", "review_transform"]
    trigger_source: str
    document_id: UUID | None = None
    original_filename: str | None = None

    # Content gates
    content_gates_passed: bool
    content_gates_result: list[ContentGateResult] | None = None

    # Pipeline result
    pipeline_result: dict[str, Any] | None = None
    transformed_content: str | None = None
    summary: str | None = None

    # Lifecycle
    status: Literal["pending", "approved", "flagged", "applied", "rejected", "failed"]
    applied_document_id: UUID | None = None
    rejection_reason: str | None = None
    error_message: str | None = None
    error_code: str | None = None
    error_detail: dict[str, Any] | None = None
    bypassed: bool = False

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    applied_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContentReviewCreateRequest(BaseModel):
    """Request body for starting a content review (extraction pipeline)."""

    document_id: UUID = Field(
        ..., description="ID of the source KUDocument to extract knowledge from"
    )


class ContentReviewRejectRequest(BaseModel):
    """Request body for rejecting a content review."""

    reason: str | None = None
