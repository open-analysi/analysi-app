"""Pydantic schemas for Skills (Knowledge Modules) API."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Skills that support knowledge extraction (Hydra)
_EXTRACTION_ELIGIBLE_CY_NAMES = {"runbooks_manager"}


def is_extraction_eligible(cy_name: str | None) -> bool:
    """Check if a skill supports knowledge extraction."""
    return cy_name in _EXTRACTION_ELIGIBLE_CY_NAMES


class SkillBase(BaseModel):
    """Base schema for Skill with common Component fields."""

    # Component fields
    name: str = Field(..., min_length=1, max_length=255, description="Skill name")
    description: str | None = Field(None, description="Skill description")
    version: str = Field(default="1.0.0", description="Skill version")
    status: str = Field(
        default="enabled", description="Skill status (enabled/disabled)"
    )
    visible: bool = Field(
        default=False, description="Whether skill is visible to users"
    )
    system_only: bool = Field(
        default=False, description="Whether skill can only be modified by system"
    )
    app: str = Field(default="default", description="App namespace")
    categories: list[str] = Field(
        default_factory=list, description="Skill categories/tags"
    )
    namespace: str = Field(
        default="/", description="Namespace path for scoping (e.g. /skill_name/)"
    )
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts (auto-generated if not provided)",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )


class SkillCreate(SkillBase):
    """Schema for creating a Skill module."""

    root_document_path: str = Field(
        default="SKILL.md", description="Path to the main skill document"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Skill configuration (triggers, model prefs)"
    )


class SkillUpdate(BaseModel):
    """Schema for updating an existing Skill."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )
    namespace: str | None = Field(None, description="Namespace path for scoping")
    status: str | None = None
    visible: bool | None = None
    categories: list[str] | None = None
    root_document_path: str | None = None
    config: dict[str, Any] | None = None


class SkillResponse(SkillBase):
    """Response schema for Skill with all fields."""

    id: UUID
    tenant_id: str
    module_type: Literal["skill"]
    created_by: UUID | None = Field(
        default=None, description="UUID of user who created this skill"
    )
    root_document_path: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    extraction_eligible: bool = False

    # Content review summary (computed from content_reviews table)
    pending_reviews_count: int = 0
    flagged_reviews_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# --- Document Management Schemas ---


class SkillDocumentLink(BaseModel):
    """Schema for linking a document to a skill."""

    document_id: UUID = Field(..., description="Document KU's component_id")
    namespace_path: str = Field(
        ..., min_length=1, max_length=255, description="Path within the skill namespace"
    )


class SkillDocumentLinkResponse(BaseModel):
    """Response schema for document link operation."""

    edge_id: str
    skill_id: str
    document_id: str
    namespace_path: str


class SkillTreeEntry(BaseModel):
    """Single entry in skill file tree."""

    path: str
    document_id: str
    staged: bool = False


class SkillTreeResponse(BaseModel):
    """Response schema for skill file tree."""

    skill_id: str
    files: list[SkillTreeEntry]
    total: int


class SkillFileContent(BaseModel):
    """Response schema for reading a skill file."""

    path: str
    document_id: str
    name: str
    content: str | None
    markdown_content: str | None
    doc_format: str | None
    document_type: str | None
    metadata: dict[str, Any] = {}

    @field_validator("metadata", mode="before")
    @classmethod
    def metadata_none_to_empty(cls, v: Any) -> dict[str, Any]:
        return v if v is not None else {}


class SkillDeleteCheck(BaseModel):
    """Response schema for pre-delete validation."""

    contained_documents: int
    skills_including_this: int
    skills_depending_on_this: int
    can_delete: bool
    warnings: list[str]


# --- Staged Documents Schemas ---


class StagedDocumentRequest(BaseModel):
    """Request schema for staging a document for a skill."""

    document_id: UUID = Field(..., description="Document KU's component_id")
    namespace_path: str = Field(
        ..., min_length=1, max_length=255, description="Path within staged namespace"
    )


class StagedDocumentEntry(BaseModel):
    """Single staged document entry."""

    document_id: str
    path: str
    edge_id: str


class StagedDocumentResponse(BaseModel):
    """Response for staging a document."""

    document_id: str
    skill_id: str
    path: str
    edge_id: str


class RepairEdgesResponse(BaseModel):
    """Response from repairing missing skill edges."""

    skills_checked: int = 0
    documents_checked: int = 0
    edges_created: int = 0
    edges_skipped: int = 0
    errors: list[Any] = []
