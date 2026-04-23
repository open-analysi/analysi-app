+++
version = "1.0"
date = "2026-03-27"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-03-27"
summary = "Actions + schedules (Project Symi)"
+++

# Unified Scheduler and Actions — v1

<!-- Project Symi -->

## Overview

Deprecates the **connector** concept from Integrations and replaces it with two cleaner abstractions:

1. **Unified Actions**: Everything an integration can do (health checks, alert pulls, enrichment, containment) is an **action**. The `type: "connector" | "tool"` distinction is removed. Actions are callable from Cy scripts via `app::{integration}::{action}(...)`.

2. **Generic Scheduler**: Any Task or Workflow can run on a schedule. The integration-specific `IntegrationSchedule` table is replaced by a generic `schedules` table. Alert ingestion, health checks, and recurring automations all use the same scheduling infrastructure.

Additionally, alert ingestion is promoted from an opaque connector side-effect to an **explicit Task** with a visible Cy script. Users can see and modify how alerts are pulled, normalized, and persisted.

```
  Before (Connectors)                        After (Symi)
  ───────────────────                        ────────────────

  Integration                                Integration
  ├── Connectors                             ├── Actions (unified)
  │   ├── pull_alerts (type: connector)      │   ├── pull_alerts
  │   ├── health_check (type: connector)     │   ├── alerts_to_ocsf
  │   └── ...                                │   ├── health_check
  ├── Tools                                  │   ├── update_notable
  │   ├── update_notable (type: tool)        │   └── ...
  │   └── ...                                ├── Managed Tasks (auto-created)
  └── IntegrationSchedule                    │   ├── "Pull alerts from Splunk Prod"
      └── (connector-specific)               │   └── "Health check for Splunk Prod"
                                             └── Schedule (generic, targets any Task or Workflow)
```

**Core insight**: Connectors were doing two unrelated things — defining executable actions and scheduling them. By splitting these concerns, we get actions that are universally callable (from Cy, from workflows, from the API) and a scheduler that works for any Task, not just integration connectors.

---

## Scope

### In Scope (v1)

- `schedules` table replacing `integration_schedules` (targets Tasks or Workflows)
- `job_runs` table replacing `integration_runs` (audit trail for scheduled executions)
- `task_checkpoints` table for cursor/checkpoint management
- `TaskRun.run_context` field: `analysis | scheduled | ad_hoc`
- Unified action model in manifests (drop `type` and `purpose` fields)
- `AlertSource` archetype with required `pull_alerts` + `alerts_to_ocsf` actions
- Task factory: auto-create alert ingestion + health check Tasks on integration setup
- Platform Cy functions: `ingest_alerts()`, `get_checkpoint()`, `set_checkpoint()`
- Managed resources API: `/integrations/{id}/managed/{key}/...`
- Default task run filtering by `run_context`
- Flyway migration for schema changes + data migration
- Scheduler handles both Tasks and Workflows as targets (`execute_task_run` or `execute_workflow_run`)
- Convenience schedule endpoints on both Tasks (`/tasks/{id}/schedule`) and Workflows (`/workflows/{id}/schedule`)
- Integration worker scheduler cron enqueues to Alert Analysis worker for execution

### Out of Scope (v1)

- Full OCSF schema definition (parallel project, Symi only provides the `alerts_to_ocsf` action hook)
- Knowledge building tasks (content pack concern, not integration lifecycle)
- UI implementation (API only; UI is a follow-up)
- Cron expressions in `schedule_type` (v1 supports `every` intervals only; cron is future)

---

## Architecture

### Execution Contexts

Task runs originate from three distinct paths. Each has its own lineage tracking:

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        TaskRun.run_context                         │
  ├─────────────┬───────────────────────┬───────────────────────────────┤
  │  "analysis" │     "scheduled"       │         "ad_hoc"             │
  │             │                       │                              │
  │  Alert      │  Schedule             │  User                        │
  │    ↓        │    ↓                  │    ↓                         │
  │  Control    │  Scheduler cron       │  POST /tasks/{id}/runs       │
  │  Event      │    ↓                  │    ↓                         │
  │    ↓        │  JobRun               │  TaskRun                     │
  │  Workflow   │    ↓                  │  (standalone)                │
  │  Run        │  TaskRun              │                              │
  │    ↓        │                       │                              │
  │  Node       │  Lineage:             │  Lineage:                    │
  │  Instance   │  Schedule → JobRun    │  none (direct)               │
  │    ↓        │    → TaskRun          │                              │
  │  TaskRun    │                       │                              │
  │             │                       │                              │
  │  Lineage:   │                       │                              │
  │  Alert →    │                       │                              │
  │  Analysis → │                       │                              │
  │  Workflow → │                       │                              │
  │  Node →     │                       │                              │
  │  TaskRun    │                       │                              │
  └─────────────┴───────────────────────┴───────────────────────────────┘
```

### Integration Setup Flow

When an integration with the `AlertSource` archetype is configured:

```
  POST /v1/{tenant}/integrations
    body: { type: "splunk", name: "Splunk Prod", ... }

  IntegrationService.create_integration()
    │
    ├── 1. Validate manifest, store Integration record
    │
    ├── 2. Detect archetypes from manifest
    │      └── "AlertSource" found → requires pull_alerts + alerts_to_ocsf
    │
    ├── 3. Task factory: create_alert_ingestion_task()
    │      └── Task(name="Pull alerts from Splunk Prod",
    │              script="...", origin_type="system",
    │              integration_id="splunk-prod")
    │
    ├── 4. Task factory: create_health_check_task()
    │      └── Task(name="Health check for Splunk Prod",
    │              script="...", origin_type="system",
    │              integration_id="splunk-prod")
    │
    ├── 5. Create Schedule for alert ingestion (enabled=false)
    │      └── Schedule(target_type="task", target_id=task.component_id,
    │              schedule_type="every", schedule_value="5m",
    │              origin_type="system", integration_id="splunk-prod")
    │
    └── 6. Create Schedule for health check (enabled=false)
           └── Schedule(target_type="task", target_id=task.component_id,
                   schedule_type="every", schedule_value="5m",
                   origin_type="system", integration_id="splunk-prod")
```

Schedules start `enabled=false`. The admin reviews configuration, adjusts intervals if needed, then enables via the Integration management API.

### Scheduled Execution Flow

```
  schedule_executor (ARQ cron, every 30s)
    │
    ├── SELECT * FROM schedules WHERE enabled=true AND next_run_at <= now()
    │   FOR UPDATE SKIP LOCKED
    │
    ├── For each due schedule:
    │   │
    │   ├── INSERT INTO job_runs (schedule_id, target_type, target_id, ...)
    │   │
    │   ├── Create TaskRun (run_context="scheduled")
    │   │
    │   ├── Enqueue ARQ job: execute_task_run(task_run_id)
    │   │
    │   └── UPDATE schedules SET last_run_at=now(),
    │         next_run_at=now()+interval
    │
    └── COMMIT
```

### Alert Ingestion Task Execution

```
  execute_task_run(task_run_id)
    │
    ├── Load Task, resolve integration_id="splunk-prod"
    │
    ├── Execute Cy script:
    │   │
    │   │  start_time = get_checkpoint("last_pull") or default_lookback()
    │   │  end_time = now()
    │   │
    │   │  raw_alerts = app::splunk::pull_alerts(start_time, end_time)
    │   │  ocsf_alerts = app::splunk::alerts_to_ocsf(raw_alerts)
    │   │  result = ingest_alerts(ocsf_alerts)
    │   │
    │   │  set_checkpoint("last_pull", end_time)
    │   │  return result
    │   │
    │   ├── app::splunk::pull_alerts → IntegrationLoader → PullAlertsAction
    │   │   └── Queries Splunk, returns raw events (tenacity retry on 5xx/429)
    │   │
    │   ├── app::splunk::alerts_to_ocsf → IntegrationLoader → AlertsToOcsfAction
    │   │   └── Splunk-specific normalization to OCSF schema
    │   │
    │   ├── ingest_alerts() → platform Cy function
    │   │   ├── Deduplicates (content hash)
    │   │   ├── Persists to alerts table
    │   │   ├── Emits control events: "alert:ingested" per alert
    │   │   └── Returns {created: N, duplicates: M, errors: E}
    │   │
    │   ├── get_checkpoint() / set_checkpoint() → platform Cy functions
    │   │   └── Reads/writes task_checkpoints table
    │   │
    │   └── Checkpoint only advances if script completes (no set_checkpoint on failure)
    │
    ├── TaskRun.status = "completed", output = {created: 4, duplicates: 1}
    │
    └── JobRun.status mirrors TaskRun.status
```

---

## Database

### `schedules` Table (replaces `integration_schedules`)

```sql
CREATE TABLE schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(255) NOT NULL,

    -- What to run
    target_type     VARCHAR(20)  NOT NULL,  -- "task" | "workflow"
    target_id       UUID         NOT NULL,  -- component_id (task) or workflow id

    -- When to run
    schedule_type   VARCHAR(20)  NOT NULL,  -- "every" (v1), "cron" (future)
    schedule_value  VARCHAR(100) NOT NULL,  -- "60s", "5m", "1h"
    timezone        VARCHAR(50)  NOT NULL DEFAULT 'UTC',
    enabled         BOOLEAN      NOT NULL DEFAULT false,

    -- Parameters passed to the target as input
    params          JSONB,

    -- Provenance
    origin_type     VARCHAR(20)  NOT NULL DEFAULT 'user',  -- "system" | "user"
    integration_id  VARCHAR(255),  -- non-null for system-managed schedules

    -- Scheduling state
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_schedules_tenant_enabled ON schedules (tenant_id, enabled)
    WHERE enabled = true;
CREATE INDEX idx_schedules_next_run ON schedules (next_run_at)
    WHERE enabled = true;
CREATE INDEX idx_schedules_integration ON schedules (tenant_id, integration_id)
    WHERE integration_id IS NOT NULL;
```

Not partitioned — row count is low (tens to hundreds per tenant, not thousands).

### `job_runs` Table (replaces `integration_runs`)

```sql
CREATE TABLE job_runs (
    id              UUID         NOT NULL DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    tenant_id       VARCHAR(255) NOT NULL,
    schedule_id     UUID         REFERENCES schedules(id) ON DELETE SET NULL,

    -- What was executed
    target_type     VARCHAR(20)  NOT NULL,  -- "task" | "workflow"
    target_id       UUID         NOT NULL,
    task_run_id     UUID,          -- FK to task_runs.id (when target_type="task")
    workflow_run_id UUID,          -- FK to workflow_runs.id (when target_type="workflow")

    -- Integration context (nullable — only for integration-related runs)
    integration_id  VARCHAR(255),
    action_id       VARCHAR(100),  -- which action was invoked (for audit)

    -- Status (mirrors the target run status)
    status          VARCHAR(50)  NOT NULL DEFAULT 'pending',
    -- pending | running | completed | failed | cancelled

    -- Timing
    triggered_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    -- Job tracking (Project Leros)
    job_tracking    JSONB        NOT NULL DEFAULT '{}',

    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
```

Partitioned monthly by `created_at` (same pattern as `integration_runs`).

### `task_checkpoints` Table

```sql
CREATE TABLE task_checkpoints (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   VARCHAR(255) NOT NULL,
    task_id     UUID         NOT NULL,  -- component_id
    key         VARCHAR(255) NOT NULL,
    value       JSONB        NOT NULL,  -- flexible: timestamps, offsets, cursors
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    UNIQUE (tenant_id, task_id, key)
);
```

Not partitioned — low row count (one row per checkpoint per task).

### `TaskRun` Additions

```sql
ALTER TABLE task_runs
    ADD COLUMN run_context VARCHAR(20) NOT NULL DEFAULT 'ad_hoc';
    -- "analysis" | "scheduled" | "ad_hoc"
```

Backfill strategy:
- Existing rows with `workflow_run_id IS NOT NULL` → `run_context = 'analysis'`
- All others → `run_context = 'ad_hoc'`

### `Task` Additions

```sql
ALTER TABLE tasks
    ADD COLUMN integration_id VARCHAR(255),  -- links system tasks to their integration
    ADD COLUMN origin_type    VARCHAR(20) NOT NULL DEFAULT 'user';
    -- "system" | "user" | "pack"
```

### Migration: `integration_schedules` → `schedules`

```sql
-- Migrate existing schedules
INSERT INTO schedules (
    id, tenant_id, target_type, target_id,
    schedule_type, schedule_value, timezone, enabled,
    params, origin_type, integration_id,
    next_run_at, last_run_at, created_at, updated_at
)
SELECT
    id, tenant_id, 'task', managed_task_id,  -- resolved during migration
    schedule_type, schedule_value, timezone, enabled,
    params, 'system', integration_id,
    next_run_at, last_run_at, created_at, updated_at
FROM integration_schedules;
```

The migration must first generate Tasks for existing connector-based integrations (alert ingestion, health checks), then point the migrated schedules at those Tasks. This is a multi-step migration — see Proposed Breakdown.

### Migration: `integration_runs` → `job_runs`

```sql
INSERT INTO job_runs (
    id, created_at, tenant_id, schedule_id,
    target_type, target_id, integration_id, action_id,
    status, triggered_at, started_at, completed_at, job_tracking
)
SELECT
    id, created_at, tenant_id, schedule_id,
    'task', NULL,  -- target_id backfilled per integration
    integration_id, connector,
    status, created_at, started_at, completed_at, job_tracking
FROM integration_runs;
```

---

## Manifest Changes

### Before

```json
{
  "id": "splunk",
  "name": "Splunk Enterprise",
  "archetypes": ["SIEM"],
  "archetype_mappings": {
    "SIEM": {
      "query_events": "pull_alerts"
    }
  },
  "actions": [
    {
      "id": "health_check",
      "type": "connector",
      "purpose": "health_monitoring"
    },
    {
      "id": "pull_alerts",
      "type": "connector",
      "purpose": "alert_ingestion"
    },
    {
      "id": "update_notable",
      "type": "tool",
      "cy_name": "update_notable"
    }
  ]
}
```

### After

```json
{
  "id": "splunk",
  "name": "Splunk Enterprise",
  "archetypes": ["SIEM", "AlertSource"],
  "archetype_mappings": {
    "SIEM": {
      "query_events": "pull_alerts"
    },
    "AlertSource": {
      "pull_alerts": "pull_alerts",
      "alerts_to_ocsf": "normalize_alerts"
    }
  },
  "actions": [
    {
      "id": "health_check",
      "categories": ["health_monitoring"],
      "cy_name": "health_check"
    },
    {
      "id": "pull_alerts",
      "categories": ["alert_ingestion"],
      "cy_name": "pull_alerts"
    },
    {
      "id": "normalize_alerts",
      "categories": ["normalization"],
      "cy_name": "alerts_to_ocsf"
    },
    {
      "id": "update_notable",
      "categories": ["investigation"],
      "cy_name": "update_notable"
    }
  ]
}
```

Changes:
- `type` field removed (was `"connector" | "tool"`)
- `purpose` field removed (was `"health_monitoring" | "alert_ingestion" | ...`)
- `categories` field added (list of strings, for discovery/filtering)
- All actions get `cy_name` (all actions are callable from Cy)
- `AlertSource` added to `archetypes` list
- `AlertSource` archetype mapping added with required actions

### AlertSource Archetype Contract

```python
class AlertSourceArchetype:
    """Contract for integrations that produce security alerts."""
    required_actions = ["pull_alerts", "alerts_to_ocsf"]
    optional_actions = ["get_alert_detail", "acknowledge_alert", "close_alert"]
```

Manifest validation enforces: if `AlertSource` is in `archetypes`, the `archetype_mappings.AlertSource` must include both `pull_alerts` and `alerts_to_ocsf`, and those must map to action IDs that exist in the `actions` list.

### ActionDefinition Model Update

```python
class ActionDefinition(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    categories: list[str] = []
    cy_name: str | None = None
    enabled: bool = True

    # Removed: type, purpose
```

---

## Platform Cy Functions

Three new functions injected into the Cy runtime by `DefaultTaskExecutor`:

### `ingest_alerts(alerts: list[dict]) -> dict`

Persists OCSF-formatted alerts to the database.

```python
async def ingest_alerts(alerts: list[dict]) -> dict:
    """
    Deduplicates and persists alerts. Emits "alert:ingested" control events.

    Args:
        alerts: List of OCSF-formatted alert dicts.

    Returns:
        {"created": int, "duplicates": int, "errors": int}
    """
```

Internally delegates to `AlertIngestionService.ingest_alerts()` (existing code, adapted for OCSF input). The function is only available when the Task has `integration_id` set (not exposed to arbitrary user tasks).

### `get_checkpoint(key: str) -> Any | None`

Reads a checkpoint value for the current task.

```python
async def get_checkpoint(key: str) -> Any | None:
    """
    Read a checkpoint value scoped to (tenant_id, task_id, key).
    Returns None if no checkpoint exists.
    """
```

### `set_checkpoint(key: str, value: Any) -> None`

Writes a checkpoint value for the current task.

```python
async def set_checkpoint(key: str, value: Any) -> None:
    """
    Write a checkpoint value scoped to (tenant_id, task_id, key).
    Uses UPSERT — creates or updates.
    """
```

Checkpoints are scoped to `(tenant_id, task_id, key)`. A task can have multiple checkpoints (e.g., `last_pull` for time-based cursor, `last_event_id` for ID-based cursor).

**Checkpoint + failure safety**: If a task fails mid-execution, `set_checkpoint` was never called (it runs at the end of the script), so the next scheduled run retries the same time window. This is by design — the checkpoint only advances on success.

---

## Task Factory

Python functions that generate Tasks when an integration is configured. Not a template system — the output is a real, editable Task.

### Alert Ingestion Task Factory

```python
def create_alert_ingestion_task(
    tenant_id: str,
    integration_id: str,
    integration_name: str,
    integration_type: str,
) -> Task:
    script = dedent(f"""\
        start_time = get_checkpoint("last_pull") or default_lookback()
        end_time = now()

        raw_alerts = app::{integration_type}::pull_alerts(start_time, end_time)
        ocsf_alerts = app::{integration_type}::alerts_to_ocsf(raw_alerts)
        result = ingest_alerts(ocsf_alerts)

        set_checkpoint("last_pull", end_time)
        return result
    """)

    return Task(
        name=f"Pull alerts from {integration_name}",
        directive=f"Pull and ingest alerts from {integration_name} ({integration_type})",
        script=script,
        origin_type="system",
        integration_id=integration_id,
    )
```

### Health Check Task Factory

```python
def create_health_check_task(
    tenant_id: str,
    integration_id: str,
    integration_name: str,
    integration_type: str,
) -> Task:
    script = dedent(f"""\
        return app::{integration_type}::health_check()
    """)

    return Task(
        name=f"Health check for {integration_name}",
        directive=f"Verify connectivity to {integration_name} ({integration_type})",
        script=script,
        origin_type="system",
        integration_id=integration_id,
    )
```

Health checks are regular Tasks that produce regular TaskRuns (`run_context="scheduled"`). The only special behavior: a **post-execution hook** updates `Integration.health_status` + `Integration.last_health_check_at` based on the TaskRun result.

**Health status is determined by the return value, not the TaskRun status.** This distinguishes "the integration is unhealthy" from "the check itself couldn't run":

| TaskRun Status | `result.healthy` | Integration Health | Meaning |
|---|---|---|---|
| completed | `true` | **healthy** | Check ran, integration responded correctly |
| completed | `false` | **unhealthy** | Check ran, integration reported a problem |
| failed | n/a | **unknown** | Check itself couldn't execute (platform/infra issue) |

The health check action contract: always return `{"healthy": bool, ...}`, never throw for integration-level failures. Only platform-level failures (worker crash, Cy interpreter error, action loading failure) should produce a failed TaskRun.

```python
# Health check action implementation pattern
class HealthCheckAction:
    async def execute(self, **params) -> dict:
        try:
            response = await self.client.get("/services/server/info")
            return {"healthy": True, "latency_ms": response.elapsed_ms}
        except Exception as e:
            # Integration problem — return result, don't throw
            return {"healthy": False, "error": str(e)}
```

Post-execution hook:
```python
if task_run.status == "failed":
    integration.health_status = "unknown"
elif task_run.status == "completed":
    result = task_run.output
    integration.health_status = "healthy" if result.get("healthy") else "unhealthy"
integration.last_health_check_at = utc_now()
```

---

## Integration Lifecycle

### Create Integration (with AlertSource)

```
POST /v1/{tenant}/integrations
  { "type": "splunk", "name": "Splunk Prod" }

1. Validate manifest, store Integration record
2. Detect archetypes from manifest
3. If AlertSource → call create_alert_ingestion_task()
4. Always call create_health_check_task() (all integrations get health checks)
5. Create Schedule for alert ingestion (enabled=false, schedule_value from manifest default)
6. Create Schedule for health check (enabled=false, schedule_value="300s")
7. Return Integration response with managed_resources block
```

**Credential ordering**: Credentials are configured via a separate endpoint (`POST /{id}/credentials`) after integration creation. Tasks and Schedules are created `enabled=false` — the admin configures credentials first, then enables the integration to start the schedules. The `app::splunk::pull_alerts()` call will fail gracefully (credential not found) if someone enables before configuring credentials.

### Enable Integration

```
POST /v1/{tenant}/integrations/{id}/enable

1. Set Integration.enabled = true
2. Set all system-managed Schedules for this integration to enabled=true
3. Compute next_run_at for each schedule
```

### Disable Integration

```
POST /v1/{tenant}/integrations/{id}/disable

1. Set Integration.enabled = false
2. Set all system-managed Schedules for this integration to enabled=false
3. Running TaskRuns are allowed to complete (no mid-flight cancellation)
```

### Delete Integration

```
DELETE /v1/{tenant}/integrations/{id}

1. Disable all schedules (stop future runs)
2. Soft-delete or archive managed Tasks (historical JobRuns/TaskRuns reference them)
3. Delete Schedules
4. Delete Integration record
5. Alerts already ingested are untouched
```

---

## REST API

### Managed Resources (new endpoints)

Convenience endpoints scoped to an integration. Delegate to canonical Task/Schedule APIs internally.

```
# View managed resources for an integration
GET /v1/{tenant}/integrations/{id}/managed
  → { "alert_ingestion": { task_id, schedule_id, ... }, "health_check": { ... } }

# View/update the task for a managed resource
GET  /v1/{tenant}/integrations/{id}/managed/{resource_key}/task
PUT  /v1/{tenant}/integrations/{id}/managed/{resource_key}/task

# View/update the schedule for a managed resource
GET  /v1/{tenant}/integrations/{id}/managed/{resource_key}/schedule
PUT  /v1/{tenant}/integrations/{id}/managed/{resource_key}/schedule
  body: { "schedule_value": "120s", "enabled": true }

# View run history for a managed resource
GET  /v1/{tenant}/integrations/{id}/managed/{resource_key}/runs
  → JobRuns filtered to this task

# Trigger an immediate run (ignores schedule)
POST /v1/{tenant}/integrations/{id}/managed/{resource_key}/run
  → Creates ad-hoc JobRun + TaskRun
```

`resource_key` is derived from the archetype: `alert_ingestion` (AlertSource), `health_check` (all integrations). Future archetypes can add more keys without API changes.

### Task/Workflow Schedule (convenience endpoints)

The natural way to schedule a task: operate directly on the task. These are thin wrappers over the `schedules` table with `target_type` and `target_id` pre-filled.

```
# Attach a schedule to a task
POST /v1/{tenant}/tasks/{task_id}/schedule
  { "type": "every", "value": "1h", "enabled": true }
  → Creates schedule row, returns schedule details

# View the schedule
GET  /v1/{tenant}/tasks/{task_id}/schedule
  → Returns schedule (or 404 if none)

# Modify the schedule
PATCH /v1/{tenant}/tasks/{task_id}/schedule
  { "value": "30m", "enabled": false }

# Remove the schedule
DELETE /v1/{tenant}/tasks/{task_id}/schedule

# Same pattern for workflows
POST  /v1/{tenant}/workflows/{workflow_id}/schedule
GET   /v1/{tenant}/workflows/{workflow_id}/schedule
PATCH /v1/{tenant}/workflows/{workflow_id}/schedule
DELETE /v1/{tenant}/workflows/{workflow_id}/schedule
```

A task or workflow can have **one schedule** (1:1 relationship via these endpoints). For the rare case of multiple schedules on the same target, use the generic API below.

### Schedules API (canonical, generic)

The full CRUD API for advanced use cases (listing across targets, multiple schedules, bulk operations).

```
# List all schedules for a tenant
GET  /v1/{tenant}/schedules
  ?target_type=task
  ?integration_id=splunk-prod
  ?origin_type=system

# Create a schedule (for advanced/multi-schedule use cases)
POST /v1/{tenant}/schedules
  { "target_type": "task", "target_id": "uuid", "schedule_type": "every",
    "schedule_value": "1h", "enabled": true }

# Update a schedule
PATCH /v1/{tenant}/schedules/{id}
  { "schedule_value": "120s", "enabled": true }

# Delete a schedule
DELETE /v1/{tenant}/schedules/{id}
```

### Task Runs Filtering (modified endpoint)

```
GET /v1/{tenant}/task-runs
  ?run_context=analysis,ad_hoc    ← default (excludes scheduled)
  ?run_context=scheduled          ← explicitly request scheduled runs
  ?integration_id=splunk-prod     ← filter by integration
  ?task_id=uuid                   ← filter by specific task
```

The default `run_context` filter excludes `scheduled` runs. Clients must explicitly request `?run_context=scheduled` or `?run_context=analysis,scheduled,ad_hoc` to see everything.

### Registry Endpoints (modified)

```
# Old (connector-specific)
GET /v1/{tenant}/integrations/registry/{type}/connectors/{connector}
GET /v1/{tenant}/integrations/registry/{type}/connectors/{connector}/default-schedule

# New (unified actions)
GET /v1/{tenant}/integrations/registry/{type}/actions
GET /v1/{tenant}/integrations/registry/{type}/actions/{action_id}
```

---

## Integration Response (modified)

The integration detail response includes managed resources:

```json
{
  "integration_id": "splunk-prod",
  "name": "Splunk Prod",
  "integration_type": "splunk",
  "archetypes": ["SIEM", "AlertSource"],
  "enabled": true,
  "actions": [
    { "id": "pull_alerts", "categories": ["alert_ingestion"], "cy_name": "pull_alerts" },
    { "id": "normalize_alerts", "categories": ["normalization"], "cy_name": "alerts_to_ocsf" },
    { "id": "health_check", "categories": ["health_monitoring"], "cy_name": "health_check" },
    { "id": "update_notable", "categories": ["investigation"], "cy_name": "update_notable" }
  ],
  "managed_resources": {
    "alert_ingestion": {
      "task_id": "550e8400-...",
      "task_name": "Alert Ingestion for splunk-prod",
      "schedule_id": "6ba7b810-...",
      "schedule": {
        "type": "every",
        "value": "5m",
        "enabled": true
      },
      "last_run": {
        "status": "completed",
        "at": "2026-03-27T10:00:00Z",
        "task_run_id": "a1b2c3d4-..."
      },
      "next_run_at": "2026-03-27T10:05:00Z"
    },
    "health_check": {
      "task_id": "7c9e6679-...",
      "task_name": "Health Check for splunk-prod",
      "schedule_id": "8f14e45f-...",
      "schedule": {
        "type": "every",
        "value": "5m",
        "enabled": true
      },
      "last_run": {
        "status": "completed",
        "at": "2026-03-27T09:55:00Z",
        "task_run_id": "e5f6g7h8-..."
      },
      "next_run_at": "2026-03-27T10:00:00Z"
    }
  }
}
```

---

## Worker Changes

Task execution requires a 3600s timeout (`execute_task_run`), but the Integrations worker has a 300s timeout. These are fundamentally different workloads — the Integrations worker handles lightweight connector operations, while task execution involves the Cy interpreter, LLM calls, and multi-step pipelines. They also run on separate Redis DBs (Integrations: DB 5, Alert Analysis: DB 0).

**Solution: Split scheduling from execution across workers.**

```
Integrations worker (DB 5, JOB_TIMEOUT=300s):
  ├── schedule_executor cron (every 30s) — lightweight polling
  ├── process_tenant_schedules — per-tenant schedule evaluation
  ├── run_integration — existing connector execution (deprecated, kept for migration)
  └── Enqueues execute_task_run to Alert Analysis worker (DB 0)

Alert Analysis worker (DB 0, JOB_TIMEOUT=3600s):
  ├── execute_task_run — handles scheduled + ad_hoc + analysis task runs
  ├── execute_workflow_run — workflow execution
  ├── process_alert_analysis — alert analysis pipeline
  └── (no changes needed — already handles task execution)
```

The `schedule_executor` reads from the new `schedules` table instead of `integration_schedules`. When a schedule fires, it:
1. Creates a `JobRun` record (direct DB, within transaction)
2. Creates a `TaskRun` (with `run_context="scheduled"`, direct DB)
3. Enqueues `execute_task_run` to the **Alert Analysis worker's queue** (DB 0)
4. Updates `schedule.next_run_at` (direct DB)

All four steps happen in a single DB transaction. The scheduler uses **direct DB access** (not REST API calls as the current `schedule_executor` does) — this eliminates HTTP round-trips and enables transactional guarantees.

**Note**: `next_run_at` is a new behavior. The current scheduler uses `last_run_at + interval` comparison. The new scheduler computes `next_run_at` on schedule creation and after each run, enabling efficient index scans with `FOR UPDATE SKIP LOCKED`.

The existing `run_integration` function is kept during migration but deprecated — new scheduled Tasks go through `execute_task_run` directly.

---

## Failure Modes

### Schedule fires but Task fails

The `TaskRun` records the failure. The `JobRun` mirrors the status. `set_checkpoint()` was not called, so the next scheduled run retries the same time window. No special retry logic at the scheduler level — tenacity handles action-level retries (3 attempts with exponential backoff on 5xx/429).

### Integration disabled while Task is running

The running TaskRun completes normally. The Schedule is marked `enabled=false`, preventing future runs. No mid-flight cancellation.

### Integration deleted with pending scheduled run

Schedule is disabled first (prevents new runs). Any in-flight TaskRun completes. The JobRun and TaskRun records are preserved (audit trail). The Task is soft-deleted — still referenced by historical records but not executable.

### Checkpoint corruption

If a checkpoint value is corrupted or set to a future timestamp, the Task's `pull_alerts` returns an empty result set. The admin can fix this by editing the Task to reset the checkpoint or by directly updating the `task_checkpoints` table via the API.

### Two schedule executors race on the same schedule

`FOR UPDATE SKIP LOCKED` on the `schedules` table ensures only one executor processes each schedule. The second executor skips it.

---

## Multi-Tenancy

- `schedules.tenant_id`: all schedules are tenant-scoped
- `job_runs.tenant_id`: all runs are tenant-scoped
- `task_checkpoints.tenant_id`: checkpoints are tenant-scoped
- Schedule executor processes tenants independently (per-tenant ARQ jobs)
- API routes enforce tenant context via path parameter
- Managed resources inherit the integration's tenant

---

## File Locations

| Component | Path |
|-----------|------|
| **Models** | |
| Schedule model | `src/analysi/models/schedule.py` (new) |
| JobRun model | `src/analysi/models/job_run.py` (new) |
| TaskCheckpoint model | `src/analysi/models/task_checkpoint.py` (new) |
| TaskRun additions | `src/analysi/models/task_run.py` (modified) |
| Task additions | `src/analysi/models/task.py` (modified) |
| **Repositories** | |
| Schedule repository | `src/analysi/repositories/schedule_repository.py` (new) |
| JobRun repository | `src/analysi/repositories/job_run_repository.py` (new) |
| Checkpoint repository | `src/analysi/repositories/task_checkpoint_repository.py` (new) |
| **Services** | |
| Task factory | `src/analysi/services/task_factory.py` (new) |
| Schedule executor | `src/analysi/scheduler/schedule_executor.py` (moved + refactored) |
| Integration service | `src/analysi/services/integration_service.py` (modified — lifecycle hooks) |
| **Cy Functions** | |
| ingest_alerts | `src/analysi/services/cy_functions.py` (new function) |
| get/set_checkpoint | `src/analysi/services/cy_functions.py` (new functions) |
| **Routers** | |
| Managed resources | `src/analysi/routers/integration_managed.py` (new) |
| Schedules API | `src/analysi/routers/schedules.py` (new) |
| Integrations router | `src/analysi/routers/integrations.py` (modified — remove connector endpoints) |
| Task runs router | `src/analysi/routers/task_execution.py` (modified — run_context filter) |
| **Framework** | |
| ActionDefinition | `src/analysi/integrations/framework/models.py` (modified) |
| Manifest validator | `src/analysi/integrations/framework/validators.py` (modified) |
| Archetype enum | `src/analysi/integrations/framework/models.py` (add AlertSource) |
| **Manifests** | |
| Splunk | `src/analysi/integrations/framework/integrations/splunk/manifest.json` (modified) |
| Echo EDR | `src/analysi/integrations/framework/integrations/echo_edr/manifest.json` (modified) |
| All others | Each integration's `manifest.json` (drop type/purpose, add categories) |
| **Migration** | |
| Flyway migration | `migrations/flyway/sql/V{next}__project_symi_unified_scheduler.sql` |
| **Worker** | |
| Integrations worker | `src/analysi/integrations/worker.py` (modified — scheduler cron, enqueue to alert analysis) |
| Alert Analysis worker | `src/analysi/alert_analysis/worker.py` (unchanged — already runs execute_task_run) |
| ARQ enqueue utility | `src/analysi/common/arq_enqueue.py` (unchanged — already routes to DB 0) |

---

## Design Decisions

Decisions made during design review and validated against the codebase:

### Why the scheduler runs on the Integrations worker but tasks execute on Alert Analysis

The Integrations worker (Redis DB 5) has `JOB_TIMEOUT=300s` and handles lightweight operations. `execute_task_run` requires `3600s` (Cy interpreter + LLM calls + multi-step pipelines) and already runs on the Alert Analysis worker (Redis DB 0). The scheduler cron is lightweight polling (~30ms per cycle) — it belongs on the Integrations worker. Task execution is heavyweight — it stays on Alert Analysis. The scheduler enqueues across worker boundaries via `arq_enqueue.py` which already targets DB 0.

### Why the new scheduler uses direct DB access instead of REST API

The current `schedule_executor` uses HTTP REST calls to list integrations, fetch schedules, create runs, and update `last_run_at`. This works but has drawbacks: HTTP round-trips add latency, no transactional guarantees across steps, and auth token management. The new scheduler operates within a single DB transaction: read due schedules → create JobRun → create TaskRun → update next_run_at → commit. `FOR UPDATE SKIP LOCKED` prevents duplicate processing by concurrent workers.

### Why `next_run_at` replaces `last_run_at + interval` comparison

The current scheduler computes "is due?" by checking `now() - last_run_at >= interval` on every poll. This requires fetching all enabled schedules and evaluating each one. Pre-computing `next_run_at` enables an indexed query: `WHERE enabled=true AND next_run_at <= now()` — the database does the filtering. This matters at scale (hundreds of schedules across tenants).

### Why checkpoints use a dedicated table instead of TaskRun.execution_context

HITL checkpoints use `TaskRun.execution_context` JSONB, but those are per-run (resume within the same run). Alert ingestion checkpoints must persist **across runs** — run N's checkpoint is run N+1's starting point. `TaskRun.execution_context` is created fresh for each run, so cross-run state needs its own table.

### Why only Splunk gets AlertSource in v1

Of 40 integrations, only Splunk currently has alert ingestion connectors. The AlertSource archetype and Task factory are designed for general use, but v1 implementation focuses on Splunk as the proof point. Other integrations (Chronicle, MSentinel, Databricks) can adopt AlertSource incrementally without design changes.

### Code locations requiring `type`/`purpose` removal (8+ sites)

The `action.type == "connector"` check appears in: `integration_registry_service.py` (4 locations: connector filtering, tool counting, API response formatting, default schedule lookup), `integration_tools.py` (2 locations: MCP tool discovery, integration tool search), and `models.py` (schema definition). All must migrate to `categories`-based filtering in a single coordinated change.

---

## Proposed Breakdown

### Step 1: Database Schema + Models

- Flyway migration: create `schedules`, `job_runs`, `task_checkpoints` tables
- Flyway migration: add `run_context` to `task_runs`, `integration_id` + `origin_type` to `tasks`
- SQLAlchemy models for Schedule, JobRun, TaskCheckpoint
- Repositories with basic CRUD
- Backfill `task_runs.run_context` from existing data
- Tests: model creation, repository CRUD, constraint validation

### Step 2: Generic Scheduler

- Refactor `schedule_executor` to read from `schedules` table
- Schedule executor creates JobRun + TaskRun (run_context="scheduled")
- Enqueues `execute_task_run` instead of `run_integration`
- Schedules API router (CRUD)
- Tests: schedule due detection, executor flow, API endpoints

### Step 3: Unified Actions in Manifests

- Remove `type` and `purpose` from ActionDefinition model
- Add `categories` field
- Add `AlertSource` to Archetype enum
- Update manifest validator: enforce AlertSource contract
- Update all integration manifests (splunk, echo_edr, etc.)
- Update IntegrationRegistryService to use new schema
- Tests: manifest validation, archetype resolution, registry queries

### Step 4: Task Factory + Integration Lifecycle

- Implement `create_alert_ingestion_task()` and `create_health_check_task()`
- Hook into `IntegrationService.create_integration()` for auto-creation
- Hook into enable/disable/delete for cascade behavior
- Managed resources API router
- Tests: factory output, lifecycle cascades, managed resources endpoints

### Step 5: Platform Cy Functions

- Implement `ingest_alerts()` Cy function (delegates to AlertIngestionService)
- Implement `get_checkpoint()` / `set_checkpoint()` Cy functions
- Register in DefaultTaskExecutor tool injection
- Tests: Cy function execution, checkpoint read/write, alert ingestion via Cy

### Step 6: Task Run Filtering + Integration Response

- Add `run_context` filter to task runs list endpoint (default excludes scheduled)
- Add `managed_resources` to integration detail response
- Tests: filtering behavior, response shape

### Step 7: Data Migration + Cleanup

- Migrate `integration_schedules` → `schedules` (generate Tasks first, point schedules at them)
- Migrate `integration_runs` → `job_runs`
- Remove old connector-specific endpoints from integrations router
- Remove `integration_schedules` and `integration_runs` tables (or rename as archive)
- Deprecation cleanup pass across codebase (remove "connector" terminology)
- Tests: migration correctness, old endpoints return 404/redirect

---

## Future Work

- **Cron expressions**: `schedule_type="cron"` with standard cron syntax (e.g., `"0 */6 * * *"`)
- **Knowledge building tasks**: Content pack ships Tasks that call integration actions like `app::splunk::get_assets()` to build KUs
- **Schedule pause/resume with reason**: Track why a schedule was disabled (admin action vs. integration disabled vs. repeated failures)
- **Automatic schedule backoff**: If a scheduled Task fails N times consecutively, automatically increase the interval or disable with an alert
- **Bulk schedule management**: Enable/disable all schedules for a tenant in one call
- **Schedule metrics**: Dashboard showing schedule health, average execution time, failure rates
