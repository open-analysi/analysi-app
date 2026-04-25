"""
TaskRun Schemas

Pydantic schemas for task execution API.
"""

import contextlib
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskRunCreate(BaseModel):
    """Schema for creating a task execution."""

    input: Any | None = (
        None  # Accept any JSON-serializable type (dict, list, str, etc.)
    )
    executor_config: dict[str, Any] | None = None


class AdHocTaskRunCreate(BaseModel):
    """Schema for ad-hoc task execution."""

    cy_script: str = Field(..., description="Cy script to execute")
    input: Any | None = (
        None  # Accept any JSON-serializable type (dict, list, str, etc.)
    )
    executor_config: dict[str, Any] | None = None


class LLMUsageResponse(BaseModel):
    """LLM token usage and cost for a single task or workflow node execution."""

    input_tokens: int = Field(..., description="Number of prompt/input tokens consumed")
    output_tokens: int = Field(
        ..., description="Number of completion/output tokens produced"
    )
    total_tokens: int = Field(..., description="Total tokens (input + output)")
    cost_usd: float | None = Field(
        None, description="Estimated cost in USD (None if model unknown)"
    )


class TaskRunResponse(BaseModel):
    """Full task run response with all details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Task run ID (trid)")
    tenant_id: str
    task_id: UUID | None = Field(None, description="Task ID (null for ad-hoc)")
    workflow_run_id: UUID | None = Field(None, description="Parent workflow run ID")
    task_name: str = Field(
        ..., description="Task name (or 'Ad Hoc Task' for ad-hoc executions)"
    )
    cy_script: str | None = Field(None, description="Cy script (for ad-hoc executions)")
    status: str = Field(..., description="Execution status")
    duration: timedelta | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Input/Output storage
    input_type: str | None = Field(None, description="Storage type for input")
    input_location: str | None = Field(None, description="Input storage location")
    input_content_type: str | None = Field(None, description="Input MIME type")
    output_type: str | None = Field(None, description="Storage type for output")
    output_location: str | None = Field(None, description="Output storage location")
    output_content_type: str | None = Field(None, description="Output MIME type")

    # Execution configuration
    executor_config: dict[str, Any] | None = None
    execution_context: dict[str, Any] | None = None

    # LLM token and cost metadata (extracted from execution_context["_llm_usage"])
    llm_usage: LLMUsageResponse | None = Field(
        None, description="LLM token counts and estimated cost for this task run"
    )

    # Metadata
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _extract_llm_usage(self) -> "TaskRunResponse":
        """Populate llm_usage from execution_context['_llm_usage'] when not set directly."""
        if self.llm_usage is None and self.execution_context:
            raw = self.execution_context.get("_llm_usage")
            if raw and isinstance(raw, dict):
                with contextlib.suppress(Exception):
                    self.llm_usage = LLMUsageResponse(**raw)
        return self


class TaskRunStatusResponse(BaseModel):
    """Lightweight task run status for polling."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(..., description="Current execution status")
    updated_at: datetime = Field(..., description="Last status update time")


class TaskRunLogsResponse(BaseModel):
    """Response containing execution logs from a task run.

    Logs are captured from Cy log() calls during execution and persisted
    as an execution_log artifact. This endpoint retrieves those entries.
    """

    trid: UUID = Field(..., description="Task run ID")
    status: str = Field(
        ..., description="Task run status (running, completed, failed, paused)"
    )
    entries: list[str | dict] = Field(
        default_factory=list,
        description="Log entries from Cy log() calls. Each entry is a dict with 'ts' (epoch) and 'message', or a plain string (legacy).",
    )
    has_logs: bool = Field(..., description="Whether the task produced any log output")


class TaskRunEnrichmentResponse(BaseModel):
    """Response containing only the enrichment data from a task run.

    When a task uses enrich_alert(), the enrichment is stored under
    output["enrichments"][cy_name]. This endpoint extracts just that data.
    """

    model_config = ConfigDict(from_attributes=True)

    trid: UUID = Field(..., description="Task run ID")
    cy_name: str | None = Field(
        None, description="Task's cy_name used as enrichment key"
    )
    enrichment: Any | None = Field(
        None, description="The enrichment data added by this task"
    )
    status: str = Field(..., description="Task run status")
    has_enrichment: bool = Field(
        ..., description="Whether the task produced enrichment data"
    )


class TaskRunInitiated(BaseModel):
    """Response when task execution is initiated."""

    model_config = ConfigDict(from_attributes=True)

    trid: UUID = Field(..., description="Task run ID for tracking")
    status: str = Field(default="running", description="Initial status")
    message: str = Field(
        default="Task execution initiated", description="Response message"
    )


class TaskExecutionRequest(BaseModel):
    """Base request for task execution."""

    input: Any | None = (
        None  # Accept any JSON-serializable type (dict, list, str, etc.)
    )
    executor_config: dict[str, Any] | None = Field(
        None, description="Executor configuration (timeout, type, etc.)"
    )


class TaskExecutionHeaders(BaseModel):
    """Headers for async task execution responses."""

    location: str = Field(..., description="URL for polling task status")
    retry_after: int = Field(
        default=5, description="Suggested polling interval in seconds"
    )


# Additional utility schemas
class ExecutorConfig(BaseModel):
    """Executor configuration schema."""

    executor_type: str = Field(default="default", description="Type of executor")
    timeout_seconds: int = Field(default=300, description="Execution timeout")
    max_workers: int | None = Field(None, description="Max concurrent workers")


class ExecutionContext(BaseModel):
    """Execution context schema."""

    tenant_id: str
    task_id: UUID | None = None
    knowledge_units: list[UUID] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    llm_model: str = Field(default="gpt-4")
    runtime_version: str = Field(default="cy-2.1")


class StorageInfo(BaseModel):
    """Storage information schema."""

    storage_type: str = Field(..., description="Storage type (inline, s3, file)")
    location: str = Field(..., description="Storage location or content")
    content_type: str = Field(..., description="MIME type")
    size_bytes: int | None = Field(None, description="Content size in bytes")


class TaskRunQueryParams(BaseModel):
    """Query parameters for listing task runs."""

    # Filtering
    task_id: UUID | None = Field(None, description="Filter by task ID")
    status: str | None = Field(
        None, description="Filter by status (running, completed, failed)"
    )

    # Sorting
    sort: str = Field(
        "created_at",
        description="Field to sort by (created_at, updated_at, status, duration)",
    )
    order: str = Field("desc", description="Sort order (asc, desc)")

    # Pagination
    skip: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(50, ge=1, le=100, description="Number of items to return")
