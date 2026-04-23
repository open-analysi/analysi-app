# Project Symi — Unified Scheduler and Actions

## Key Points

- **Connectors deprecated**: The `type: "connector" | "tool"` distinction in integration manifests is removed. Everything an integration can do is an **action** with `categories` for discovery. All actions are callable from Cy via `app::{integration}::{action}(...)`.
- **Generic scheduler**: `IntegrationSchedule` → `schedules` table that targets any Task or Workflow. Alert ingestion, health checks, and user-defined recurring automations share the same scheduling infrastructure.
- **Alert ingestion as a Task**: Each AlertSource integration gets an auto-created Task with a visible Cy script (`pull_alerts` → `alerts_to_ocsf` → `ingest_alerts`). Admins can view and modify it.
- **AlertSource archetype**: New archetype requiring `pull_alerts` and `alerts_to_ocsf` actions. Separate from SIEM — an EDR or custom webhook can also be an AlertSource.
- **Explicit persistence**: `ingest_alerts()` is a platform Cy function, not magic. The Task script explicitly calls it. `get_checkpoint()` / `set_checkpoint()` manage time cursors.
- **Task factory, not templates**: Python functions generate Tasks on integration setup. Output is a real, editable Task — no template model, no template-instance drift.
- **JobRun for scheduled runs only**: `IntegrationRun` → `job_runs` table tracks scheduled executions (Schedule → JobRun → TaskRun). Analysis runs and ad-hoc runs have their own lineage.
- **TaskRun.run_context**: `analysis | scheduled | ad_hoc` — the default task runs list excludes `scheduled` to keep integration noise out of the troubleshooting view.
- **Managed resources API**: `/integrations/{id}/managed/{resource_key}/task|schedule|runs` — convenience endpoints scoped to an integration for viewing and managing its auto-created Tasks and Schedules.
- **Integration lifecycle cascades**: Create → auto-create Tasks + Schedules (disabled). Enable → enable schedules. Disable → stop schedules. Delete → cleanup.
- **Spec**: `docs/specs/UnifiedSchedulerAndActions.md`

## Locked Decisions

Decisions validated against the codebase and locked for implementation:

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Everything is an **action** — no connector/tool distinction | Eliminates confusing terminology. `categories` field replaces `type` + `purpose`. 8 code locations need update (registry_service, integration_tools, models). |
| 2 | `alerts_to_ocsf()` is an **integration action** (AlertSource archetype), not a generic Cy function | Normalization is integration-specific. Each AlertSource implements its own. |
| 3 | `ingest_alerts()` is an **explicit platform Cy function** — no magic persistence | User sees exactly what happens in the Task script. Handles dedup + persist + control event emission. |
| 4 | **Task factory** functions, no template model | Generates real editable Tasks on integration setup. No template-instance drift problem. |
| 5 | `origin_type` field on Tasks and Schedules: `system \| user \| pack` | Transparency about who created it. Not access control — admins can edit system tasks. |
| 6 | **Checkpoints** use a dedicated `task_checkpoints` table, not TaskRun.execution_context | Must persist across runs (run N's cursor → run N+1's start). execution_context is per-run. |
| 7 | **Scheduler cron** runs on Integrations worker (DB 5), **task execution** on Alert Analysis worker (DB 0) | Timeout mismatch: scheduler is 300s lightweight polling, tasks need 3600s. Scheduler enqueues across worker boundary. |
| 8 | Scheduler uses **direct DB** with `FOR UPDATE SKIP LOCKED`, not REST API calls | Current scheduler uses HTTP round-trips. Direct DB enables transactional guarantees and eliminates latency. |
| 9 | `next_run_at` is **pre-computed** (new behavior, replaces `last_run_at` + interval comparison) | Enables indexed query `WHERE enabled=true AND next_run_at <= now()`. Better at scale. |
| 10 | **Workflows are in scope** as schedule targets alongside Tasks | One-line branch in scheduler (`execute_task_run` vs `execute_workflow_run`). No reason to defer. |
| 11 | **Health checks are Tasks** that produce TaskRuns | One execution path. No lightweight/separate health check runner. `run_context="scheduled"` keeps them filtered. |
| 12 | Health status from **return value**, not TaskRun status | `completed + healthy=true` → healthy. `completed + healthy=false` → unhealthy. `failed` → unknown (platform issue, not integration issue). Three-state model. |
| 13 | Health check actions **catch their own errors** and return `{"healthy": false}` | Only infrastructure failures produce failed TaskRuns. Integration failures are reported, not thrown. |
| 14 | Convenience schedule endpoints: `POST /tasks/{id}/schedule`, `POST /workflows/{id}/schedule` | Natural UX. User doesn't need to know about the generic schedules table. |
| 15 | Credentials configured **separately after** integration creation | Tasks + Schedules created `enabled=false`. Admin configures credentials, then enables integration. |
| 16 | **Knowledge building** is a content pack concern, not integration lifecycle | Integration provides the action (`get_assets`). Content pack provides the Task that calls it. |
| 17 | **No backwards compatibility** needed for migration | Clean rename: `integration_schedules` → `schedules`, `integration_runs` → `job_runs`. |
| 18 | Only **Splunk** gets AlertSource in v1 | 1 of 40 integrations has alert ingestion today. Others adopt incrementally. |
| 19 | **Dedicated `task_checkpoints` table**, not KU Tables | KU Tables require 3-way joins (Component → KnowledgeUnit → KUTable) and full JSONB content replacement per write. Checkpoints need atomic upsert on a unique index every ~60s. `task_checkpoints` gives O(1) lookup via `UNIQUE(tenant_id, task_id, key)` and PostgreSQL `INSERT ... ON CONFLICT UPDATE`. |
| 20 | **Input vs configuration deferred** to push-based execution | Polling tasks (alert ingestion, health checks) are self-contained — they get state from checkpoints, not external input. Clean separation of `input` (data to process) vs `configuration` (how to process) matters for push-based tasks triggered by control events or webhooks. Not needed for v1 scheduled polling. |

## Terminology

| Term | Definition |
|------|-----------|
| **Action** | Anything an integration can do: pull alerts, health check, update a notable, isolate a host. Replaces both "connector" and "tool." Defined in the integration manifest and callable via `app::{integration}::{action}()`. |
| **AlertSource** | An archetype for integrations that produce security alerts. Requires `pull_alerts` (fetch raw events) and `alerts_to_ocsf` (normalize to OCSF). SIEMs, EDRs, and custom sources can all be AlertSources. |
| **Schedule** | A row in the `schedules` table that fires a Task or Workflow on a recurring interval. Replaces `IntegrationSchedule`. Has `origin_type` to distinguish system-managed (auto-created) from user-created. |
| **JobRun** | An audit record created each time a Schedule fires. Links the schedule to the resulting TaskRun or WorkflowRun. Only exists for scheduled executions — analysis and ad-hoc runs have their own lineage. Replaces `IntegrationRun`. |
| **run_context** | A field on `TaskRun` indicating why the run happened: `analysis` (alert processing workflow), `scheduled` (timer-based), or `ad_hoc` (human-initiated). Used for default filtering in the task runs list. |
| **Managed resource** | A Task + Schedule that the platform auto-created for an integration (e.g., alert ingestion, health check). Accessible via the integration's managed resources API. Editable by admins. |
| **Task factory** | A Python function that generates a Task when an integration is configured. Not a template — the output is a real Task with no reference back to a factory. |
| **Checkpoint** | A key-value pair scoped to (tenant, task) that persists cursor state between scheduled runs. Written by `set_checkpoint()` in the Cy script. Only advances on successful completion. |
| **origin_type** | A field on Tasks and Schedules indicating who created them: `system` (platform auto-created), `user` (human-created), or `pack` (content pack). Used for UI indicators, not access control — admins can edit system tasks. |
