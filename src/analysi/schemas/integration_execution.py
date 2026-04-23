"""Schemas for integration tool execution API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class IntegrationToolExecuteRequest(BaseModel):
    """Request schema for integration tool execution."""

    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific parameters",
        examples=[{"ip": "8.8.8.8"}, {}],
    )
    timeout_seconds: int = Field(
        default=30,
        description="Execution timeout in seconds",
        ge=1,
        le=300,
    )
    capture_schema: bool = Field(
        default=False,
        description="If True, generate JSON schema from tool output",
    )


class IntegrationToolExecuteResponse(BaseModel):
    """Response schema for integration tool execution."""

    status: Literal["success", "error", "timeout"] = Field(
        ..., description="Execution status"
    )
    output: Any | None = Field(None, description="Raw tool output")
    output_schema: dict[str, Any] | None = Field(
        None, description="JSON Schema of output (if requested)"
    )
    error: str | None = Field(None, description="Error message if failed")
    execution_time_ms: int | None = Field(
        None, description="Execution time in milliseconds"
    )
