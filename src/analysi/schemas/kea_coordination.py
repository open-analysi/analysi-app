"""Pydantic schemas for Kea Coordination."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Enums
class WorkflowGenerationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowGenerationStage(StrEnum):
    """Stages of workflow generation process."""

    RUNBOOK_GENERATION = "runbook_generation"
    TASK_PROPOSALS = "task_proposals"
    TASK_BUILDING = "task_building"
    WORKFLOW_ASSEMBLY = "workflow_assembly"


class PhaseStatus(StrEnum):
    """Status of a workflow generation phase."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# Ordered list of all workflow generation stages
WORKFLOW_STAGES = [
    WorkflowGenerationStage.RUNBOOK_GENERATION,
    WorkflowGenerationStage.TASK_PROPOSALS,
    WorkflowGenerationStage.TASK_BUILDING,
    WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
]


# Analysis Group Schemas
class AnalysisGroupCreate(BaseModel):
    """Schema for creating an analysis group."""

    title: str = Field(
        ..., min_length=1, max_length=255, description="Group title (usually rule_name)"
    )
    triggering_alert_analysis_id: UUID | None = Field(
        None, description="ID of the alert_analysis that triggered workflow generation"
    )


class AnalysisGroupResponse(BaseModel):
    """Schema for analysis group response."""

    id: UUID
    tenant_id: str
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Workflow Generation Schemas
class WorkflowGenerationPhase(BaseModel):
    """A single phase entry in workflow generation progress.

    All four phases are initialized upfront with status=not_started.
    As each phase starts, its status changes to in_progress and started_at is set.
    When complete, status changes to completed and completed_at is set.
    """

    stage: WorkflowGenerationStage
    status: PhaseStatus = Field(
        PhaseStatus.NOT_STARTED,
        description="Phase status: not_started, in_progress, or completed",
    )
    started_at: datetime | None = Field(
        None,
        description="When the phase started (set when status changes to in_progress)",
    )
    completed_at: datetime | None = Field(
        None,
        description="When the phase completed (set when status changes to completed)",
    )
    tasks_count: int | None = Field(
        None, description="Number of tasks being built (task_building stage only)"
    )


class WorkflowGenerationProgress(BaseModel):
    """Progress tracking for workflow generation with all 4 phases pre-populated.

    All phases are initialized upfront so the UI knows what to expect:
    - Initial: phases=[
        {stage: runbook_generation, status: not_started},
        {stage: task_proposals, status: not_started},
        {stage: task_building, status: not_started},
        {stage: workflow_assembly, status: not_started}
      ]
    - Stage 1 starts: phases=[
        {stage: runbook_generation, status: in_progress, started_at: ...},
        {stage: task_proposals, status: not_started},
        ...
      ]
    - Stage 1 completes, stage 2 starts: phases=[
        {stage: runbook_generation, status: completed, started_at: ..., completed_at: ...},
        {stage: task_proposals, status: in_progress, started_at: ...},
        ...
      ]
    """

    phases: list[WorkflowGenerationPhase] = Field(
        default_factory=list,
        description="All 4 phases in order. Status transitions: not_started → in_progress → completed",
    )


class WorkflowGenerationResponse(BaseModel):
    """Schema for workflow generation response."""

    id: UUID
    tenant_id: str
    analysis_group_id: UUID
    workflow_id: UUID | None = None
    status: WorkflowGenerationStatus
    is_active: bool
    triggering_alert_analysis_id: UUID | None = Field(
        None,
        description="ID of the alert_analysis that triggered this workflow generation",
    )
    progress: WorkflowGenerationProgress | None = Field(
        None,
        validation_alias="current_phase",
        description="Incremental progress tracking - list of phases that accumulates during execution",
    )
    orchestration_results: dict[str, Any] | None = Field(
        None,
        description="Complete orchestration results including runbook, task_proposals, tasks_built, workflow_composition, metrics, and error (if failed)",
    )
    workspace_path: str | None = Field(
        None,
        description="Path to workspace directory for cleanup/debugging",
    )
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowGenerationProgressUpdate(BaseModel):
    """Schema for updating workflow generation progress.

    Supports two types of updates:
    1. stage: Stage name to mark as in_progress (previous stages auto-complete)
    2. workspace_path: Update workspace path for early tracking

    Example flow:
    - PATCH {stage: "runbook_generation"}
      → runbook_generation becomes in_progress, others remain not_started
    - PATCH {stage: "task_proposals"}
      → runbook_generation becomes completed, task_proposals becomes in_progress
    """

    stage: WorkflowGenerationStage | None = Field(
        None,
        description="Stage to mark as in_progress (previous stages will be marked completed)",
    )
    tasks_count: int | None = Field(
        None, description="Number of tasks being built (task_building stage only)"
    )
    workspace_path: str | None = Field(
        None, description="Workspace path for early tracking"
    )


class WorkflowGenerationStageComplete(BaseModel):
    """Schema for marking a stage as completed.

    Used to explicitly mark a stage as completed (vs implicit marking when next stage starts).
    This is called after parallel task building completes to ensure accurate status tracking.
    """

    stage: WorkflowGenerationStage = Field(
        ..., description="Stage to mark as completed"
    )


class WorkflowGenerationUpdateResults(BaseModel):
    """Schema for updating workflow generation with orchestration results."""

    workflow_id: UUID | None = None
    workspace_path: str | None = Field(
        None, description="Path to workspace directory for cleanup"
    )
    status: WorkflowGenerationStatus
    orchestration_results: dict[str, Any] | None = Field(
        None,
        description="Complete orchestration results: runbook, task_proposals, tasks_built, workflow_composition, metrics, error",
    )


# Alert Routing Rule Schemas
class AlertRoutingRuleCreate(BaseModel):
    """Schema for creating an alert routing rule."""

    analysis_group_id: UUID
    workflow_id: UUID


class AlertRoutingRuleResponse(BaseModel):
    """Schema for alert routing rule response."""

    id: UUID
    tenant_id: str
    analysis_group_id: UUID
    workflow_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Atomic Creation Schema
class AnalysisGroupWithGenerationResponse(BaseModel):
    """Schema for atomic creation of analysis group + workflow generation."""

    analysis_group: AnalysisGroupResponse
    workflow_generation: WorkflowGenerationResponse

    model_config = ConfigDict(from_attributes=True)


# Generation Summary for Active Workflow Response
class GenerationSummary(BaseModel):
    """Lightweight generation info for reconciliation.

    Only includes fields needed to determine if generation is terminal
    and what the outcome was.
    """

    id: UUID
    analysis_group_id: UUID
    status: str  # "running", "completed", "failed"
    workflow_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


# Active Workflow Schema
class ActiveWorkflowResponse(BaseModel):
    """Schema for active workflow query response.

    Used by reconciliation to check if workflows are ready for paused alerts.
    Returns both routing_rule (if exists) AND latest generation status
    so reconciliation can detect failed generations.
    """

    routing_rule: AlertRoutingRuleResponse | None = None
    generation: GenerationSummary | None = None


# Push-based Resume Response
class ResumePausedAlertsResponse(BaseModel):
    """Response for push-based alert resume operation.

    Used by workflow_generation_job after creating routing rule
    to resume all alerts waiting for this workflow.
    """

    resumed_count: int = Field(
        ..., description="Number of alerts successfully resumed and enqueued"
    )
    skipped_count: int = Field(
        0, description="Number of alerts already resumed by another worker"
    )
    alert_ids: list[str] = Field(
        default_factory=list, description="IDs of alerts that were resumed"
    )
