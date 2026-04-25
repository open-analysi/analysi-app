"""
Schemas for Knowledge Dependency Graph operations.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EdgeDirection(StrEnum):
    """Direction filter for edge queries."""

    IN = "in"
    OUT = "out"
    BOTH = "both"


class NodeType(StrEnum):
    """Type filter for node queries - detailed types for precise filtering."""

    TASK = "task"
    DOCUMENT = "document"
    TABLE = "table"
    INDEX = "index"
    TOOL = "tool"  # Future integration with mcp-service
    SKILL = "skill"  # Knowledge modules (skills)


class EdgeType(StrEnum):
    """Valid relationship types for edges."""

    USES = "uses"
    GENERATES = "generates"
    UPDATES = "updates"
    CALLS = "calls"
    TRANSFORMS_INTO = "transforms_into"
    SUMMARIZES_INTO = "summarizes_into"
    INDEXES_INTO = "indexes_into"
    DERIVED_FROM = "derived_from"
    ENRICHES = "enriches"
    # Module composition edge types
    CONTAINS = "contains"
    INCLUDES = "includes"
    DEPENDS_ON = "depends_on"
    REFERENCES = "references"
    # Staged document edge type
    STAGED_FOR = "staged_for"
    # Feedback edge type
    FEEDBACK_FOR = "feedback_for"


class NodeResponse(BaseModel):
    """Response schema for a node (Task or any KU type)."""

    id: UUID
    type: NodeType
    name: str
    description: str | None = None
    version: str = "1.0.0"
    status: str = "enabled"
    categories: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = Field(
        default=None, description="UUID of user who created this node"
    )

    # Task-specific fields (None for KUs)
    function: str | None = None
    scope: str | None = None

    # KU type field (None for Tasks)
    ku_type: str | None = None  # document, table, index, tool

    # Document-specific fields
    document_type: str | None = None  # pdf, markdown, html, etc.

    # Table-specific fields
    row_count: int | None = None
    column_count: int | None = None

    # Index-specific fields
    index_type: str | None = None  # simple_rag, graph_rag
    build_status: str | None = None  # building, ready, failed

    # Tool-specific fields (future)
    tool_type: str | None = None  # mcp, native


class EdgeCreate(BaseModel):
    """Schema for creating a new edge."""

    source_id: UUID
    target_id: UUID
    relationship_type: EdgeType
    is_required: bool = False
    execution_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeResponse(BaseModel):
    """Response schema for an edge with node details."""

    id: UUID
    source_node: NodeResponse
    target_node: NodeResponse
    relationship_type: EdgeType
    is_required: bool
    execution_order: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EdgeUpdate(BaseModel):
    """Schema for updating an edge."""

    is_required: bool | None = None
    execution_order: int | None = None
    metadata: dict[str, Any] | None = None


class GraphResponse(BaseModel):
    """Response schema for graph traversal."""

    nodes: list[NodeResponse]
    edges: list[EdgeResponse]
    traversal_depth: int
    total_nodes: int
    total_edges: int


class GraphQueryParams(BaseModel):
    """Schema for global graph query parameters."""

    include_tasks: bool = Field(default=True, description="Include task nodes")
    include_knowledge_units: bool = Field(default=True, description="Include KU nodes")
    depth: int | None = Field(
        default=None, ge=1, le=5, description="Traversal depth limit"
    )
    max_nodes: int | None = Field(
        default=None, ge=1, le=1000, description="Maximum nodes to return"
    )


class GlobalGraphResponse(BaseModel):
    """Response schema for global graph endpoint."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
