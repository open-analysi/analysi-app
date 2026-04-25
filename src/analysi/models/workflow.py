"""
Workflow-related SQLAlchemy models for static workflow definitions.
These models represent the blueprint layer of the workflow system.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from analysi.models.task import Task

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base


class Workflow(Base):
    """
    Static workflow definition (blueprint).
    Represents a workflow template that can be executed multiple times.
    """

    __tablename__ = "workflows"

    # Primary identification
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Content Pack organization (Project Delos)
    app: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", index=True
    )

    # Basic metadata
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Schema definition
    io_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Sample data for testing - each sample can be any JSON type
    data_samples: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    # Validation status: draft (created), validated (type-checked), invalid (has errors)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")

    # Authoring information (UUID FK to users table)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        server_default="00000000-0000-0000-0000-000000000001",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Future: AI planner integration
    planner_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # Mutable workflow support
    is_ephemeral: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    nodes: Mapped[list["WorkflowNode"]] = relationship(
        "WorkflowNode", back_populates="workflow", cascade="all, delete-orphan"
    )
    edges: Mapped[list["WorkflowEdge"]] = relationship(
        "WorkflowEdge", back_populates="workflow", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Workflow(id={self.id}, name='{self.name}', tenant='{self.tenant_id}')>"
        )


class WorkflowNode(Base):
    """
    Node definition within a workflow.
    Represents a unit of work (task, transformation, foreach, etc.).
    """

    __tablename__ = "workflow_nodes"

    # Primary identification
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Node identification within workflow
    node_id: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # e.g., "n-start", "n-geoip"

    # Type propagation - mark start nodes
    is_start_node: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Node type and metadata
    kind: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # task, transformation, foreach
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Type-specific references (only one should be populated based on kind)
    # task_id references component.id (the external-facing ID for tasks)
    # No ondelete - task deletion should be blocked if workflows reference it
    task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("components.id"), nullable=True
    )
    node_template_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("node_templates.id"),
        nullable=True,
    )

    # Foreach-specific configuration
    foreach_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )

    # Schema definitions
    schemas: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="nodes")
    node_template: Mapped[Optional["NodeTemplate"]] = relationship("NodeTemplate")
    # task_id references component.id, join to Task via Task.component_id
    task: Mapped[Optional["Task"]] = relationship(
        "Task",
        foreign_keys="[WorkflowNode.task_id]",
        primaryjoin="WorkflowNode.task_id == Task.component_id",
    )

    # Constraint: unique node_id per workflow
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "node_id", name="uq_workflow_nodes_workflow_node_id"
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkflowNode(id={self.id}, node_id='{self.node_id}', kind='{self.kind}')>"


class WorkflowEdge(Base):
    """
    Edge definition connecting workflow nodes.
    Represents data flow between nodes.
    """

    __tablename__ = "workflow_edges"

    # Primary identification
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Edge identification within workflow
    edge_id: Mapped[str] = mapped_column(Text, nullable=False)  # e.g., "e1", "e2"

    # Connection specification
    from_node_uuid: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workflow_nodes.id"), nullable=False
    )
    to_node_uuid: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("workflow_nodes.id"), nullable=False
    )

    # Optional metadata
    alias: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="edges")
    from_node: Mapped["WorkflowNode"] = relationship(
        "WorkflowNode", foreign_keys=[from_node_uuid]
    )
    to_node: Mapped["WorkflowNode"] = relationship(
        "WorkflowNode", foreign_keys=[to_node_uuid]
    )

    # Constraint: unique edge_id per workflow
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "edge_id", name="uq_workflow_edges_workflow_edge_id"
        ),
    )

    def __repr__(self) -> str:
        return f"<WorkflowEdge(id={self.id}, edge_id='{self.edge_id}')>"


class NodeTemplate(Base):
    """
    Reusable code templates for transformation nodes.
    Supports versioning through resource_id grouping.
    System templates have tenant_id=NULL and are accessible to all tenants.
    """

    __tablename__ = "node_templates"

    # Primary identification
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    resource_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )  # Groups versions

    # Tenant ownership (NULL for system templates)
    tenant_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Template metadata
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Type inference classification
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    # Schema definitions
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Template code
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="python")

    # Template type and status
    type: Mapped[str] = mapped_column(
        Text, nullable=False, default="static"
    )  # static or dynamic
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revision_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Note: Unique constraint for only one enabled version per resource_id
    # is handled in the database migration (partial unique index)
    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<NodeTemplate(id={self.id}, name='{self.name}', version={self.revision_num})>"


def validate_workflow_dag(nodes: list[dict], edges: list[dict]) -> bool:
    """
    Validate that workflow forms a valid DAG (no cycles).

    Args:
        nodes: List of node definitions
        edges: List of edge definitions

    Returns:
        True if valid DAG, False if cycles detected

    Raises:
        ValueError: If invalid node/edge references
    """
    if not nodes:
        return True  # Empty workflow is valid

    # Extract node IDs
    node_ids = {node.get("node_id") for node in nodes}
    if None in node_ids:
        raise ValueError("All nodes must have node_id")

    # Validate edge references
    for edge in edges:
        from_id = edge.get("from_node_id")
        to_id = edge.get("to_node_id")

        if from_id not in node_ids:
            raise ValueError(f"Edge references non-existent node: {from_id}")
        if to_id not in node_ids:
            raise ValueError(f"Edge references non-existent node: {to_id}")

    # Check for cycles using DFS
    # Build adjacency list
    graph = {node_id: [] for node_id in node_ids}
    for edge in edges:
        from_id = edge.get("from_node_id")
        to_id = edge.get("to_node_id")
        graph[from_id].append(to_id)

    # DFS to detect cycles
    visited = set()
    rec_stack = set()

    def has_cycle(node):
        visited.add(node)
        rec_stack.add(node)

        for neighbor in graph[node]:
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True

        rec_stack.remove(node)
        return False

    # Check all nodes for cycles
    for node_id in node_ids:
        if node_id not in visited and has_cycle(node_id):
            return False  # Cycle detected

    return True


def validate_workflow_schema(workflow_data: dict) -> bool:  # noqa: C901
    """
    Validate workflow JSON schema according to Rodos requirements.

    Enforces:
    - Exactly one entry node (is_start_node=True)
    - Entry node must be transformation with identity template
    - Input schema must define properties (no bare {"type": "object"})
    - data_samples must be provided and validate against input schema

    Args:
        workflow_data: Complete workflow definition

    Returns:
        True if schema is valid

    Raises:
        ValueError: If schema validation fails
    """
    # Required fields
    required_fields = ["name", "io_schema", "data_samples"]
    for field in required_fields:
        if field not in workflow_data:
            raise ValueError(f"Missing required field: {field}")

    # Validate types
    if not isinstance(workflow_data["name"], str) or not workflow_data["name"].strip():
        raise ValueError("Name must be a non-empty string")

    if not isinstance(workflow_data["io_schema"], dict):
        raise ValueError("io_schema must be a dictionary")

    # Validate io_schema structure
    io_schema = workflow_data["io_schema"]
    if "input" not in io_schema or "output" not in io_schema:
        raise ValueError("io_schema must contain 'input' and 'output' schemas")

    # Require input schema to define properties
    input_schema = io_schema["input"]
    if not isinstance(input_schema, dict):
        raise ValueError("io_schema.input must be a JSON Schema object")

    if input_schema.get("type") != "object":
        raise ValueError("io_schema.input must have type 'object'")

    if "properties" not in input_schema or not input_schema["properties"]:
        raise ValueError(
            "io_schema.input must define 'properties'. "
            "Bare {'type': 'object'} is not allowed. "
            "Example: {'type': 'object', 'properties': {'ip': {'type': 'string'}}, 'required': ['ip']}"
        )

    # Validate data_samples
    data_samples = workflow_data.get("data_samples")
    if data_samples is None or not isinstance(data_samples, list):
        raise ValueError("data_samples must be a non-empty list of sample inputs")

    if len(data_samples) == 0:
        raise ValueError("data_samples must contain at least one sample input")

    # Validate data_samples against input schema using jsonschema library
    try:
        from jsonschema import validate as json_validate
        from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

        for i, sample in enumerate(data_samples):
            # Extract actual input from envelope format if present
            # Envelope format: {name, input, description, expected_output}
            actual_sample = sample
            if isinstance(sample, dict) and "input" in sample:
                # Check if this looks like the envelope format
                envelope_keys = {"name", "input", "description", "expected_output"}
                if set(sample.keys()).issubset(envelope_keys):
                    actual_sample = sample["input"]

            try:
                json_validate(instance=actual_sample, schema=input_schema)
            except JsonSchemaValidationError as e:
                # Provide helpful error message indicating whether it's envelope or raw
                sample_type = "envelope input" if actual_sample != sample else "sample"
                raise ValueError(
                    f"data_samples[{i}] does not match io_schema.input: {e.message}. "
                    f"Validating {sample_type} field."
                )
    except ImportError:
        # jsonschema not available - skip validation
        pass

    # Validate nodes and edges if present
    nodes = workflow_data.get("nodes", [])
    edges = workflow_data.get("edges", [])

    if not isinstance(nodes, list):
        raise ValueError("nodes must be a list")

    if len(nodes) == 0:
        raise ValueError("workflow must have at least one node")

    if not isinstance(edges, list):
        raise ValueError("edges must be a list")

    # Validate exactly one entry node
    start_nodes = []
    for node in nodes:
        if node.get("is_start_node", False):
            start_nodes.append(node)

    if len(start_nodes) == 0:
        raise ValueError(
            "Workflow must have exactly one entry node with is_start_node=True. "
            "The entry node distributes workflow input to downstream nodes."
        )

    if len(start_nodes) > 1:
        start_node_ids = [n["node_id"] for n in start_nodes]
        raise ValueError(
            f"Workflow must have exactly one entry node, found {len(start_nodes)}: {start_node_ids}. "
            "Only one node can have is_start_node=True."
        )

    # Validate entry node is transformation or task type
    entry_node = start_nodes[0]
    entry_kind = entry_node.get("kind")
    if entry_kind not in ["transformation", "task"]:
        raise ValueError(
            f"Entry node '{entry_node['node_id']}' must be kind='transformation' or kind='task'. "
            f"Found kind='{entry_kind}'. "
            "The entry node receives workflow input and distributes it to downstream nodes."
        )

    # Entry node must have appropriate ID based on kind
    if entry_kind == "transformation":
        if not entry_node.get("node_template_id"):
            raise ValueError(
                f"Entry node '{entry_node['node_id']}' with kind='transformation' must reference a NodeTemplate via node_template_id. "
                "Use a passthrough/identity template to distribute workflow input."
            )
    elif entry_kind == "task" and not entry_node.get("task_id"):
        raise ValueError(
            f"Entry node '{entry_node['node_id']}' with kind='task' must reference a Task via task_id."
        )

    # Validate node schema
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"Node {i} must be a dictionary")

        if "node_id" not in node:
            raise ValueError(f"Node {i} missing node_id")

        if "kind" not in node:
            raise ValueError(f"Node {i} missing kind")

        if node["kind"] not in ["task", "transformation", "foreach"]:
            raise ValueError(f"Node {i} has invalid kind: {node['kind']}")

    return True


def enrich_workflow_json(workflow: Workflow) -> dict:
    """
    Enrich workflow with template code and task details.

    Args:
        workflow: Workflow instance with loaded relationships

    Returns:
        Complete workflow JSON with joined data
    """
    # Build nodes list
    enriched_nodes: list[dict] = []
    for node in workflow.nodes:
        node_data = {
            "id": str(node.id),
            "node_id": node.node_id,
            "kind": node.kind,
            "name": node.name,
            "task_id": str(node.task_id) if node.task_id else None,
            "node_template_id": (
                str(node.node_template_id) if node.node_template_id else None
            ),
            "foreach_config": node.foreach_config,
            "schemas": node.schemas,
            "is_start_node": node.is_start_node,
            "created_at": node.created_at.isoformat(),
        }

        # Add template code if available
        if node.node_template:
            node_data["template_code"] = node.node_template.code
            node_data["template_language"] = node.node_template.language

        enriched_nodes.append(node_data)

    # Build edges list
    enriched_edges: list[dict] = []
    for edge in workflow.edges:
        edge_data = {
            "id": str(edge.id),
            "edge_id": edge.edge_id,
            "from_node_uuid": str(edge.from_node_uuid),
            "to_node_uuid": str(edge.to_node_uuid),
            "alias": edge.alias,
            "created_at": edge.created_at.isoformat(),
        }
        enriched_edges.append(edge_data)

    # Base workflow data
    result = {
        "id": str(workflow.id),
        "tenant_id": workflow.tenant_id,
        "name": workflow.name,
        "description": workflow.description,
        "is_dynamic": workflow.is_dynamic,
        "io_schema": workflow.io_schema,
        "data_samples": workflow.data_samples,
        "status": workflow.status,
        "created_by": str(workflow.created_by),
        "created_at": workflow.created_at.isoformat(),
        "planner_id": str(workflow.planner_id) if workflow.planner_id else None,
        "nodes": enriched_nodes,
        "edges": enriched_edges,
    }

    return result


def enrich_workflow_json_slim(workflow: Workflow) -> dict:
    """
    Enrich workflow with minimal verbosity for LLM consumption.

    Slim mode removes:
    - Timestamps (created_at fields)
    - Database UUIDs (id fields for nodes/edges)
    - Template code
    - Verbose schemas (keeps only kind information)

    Args:
        workflow: Workflow instance with loaded relationships

    Returns:
        Slim workflow JSON optimized for readability
    """
    from analysi.mcp.tools.workflow_tools import _get_node_identifier

    # Slim nodes - only essential fields
    slim_nodes: list[dict] = []
    for node in workflow.nodes:
        node_data: dict = {
            "node_id": node.node_id,
            "kind": node.kind,
            "name": node.name,
        }

        # Add human-readable identifier
        identifier = _get_node_identifier(node)
        if identifier != node.node_id:
            node_data["identifier"] = identifier

        slim_nodes.append(node_data)

    # Slim edges - logical IDs only (no database UUIDs)
    slim_edges: list[dict] = []
    for edge in workflow.edges:
        # Find source and target node_ids
        from_node = next(
            (n for n in workflow.nodes if n.id == edge.from_node_uuid), None
        )
        to_node = next((n for n in workflow.nodes if n.id == edge.to_node_uuid), None)

        edge_data: dict = {
            "from": from_node.node_id if from_node else str(edge.from_node_uuid),
            "to": to_node.node_id if to_node else str(edge.to_node_uuid),
        }

        if edge.alias:
            edge_data["alias"] = edge.alias

        slim_edges.append(edge_data)

    # Base workflow data (keep essential metadata)
    result: dict = {
        "id": str(workflow.id),
        "tenant_id": workflow.tenant_id,
        "name": workflow.name,
        "description": workflow.description,
        "status": workflow.status,
        "nodes": slim_nodes,
        "edges": slim_edges,
    }

    # Include io_schema and data_samples for workflow configuration
    if workflow.io_schema:
        result["io_schema"] = workflow.io_schema
    if workflow.data_samples:
        result["data_samples"] = workflow.data_samples

    return result
