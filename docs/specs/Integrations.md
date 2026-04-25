+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Integration framework and registry"
+++

# Integrations

## Overview

Integrations are a special type of **App** that represent configured connections to 3rd party tools (SIEM, SOAR, EDR, etc.).

### Apps Context
In the future, we may bundle knowledge units and functionality into Apps. An Integration App includes:
- **(a) Tools** - Functions that interact with the integration (e.g., SPL search execution)
- **(b) Tasks** - Automated workflows and procedures
- **(c) Documents and Tables** - Knowledge Units for the integration
- **(d) Connectors** - Specialized components for data flow and integration management

### Integration Instance Components
Each integration instance has:

* **Settings** (credentials, hostnames, ports, URLs)
* **Connectors** (specialized data flow and management units)
* **Tools** (general-purpose functions for interaction)
* **Runs** (single connector executions)
* **Schedules** (recurring connector runs)
* **Health** (connectivity + last run info)

All state is persisted in Postgres. Connector runs are async jobs via ARQ + Valkey.

---

## Connectors vs Tools

### Critical Distinction
Both **Connectors** and **Tools** use integration settings (credentials, hostnames, ports, URLs) to connect with remote services, but they serve fundamentally different purposes.

### Connectors (5 Core Purposes)
Connectors are specialized components responsible for:

1. **Alert Ingestion & Normalization** - Pull new alerts from the source and normalize them to NAS (Notable Alert Schema)
2. **Alert Output & Updates** - Push alert updates back to the source (e.g., Splunk, JIRA, ServiceNow)
3. **Health Monitoring** - Perform health checks and probes for their integration
4. **Activity/Audit Logging** - Send task execution logs and audit trails to the integration source
5. **Knowledge Building** - Scan the integration source to build Knowledge Units (Docs, Tables, Vector DB indexes) needed for proper integration operation

**Examples of Connectors:**
- `pull_alerts` - Fetches and normalizes alerts from Splunk
- `health_check` - Monitors Splunk connectivity and status
- `send_audit_logs` - Pushes Analysi activity logs to Splunk
- `scan_datamodels` - Builds knowledge about available Splunk data models

### Tools (Everything Else)
Tools are general-purpose functions that interact with the integration but don't achieve the 5 connector goals.

**Examples of Tools:**
- `run_spl_search` - Executes an SPL search in Splunk (investigation tool)
- `get_user_info` - Retrieves user details from Active Directory
- `create_ticket` - Creates a new ServiceNow ticket
- `download_file` - Downloads a file from an S3 bucket

**Key Difference:** If a function primarily serves investigation, analysis, or ad-hoc interaction (rather than data flow management), it's a Tool, not a Connector.

---

## Consumers

* **UI**

  * Configure and enable integrations from a supported list.
  * Show enabled integrations with status (name, created, health, toggle).
  * Drill-in views fetch settings, health, connectors, runs.
* **Tasks**

  * Trigger connector runs to fetch or push data (e.g., EDR endpoint lookup).
  * Scheduled runs probe tools like Splunk for new alerts.

---

## AI Dev Context

* Endpoints are tenant-scoped.
* **Connectors only**: Only the 5 connector purposes (alert ingestion, output, health, audit, knowledge building) use the connector runs system.
* **Tools are separate**: General-purpose integration functions (like `run_spl_search`) are Tools, not Connectors. Tool invocations are NOT tracked by connector runs.
* Splunk: prefer `{ "earliest": ..., "latest": ... }`, relative windows allowed and normalized.
* Secrets encrypted, masked on read.
* Run states follow existing pattern: running → succeeded | failed | paused_by_user
* Bulk fan-out requires confirm\_all when targeting many instances.
* Workers use REST API exclusively (no direct DB access)

**Example – Single run:**

```http
POST /v1/acme/integrations/splunk-prod/connectors/pull_alerts/connector-runs
{ "params": { "earliest": "2026-04-26T10:00:00Z", "latest": "2026-04-26T10:02:00Z" }}
```

**Example – Bulk run (FUTURE):**

```http
POST /v1/acme/connectors/pull_alerts/connector-runs
{ "selector": { "integration_type": "splunk" }, "params": { "earliest": "2026-04-26T10:00:00Z", "latest": "2026-04-26T10:02:00Z" }, "safety": { "confirm_all": true }}
```

---

## Persistence & Services

* REST API service: owns Postgres + ARQ; exposes run/schedule CRUD.
* Connector worker service: **no DB access**, calls REST API for all updates.

**Tables**

* `integrations` (stores configured integration instances)

  * Fields: integration\_id (VARCHAR), tenant\_id (VARCHAR), integration\_type, name, description, enabled (BOOLEAN), settings (JSONB for encrypted credentials/config), created\_at, updated\_at.
  * Primary Key: (tenant\_id, integration\_id) - composite for multi-tenancy
  * integration\_id uses human-readable strings like "splunk-prod", "echo-staging"

* `integration_runs` (time-partitioned by `created_at` - matches existing pattern)

  * Fields: run\_id, tenant\_id, integration\_id, integration\_type, connector, run\_type, status, created\_at, updated\_at, start\_time, end\_time, attempt, max\_attempts, params (JSONB), run\_details (JSONB).
  * Status values: `'running', 'succeeded', 'failed', 'paused_by_user'` (VARCHAR with CHECK constraint)
  * `run_details.preview` (JSONB, optional): small preview for UI (e.g., last probe status, sample of results). Keep under **32KB**.

* `integration_schedules`

  * Fields: schedule\_id, tenant\_id, integration\_id, integration\_type, connector, schedule\_type (every|cron), schedule\_value, timezone, enabled, params (JSONB), selector (JSONB), fanout (JSONB), created\_at, updated\_at.
  * **Note on unused fields**: `selector` and `fanout` are reserved for Phase 2 bulk operations (not currently used):
    - `selector`: Will specify which integrations to target in bulk schedules
    - `fanout`: Will contain execution policies like `confirm_all`, `max_parallel`, `failure_policy`

**Flow**

1. Client POST /connector-runs → REST inserts `integration_runs(status='running')` then enqueues ARQ.
2. Worker picks job, calls `PATCH /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs/{run_id}` to maintain status.
3. Worker completes → `PATCH /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs/{run_id}` with terminal status + details.
4. Clients GET /connector-runs/{run\_id} (or bulk parent) until terminal.

**Worker API Client Pattern**

Workers use an API client similar to existing `BackendAPIClient`:

```python
class IntegrationAPIClient(BackendAPIClient):
    """HTTP client for integration workers to call REST API"""

    async def update_run_status(
        self, tenant_id: str, integration_id: str,
        connector: str, run_id: str,
        status: str, run_details: dict = None
    ):
        """Update run status via REST API"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.patch(
                f"{self.base_url}/v1/{tenant_id}/integrations/{integration_id}/connectors/{connector}/connector-runs/{run_id}",
                json={"status": status, "run_details": run_details}
            )
            response.raise_for_status()
```

**Scheduling execution model**

* REST owns schedule CRUD in DB. Connector service runs a **reconciler** that reads `/schedules` and ensures **one ARQ periodic job per schedule** (create/update/delete).
* Each ARQ tick **calls REST** (`POST .../connector-runs` with computed `{earliest,latest}`) — the connector service **does not write DB directly**.
* REST creates the `integration_runs` row and (for immediate work) enqueues the execution job; the worker executes and PATCHes status.
* Reconciler honors `enabled=false` (pauses), updates cron/`every` changes, and backfill policy (catch-up vs next-only) per schedule config.

**Connector worker functions**

* Each connector type maps to a distinct ARQ function (e.g., `splunk_pull_alerts`, `splunk_health_check`, `echo_edr_pull_alerts`).
* **Important**: Only the 5 connector purposes get ARQ functions. Tools like `run_spl_search` or `pull_browser_history` are executed differently.
* REST sets the target function name in the ARQ payload based on `{integration_type, connector}`.
* Workers import/route to these functions; adding a connector = adding a function.

**ARQ payload (example)**

```json
{
  "run_id": "uuid-1",
  "tenant_id": "acme",
  "integration_id": "splunk-prod",
  "integration_type": "splunk",
  "connector": "pull_alerts",
  "function": "splunk_pull_alerts",
  "params": {
    "earliest": "2026-04-26T10:00:00Z",
    "latest": "2026-04-26T10:02:00Z",
    "dedupe": true
  }
}
```

---

## Endpoints

### Connector Types (Registry)

Standard registry describing each connector type (semantics, params, results).

```
GET /v1/{tenant}/connector-types?integration_type={type}  # Filter by integration type
GET /v1/{tenant}/connector-types/{connector_type}
```

**Example - List connectors for Splunk:**
```
GET /v1/{tenant}/connector-types?integration_type=splunk
```

Returns only connectors available for Splunk integrations.

**Example - Single connector type:**

```json
{
  "connector_type": "pull_alerts",
  "integration_types": ["splunk", "qradar"],  // Which integrations support this
  "display_name": "Pull Alerts",
  "description": "Fetch alerts within earliest/latest window.",
  "params_schema": {
    "type": "object",
    "properties": {
      "earliest": { "type": "string", "format": "date-time", "required": true },
      "latest":   { "type": "string", "format": "date-time", "required": true },
      "dedupe":   { "type": "boolean", "default": true }
    }
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "records": { "type": "integer" },
      "artifact_refs": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

---

## Endpoints

### Integration Types

```
GET /v1/{tenant}/integration-types
```

Returns supported integration types, connector list, and schema refs.

### Connector Types (Registry)

```
GET /v1/{tenant}/connector-types
GET /v1/{tenant}/connector-types/{connector_type}
```

Provides metadata and JSON schema for each connector type.

**Example – GET /v1/{tenant}/connector-types/pull\_alerts**

```json
{
  "connector_type": "pull_alerts",
  "display_name": "Pull Alerts",
  "description": "Fetch new alerts from the integration within a specified earliest/latest window.",
  "params_schema": {
    "type": "object",
    "properties": {
      "earliest": { "type": "string", "format": "date-time", "required": true },
      "latest":   { "type": "string", "format": "date-time", "required": true },
      "dedupe":   { "type": "boolean", "default": true }
    }
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "records": { "type": "integer" },
      "artifact_refs": { "type": "array", "items": { "type": "string" } }
    }
  }
}
```

```
GET /v1/{tenant}/integration-types
```

Returns supported integration types, connector list, and schema refs.

### Integrations

```
GET  /v1/{tenant}/integrations
POST /v1/{tenant}/integrations
GET  /v1/{tenant}/integrations/{integration_id}
PATCH/DELETE /v1/{tenant}/integrations/{integration_id}
GET  /v1/{tenant}/integrations/{integration_id}/settings
GET  /v1/{tenant}/integrations/{integration_id}/health
GET  /v1/{tenant}/integrations/{integration_id}/connectors
```

### Connector Runs

```
POST /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs
GET  /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs
GET  /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs/{run_id}
PATCH /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/connector-runs/{run_id}
```

**Run lifecycle:** `running → succeeded | failed | paused_by_user`

**Status mapping for compatibility:**
- External requests for "queued" state → Create as "running"
- External requests for "canceled" → Map to "paused_by_user"
- Timeout scenarios → Use "failed" with timeout details in run_details

**Time parameters (Splunk):**

* Prefer explicit timestamps: `{ "earliest": "2026-04-26T10:00:00Z", "latest": "2026-04-26T10:02:00Z" }`
* Relative ranges (e.g., `"-2m..now"`) may be provided; normalized to earliest/latest internally.

**Run results (artifacts-first):**

* Workers do **not** return large payloads inline.
* On completion, workers `PATCH` `run_details` with a **summary** (metrics, counts) and **artifact\_refs** pointing to the Artifact Store.
* Clients fetch results via `GET /.../connector-runs/{run_id}` to discover `artifact_ids`, then call the Artifacts API.

**Example run (terminal):**

```json
{
  "run_id": "uuid-1",
  "status": "succeeded",
  "run_details": {
    "metrics": { "records": 1432, "bytes": 920311, "duration_ms": 8423 },
    "artifact_refs": [
      { "artifact_id": "art-7f2a", "kind": "parquet", "purpose": "alerts" },
      { "artifact_id": "art-7f2b", "kind": "ndjson",  "purpose": "log" }
    ]
  }
}
```

### Schedules

```
POST   /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules
GET    /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules
PATCH  /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}
DELETE /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}
GET    /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}/connector-runs
```

**Create schedule (example):**

```http
POST /v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules
{
  "enabled": true,
  "every": "1m",                // or cron: "*/1 * * * *"
  "timezone": "America/Los_Angeles",
  "params": { "time_range": "-2m..now", "dedupe": true }
}
→ 201 { "schedule_id": "uuid", "next_run_at": "2026-04-26T10:03:00Z" }
```

**Linkage:** each scheduled trigger creates a new `integration_runs` row with `run_type = schedule` and `schedule_id` set. UI/clients can query past runs of a schedule via `/schedules/{schedule_id}/connector-runs`.

---

## Artifacts API (reference)

Connector results are persisted in the Artifact Store; `run_details.artifact_refs` carry the IDs.

```
POST   /v1/{tenant}/artifacts                     # Create artifact
GET    /v1/{tenant}/artifacts                     # List artifacts
GET    /v1/{tenant}/artifacts/{artifact_id}       # Get artifact metadata
DELETE /v1/{tenant}/artifacts/{artifact_id}       # Delete artifact
GET    /v1/{tenant}/artifacts/{artifact_id}/download  # Download payload
```

---

## Safety & Security

* Secrets encrypted & masked on read
* Audit trail for settings and runs
* Rate limits per tenant/type
* Trace IDs for observability

---

## Future Work

### Phase 2 (Bulk Operations)
* **Bulk Runs**: `POST /v1/{tenant}/connectors/{connector}/connector-runs` - Run a connector across multiple integrations with selector
* **Bulk Run Status**: `GET /v1/{tenant}/bulk-runs/{bulk_run_id}` - Track bulk run progress
* **Bulk Schedules**: `POST /v1/{tenant}/connectors/{connector}/schedules` - Create schedules for multiple integrations
  - Uses `selector` field to target integrations (e.g., `{"integration_type": "splunk"}`)
  - Uses `fanout` field for execution control:
    ```json
    {
      "confirm_all": true,        // All targets must be healthy
      "max_parallel": 5,          // Max concurrent executions
      "failure_policy": "continue" // continue|stop on failure
    }
    ```
* **Bulk Schedule Listing**: `GET /v1/{tenant}/connectors/{connector}/schedules` - List all schedules across integrations

### Phase 3 (Advanced Features)
* **Groups**: Reusable sets of integrations for bulk operations
* **Webhooks**: Notify external systems on run completion
* **Bulk fan-out safety**: `confirm_all` parameter for operations affecting many integrations

### Phase 4 (Architecture Consolidation)
* **Tool Service Migration**: Move all Tools to be served by the Connector Service to isolate all 3rd party interactions into a single microservice
* **Unified Integration Gateway**: Single service handling both Connectors and Tools for better security and control
* **Tool Execution Tracking**: Separate tracking system for Tool invocations (different from connector runs)

---

## Initial Integrations

### Splunk
**Connectors:**
- `health_check` - Monitor Splunk connectivity and status
- `pull_alerts` - Fetch and normalize alerts to NAS
- `send_audit_logs` - Push Analysi activity logs to Splunk
- `scan_datamodels` - Build knowledge about available data models
- `scan_sourcetypes` - Build knowledge about available source types

**Tools:**
- `run_spl_search` - Execute SPL searches for investigation
- `get_user_info` - Retrieve user details from Splunk
- `list_security_tas` - List installed security technology add-ons

### Echo EDR
**Connectors:**
- `health_check` - Monitor Echo EDR connectivity and status
- `pull_alerts` - Fetch and normalize security alerts to NAS
- `send_audit_logs` - Push Analysi activity logs to Echo EDR

**Tools:**
- `pull_browser_history` - Retrieve browser history for investigation
- `pull_terminal_history` - Retrieve terminal/command history
- `pull_running_processes` - Get current running processes
- `isolate_endpoint` - Isolate a compromised endpoint

---

## Implementation Notes for Consistency

### Status Values
- Use existing pattern: `VARCHAR(50) CHECK (status IN (...))`
- No new PostgreSQL enum types
- Map external states to our states in API layer if needed

### Table Patterns
- Partition by `created_at` (not `started_at`) to match existing tables
- Use `TIMESTAMP WITH TIME ZONE` for all timestamps
- Follow naming: snake_case for all fields

### Worker Pattern
- Workers call REST API via `IntegrationAPIClient`
- No direct database access from workers
- Reuse existing httpx patterns and retry policies

### API Patterns
- Follow existing router patterns: `/{tenant}/resource/{id}/action`
- Use consistent pagination: skip/limit parameters
- Return same response structures as other services
