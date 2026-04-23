"""Pydantic schemas for Knowledge Extraction API — Hydra project."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Status enum ---


class ExtractionStatus(StrEnum):
    """Extraction lifecycle status."""

    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


# --- Pipeline output models ---


class DocumentClassification(BaseModel):
    """Output of Node 1: classify_document."""

    doc_type: Literal[
        "new_runbook",
        "source_evidence_pattern",
        "attack_type_pattern",
        "evidence_collection",
        "universal_pattern",
        "reference_documentation",
        "low_security_runbook_relevance",
    ]
    confidence: Literal["high", "medium", "low"]
    reasoning: str = ""


class RelevanceAssessment(BaseModel):
    """Output of Node 2: assess_relevance."""

    is_relevant: bool
    applicable_namespaces: list[str] = Field(default_factory=list)
    reasoning: str = ""


VALID_NAMESPACES = (
    "repository/",
    "common/by_source/",
    "common/by_type/",
    "common/evidence/",
    "common/universal/",
    "references/",
)


class PlacementDecision(BaseModel):
    """Output of Node 3: determine_placement."""

    target_namespace: str
    target_filename: str
    merge_strategy: Literal["create_new", "merge_with_existing"]
    merge_target: str | None = None
    reasoning: str = ""

    @field_validator("target_namespace", mode="after")
    @classmethod
    def normalize_namespace(cls, v: str) -> str:
        """Normalize namespace to a known value with trailing slash."""
        if not v.endswith("/"):
            v += "/"
        # Match against known namespaces
        for ns in VALID_NAMESPACES:
            if v == ns:
                return v
        # Fuzzy: strip slashes and compare
        stripped = v.strip("/")
        for ns in VALID_NAMESPACES:
            if stripped == ns.strip("/"):
                return ns
        # Fall back to closest prefix match
        for ns in VALID_NAMESPACES:
            if stripped.startswith(ns.strip("/")):
                return ns
        return v


class MergeResult(BaseModel):
    """Output of Node 4b: merge_with_existing."""

    merged_content: str
    original_content: str
    change_summary: str
    sections_added: list[str] = Field(default_factory=list)
    sections_modified: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Output of Node 5: validate_output."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionSummary(BaseModel):
    """Output of Node 6: summarize_extraction."""

    summary: str


# --- Request schemas ---


class ExtractionCreateRequest(BaseModel):
    """Request to start a knowledge extraction."""

    document_id: UUID = Field(
        ..., description="ID of the source KUDocument to extract knowledge from"
    )


class ExtractionApplyRequest(BaseModel):
    """Optional overrides when applying an extraction."""

    content: str | None = Field(None, description="Override the transformed content")
    target_namespace: str | None = Field(
        None, description="Override the target namespace"
    )
    target_filename: str | None = Field(
        None, description="Override the target filename"
    )


class ExtractionRejectRequest(BaseModel):
    """Optional reason when rejecting an extraction."""

    reason: str | None = Field(None, description="Why this extraction was rejected")


# --- Response schemas ---


class ExtractionResponse(BaseModel):
    """Full extraction details."""

    id: UUID
    skill_id: UUID
    document_id: UUID
    status: ExtractionStatus
    classification: dict[str, Any] | None = None
    relevance: dict[str, Any] | None = None
    placement: dict[str, Any] | None = None
    transformed_content: str | None = None
    merge_info: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    extraction_summary: str | None = None
    applied_document_id: UUID | None = None
    rejection_reason: str | None = None
    error_message: str | None = None
    created_at: datetime
    applied_at: datetime | None = None
    rejected_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ExtractionApplyResponse(BaseModel):
    """Response after applying an extraction."""

    document_id: UUID = Field(..., description="The created/updated KUDocument ID")
    skill_id: UUID
    namespace_path: str
    extraction_id: UUID


class ExtractionRejectResponse(BaseModel):
    """Response after rejecting an extraction."""

    extraction_id: UUID
    status: ExtractionStatus
    reason: str | None = None
