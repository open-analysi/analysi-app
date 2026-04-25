"""
Pydantic schemas for workflow-related API requests and responses.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from analysi.config.logging import get_logger


class NodeKind(StrEnum):
    """Node type enumeration."""

    TASK = "task"
    TRANSFORMATION = "transformation"
    FOREACH = "foreach"


class NodeSchemas(BaseModel):
    """
    Schema for WorkflowNode.schemas JSONB field.

    Supports both existing schema fields and new type propagation fields.

    STUB: Basic structure only. Full validation to be added in 050 cycle.
    """

    # Existing fields (backward compatibility)
    input: dict[str, Any] | None = Field(None, description="Node input schema")
    output: dict[str, Any] | None = Field(None, description="Node output schema")

    # Type propagation fields
    inferred_input: dict[str, Any] | None = Field(
        None, description="Type-inferred input schema from propagation"
    )
    inferred_output: dict[str, Any] | None = Field(
        None, description="Type-inferred output schema from propagation"
    )
    type_checked: bool = Field(
        False, description="Whether this node has been type-checked"
    )
    validated_at: datetime | None = Field(
        None, description="Timestamp of last type validation"
    )

    model_config = ConfigDict(
        extra="allow",  # Allow other fields for extensibility
        json_schema_extra={
            "example": {
                "inferred_input": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                "inferred_output": {
                    "type": "object",
                    "properties": {"threat_score": {"type": "number"}},
                },
                "type_checked": True,
                "validated_at": "2026-04-26T10:30:00Z",
            }
        },
    )


class TemplateType(StrEnum):
    """Template type enumeration."""

    STATIC = "static"
    DYNAMIC = "dynamic"


# Node Template Schemas
class NodeTemplateCreate(BaseModel):
    """Schema for creating node templates."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    input_schema: dict[str, Any] = Field(
        ..., description="JSON Schema for input validation"
    )
    output_schema: dict[str, Any] = Field(
        ..., description="JSON Schema for output validation"
    )
    code: str = Field(..., min_length=1, description="Template execution code")
    language: str = Field(default="python", description="Template language")
    type: TemplateType = Field(default=TemplateType.STATIC, description="Template type")
    kind: str = Field(
        default="identity",
        description="Template kind for type inference (identity, merge, collect)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "pick_primary_ip",
                "description": "Extract primary IP from alert data",
                "input_schema": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"primary_ip": {"type": "string"}},
                },
                "code": "alert = inp['alert']\nreturn {'primary_ip': alert.get('src', {}).get('ip')}",
                "language": "python",
                "type": "static",
            }
        }
    )


class NodeTemplateResponse(BaseModel):
    """Schema for node template responses."""

    id: UUID
    resource_id: UUID
    tenant_id: str | None  # NULL for system templates
    name: str
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    code: str
    language: str
    type: str
    kind: str | None = Field(
        default="identity",
        description="Type inference classification (identity, merge, collect)",
    )
    enabled: bool
    revision_num: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Workflow Node Schemas
class WorkflowNodeCreate(BaseModel):
    """Schema for workflow node creation."""

    node_id: str = Field(
        ..., min_length=1, description="Unique node ID within workflow"
    )
    kind: NodeKind = Field(..., description="Type of node")
    name: str = Field(..., min_length=1, description="Human-readable node name")

    # Rodos: Explicit start node marking
    is_start_node: bool = Field(
        default=False,
        description="True if this is an entry point for the workflow (receives workflow input)",
    )

    # Type-specific references (only one should be provided based on kind)
    task_id: UUID | None = None
    node_template_id: UUID | None = None

    # Foreach-specific configuration
    foreach_config: dict[str, Any] | None = None

    # Schema definitions
    schemas: dict[str, Any] = Field(
        ..., description="Input/output schemas for the node"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "n-pick-ip",
                "kind": "transformation",
                "name": "Pick Primary IP",
                "is_start_node": False,
                "node_template_id": "550e8400-e29b-41d4-a716-446655440000",
                "schemas": {
                    "input": {"type": "object"},
                    "output_envelope": {"type": "object"},
                    "output_result": {
                        "type": "object",
                        "properties": {"primary_ip": {"type": "string"}},
                    },
                },
            }
        }
    )

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "WorkflowNodeCreate":
        """Validate that kind-specific fields are correctly set.

        Matches the DB constraint workflow_nodes_kind_fields:
        - task: task_id required, node_template_id must be None
        - transformation: node_template_id required, task_id must be None
        - foreach: foreach_config required, task_id and node_template_id must be None
        """
        if self.kind == NodeKind.TASK:
            if self.task_id is None:
                raise ValueError("task_id is required for kind='task'")
            if self.node_template_id is not None:
                raise ValueError("node_template_id must be None for kind='task'")
            if self.foreach_config is not None:
                raise ValueError("foreach_config must be None for kind='task'")
        elif self.kind == NodeKind.TRANSFORMATION:
            if self.node_template_id is None:
                raise ValueError(
                    "node_template_id is required for kind='transformation'"
                )
            if self.task_id is not None:
                raise ValueError("task_id must be None for kind='transformation'")
            if self.foreach_config is not None:
                raise ValueError(
                    "foreach_config must be None for kind='transformation'"
                )
        elif self.kind == NodeKind.FOREACH:
            if self.foreach_config is None:
                raise ValueError("foreach_config is required for kind='foreach'")
            if self.task_id is not None:
                raise ValueError("task_id must be None for kind='foreach'")
            if self.node_template_id is not None:
                raise ValueError("node_template_id must be None for kind='foreach'")
        return self


class WorkflowNodeResponse(BaseModel):
    """Schema for workflow node responses."""

    id: UUID
    node_id: str
    kind: str
    name: str
    task_id: UUID | None
    node_template_id: UUID | None
    foreach_config: dict[str, Any] | None
    schemas: dict[str, Any]
    is_start_node: bool = False
    created_at: datetime

    # Enriched data (when requested)
    template_code: str | None = Field(
        None, description="Template code (if template node)"
    )
    task_details: dict[str, Any] | None = Field(
        None, description="Task details (if task node)"
    )

    model_config = ConfigDict(from_attributes=True)


# Workflow Edge Schemas
class WorkflowEdgeCreate(BaseModel):
    """Schema for workflow edge creation."""

    edge_id: str = Field(
        ..., min_length=1, description="Unique edge ID within workflow"
    )
    from_node_id: str = Field(..., description="Source node ID")
    to_node_id: str = Field(..., description="Target node ID")
    alias: str | None = Field(None, description="Optional edge label")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "edge_id": "e1",
                "from_node_id": "n-start",
                "to_node_id": "n-pick-ip",
                "alias": "initial_data",
            }
        }
    )


class WorkflowEdgeResponse(BaseModel):
    """Schema for workflow edge responses."""

    id: UUID
    edge_id: str
    from_node_uuid: UUID
    to_node_uuid: UUID
    alias: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Workflow Schemas
class WorkflowCreate(BaseModel):
    """Schema for creating complete workflows with nodes and edges."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_dynamic: bool = Field(default=False, description="True if created by AI planner")
    io_schema: dict[str, Any] = Field(
        ..., description="Overall workflow input/output schema"
    )
    data_samples: list[Any] | None = Field(
        None,
        description=(
            "Sample input data for testing the workflow. "
            "RECOMMENDED: Use structure {name, input, description, expected_output} "
            "where 'input' contains the actual test data. "
            "The composer will extract the 'input' field for execution."
        ),
        json_schema_extra={
            "example": [
                {
                    "name": "Test Alert - SSH Brute Force",
                    "input": {
                        "title": "SSH Brute Force Attack Detected",
                        "severity": "high",
                        "source_ip": "185.220.101.45",
                    },
                    "description": "Test workflow with brute force alert",
                    "expected_output": {"disposition": "malicious", "action": "block"},
                }
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
                "workflow_data_samples_pattern_recommendation",
                message=(
                    f"Only {recommended_pattern_count}/{len(v)} workflow data_samples use "
                    "recommended {name, input, description, expected_output} structure. "
                    "Consider using this pattern for better schema inference and UI display."
                ),
                samples_count=len(v),
                recommended_count=recommended_pattern_count,
            )

        return v

    app: str = Field(
        default="default",
        max_length=100,
        description="Content pack name (set during pack install)",
    )

    # Nested node and edge definitions (can be empty for incremental building)
    nodes: list[WorkflowNodeCreate] = Field(
        default_factory=list, description="Workflow nodes"
    )
    edges: list[WorkflowEdgeCreate] = Field(
        default_factory=list, description="Workflow edges"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "IP Blocking Workflow",
                "description": "Extract IP and block in firewall",
                "is_dynamic": False,
                "io_schema": {
                    "input": {
                        "type": "object",
                        "properties": {"alert": {"type": "object"}},
                    },
                    "output": {
                        "type": "object",
                        "properties": {"action_id": {"type": "string"}},
                    },
                },
                "nodes": [
                    {
                        "node_id": "n-start",
                        "kind": "transformation",
                        "name": "Start Node",
                        "node_template_id": "550e8400-e29b-41d4-a716-446655440000",
                        "schemas": {
                            "input": {"type": "object"},
                            "output_result": {"type": "object"},
                        },
                    }
                ],
                "edges": [],
            }
        }
    )


class WorkflowResponse(BaseModel):
    """Schema for workflow responses with enriched data."""

    id: UUID
    tenant_id: str
    name: str
    description: str | None
    is_dynamic: bool
    io_schema: dict[str, Any]
    data_samples: list[Any] | None = Field(
        None, description="Sample input data for testing"
    )
    status: str = Field(
        default="draft",
        description="Validation status: draft (created), validated (type-checked), invalid (has errors)",
    )
    created_by: UUID
    created_at: datetime
    planner_id: UUID | None

    # Nested enriched nodes and edges
    nodes: list[WorkflowNodeResponse] = Field(
        ..., description="Workflow nodes with enriched data"
    )
    edges: list[WorkflowEdgeResponse] = Field(..., description="Workflow edges")

    model_config = ConfigDict(from_attributes=True)


def validate_node_references(
    nodes: list[WorkflowNodeCreate], edges: list[WorkflowEdgeCreate]
) -> bool:
    """
    Validate that all edge references point to existing nodes.

    Args:
        nodes: List of node definitions
        edges: List of edge definitions

    Returns:
        True if all references are valid

    Raises:
        ValueError: If invalid references found
    """
    raise NotImplementedError("Node reference validation to be implemented")


def validate_workflow_completeness(workflow: WorkflowCreate) -> bool:
    """
    Validate that workflow is complete and well-formed.

    Args:
        workflow: Complete workflow definition

    Returns:
        True if workflow is valid

    Raises:
        ValueError: If workflow validation fails
    """
    raise NotImplementedError("Workflow completeness validation to be implemented")


# Workflow Composer Schemas
class ComposeRequest(BaseModel):
    """Schema for workflow composition requests."""

    composition: list[Any] = Field(
        ...,
        description="Array of cy_names, shortcuts, or nested arrays for parallel execution",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Workflow name")
    description: str | None = Field(None, description="Workflow description")
    execute: bool = Field(
        default=False,
        description="If True, create workflow; if False, return plan only",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "composition": [
                    "identity",
                    "extract_ip",
                    ["lookup_virustotal", "lookup_abuseipdb"],
                    "merge",
                    "block_firewall",
                ],
                "name": "Threat Intelligence Workflow",
                "description": "Extract IP and check multiple threat intel sources",
                "execute": False,
            }
        }
    )


class CompositionError(BaseModel):
    """Schema for composition errors."""

    error_type: str = Field(..., description="Error category")
    message: str = Field(..., description="Human-readable error message")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional error context"
    )


class CompositionWarning(BaseModel):
    """Schema for composition warnings."""

    warning_type: str = Field(..., description="Warning category")
    message: str = Field(..., description="Human-readable warning message")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional warning context"
    )


class CompositionQuestion(BaseModel):
    """Schema for composition questions requiring user decision."""

    question_id: str = Field(..., description="Unique question identifier")
    question_type: str = Field(..., description="Question type")
    message: str = Field(..., description="Question text")
    options: list[str] = Field(..., description="Available choices")
    suggested: str | None = Field(None, description="Recommended option")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )


class CompositionPlan(BaseModel):
    """Schema for composition plan showing what would be created."""

    nodes: int = Field(..., description="Number of nodes")
    edges: int = Field(..., description="Number of edges")
    inferred_input_schema: dict[str, Any] = Field(
        ..., description="Workflow input schema"
    )
    inferred_output_schema: dict[str, Any] = Field(
        ..., description="Workflow output schema"
    )
    node_details: list[dict[str, Any]] = Field(
        default_factory=list, description="Detailed node information"
    )


class ComposeResponse(BaseModel):
    """Schema for workflow composition responses."""

    status: str = Field(
        ...,
        description="Result status: success, needs_decision, or error",
    )
    workflow_id: UUID | None = Field(None, description="Created workflow ID")
    errors: list[CompositionError] = Field(
        default_factory=list, description="Blocking errors"
    )
    warnings: list[CompositionWarning] = Field(
        default_factory=list, description="Non-blocking warnings"
    )
    questions: list[CompositionQuestion] = Field(
        default_factory=list, description="Decisions needed from user"
    )
    plan: CompositionPlan | None = Field(None, description="What was/would be created")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                "errors": [],
                "warnings": [],
                "questions": [],
                "plan": {
                    "nodes": 6,
                    "edges": 7,
                    "inferred_input_schema": {"type": "object"},
                    "inferred_output_schema": {"type": "object"},
                    "node_details": [],
                },
            }
        }
    )


# ========== Mutable Workflow Schemas ==========


class WorkflowUpdate(BaseModel):
    """Partial update for workflow metadata."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    io_schema: dict[str, Any] | None = None
    data_samples: list[Any] | None = None


class AddNodeRequest(BaseModel):
    """Request to add a node to an existing workflow."""

    node_id: str = Field(
        ..., min_length=1, description="Unique node ID within workflow"
    )
    kind: NodeKind = Field(..., description="Node type: task, transformation, foreach")
    name: str = Field(..., min_length=1, max_length=255)
    is_start_node: bool = Field(
        default=False, description="True if this is the entry node"
    )
    task_id: UUID | None = Field(None, description="Task ID for task nodes")
    node_template_id: UUID | None = Field(
        None, description="Template ID for transformation nodes"
    )
    foreach_config: dict[str, Any] | None = Field(
        None, description="Config for foreach nodes"
    )
    schemas: dict[str, Any] = Field(..., description="Node input/output schemas")


class WorkflowNodeUpdate(BaseModel):
    """Partial update for a workflow node."""

    name: str | None = Field(None, min_length=1, max_length=255)
    schemas: dict[str, Any] | None = None
    task_id: UUID | None = None
    node_template_id: UUID | None = None


class AddEdgeRequest(BaseModel):
    """Request to add an edge to an existing workflow."""

    edge_id: str = Field(
        ..., min_length=1, description="Unique edge ID within workflow"
    )
    from_node_id: str = Field(..., description="Source node ID (logical)")
    to_node_id: str = Field(..., description="Target node ID (logical)")
    alias: str | None = Field(None, description="Optional edge label")


class ValidationResult(BaseModel):
    """Response from on-demand workflow validation."""

    valid: bool = Field(..., description="True if workflow is valid")
    workflow_status: str = Field(
        ..., description="New workflow status: draft, validated, invalid"
    )
    dag_errors: list[str] = Field(
        default_factory=list, description="DAG structure errors (cycles, disconnected)"
    )
    type_errors: list[str] = Field(
        default_factory=list, description="Type propagation errors"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking issues")


# Workflow Validation Responses (Project Sifnos)
class WorkflowDefinitionValidation(BaseModel):
    """Response from workflow definition validation."""

    valid: bool
    node_count: int
    edge_count: int
    has_cycles: bool


class TemplateCodeValidation(BaseModel):
    """Response from template code validation."""

    valid: bool
    language: str
    line_count: int


class WorkflowTypesClearedResponse(BaseModel):
    """Response from clearing workflow type annotations."""

    success: bool
    nodes_updated: int
    workflow_id: str


# Workflow Mutation Responses (Project Sifnos)
class WorkflowNodeMutationResponse(BaseModel):
    """Response when a workflow node is added or updated."""

    id: str
    node_id: str
    kind: str
    name: str
    is_start_node: bool
    schemas: dict[str, Any] | None = None


class WorkflowEdgeMutationResponse(BaseModel):
    """Response when a workflow edge is added."""

    id: str
    edge_id: str
    from_node_id: str
    to_node_id: str
    alias: str | None = None
