# Analysi Integrations — UI User Guide

> **Scope**: This guide is for the in-repo `ui/` subproject (React + TypeScript).
> It describes the integration endpoints consumed by `ui/src/services/integrationsApi.ts`
> and the patterns used by `ui/src/pages/Integrations.tsx` and
> `ui/src/components/integrations/`.
>
> For the authoritative backend contract, see
> [`docs/specs/Integrations.md`](../../docs/specs/Integrations.md) and
> [`docs/specs/ConnectorPullService.md`](../../docs/specs/ConnectorPullService.md).
> If anything in this doc disagrees with the specs or the code in
> `src/analysi/integrations/` and `src/analysi/routers/`, the code and the
> specs win.

This guide explains how to configure and manage integrations with external
security systems from the UI. Examples throughout reference sample
integrations such as Splunk, Echo EDR, and VirusTotal — these are illustrative
and are not guaranteed to be available in every deployment. The actual list
depends on which integration manifests are packaged into your build.

## Core Concepts

### Integration (type / instance)
An **integration type** is a manifest-defined connector to an external system
(e.g., `splunk`, `echo_edr`, `virustotal`). An **integration instance** is a
configured connection — essentially the "account" or endpoint you're talking
to. Instances are identified by a tenant-scoped `integration_id` string like
`splunk-prod`.

### Action
An **Action** is a single callable operation exposed by an integration
(for example `pull_alerts`, `health_check`, `ip_reputation`, `run_spl_search`).
Each action has a `params_schema` and a `result_schema` that describe its
inputs and outputs. Actions are what the registry advertises and what Cy
scripts invoke.

### Managed Resource
A **Managed Resource** is a Task (and optional Schedule) that the integration
auto-creates for recurring work such as alert ingestion or periodic health
checks. Managed resources are looked up by a short `resource_key` (e.g.
`pull_alerts`, `health_check`) scoped to one integration instance.

### Schedule
A **Schedule** is the generic scheduler record that fires a Task or Workflow
on an interval (or cron). Schedules are not nested under an action in the
URL — they live at `/v1/{tenant}/schedules` and can be filtered by
`integration_id`. The managed-resource convenience routes let the UI edit the
single schedule attached to a managed resource without having to know its
schedule UUID.

### Run
When a managed resource fires (or is triggered ad-hoc), it creates a
**TaskRun**. The UI reads run history through
`/integrations/{id}/managed/{resource_key}/runs`, which returns
`ManagedRunItem` records. Each item has `task_run_id`, `status`,
`run_context`, `started_at`, `completed_at`, and `created_at`. There is no
separate `integration_runs` endpoint anymore; runs are always TaskRuns.

### Credential
An encrypted secret stored in Vault (via the Credential service) and linked
to an integration. The UI typically creates and associates a credential in a
single call via `POST /integrations/{id}/credentials`.

---

## API Endpoints

All paths are tenant-scoped under `/v1/{tenant}/…`. Responses use the Sifnos
envelope: single items return `{"data": {...}, "meta": {...}}` and lists
return `{"data": [...], "meta": {"total": N, ...}}`. The UI's
`fetchOne`/`mutateOne` helpers auto-unwrap the envelope.

### Registry (discovery)
- `GET /integrations/registry` — list all available integration types
- `GET /integrations/registry/{integration_type}` — type detail, including
  `credential_schema`, `settings_schema`, `archetypes`, and `actions[]`
- `GET /integrations/registry/{integration_type}/actions` — action list only
- `GET /integrations/registry/{integration_type}/actions/{action_id}` — action
  detail with `params_schema` and `result_schema`
- `GET /integrations/tools/all` — flat list of all callable tools (native +
  integration) with parameter schemas, used for Cy autocomplete

### Integration management
- `GET /integrations` — list instances (query: `enabled`, `limit`, `skip`)
- `POST /integrations` — create an instance
- `GET /integrations/{integration_id}` — detail (includes `managed_resources`
  block and `health` when available)
- `PATCH /integrations/{integration_id}` — update name / description /
  enabled / settings
- `DELETE /integrations/{integration_id}` — delete instance + managed
  resources
- `POST /integrations/{integration_id}/enable` — enable + cascade-enable
  schedules
- `POST /integrations/{integration_id}/disable` — disable + cascade-disable
  schedules
- `GET /integrations/{integration_id}/health` — health summary
- `POST /integrations/provision-free` — idempotently provision every
  integration type whose manifest has `requires_credentials: false`

### Managed resources (auto-created tasks + schedules)
- `GET /integrations/{integration_id}/managed` — map of
  `{resource_key → ManagedResourceSummary}`
- `GET /integrations/{integration_id}/managed/{resource_key}/task` — task
  detail (script, function, scope, origin)
- `PUT  /integrations/{integration_id}/managed/{resource_key}/task` — edit
  name / description / script
- `GET /integrations/{integration_id}/managed/{resource_key}/schedule` —
  schedule detail
- `PUT  /integrations/{integration_id}/managed/{resource_key}/schedule` —
  update `schedule_value` and/or `enabled`
- `GET /integrations/{integration_id}/managed/{resource_key}/runs` — list
  TaskRuns for this managed resource (`skip`, `limit`)
- `POST /integrations/{integration_id}/managed/{resource_key}/run` — trigger
  an ad-hoc run, returns `{task_run_id, status, task_id, resource_key}`

### Generic schedules
- `GET    /schedules` — filter by `target_type`, `integration_id`,
  `origin_type`, `enabled`
- `POST   /schedules` — create (generic path; most UI flows should use the
  managed-resource endpoint or the task-specific convenience endpoint)
- `PATCH  /schedules/{schedule_id}`
- `DELETE /schedules/{schedule_id}`

### Direct tool execution (for "Test" buttons in the UI)
- `POST /integrations/{integration_id}/tools/{action_id}/execute` — executes
  an action synchronously (body: `{arguments, timeout_seconds,
  capture_schema}`) and returns `{status, output, output_schema, error,
  execution_time_ms}`. This is the path the IntegrationSetupWizard's
  connection-test step uses.

### Credentials
- `POST   /integrations/{integration_id}/credentials` — **preferred**: create
  + associate in one call
- `GET    /credentials/integrations/{integration_id}` — list credentials
  linked to an integration
- `POST   /credentials/integrations/{integration_id}/associate` — link an
  existing credential
- `POST   /credentials` — create a credential without linking
- `GET    /credentials` — list credential metadata (no secrets)
- `GET    /credentials/{credential_id}` — fetch decrypted credential
  (audited, requires `integrations.update`)
- `POST   /credentials/{credential_id}/rotate` — re-encrypt with latest key
- `DELETE /credentials/{credential_id}`

---

## Setting Up an Integration

### Step 1 — Discover the type

```http
GET /v1/default/integrations/registry/splunk
```

The response includes `credential_schema` (what the credential form must
collect), `settings_schema` (non-secret configuration fields), and the full
`actions` array with each action's `params_schema` and `result_schema`.

### Step 2 — Create the instance

```http
POST /v1/default/integrations
Content-Type: application/json

{
  "integration_id": "splunk-prod",
  "integration_type": "splunk",
  "name": "Production Splunk",
  "description": "Main SIEM",
  "enabled": true,
  "settings": {
    "host": "splunk.example.com",
    "port": 8089,
    "use_ssl": true,
    "verify_ssl": false,
    "timeout": 60
  }
}
```

The shape of `settings` is governed by the type's `settings_schema`. Some
integrations support per-action setting overrides under
`settings.actions.<action_id>` (e.g., a different host for a write action vs
a read action). Check the type's `settings_schema` before assuming this is
available.

### Step 3 — Attach credentials

The combined endpoint creates the credential in Vault and links it to the
integration in one call:

```http
POST /v1/default/integrations/splunk-prod/credentials
Content-Type: application/json

{
  "provider": "splunk",
  "account": "splunk-prod",
  "secret": { "username": "admin", "password": "…" },
  "is_primary": true,
  "purpose": "admin"
}
```

Response contains `credential_id`, `provider`, `account`, `is_primary`,
`purpose`, `key_version`, and `created_at`. Pick the least-privileged
`purpose` the action actually needs.

### Step 4 — Test the connection

Use the synchronous execute endpoint from a "Test connection" button. This
runs the action in-process (subject to `timeout_seconds`) and returns the
result immediately — no polling loop required:

```http
POST /v1/default/integrations/splunk-prod/tools/health_check/execute
Content-Type: application/json

{ "arguments": {}, "timeout_seconds": 30 }
```

### Step 5 — Enable the managed schedule

Most integrations auto-create managed resources (e.g., `pull_alerts`,
`health_check`) when the instance is created. Inspect and enable them:

```http
GET /v1/default/integrations/splunk-prod/managed
PUT /v1/default/integrations/splunk-prod/managed/pull_alerts/schedule
Content-Type: application/json

{ "schedule_value": "5m", "enabled": true }
```

To trigger an ad-hoc run:

```http
POST /v1/default/integrations/splunk-prod/managed/pull_alerts/run
{ "params": { "lookback_seconds": 3600 } }
```

---

## UI Implementation Notes

### Service layer (`ui/src/services/integrationsApi.ts`)

All calls go through `withApi`/`fetchOne`/`mutateOne`, which attach auth
headers, strip the Sifnos envelope, and plug into the app's error-handling
system. Components should import from `integrationsApi`, **not** fetch
directly. Relevant exports:

| Function | Endpoint |
|---|---|
| `getIntegrationTypes` | `GET /integrations/registry` |
| `getIntegrationType` | `GET /integrations/registry/{type}` |
| `getIntegrationActions` | `GET /integrations/registry/{type}/actions` |
| `getIntegrations` | `GET /integrations` |
| `createIntegration` | `POST /integrations` |
| `getIntegration` | `GET /integrations/{id}` |
| `updateIntegration` | `PATCH /integrations/{id}` |
| `deleteIntegration` | `DELETE /integrations/{id}` |
| `enableIntegration` / `disableIntegration` | `POST /integrations/{id}/(en|dis)able` |
| `getIntegrationHealth` | `GET /integrations/{id}/health` |
| `provisionFreeIntegrations` | `POST /integrations/provision-free` |
| `getManagedResources` | `GET /integrations/{id}/managed` |
| `getManagedSchedule` / `updateManagedSchedule` | `GET|PUT /integrations/{id}/managed/{key}/schedule` |
| `triggerManagedRun` | `POST /integrations/{id}/managed/{key}/run` |
| `getManagedRuns` | `GET /integrations/{id}/managed/{key}/runs` |
| `getSchedules` / `deleteSchedule` | `GET /schedules`, `DELETE /schedules/{id}` |
| `createIntegrationCredential` | `POST /integrations/{id}/credentials` |
| `getIntegrationCredentials` | `GET /credentials/integrations/{id}` |
| `createCredential`, `getCredentials`, `getCredential`, `deleteCredential`, `associateCredentialWithIntegration` | corresponding `/credentials` routes |

### Integration types (`ui/src/types/integration.ts`)

The UI's `IntegrationInstance` extends the generated API type with three
UI-computed fields derived on the Integrations page:

- `health_status` — `'healthy' | 'degraded' | 'unhealthy' | 'unknown'`
- `last_run_at` — derived from recent managed runs
- `last_run_status` — `'completed' | 'failed' | 'running'`

`IntegrationTypeInfo.actions` is the authoritative source for what an
integration type can do.

### Run status polling

Ad-hoc managed runs return a `task_run_id` and an initial status. To poll
completion, re-fetch `GET /integrations/{id}/managed/{key}/runs` (or, for a
single run, use the Task Runs API). `ManagedRunItem` carries `status`,
`started_at`, `completed_at`, and `created_at` — use these for duration and
"last success" calculations.

### Health dashboard

`GET /integrations/{id}/health` returns:

```ts
type IntegrationHealth = {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  last_success_at?: string;
  success_rate_24h?: number;
  recent_failures?: number;
  message?: string;
};
```

The Integrations page fetches this per-integration and merges it into the
card view.

---

## Common Workflows

### Add an integration wizard
The canonical implementation is
[`IntegrationSetupWizard.tsx`](../src/components/integrations/IntegrationSetupWizard.tsx).
It drives a multi-step flow:

1. `getIntegrationTypes()` → pick a type
2. Render a credential form from the type's `credential_schema`
3. Render a settings form from the type's `settings_schema`
4. `createIntegration()` → then `createIntegrationCredential()`
5. Optionally call the tool-execute endpoint for a connection test
6. Optionally `updateManagedSchedule()` to enable recurring runs

### Troubleshoot a failing integration
1. `getIntegrationHealth(id)` — check `status` and `message`
2. `getManagedRuns(id, 'pull_alerts', { limit: 5 })` — inspect recent
   failures. Each item has `status`, `started_at`, `completed_at` on the
   TaskRun record.
3. For the full task-run detail (script, logs, artifacts) use the Task Runs
   API with `task_run_id`.
4. Trigger a test run: `triggerManagedRun(id, 'health_check')` or the
   synchronous `/tools/{action_id}/execute` endpoint with a small payload.

### Disable / re-enable
`POST /integrations/{id}/disable` cascades to the integration's schedules.
This is the right call for "pause" in the UI — it preserves config and
managed resources.

---

## Error Handling

Endpoints return standard `{detail: "..."}` errors on failure. The UI's
`useErrorHandler` / `runSafe` helpers already classify these. A few recurring
cases to handle explicitly:

- **409** on `POST /integrations` — integration_id already taken, **or**
  integration_type not supported (the router maps both to 409)
- **404** — integration, managed resource, schedule, or credential missing
- **400** on `PUT …/managed/{key}/schedule` — invalid `schedule_value`
  (format must be parseable by the interval scheduler, e.g. `"5m"`, `"1h"`)
- **500** on tool execute — inspect `result.error` in the response body for
  the underlying integration-level failure

---

## Testing Your UI

- Use `make test-integration-db` for service-layer tests that only need
  Postgres. The integration framework ships a fixture-based registry.
- For end-to-end UI tests, Playwright + the dev server at
  `http://localhost:5173` is the supported path (see `ui/CLAUDE.md`).
- To smoke-test the lab locally, provision free integrations (no
  credentials) once: `POST /integrations/provision-free`. Otherwise,
  `analysi-demo-loader` seeds Splunk / OpenLDAP / Echo EDR credentials and
  network access.

---

## Troubleshooting Common Issues

### Managed resource run never starts
1. Confirm the integration itself is `enabled`
2. Confirm the managed schedule is `enabled` and has a valid `schedule_value`
3. Check that the integrations-worker is running and consuming the ARQ queue
4. Review the latest entry in `getManagedRuns(...)` for the actual error

### "No schedule for this managed resource"
Not every managed resource has a schedule — health checks, for example, may
only be triggered on demand. The `managed_resources` block on the
integration detail will show `schedule_id: null` in that case.

### Credential errors
- 401 / auth errors from the target system: rotate via
  `POST /credentials/{id}/rotate` and re-test
- Missing fields: compare the submitted `secret` against the type's
  `credential_schema`

---

## Appendix: Registry API Tutorial

Concrete curl examples for the integration registry endpoints, useful
when building UI that discovers available integrations dynamically.
Assume `http://localhost:8001` and tenant `demo` below.

### 1. List all available integration types

```bash
curl -X GET "http://localhost:8001/v1/demo/integrations/registry"
```

Returns an array of `{integration_type, display_name, description, connectors}`.

### 2. Get detailed information for a specific integration

```bash
curl -X GET "http://localhost:8001/v1/demo/integrations/registry/splunk"
```

Returns the integration's `credential_schema`, `settings_schema`, and a
list of `connectors` each with its own `params_schema` and `result_schema`.

### 3. Get details for a specific connector

```bash
curl -X GET "http://localhost:8001/v1/demo/integrations/registry/splunk/actions/pull_alerts"
```

Includes `credential_scopes`, `default_schedule`, `params_schema`, and
`result_schema` for the connector.

### Understanding the schemas

- **credential_schema** — format of credentials required by the
  integration (e.g. username/password, API key). Drives dynamic
  credential forms in the UI.
- **settings_schema** — non-secret configuration like host, port, URLs.
  Stored in plaintext on the integration record.
- **params_schema** — inputs required to run a connector (provided at
  schedule-create time or manual run time).
- **result_schema** — shape of the connector's successful result; stored
  on the run record as `run_details`.

### 4. Get the default schedule for a connector

```bash
curl -X GET "http://localhost:8001/v1/demo/integrations/registry/splunk/actions/pull_alerts/default-schedule"
```

### 5. Create an integration instance (with typed settings)

```bash
curl -X POST "http://localhost:8001/v1/demo/integrations" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "splunk-prod",
    "integration_type": "splunk",
    "name": "Production Splunk",
    "enabled": true,
    "settings": {
      "host": "splunk.company.com",
      "port": 8089,
      "verify_ssl": false,
      "connectors": {
        "pull_alerts": { "enabled": true, "credential_id": null }
      }
    }
  }'
```

Per-connector setting overrides (e.g. a different `port` for HEC
vs management) are supported by placing them under
`settings.connectors.<connector_type>`.

### 6. Create a credential for the integration

```bash
curl -X POST "http://localhost:8001/v1/demo/integrations/splunk-prod/credentials" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "splunk",
    "account": "splunk-prod",
    "secret": { "username": "admin", "password": "secure-password" },
    "is_primary": true,
    "purpose": "admin"
  }'
```

The credential is auto-associated with the integration — no separate
association step.

### 7. Create a schedule

```bash
curl -X POST "http://localhost:8001/v1/demo/integrations/splunk-prod/managed/pull_alerts/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_type": "every",
    "schedule_value": "5m",
    "enabled": true,
    "params": { "lookback_seconds": 300 }
  }'
```

### 8. Trigger a connector run manually

```bash
curl -X POST "http://localhost:8001/v1/demo/integrations/splunk-prod/managed/pull_alerts/run" \
  -H "Content-Type: application/json" \
  -d '{ "run_type": "manual", "params": { "lookback_seconds": 86400 } }'
```

### Troubleshooting

- **404 on registry endpoints** — ensure paths are under
  `/integrations/registry/`, not the old `/connector-types/` or
  `/integration-types/` paths.
- **Invalid credential scope** — check the connector's
  `credential_scopes` array. Destructive connectors (e.g. `update_notable`)
  typically require `read/write` or `admin`.
- **Missing required parameters** — verify against the connector's
  `params_schema`. Fields with `"required": true` must be present.
