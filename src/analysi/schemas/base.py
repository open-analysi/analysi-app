"""Base Pydantic schemas for the API."""

from typing import Any

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details response — the standard error shape for all endpoints.

    Standard fields: type, title, status, detail.
    Extension fields: request_id (always), error_code/hint (domain-specific).
    """

    type: str = Field(default="about:blank", description="Problem type URI")
    title: str = Field(description="Short human-readable summary")
    status: int = Field(description="HTTP status code")
    detail: str | None = Field(None, description="Detailed explanation")
    request_id: str | None = Field(None, description="Request correlation ID")
    error_code: str | None = Field(
        None, description="Machine-readable error code for domain-specific errors"
    )
    hint: str | None = Field(
        None, description="Actionable guidance on how to fix the problem"
    )


class ErrorResponse(BaseModel):
    """Error response schema (used by legacy error handling middleware)."""

    error: str = Field(..., description="Human-readable error message")
    error_code: str = Field(..., description="Machine-readable error code")
    context: dict[str, Any] | None = Field(None, description="Additional error context")
    execution_time: float = Field(..., description="Request execution time in seconds")
