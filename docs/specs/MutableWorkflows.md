+++
version = "1.0"
date = "2025-11-17"
status = "active"

[[changelog]]
version = "1.0"
date = "2025-11-17"
summary = "Mutable workflow editing"
+++

# Mutable Workflows Specification

**Version**: 1.0
**Status**: Planned
**Supersedes**: Immutability design in `IntroducingWorkflows_v1.md`

## Summary

Transform workflows from immutable blueprints to fully mutable DAGs with:
1. Fine-grained mutation APIs (add/remove nodes/edges)
2. Ad-hoc workflow execution with ephemeral storage
3. Example management APIs for workflows and tasks

## Design Principles

- **Mutability**: Fine-grained node/edge mutations (no auto-validation - supports UI construction)
- **On-demand Validation**: Validate explicitly or at execution time (not after every mutation)
- **Ad-hoc Execution**: Run workflows without creating named workflow; keep records for 7 days for debugging
- **Examples**: Multiple data_samples with APIs to manage individual examples (like tasks)

---

## Database Schema Changes

### Migration V067: Mutable workflow support

**File**: `migrations/flyway/sql/V067__mutable_workflows.sql`

```sql
-- Add ephemeral workflow columns
ALTER TABLE workflows ADD COLUMN is_ephemeral BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE workflows ADD COLUMN expires_at TIMESTAMPTZ;
ALTER TABLE workflows ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now() NOT NULL;

-- Index for cleanup job
CREATE INDEX idx_workflows_ephemeral_expires
  ON workflows(is_ephemeral, expires_at)
  WHERE is_ephemeral = TRUE;
```

### New Workflow Fields

| Field | Type | Description |
|-------|------|-------------|
| `is_ephemeral` | BOOLEAN | True for ad-hoc workflows (auto-cleanup) |
| `expires_at` | TIMESTAMPTZ | When ephemeral workflow will be deleted |
| `updated_at` | TIMESTAMPTZ | Last modification timestamp |

---

## Workflow Mutation APIs

### Pydantic Schemas

```python
# Workflow metadata update
class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    io_schema: dict | None = None
    data_samples: list | None = None

# Node operations
class AddNodeRequest(BaseModel):
    node_id: str
    kind: str  # task, transformation, foreach
    name: str
    is_start_node: bool = False
    task_id: UUID | None = None
    node_template_id: UUID | None = None
    foreach_config: dict | None = None
    schemas: dict

class WorkflowNodeUpdate(BaseModel):
    name: str | None = None
    schemas: dict | None = None
    task_id: UUID | None = None
    node_template_id: UUID | None = None

# Edge operations
class AddEdgeRequest(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    alias: str | None = None

# Validation response (on-demand only)
class ValidationResult(BaseModel):
    valid: bool
    workflow_status: str  # draft, validated, invalid
    dag_errors: list[str] = []      # Cycle detection, connectivity
    type_errors: list[str] = []     # Schema mismatches
    warnings: list[str] = []        # Non-blocking issues
```

### REST API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| PATCH | `/{tenant}/workflows/{workflow_id}` | Update workflow metadata |
| POST | `/{tenant}/workflows/{workflow_id}/nodes` | Add node |
| PATCH | `/{tenant}/workflows/{workflow_id}/nodes/{node_id}` | Update node |
| DELETE | `/{tenant}/workflows/{workflow_id}/nodes/{node_id}` | Remove node (cascades edges) |
| POST | `/{tenant}/workflows/{workflow_id}/edges` | Add edge |
| DELETE | `/{tenant}/workflows/{workflow_id}/edges/{edge_id}` | Remove edge |
| POST | `/{tenant}/workflows/{workflow_id}/validate` | On-demand validation (DAG + types) |

### Validation Strategy

- Mutations succeed even if graph is incomplete/invalid (supports UI building)
- Validation is **on-demand**: user explicitly calls `/validate` endpoint
- Validation runs **automatically at execution time** - can't run invalid workflow
- `workflow.status` stays `draft` until explicitly validated

### Service Layer Methods

```python
async def update_workflow_metadata(tenant_id, workflow_id, update_data) -> Workflow
async def add_node(tenant_id, workflow_id, node_request) -> WorkflowNode
async def update_node(tenant_id, workflow_id, node_id, update_data) -> WorkflowNode
async def remove_node(tenant_id, workflow_id, node_id) -> bool  # cascade removes edges
async def add_edge(tenant_id, workflow_id, edge_request) -> WorkflowEdge
async def remove_edge(tenant_id, workflow_id, edge_id) -> bool

# On-demand validation (called explicitly or at execution time)
async def validate_workflow(tenant_id, workflow_id) -> ValidationResult
```

---

## Ad-hoc Workflow Execution

### Overview

Ad-hoc execution allows running a workflow composition without creating a named workflow. The workflow is stored as "ephemeral" and automatically cleaned up after 7 days.

### Schemas

```python
class WorkflowAdhocExecuteRequest(BaseModel):
    composition: list  # Same format as compose_workflow
    input_data: Any = None
    timeout_seconds: int = 300

class WorkflowAdhocExecuteResponse(BaseModel):
    workflow_run_id: UUID
    workflow_id: UUID  # Ephemeral workflow for debugging
    status: str
    output: Any | None
    error: str | None
    execution_time_ms: int
    expires_at: datetime
```

### REST Endpoint

```
POST /{tenant}/workflows/execute-adhoc
```

### Flow

1. Use WorkflowComposerService to build workflow
2. Set `is_ephemeral=True`, `expires_at=now()+7days`
3. Execute using existing `execute_workflow`
4. Return result with workflow_run_id and ephemeral workflow_id

### Cleanup Job

**File**: `src/analysi/jobs/workflow_cleanup.py`

```python
async def cleanup_expired_workflows(ctx: dict) -> dict:
    """Delete workflows where is_ephemeral=TRUE AND expires_at < now()"""
```

Runs as ARQ cron job every 6 hours.

---

## Example Management APIs

### Data Sample Envelope Format

```python
class DataSampleEnvelope(BaseModel):
    name: str
    input: Any
    description: str | None = None
    expected_output: Any | None = None
```

### REST Endpoints

**Workflows**: `/{tenant}/workflows/{workflow_id}/examples`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/{workflow_id}/examples` | List examples |
| POST | `/{workflow_id}/examples` | Add example |
| PUT | `/{workflow_id}/examples/{index}` | Update example |
| DELETE | `/{workflow_id}/examples/{index}` | Remove example |

**Tasks**: Same pattern at `/{tenant}/tasks/{task_id}/examples`

---

## MCP Tools

### Mutation Tools

| Tool | Status | Description |
|------|--------|-------------|
| `add_node()` | Enable | Currently returns error, implement |
| `add_edge()` | Enable | Currently returns error, implement |
| `remove_node()` | New | Remove node and cascade edges |
| `remove_edge()` | New | Remove edge |
| `update_workflow()` | New | Update metadata |
| `update_node()` | New | Update node properties |

### Execution Tools (REST exists, MCP missing)

| Tool | Description |
|------|-------------|
| `delete_workflow()` | Delete workflow by ID |
| `start_workflow()` | Non-blocking start, returns workflow_run_id |
| `get_workflow_run_status()` | Lightweight polling |
| `get_workflow_run()` | Full details with output |
| `list_workflow_runs()` | Execution history |
| `execute_workflow_adhoc()` | Execute without creating named workflow |

### Example Management Tools

- `list_workflow_examples(workflow_id)`
- `add_workflow_example(workflow_id, name, input, description?, expected_output?)`
- `update_workflow_example(workflow_id, index, ...)`
- `remove_workflow_example(workflow_id, index)`

Same tools for tasks in `task_tools.py`.

---

## Implementation Notes

- **NO auto-validation** - mutations succeed even with incomplete graphs (supports UI building)
- Validation is **on-demand** via explicit `/validate` endpoint or **at execution time**
- Removing a node cascades to remove connected edges
- Ephemeral workflows filtered out by default in list APIs
- Task example APIs mirror workflow example APIs exactly
- Workflows start in `draft` status, move to `validated`/`invalid` after explicit validation

## Related Documents

- `IntroducingWorkflows_v2.md` - Core workflow model (updated to reference this spec)
- `TypedWorkflows_v1.md` - Type validation system
- `AutomatedWorkflowBuilder_v1.md` - Project Kea workflow generation
