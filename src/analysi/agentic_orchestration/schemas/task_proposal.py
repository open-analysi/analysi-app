"""Task proposal schemas for workflow generation."""

from enum import StrEnum

from pydantic import BaseModel


class TaskDesignation(StrEnum):
    """Designation for a proposed task."""

    EXISTING = "existing"
    MODIFICATION = "modification"
    NEW = "new"


class TaskProposal(BaseModel):
    """A proposed task from runbook analysis."""

    name: str
    description: str
    designation: TaskDesignation
    existing_task_id: str | None = None  # If EXISTING or MODIFICATION
    required_integrations: list[str]
    input_schema: dict | None = None
    output_schema: dict | None = None


class TaskProposalList(BaseModel):
    """Collection of task proposals from runbook analysis."""

    proposals: list[TaskProposal]
    analysis_summary: str
