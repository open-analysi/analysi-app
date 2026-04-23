"""
Pydantic schemas for workflow execution API.
"""

import contextlib
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from analysi.schemas.task_run import LLMUsageResponse


# Workflow Run Schemas
class WorkflowRunCreate(BaseModel):
    """Request to start workflow execution."""

    input_data: Any = Field(
        ..., description="Input data for workflow (accepts any JSON-serializable type)"
    )
    execution_context: dict[str, Any] | None = Field(
        None, description="Optional context (e.g., analysis_id for artifact linking)"
    )


class WorkflowRunStatus(BaseModel):
    """Lightweight workflow run status response."""

    workflow_run_id: UUID
    status: str  # pending, running, completed, failed, cancelled
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowRunResponse(BaseModel):
    """Full workflow run details."""

    workflow_run_id: UUID = Field(..., alias="id")
    tenant_id: str
    workflow_id: UUID | None
    workflow_name: str = Field(
        ..., description="Workflow name (or 'Ad Hoc Workflow' for ad-hoc executions)"
    )
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_data: Any | None = None
    output_data: Any | None = (
        None  # Can be dict, list, or primitive from terminal node's result
    )
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    # Aggregate LLM usage across all nodes in this workflow run
    # Populated by the router/service when returning full run details.
    llm_usage: LLMUsageResponse | None = Field(
        None,
        description="Aggregate LLM token counts and cost across all workflow nodes",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkflowRunInitiated(BaseModel):
    """Response when workflow execution is initiated."""

    workflow_run_id: UUID
    status: str = "pending"
    message: str = "Workflow execution initiated"


# Node Instance Schemas
class NodeInstanceEnvelope(BaseModel):
    """Standard envelope structure for node output."""

    node_id: str
    context: dict[str, Any] | None = None
    description: str | None = None
    result: Any


class WorkflowNodeInstanceResponse(BaseModel):
    """Node instance execution details."""

    node_instance_id: UUID = Field(..., alias="id")
    workflow_run_id: UUID
    node_id: str
    node_uuid: UUID
    status: str
    parent_instance_id: UUID | None = None
    loop_context: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_data: Any | None = None
    output_data: NodeInstanceEnvelope | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    # LLM token and cost metadata for this node (from output_data.context.llm_usage)
    llm_usage: LLMUsageResponse | None = Field(
        None, description="LLM token counts and cost for this workflow node"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @model_validator(mode="after")
    def _extract_llm_usage(self) -> "WorkflowNodeInstanceResponse":
        """Populate llm_usage from output_data.context['llm_usage'] when not set directly."""
        if self.llm_usage is None and self.output_data is not None:
            context = self.output_data.context or {}
            raw = context.get("llm_usage")
            if raw and isinstance(raw, dict):
                with contextlib.suppress(Exception):
                    self.llm_usage = LLMUsageResponse(**raw)
        return self


# Edge Instance Schemas
class WorkflowEdgeInstanceResponse(BaseModel):
    """Edge instance for data flow visualization."""

    edge_instance_id: UUID = Field(..., alias="id")
    workflow_run_id: UUID
    edge_id: str
    edge_uuid: UUID
    from_instance_id: UUID
    to_instance_id: UUID
    delivered_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# Graph Visualization Schema
class WorkflowRunGraph(BaseModel):
    """Materialized execution graph for visualization."""

    workflow_run_id: UUID
    is_complete: bool
    status: str | None = (
        None  # Overall workflow run status: pending, running, completed, failed, cancelled
    )
    snapshot_at: datetime
    summary: dict[str, int] = Field(
        default_factory=lambda: {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
    )
    nodes: list[WorkflowNodeInstanceResponse]
    edges: list[WorkflowEdgeInstanceResponse]
