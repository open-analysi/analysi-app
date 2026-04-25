"""Pydantic schemas for .skill zip import."""

from uuid import UUID

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """Manifest schema for .skill zip files.

    Every .skill zip must contain a manifest.json at root with these fields.
    """

    name: str = Field(description="Human-readable skill name")
    description: str = Field(description="What the skill does")
    version: str = Field(default="1.0.0", description="Skill version")
    cy_name: str = Field(description="Machine-friendly name (snake_case)")
    categories: list[str] = Field(default_factory=list, description="Skill categories")
    config: dict = Field(default_factory=dict, description="Skill configuration")


class SkillImportResponse(BaseModel):
    """Response from skill import endpoint."""

    skill_id: UUID
    name: str
    documents_submitted: int
    review_ids: list[UUID] = Field(
        description="One review ID per file, for polling status",
    )
    sync_failures: list[dict] = Field(
        default_factory=list,
        description="Files that failed sync gate (means import rejected)",
    )
