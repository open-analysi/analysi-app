+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Initial spec"
+++

# Activity Audit Trail

## Overview

The Activity Audit Trail provides comprehensive logging of user and system actions for compliance, debugging, and analytics. It tracks who did what, when, and from where.

## Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | UUID | Yes | Unique event ID (auto-generated) |
| `created_at` | Timestamp (TZ) | Yes | When the event occurred (partition key) |
| `tenant_id` | VARCHAR(255) | Yes | Multi-tenant isolation |
| `actor_id` | VARCHAR(255) | Yes | **WHO** performed the action |
| `actor_type` | VARCHAR(50) | Yes | **Type of actor** |
| `source` | VARCHAR(50) | No | **WHERE** the action originated |
| `action` | VARCHAR(100) | Yes | **WHAT** happened |
| `resource_type` | VARCHAR(100) | No | Type of resource affected |
| `resource_id` | VARCHAR(255) | No | ID of the affected resource |
| `details` | JSONB | No | Additional structured data |
| `ip_address` | VARCHAR(45) | No | Client IP (IPv4/IPv6) |
| `user_agent` | TEXT | No | Browser/client info |
| `request_id` | VARCHAR(100) | No | Correlation ID for tracing |

## Field Details

### actor_id
The identifier of who performed the action:
- User email (e.g., `user@example.com`)
- `mcp_user` for MCP tool operations
- API key name for API key authenticated requests

### actor_type
Enum indicating the type of actor:
| Value | Description |
|-------|-------------|
| `user` | Human user via UI or API |
| `system` | System/automated operation (MCP tools, background jobs) |
| `api_key` | External API client using API key auth |
| `workflow` | Action triggered by workflow execution |

### source
Enum indicating which subsystem generated the audit log:
| Value | Description |
|-------|-------------|
| `rest_api` | REST API endpoint (direct API calls) |
| `mcp` | MCP Server tools (Claude Code, AI clients) |
| `ui` | Frontend UI application |
| `internal` | Internal system operations |
| `unknown` | Source not specified (legacy) |

### action
Action naming convention: `resource.verb`

| Action | Description |
|--------|-------------|
| `task.create` | New task created |
| `task.update` | Task modified |
| `task.delete` | Task deleted |
| `workflow.create` | New workflow created |
| `workflow.delete` | Workflow deleted |

### details
JSONB field for action-specific metadata:

```json
// task.create
{
  "task_name": "IP Reputation Check",
  "cy_name": "ip_reputation_check"
}

// task.update
{
  "task_name": "IP Reputation Check",
  "updated_fields": ["description", "script"]
}

// workflow.create (via compose_workflow)
{
  "workflow_name": "Alert Triage Pipeline",
  "source": "compose_workflow"
}
```

## Example Scenarios

### User creates task via UI
```json
{
  "actor_id": "user@example.com",
  "actor_type": "user",
  "source": "rest_api",
  "action": "task.create",
  "resource_type": "task",
  "resource_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": {"task_name": "My Task", "cy_name": "my_task"}
}
```

### Claude Code creates workflow via MCP
```json
{
  "actor_id": "mcp_user",
  "actor_type": "system",
  "source": "mcp",
  "action": "workflow.create",
  "resource_type": "workflow",
  "resource_id": "workflow-uuid",
  "details": {"workflow_name": "Alert Pipeline"}
}
```

## REST API

### List Audit Events
```
GET /{tenant}/audit-trail
```

Query parameters:
- `actor_id` - Filter by actor
- `source` - Filter by source (`rest_api`, `mcp`, `ui`, `internal`)
- `action` - Filter by action (supports prefix match with `%`)
- `resource_type` - Filter by resource type
- `resource_id` - Filter by resource ID
- `from_date` - Start of date range (inclusive)
- `to_date` - End of date range (exclusive)
- `limit` - Page size (max 500, default 50)
- `offset` - Starting position

### Get Single Event
```
GET /{tenant}/audit-trail/{event_id}
```

## Database Notes

- Table is **partitioned by `created_at`** for time-series performance
- Indexed on: `tenant_id`, `actor_id`, `action`, `source`, `created_at`, `(resource_type, resource_id)`
- Events are **immutable** (append-only)

## Implementation Notes

Audit logging is implemented at the **service layer** for DRY:
- `TaskService._log_audit()` - logs task operations
- `WorkflowService._log_audit()` - logs workflow operations
- `ComposerWorkflowBuilder._log_audit()` - logs compose_workflow operations

Callers pass `AuditContext` which contains actor and source information:
- REST routers set `source="rest_api"`
- MCP tools set `source="mcp"`
- UI should set `source="ui"` when implemented
