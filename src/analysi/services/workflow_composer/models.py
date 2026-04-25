"""
Data models for Workflow Composer.

These models represent the intermediate states and results during composition.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

# ============================================================================
# Parsed Composition Models
# ============================================================================


@dataclass
class ParsedNode:
    """
    Intermediate node representation after parsing composition array.

    Attributes:
        node_id: Auto-generated node identifier (e.g., "n1", "n2")
        reference: cy_name (for tasks) or shortcut (for templates)
        layer: Sequential layer number (1, 2, 3...)
        parallel_group: Group ID for parallel execution (None if sequential)
    """

    node_id: str
    reference: str
    layer: int
    parallel_group: int | None = None


@dataclass
class ParsedEdge:
    """
    Intermediate edge representation after parsing composition.

    Attributes:
        from_node_id: Source node ID
        to_node_id: Target node ID
        edge_id: Auto-generated edge identifier
    """

    from_node_id: str
    to_node_id: str
    edge_id: str


@dataclass
class ParsedComposition:
    """
    Result of parsing array-based composition into graph structure.

    Attributes:
        nodes: List of parsed nodes
        edges: List of parsed edges
        max_layer: Maximum layer number (depth of workflow)
    """

    nodes: list[ParsedNode]
    edges: list[ParsedEdge]
    max_layer: int


# ============================================================================
# Resolved Task/Template Models
# ============================================================================


@dataclass
class ResolvedTask:
    """
    Task resolved from cy_name lookup.

    Attributes:
        task_id: Database UUID
        cy_name: Canonical name
        name: Human-readable name
        input_schema: Inferred from data_samples (via Finding #6)
        output_schema: Inferred from Cy script analysis
        data_samples: Example input data
    """

    task_id: UUID
    cy_name: str
    name: str
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    data_samples: list[dict[str, Any]]


@dataclass
class ResolvedTemplate:
    """
    Template resolved from shortcut.

    Attributes:
        template_id: Database UUID
        shortcut: Lowercase shortcut ("identity", "merge", "collect")
        name: System template name
        kind: Template kind (identity, merge, collect)
        input_schema: Template input schema
        output_schema: Template output schema
    """

    template_id: UUID
    shortcut: str
    name: str
    kind: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


# ============================================================================
# Validation Error/Warning Models
# ============================================================================


@dataclass
class CompositionError:
    """
    Blocking error during composition.

    Attributes:
        error_type: Error category (task_not_found, cycle_detected, etc.)
        message: Human-readable error message
        context: Additional error context
    """

    error_type: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositionWarning:
    """
    Non-blocking warning during composition.

    Attributes:
        warning_type: Warning category
        message: Human-readable warning message
        context: Additional warning context
    """

    warning_type: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Question:
    """
    Decision point requiring user input.

    Attributes:
        question_id: Unique question identifier
        question_type: Type of question (missing_aggregation, ambiguous_resolution)
        message: Question text for user
        options: Available choices
        suggested: Recommended option (optional)
        context: Additional context to help decision
    """

    question_id: str
    question_type: str
    message: str
    options: list[str]
    suggested: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Composition Result Models
# ============================================================================


@dataclass
class CompositionPlan:
    """
    Plan showing what workflow would be created.

    Attributes:
        nodes: Node count
        edges: Edge count
        inferred_input_schema: Workflow input schema
        inferred_output_schema: Workflow output schema
        node_details: Detailed node information
    """

    nodes: int
    edges: int
    inferred_input_schema: dict[str, Any]
    inferred_output_schema: dict[str, Any]
    node_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CompositionResult:
    """
    Final result of composition attempt.

    Attributes:
        status: Result status (success, needs_decision, error)
        workflow_id: Created workflow ID (if status=success)
        errors: Blocking errors
        warnings: Non-blocking warnings
        questions: Decisions needed from user
        plan: What was/would be created
    """

    status: Literal["success", "needs_decision", "error"]
    workflow_id: UUID | None
    errors: list[CompositionError]
    warnings: list[CompositionWarning]
    questions: list[Question]
    plan: CompositionPlan | None
