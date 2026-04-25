"""
Pydantic schemas for workflow type validation API.

Status: STUBBED - To be implemented in 050 cycle
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowTypeValidationRequest(BaseModel):
    """
    Request schema for workflow type validation.

    STUB: Basic structure only. Full validation to be added in 050 cycle.
    """

    initial_input_schema: dict[str, Any] = Field(
        ...,
        description="JSON Schema for workflow input",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "initial_input_schema": {
                    "type": "object",
                    "properties": {
                        "alert_id": {"type": "string"},
                        "ip_address": {"type": "string"},
                    },
                    "required": ["alert_id", "ip_address"],
                }
            }
        }
    )


class NodeTypeInfoResponse(BaseModel):
    """
    Response schema for node type information.

    STUB: Basic structure only.
    """

    node_id: str
    kind: str
    template_kind: str | None = None
    inferred_input: dict[str, Any] | list[dict[str, Any]]
    inferred_output: dict[str, Any]


class TypeErrorResponse(BaseModel):
    """
    Response schema for type errors and warnings.

    STUB: Basic structure only.
    """

    node_id: str
    error_type: str
    message: str
    suggestion: str
    severity: Literal["error", "warning"] = "error"
    expected_schema: dict[str, Any] | None = None
    actual_schema: dict[str, Any] | None = None


class WorkflowTypeValidationResponse(BaseModel):
    """
    Response schema for workflow type validation.

    STUB: Basic structure only.
    """

    status: Literal["valid", "invalid", "valid_with_warnings"]
    nodes: list[NodeTypeInfoResponse]
    workflow_output_schema: dict[str, Any] | None = None
    errors: list[TypeErrorResponse] = Field(default_factory=list)
    warnings: list[TypeErrorResponse] = Field(default_factory=list)


class WorkflowTypeApplyResponse(WorkflowTypeValidationResponse):
    """
    Response schema for apply-types operation.

    STUB: Extends validation response with persistence metadata.
    """

    applied: bool = Field(..., description="Whether types were persisted to database")
    nodes_updated: int = Field(..., description="Number of nodes updated")
    updated_at: datetime = Field(..., description="Timestamp of update")
