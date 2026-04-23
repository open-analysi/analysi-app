"""Pydantic schemas for Alert system.

Project Skaros: OCSF Detection Finding v1.8.0 shape.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from analysi.constants import AlertConstants
from analysi.schemas.ocsf.detection_finding import (
    OSINT,
    Actor,
    EvidenceArtifact,
    FindingInfo,
    Observable,
    OCSFCloud,
    OCSFDevice,
    OCSFMetadata,
    VulnerabilityDetail,
)


# Enums for validation
class AlertSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


AlertStatus = AlertConstants.Status


# Alert Schemas — OCSF Detection Finding v1.8.0
class AlertBase(BaseModel):
    """Base schema for Alert — OCSF Detection Finding v1.8.0.

    Legacy fields (primary_risk_entity_value, network_info, etc.) are no longer
    part of the schema. Normalizers may still produce dicts that contain them;
    Pydantic silently ignores the extras so AlertCreate(**extracted_dict) works.
    """

    model_config = {"extra": "ignore"}

    # Core fields (always present)
    title: str = Field(..., min_length=1, max_length=500, description="Alert title")
    triggering_event_time: datetime = Field(..., description="When the event occurred")
    severity: AlertSeverity = Field(
        ..., description="Severity caption (critical/high/medium/low/info)"
    )
    raw_data: str = Field(..., description="Original alert as received")

    # Source identification (shared columns)
    source_vendor: str | None = Field(None, max_length=100, description="Source vendor")
    source_product: str | None = Field(
        None, max_length=100, description="Source product"
    )
    rule_name: str | None = Field(
        None, max_length=255, description="Detection rule name"
    )
    source_event_id: str | None = Field(
        None, max_length=500, description="Source event ID"
    )

    # OCSF structured fields (JSONB) — typed with OCSF sub-models
    finding_info: FindingInfo | None = Field(
        None, description="OCSF FindingInfo: title, uid, analytic, types"
    )
    ocsf_metadata: OCSFMetadata | None = Field(
        None, description="OCSF Metadata: product, version, labels, profiles"
    )
    evidences: list[EvidenceArtifact] | None = Field(
        None,
        description="OCSF Evidence Artifacts: src_endpoint, dst_endpoint, process, file, url",
    )
    observables: list[Observable] | None = Field(
        None, description="OCSF Observables: type_id, type, value"
    )
    osint: list[OSINT] | None = Field(
        None, description="OCSF OSINT: threat intel indicators"
    )
    actor: Actor | None = Field(None, description="OCSF Actor: user, process, session")
    device: OCSFDevice | None = Field(None, description="OCSF Device: hostname, ip, os")
    cloud: OCSFCloud | None = Field(
        None, description="OCSF Cloud: provider, region, account"
    )
    vulnerabilities: list[VulnerabilityDetail] | None = Field(
        None, description="OCSF Vulnerabilities: cve, cvss"
    )
    unmapped: dict[str, Any] | None = Field(
        None, description="OCSF unmapped: catch-all"
    )

    # OCSF scalar enums
    severity_id: int | None = Field(
        None,
        ge=1,
        le=6,
        description="OCSF severity: 1=Info, 2=Low, 3=Medium, 4=High, 5=Critical, 6=Fatal",
    )
    disposition_id: int | None = Field(
        None, description="OCSF disposition: 0=Unknown, 1=Allowed, 2=Blocked, etc."
    )
    verdict_id: int | None = Field(
        None, description="OCSF verdict: 1=FP, 2=TP, 4=Suspicious"
    )
    action_id: int | None = Field(
        None, description="OCSF action: 0=Unknown, 1=Allowed, 2=Denied"
    )
    status_id: int | None = Field(
        None, description="OCSF status: 1=New, 2=In Progress, 4=Resolved"
    )
    confidence_id: int | None = Field(
        None, description="OCSF confidence: 1=Low, 2=Medium, 3=High"
    )
    risk_level_id: int | None = Field(
        None, description="OCSF risk: 0=Info, 1=Low, 2=Medium, 3=High, 4=Critical"
    )

    # OCSF time + dedup
    ocsf_time: int | None = Field(None, description="Event time as epoch milliseconds")
    detected_at: datetime | None = Field(
        None, description="When source system detected"
    )

    @model_validator(mode="before")
    @classmethod
    def _map_raw_alert_to_raw_data(cls, values: Any) -> Any:
        """Map legacy raw_alert -> raw_data for backward compat with normalizers."""
        if (
            isinstance(values, dict)
            and "raw_alert" in values
            and "raw_data" not in values
        ):
            values["raw_data"] = values.pop("raw_alert")
        return values

    @property
    def raw_alert(self) -> str:
        """Backward-compatible alias: raw_alert -> raw_data.

        Normalizers and many tests still access .raw_alert.
        """
        return self.raw_data


class AlertCreate(AlertBase):
    """Schema for creating new alerts — OCSF shape."""

    human_readable_id: str | None = Field(None, description="Custom human-readable ID")


class AlertUpdate(BaseModel):
    """Schema for updating alert analysis fields only."""

    analysis_status: AlertStatus | None = None
    current_analysis_id: UUID | None = None

    model_config = {"extra": "forbid"}


class AlertResponse(AlertBase):
    """Schema for alert API responses — OCSF shape."""

    alert_id: UUID = Field(..., description="Globally unique identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    human_readable_id: str = Field(..., description="Human-friendly ID")

    current_analysis_id: UUID | None = Field(None, description="Current analysis")
    analysis_status: AlertStatus = Field(..., description="Analysis status")

    # Denormalized disposition
    current_disposition_category: str | None = None
    current_disposition_subcategory: str | None = None
    current_disposition_display_name: str | None = None
    current_disposition_confidence: int | None = Field(None, ge=0, le=100)

    raw_data_hash: str = Field(..., description="SHA-256 deduplication hash")
    ingested_at: datetime = Field(..., description="When ingested")
    created_at: datetime
    updated_at: datetime

    current_analysis: Optional["AlertAnalysisResponse"] = None
    short_summary: str | None = None

    model_config = {"from_attributes": True}


class AlertList(BaseModel):
    """Schema for paginated alert list responses."""

    alerts: list[AlertResponse] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total number of alerts")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Pagination offset")


# Analysis Schemas
class AnalysisStatus(StrEnum):
    """Analysis-level status (internal pipeline state)."""

    RUNNING = "running"  # Pipeline actively executing steps
    PAUSED_WORKFLOW_BUILDING = (
        "paused"  # Waiting for workflow generation (V112: renamed)
    )
    PAUSED_HUMAN_REVIEW = (
        "paused_human_review"  # HITL — Project Kalymnos: waiting for human input
    )
    COMPLETED = "completed"  # All steps finished successfully
    FAILED = "failed"  # Pipeline failed
    CANCELLED = "cancelled"  # User cancelled


# Pipeline Step Progress Schemas
class PipelineStep(StrEnum):
    """Pipeline steps in execution order."""

    PRE_TRIAGE = "pre_triage"
    WORKFLOW_BUILDER = "workflow_builder"
    WORKFLOW_EXECUTION = "workflow_execution"
    FINAL_DISPOSITION = "final_disposition_update"


class StepStatus(StrEnum):
    """Status of a pipeline step."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Ordered list of all pipeline steps
PIPELINE_STEPS = [
    PipelineStep.PRE_TRIAGE,
    PipelineStep.WORKFLOW_BUILDER,
    PipelineStep.WORKFLOW_EXECUTION,
    PipelineStep.FINAL_DISPOSITION,
]


class PipelineStepProgress(BaseModel):
    """Progress for a single pipeline step.

    All steps are initialized upfront with status=not_started.
    As each step starts, its status changes to in_progress and started_at is set.
    When complete, status changes to completed and completed_at is set.

    Like WorkflowGenerationPhase but for alert analysis pipeline.
    """

    step: PipelineStep
    status: StepStatus = Field(
        StepStatus.NOT_STARTED,
        description="Step status: not_started, in_progress, completed, failed, skipped",
    )
    started_at: datetime | None = Field(
        None,
        description="When the step started (set when status changes to in_progress)",
    )
    completed_at: datetime | None = Field(
        None,
        description="When the step completed (set when status changes to completed/failed)",
    )
    error: str | None = Field(None, description="Error message if step failed")
    retries: int = Field(0, description="Number of retry attempts for this step")
    result: dict[str, Any] | None = Field(None, description="Step-specific result data")


class PipelineStepsProgress(BaseModel):
    """Complete steps progress for alert analysis pipeline.

    All 4 steps are initialized upfront so the UI knows what to expect:
    - Initial: steps=[
        {step: pre_triage, status: not_started},
        {step: workflow_builder, status: not_started},
        {step: workflow_execution, status: not_started},
        {step: final_disposition_update, status: not_started}
      ]
    - Step 1 starts: steps=[
        {step: pre_triage, status: in_progress, started_at: ...},
        {step: workflow_builder, status: not_started},
        ...
      ]

    Like WorkflowGenerationProgress but for alert analysis pipeline.
    """

    steps: list[PipelineStepProgress] = Field(
        default_factory=list,
        description="All 4 steps in order. Status transitions: not_started → in_progress → completed/failed",
    )

    @classmethod
    def initialize_all_steps(cls) -> "PipelineStepsProgress":
        """Create a new progress with all 4 steps initialized to not_started."""
        return cls(steps=[PipelineStepProgress(step=step) for step in PIPELINE_STEPS])  # type: ignore[call-arg]

    def get_step(self, step: PipelineStep) -> PipelineStepProgress | None:
        """Get progress for a specific step."""
        for s in self.steps:
            if s.step == step:
                return s
        return None

    def mark_step_in_progress(self, step: PipelineStep) -> None:
        """Mark a step as in_progress and set started_at."""
        step_progress = self.get_step(step)
        if step_progress:
            step_progress.status = StepStatus.IN_PROGRESS
            step_progress.started_at = datetime.now(UTC)

    def mark_step_completed(
        self, step: PipelineStep, result: dict[str, Any] | None = None
    ) -> None:
        """Mark a step as completed and set completed_at."""
        step_progress = self.get_step(step)
        if step_progress:
            step_progress.status = StepStatus.COMPLETED
            step_progress.completed_at = datetime.now(UTC)
            if result:
                step_progress.result = result

    def mark_step_failed(self, step: PipelineStep, error: str) -> None:
        """Mark a step as failed with error message."""
        step_progress = self.get_step(step)
        if step_progress:
            step_progress.status = StepStatus.FAILED
            step_progress.completed_at = datetime.now(UTC)
            step_progress.error = error

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSONB storage."""
        return {"steps": [s.model_dump(mode="json") for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineStepsProgress":
        """Create from dictionary (from JSONB storage).

        Handles both new format (with "steps" array) and old format (dict of step dicts).

        Old format example:
            {"pre_triage": {"completed": true, "started_at": "..."}, ...}

        New format example:
            {"steps": [{"step": "pre_triage", "status": "completed", ...}, ...]}
        """
        if not data:
            return cls.initialize_all_steps()

        # New format: has "steps" key
        if "steps" in data:
            return cls(steps=[PipelineStepProgress(**s) for s in data.get("steps", [])])

        # Old format: convert dict-of-dicts to new format
        steps = []
        for pipeline_step in PIPELINE_STEPS:
            step_name = pipeline_step.value
            old_step_data = data.get(step_name, {})

            # Convert old format to new format
            if old_step_data.get("completed"):
                status = StepStatus.COMPLETED
            elif old_step_data.get("error"):
                status = StepStatus.FAILED
            elif old_step_data.get("started_at"):
                status = StepStatus.IN_PROGRESS
            else:
                status = StepStatus.NOT_STARTED

            steps.append(
                PipelineStepProgress(
                    step=pipeline_step,
                    status=status,
                    started_at=old_step_data.get("started_at"),
                    completed_at=old_step_data.get("completed_at"),
                    error=old_step_data.get("error"),
                    retries=old_step_data.get("retries", 0),
                    result=old_step_data.get("result"),
                )
            )

        return cls(steps=steps)


class StepProgress(BaseModel):
    """Legacy schema for individual step progress (for backward compatibility)."""

    completed: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retries: int = 0
    error: str | None = None


class AlertAnalysisResponse(BaseModel):
    """Schema for alert analysis responses."""

    id: UUID = Field(..., description="Analysis ID")
    alert_id: UUID = Field(..., description="Associated alert")
    tenant_id: str = Field(..., description="Tenant identifier")

    status: AnalysisStatus = Field(..., description="Analysis status")
    error_message: str | None = Field(
        None, description="Error message if analysis failed"
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None

    current_step: str | None = None
    steps_progress: dict[str, Any] = Field(default_factory=dict)

    disposition_id: UUID | None = None
    confidence: int | None = Field(None, ge=0, le=100)
    short_summary: str | None = None
    long_summary: str | None = None

    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnalysisProgress(BaseModel):
    """Schema for analysis progress endpoint."""

    analysis_id: UUID
    current_step: str
    completed_steps: int
    total_steps: int = len(PIPELINE_STEPS)
    status: AnalysisStatus
    error_message: str | None = None
    steps_detail: dict[str, StepProgress]


class AnalysisHistory(BaseModel):
    """Schema for analysis history endpoint."""

    analyses: list[AlertAnalysisResponse]
    total: int


# Disposition Schemas
class DispositionResponse(BaseModel):
    """Schema for disposition in alert responses."""

    disposition_id: UUID = Field(alias="disposition_id")
    category: str
    subcategory: str
    display_name: str
    color_hex: str
    color_name: str
    priority_score: int
    requires_escalation: bool

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to map 'id' field to 'disposition_id'."""
        if hasattr(obj, "id"):
            # SQLAlchemy model object
            data = {
                "disposition_id": obj.id,
                "category": obj.category,
                "subcategory": obj.subcategory,
                "display_name": obj.display_name,
                "color_hex": obj.color_hex,
                "color_name": obj.color_name,
                "priority_score": obj.priority_score,
                "requires_escalation": obj.requires_escalation,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


# Alert Analysis Operation Responses (Project Sifnos)
class AnalysisStartedResponse(BaseModel):
    """Response when alert analysis is initiated."""

    analysis_id: str
    status: str
    message: str


class AnalysisStepUpdatedResponse(BaseModel):
    """Response when an analysis step is updated."""

    status: str
    step: str


class AnalysisCompletedResponse(BaseModel):
    """Response when an analysis is completed."""

    status: str
    analysis_id: str


class AnalysisStatusUpdatedResponse(BaseModel):
    """Response when analysis or alert analysis status is updated."""

    status: str
    analysis_status: str


class AnalysisCancelledResponse(BaseModel):
    """Response when an analysis is cancelled."""

    status: str
    previous_status: str


# Update forward references
AlertResponse.model_rebuild()
AlertAnalysisResponse.model_rebuild()
