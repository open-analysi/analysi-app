"""Task schemas for API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analysi.config.logging import get_logger
from analysi.models.task import TaskMode, TaskScope


class TaskBase(BaseModel):
    """Base schema for Task with common fields."""

    # Component fields
    name: str = Field(..., min_length=1, max_length=255, description="Task name")
    description: str | None = Field(None, description="Task description")
    version: str = Field(default="1.0.0", description="Task version")
    status: str = Field(default="enabled", description="Task status (enabled/disabled)")
    visible: bool = Field(default=False, description="Whether task is visible to users")
    system_only: bool = Field(
        default=False, description="Whether task can only be modified by system"
    )
    app: str = Field(default="default", description="App namespace")
    categories: list[str] = Field(
        default_factory=list,
        description="Task categories/tags",
        # Note: We handle tags/categories mapping in task_tools.py instead of using
        # validation_alias to avoid Pydantic ignoring direct 'categories' parameter
    )
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts (auto-generated if not provided)",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )

    # Task-specific fields
    script: str = Field(..., min_length=1, description="Cy script content")
    directive: str | None = Field(None, description="System message for LLM calls")
    function: str | None = Field(None, description="Task function type")
    scope: str | None = Field(None, description="Task scope (input/processing/output)")
    schedule: str | None = Field(None, description="Cron expression for scheduling")
    mode: str = Field(default="saved", description="Task mode (ad_hoc/saved)")
    llm_config: dict[str, Any] | None = Field(None, description="LLM configuration")
    data_samples: list[Any] | None = Field(
        None,
        description=(
            "Sample input data for testing the task. "
            "RECOMMENDED: Use structure {name, input, description, expected_output} "
            "where 'input' contains the actual test data. "
            "The resolver will extract the 'input' field when inferring schemas."
        ),
        json_schema_extra={
            "example": [
                {
                    "name": "Test Case 1",
                    "input": {"ip": "192.168.1.100", "context": "firewall_alert"},
                    "description": "Test IP reputation check",
                    "expected_output": {"threat_level": "low"},
                },
                {
                    "name": "Test Case 2",
                    "input": "simple_string_input",
                    "description": "Test simple string input",
                },
            ]
        },
    )

    @field_validator("data_samples")
    @classmethod
    def validate_data_samples_structure(cls, v: list[Any] | None) -> list[Any] | None:
        """
        Validate data_samples follow recommended structure.

        Checks if samples use {name, input, description, expected_output} pattern.
        Logs warning if not, but doesn't fail (backward compatible).
        """
        if v is None or len(v) == 0:
            return v

        # Check if samples follow recommended pattern
        recommended_pattern_count = 0
        for sample in v:
            if isinstance(sample, dict) and "input" in sample:
                recommended_pattern_count += 1

        # If less than 50% use recommended pattern, log warning
        if recommended_pattern_count < len(v) * 0.5:
            logger = get_logger(__name__)
            logger.warning(
                "data_samples_pattern_recommendation",
                message=(
                    f"Only {recommended_pattern_count}/{len(v)} data_samples use "
                    "recommended {name, input, description, expected_output} structure. "
                    "Consider using this pattern for better schema inference and UI display."
                ),
                samples_count=len(v),
                recommended_count=recommended_pattern_count,
            )

        return v

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        """Validate task scope is one of the allowed values."""
        if v is None:
            return v

        valid_scopes = [TaskScope.INPUT, TaskScope.PROCESSING, TaskScope.OUTPUT]
        if v not in valid_scopes:
            raise ValueError(
                f"Invalid task scope '{v}'. Must be one of: {', '.join(valid_scopes)}. "
                f"'input' for data ingestion tasks, 'processing' for data transformation/analysis tasks, "
                f"'output' for tasks that produce final results or visualizations."
            )
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate task mode is one of the allowed values."""
        valid_modes = [TaskMode.AD_HOC, TaskMode.SAVED]
        if v not in valid_modes:
            raise ValueError(
                f"Invalid task mode '{v}'. Must be one of: {', '.join(valid_modes)}. "
                f"'ad_hoc' for temporary one-time tasks, 'saved' for persistent reusable tasks."
            )
        return v


class TaskCreate(TaskBase):
    """Schema for creating a new task."""

    pass


class TaskUpdate(BaseModel):
    """Schema for updating an existing task."""

    # Component fields
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    version: str | None = None
    status: str | None = None
    visible: bool | None = None
    system_only: bool | None = None
    app: str | None = None
    categories: list[str] | None = None
    cy_name: str | None = Field(
        None,
        description="Script-friendly identifier for Cy scripts",
        pattern="^[a-z][a-z0-9_]*$",
        min_length=1,
        max_length=255,
    )

    # Task-specific fields
    script: str | None = Field(None, min_length=1)
    directive: str | None = None
    function: str | None = None
    scope: str | None = None
    schedule: str | None = None
    mode: str | None = None
    llm_config: dict[str, Any] | None = None
    data_samples: list[Any] | None = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        """Validate task scope is one of the allowed values."""
        if v is None:
            return v

        valid_scopes = [TaskScope.INPUT, TaskScope.PROCESSING, TaskScope.OUTPUT]
        if v not in valid_scopes:
            raise ValueError(
                f"Invalid task scope '{v}'. Must be one of: {', '.join(valid_scopes)}. "
                f"'input' for data ingestion tasks, 'processing' for data transformation/analysis tasks, "
                f"'output' for tasks that produce final results or visualizations."
            )
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str | None) -> str | None:
        """Validate task mode is one of the allowed values."""
        if v is None:
            return v

        valid_modes = [TaskMode.AD_HOC, TaskMode.SAVED]
        if v not in valid_modes:
            raise ValueError(
                f"Invalid task mode '{v}'. Must be one of: {', '.join(valid_modes)}. "
                f"'ad_hoc' for temporary one-time tasks, 'saved' for persistent reusable tasks."
            )
        return v


class TaskResponse(TaskBase):
    """Schema for task response."""

    id: UUID
    tenant_id: str
    created_by: UUID | None = Field(
        default=None, description="UUID of user who created this task"
    )
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ScriptAnalysisRequest(BaseModel):
    """Request body for ad-hoc script analysis."""

    script: str = Field(..., min_length=1, description="Cy script to analyze")


class ScriptAnalysisResponse(BaseModel):
    """Response from script static analysis (tools_used + external_variables)."""

    task_id: UUID | None = None
    cy_name: str | None = None
    tools_used: list[str] | None = None
    external_variables: list[str] | None = None
    errors: list[str] | None = None


# Task Operation Responses (Project Sifnos)
class SyncEdgesResponse(BaseModel):
    """Response from backfilling KDG tool edges."""

    synced: int
    skipped: int
    errors: list[str] = []


class WorkflowUsage(BaseModel):
    """Summary of a workflow using a task."""

    name: str
    id: str | None = None

    model_config = ConfigDict(extra="allow")


class CheckDeleteResponse(BaseModel):
    """Response from checking if a task can be deleted."""

    can_delete: bool
    reason: str | None = None
    message: str | None = None
    workflows: list[WorkflowUsage] | None = None
