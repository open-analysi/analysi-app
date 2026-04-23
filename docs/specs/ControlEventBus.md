+++
version = "1.0"
date = "2026-02-17"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-02-17"
summary = "Transactional outbox event bus (Project Tilos)"
+++

# Control Event Bus - v1

## Overview

Introduces a **transactional outbox** pattern using a PostgreSQL `control_events` table as a durable event bus. "Control events" are system-internal coordination signals, distinct from security events (SIEM telemetry, EDR alerts). Two purposes:

1. **Control Event Rules** (primary): When the alert pipeline reaches a terminal state — disposition or failure — configured rules react independently. A JIRA sync Task, a Slack notification Workflow, a webhook push — all added and removed without modifying the analysis workflow.

2. **Internal coordination** (secondary): Replace scattered, fire-and-forget HTTP calls and ad-hoc Valkey pool management between workers with the same durable table.

```
  Analysis Pipeline                                  Control Event Rules
  ─────────────────                                  ───────────────────
  [pre-triage]
  [workflow builder]
  [workflow execution]        disposition:ready      ┌─ JIRA sync (Task)
  [disposition]          ─── control event ──────▶   ├─ Slack alert (Workflow)
       │                                             ├─ Webhook push (Task)
       │                                             └─ (add/remove at runtime)
       │
       │  (on failure)        analysis:failed        ┌─ PagerDuty (Workflow)
       └───────────────────── control event ─────▶   └─ Failure tracker (Task)
```

**Core insight**: The analysis workflow is responsible for *reaching a disposition* (or failing). What happens with that outcome is a separate concern. The workflow never knows about JIRA, Slack, or webhooks.

---

## Scope

### In Scope (v1)

- `control_events` table with monthly partitions
- `control_event_rules` table mapping (tenant, channel) → Task or Workflow to execute
- `consume_control_events` ARQ cron that dispatches fan-out channels only
- `run_control_event_rule` ARQ job that executes a Task or Workflow with enriched payload
- Fan-out channels: `disposition:ready`, `analysis:failed`
- REST API for managing control event rule configurations

### Deferred (originally in v1, moved to future work)

> See `TODO.md` — "Project Tilos: Full Control Event Bus"

- Internal channels: `workflow:ready`, `generation:failed`, `alert:analyze`
- Migration of `workflow_generation_job` from HTTP push → control event INSERT
- Slimming `reconcile_paused_alerts` to timer-based safety nets only

Rationale: reconciliation is stable and hard-won. Limiting v1 to disposition fan-out reduces risk and delivers the primary value (extensible output connectors) without touching the generation/reconciliation pipeline.

### Out of Scope (v1)

- Sub-second latency — 2-10s poll interval is acceptable
- User-initiated actions (POST /alerts/{id}/analyze) — keep direct ARQ enqueue for instant response
- Rule ordering guarantees — rules for the same event fire in parallel
- Rule retry policies — v1 fails fast; retry is a future concern
- UI for control event rule management — API only

---

## Architecture

```
  Producers                   control_events table      consume_control_events cron
  ─────────────               ────────────────────      ─────────────────────────────────────
                              ┌────────────┐
  process_alert_analysis      │            │  BEGIN TX
    analysis complete         │  channel   │  SELECT FOR UPDATE SKIP LOCKED (LIMIT 50)
        │                     │  tenant_id │ ◀────────────────────────────────────────
        ├──INSERT──────────▶  │  payload   │
        │  "disposition:ready"│  status    │  dispatch by channel type (tx still open):
        │  (same tx as        │  created_at│
        │   analysis update)  │  claimed_by│    INTERNAL channels
        │                     │  claimed_at│    (workflow:ready, generation:failed, alert:analyze)
    analysis fails            │            │      → single handler → enqueue_job() to Valkey
        │                     └────────────┘      → UPDATE control_event status='processed'
        └──INSERT──────────▶        │
           "analysis:failed"        │           FAN-OUT channels
           (same tx as              │           (disposition:ready, analysis:failed)
            status update)          │             → query control_event_rules
                                    │             → enqueue_job("run_control_event_rule")
  workflow_generation_job           │               per enabled rule (Task or Workflow)
    generation complete             │             → UPDATE control_event status='processed'
        │                           │
        ├──INSERT──────────▶  COMMIT TX
        │  "workflow:ready"
        │  (same tx as
        │   generation update)
    generation fails
        │
        └──INSERT──────────▶
           "generation:failed"
           (same tx as
            generation update)


  control_event_rules                                run_control_event_rule ARQ job
  ───────────────────                                ──────────────────────────────────
  tenant | channel           | target_type | target  1. Load control_event_rule config
  ───────┼──────────────────┼────────────┼────────   2. Enrich: load full alert + analysis from DB
  acme   | disposition:ready | task       | jira-    3a. Task → execute Cy script with payload
  acme   | disposition:ready | workflow   | slack-   3b. Workflow → execute_workflow with payload
  acme   | disposition:ready | task       | webhook  4. Rules MUST be idempotent
  acme   | analysis:failed   | workflow   | pager-      (at-least-once delivery)
```

---

## Database

### Table: `control_events`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, auto-generated |
| channel | TEXT | e.g., `"disposition:ready"`, `"workflow:ready"` |
| tenant_id | TEXT | Multi-tenancy scoping |
| payload | JSONB | Envelope with IDs + key fields |
| status | TEXT | `'pending'` \| `'processed'` \| `'failed'` |
| created_at | TIMESTAMPTZ | Partition key |
| claimed_by | TEXT | Worker instance ID for debugging |
| claimed_at | TIMESTAMPTZ | When claimed; used for stuck detection |

**Partitioning**: Monthly, `PARTITION BY RANGE (created_at)`. Cleanup by partition drop — no `DELETE` needed.

**Why monthly, not daily**: `max_locks_per_transaction = 64`. Existing daily-partitioned tables already consume most of the budget. Monthly = 12 extra locks/year vs 365 for daily.

**Indexes (per partition):**
- `(status, channel, created_at)` — consumer's hot path
- `(tenant_id, status, created_at)` — tenant-scoped monitoring queries

### Table: `control_event_rules`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, auto-generated |
| tenant_id | TEXT | Scoped per tenant |
| channel | TEXT | Which control event channel triggers this rule |
| target_type | TEXT | `'task'` \| `'workflow'` |
| target_id | UUID | FK to the Task or Workflow (component) to execute |
| config | JSONB | Rule-specific overrides (e.g., JIRA project key, webhook URL) |
| enabled | BOOLEAN | Soft enable/disable without deleting |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Indexes:**
- `(tenant_id, channel, enabled)` — the fan-out lookup at dispatch time

**Note**: This table is NOT partitioned. Volume is tiny (O(rules per tenant), operator-configured, not driven by alert volume).

**Credentials**: The `config` field holds non-secret overrides only (JIRA project key, Slack channel name, issue type). Secrets (API keys, webhook secrets, tokens) are stored in the **Credentials Store** and referenced by `credential_id` in the config:

```json
{
  "jira_project": "SEC",
  "issue_type": "Bug",
  "credential_id": "uuid → resolved at execution time via credential_service"
}
```

This is the same pattern used by integrations. `run_control_event_rule` calls `credential_service.get_credential(tenant_id, credential_id)` at execution time to decrypt secrets.

---

## Multi-Tenancy

Tenant isolation is strict. An event from tenant A must never trigger an action configured by tenant B.

### Enforcement Points

| Component | Isolation mechanism |
|-----------|-------------------|
| **Control event INSERT** (producer) | `tenant_id` is set by the producer from the current execution context (alert's tenant). Not user-supplied. |
| **`consume_control_events`** (consumer) | The consumer itself is tenant-unaware — it processes control events from all tenants in FIFO order. Tenant scoping happens at dispatch. |
| **Fan-out dispatch** | `control_event_rules` lookup uses `WHERE tenant_id = event.tenant_id AND channel = event.channel AND enabled = true`. The `tenant_id` comes from the control event row, not from any external input. |
| **`run_control_event_rule`** (enrichment) | All DB queries include `AND tenant_id = event.tenant_id` — even though UUIDs are globally unique, the tenant filter is mandatory as defense in depth. |
| **`run_control_event_rule`** (credential resolution) | `credential_service.get_credential(tenant_id, credential_id)` — the credential store enforces tenant scoping independently. A credential_id from tenant B would fail lookup for tenant A. |
| **`run_control_event_rule`** (target validation) | Before execution, verify that `target_id` (Task or Workflow) belongs to `event.tenant_id`. Prevents a misconfigured rule from executing another tenant's Task. |
| **REST API** | All endpoints scoped by `{tenant_id}` path parameter. Standard auth middleware enforces access. |
| **Internal channel handlers** | Operate on specific resource IDs (alert_id, generation_id). All DB queries include `tenant_id` from the event payload. |

### What the consumer does NOT do

The consumer does NOT filter control events by tenant. It processes all tenants' control events in a shared queue ordered by `created_at`. This is acceptable for v1 (single tenant, low volume). At production scale, a noisy tenant could delay others — see Future Considerations for per-tenant queuing.

---

## Event Channels

### Fan-Out Channels (rules dispatched via `control_event_rules`)

#### `disposition:ready`

**Producer**: `process_alert_analysis`, in the same DB transaction as marking analysis `status='complete'`.

**Payload:**
```json
{
  "alert_id": "uuid",
  "analysis_id": "uuid",
  "disposition": "true_positive | false_positive | ...",
  "severity": "critical | high | medium | low",
  "summary": "brief human-readable summary"
}
```

**Consumer**: Fan-out to all enabled `control_event_rules` for this tenant + channel. Each rule is enqueued as a separate `run_control_event_rule` ARQ job.

#### `analysis:failed`

**Producer**: `process_alert_analysis`, in the same DB transaction as marking analysis `status='failed'`.

**Payload:**
```json
{
  "alert_id": "uuid",
  "analysis_id": "uuid",
  "error_category": "workflow_execution | llm_error | timeout | internal",
  "error_message": "brief description"
}
```

**Consumer**: Same fan-out mechanism as `disposition:ready`. Operators can configure separate rules for failure notifications (PagerDuty, failure tracking dashboard) without needing to combine them into the happy-path workflow.

### Internal Channels (single handler, no `control_event_rules` lookup)

#### `workflow:ready`

**Producer**: `workflow_generation_job`, in the same DB transaction as marking the generation `status='success'`.

**Payload:**
```json
{
  "alert_id": "uuid",
  "analysis_id": "uuid",
  "workflow_generation_id": "uuid",
  "workflow_id": "uuid"
}
```

**Handler**: `try_resume_alert()` CAS → on success, `enqueue_job("process_alert_analysis", ...)`.

**Replaces**: HTTP POST to `/resume-paused-alerts` from inside `workflow_generation_job`.

#### `generation:failed`

**Producer**: `workflow_generation_job`, in the same DB transaction as marking the generation `status='failed'`.

**Payload:**
```json
{
  "alert_id": "uuid",
  "analysis_id": "uuid",
  "workflow_generation_id": "uuid",
  "error_message": "brief description",
  "retry_count": 2
}
```

**Handler**: Check retry budget (max 5, exponential backoff). If eligible → re-enqueue `execute_workflow_generation`. If exhausted → mark alert analysis as failed.

**Replaces**: The retry logic currently buried inside `reconcile_paused_alerts` that checks for failed generations, computes backoff, and re-queues. With control events, the retry decision happens immediately on failure instead of waiting up to 10s for the next reconciliation cycle.

#### `alert:analyze`

**Producer**: Internal system components (e.g., `kea_coordination` router) that need to trigger analysis from a different process.

**Payload:**
```json
{
  "alert_id": "uuid",
  "analysis_id": "uuid"
}
```

**Handler**: `enqueue_job("process_alert_analysis", ...)`.

---

## Control Event Rule Dispatch

### Transaction Model

`consume_control_events` holds a single DB transaction for the batch. `FOR UPDATE SKIP LOCKED` claim and `UPDATE status='processed'` are both within this transaction. Valkey enqueues happen inside the same Python scope but outside the DB transaction boundary.

**Crash consequence**: DB transaction rolls back, control events return to `pending`. Valkey enqueues that already succeeded stay in Valkey — those ARQ jobs will still execute. This is **at-least-once delivery**. Rule targets (Tasks and Workflows) must be idempotent.

### Dispatch Logic

```
BEGIN DB TRANSACTION

for each claimed control event:

  if channel in INTERNAL_CHANNELS:      # workflow:ready, generation:failed, alert:analyze
      handler = INTERNAL_DISPATCH[channel]
      await handler(event)               # enqueues to Valkey
      event.status = 'processed'

  elif channel in FAN_OUT_CHANNELS:     # disposition:ready, analysis:failed
      rules = query control_event_rules
              WHERE tenant_id = event.tenant_id
                AND channel   = event.channel
                AND enabled   = true

      for each rule:                     # empty list = silent no-op
          enqueue_job("run_control_event_rule",
              rule_id  = rule.id,
              event_id = event.id,
              payload  = event.payload)

      event.status = 'processed'

COMMIT DB TRANSACTION
```

### `run_control_event_rule` ARQ job

Executes a single rule target (Task or Workflow) with enriched payload:

1. Load `control_event_rule` by `rule_id`
2. **Tenant gate**: verify `control_event_rule.tenant_id == event.tenant_id`. Abort if mismatch (should never happen — indicates data corruption or bug).
3. **Target gate**: verify `target_id` (Task or Workflow) belongs to `event.tenant_id`. Abort if mismatch.
4. **Enrich**: load full alert + analysis records from DB, always with `WHERE tenant_id = event.tenant_id AND alert_id = ...` (defense in depth — never query by UUID alone across tenants)
5. **Resolve credentials**: if `config` contains `credential_id`, call `credential_service.get_credential(tenant_id, credential_id)` to decrypt secrets at execution time
6. Merge enriched context with rule `config` to form task/workflow input
7. **Execute by target_type**:
   - `task` → execute Cy script via Task runner, passing merged input
   - `workflow` → execute Workflow via `execute_workflow()`, passing merged input as `input_data`
8. Log outcome (success / failure + error message)

**Idempotency requirement**: Rule targets must handle being called more than once for the same `event_id` gracefully. Recommended pattern: use `event_id` as an idempotency key.

---

## Control Event Rule Configuration API

```
GET    /v1/{tenant_id}/control-event-rules
POST   /v1/{tenant_id}/control-event-rules
GET    /v1/{tenant_id}/control-event-rules/{id}
PATCH  /v1/{tenant_id}/control-event-rules/{id}
DELETE /v1/{tenant_id}/control-event-rules/{id}
```

**POST body:**
```json
{
  "channel": "disposition:ready",
  "target_type": "task",
  "target_id": "uuid of the Task or Workflow",
  "config": { "jira_project": "SEC", "issue_type": "Bug" },
  "enabled": true
}
```

Operators add a new reaction by creating a rule here — no code change, no workflow modification, no restart.

---

## What `reconcile_paused_alerts` Becomes

Today reconciliation is a monolith that handles both event-driven concerns (resume paused alerts, retry failed generations) and timer-based concerns (stuck detection, orphan cleanup). Control events absorb all the event-driven work. Reconciliation becomes purely **timer-based safety nets and maintenance**.

### Responsibilities that move to control events

| Responsibility | Before (reconciliation) | After (control events) |
|---|---|---|
| Resume paused alerts | Poll Kea API every 10s, check if workflow ready | `workflow:ready` control event → immediate resume |
| Retry failed generations | Detect failed generation, compute backoff, re-queue | `generation:failed` control event → immediate retry decision |
| Notify on analysis failure | Not done (silent failure) | `analysis:failed` control event → fan-out to configured rules |
| Notify on disposition | Not done | `disposition:ready` control event → fan-out to configured rules |

### Responsibilities that stay in reconciliation

All timer-based — these detect the *absence* of an expected event:

| Responsibility | Why it stays | Cadence |
|---|---|---|
| Stuck generation timeout (>35 min) | Generation job crashed without emitting `generation:failed` | 60s |
| Stuck running alerts (>60 min) | Analysis job crashed without emitting any terminal event | 60s |
| Mismatched status sync | HTTP call to update alert status failed (much rarer with control events, but still possible) | 60s |
| Orphaned workspace cleanup | Filesystem scan, no event source | 60s |
| Orphaned analysis detection | Timer-based, no event source | 60s |
| Partition maintenance | Scheduled maintenance | hourly |
| **Safety net**: paused alerts with completed generation | Catch-all for missed `workflow:ready` control events | 60s |

**New cadence**: 60s (was 10s). The reconciliation cron no longer needs to be fast because it's not the primary dispatch mechanism for anything.

---

## Component Changes

### New: `consume_control_events` ARQ cron (alert worker)

**Frequency**: Every 5-10 seconds. Separate cron from `reconcile_paused_alerts`.

Polls `control_events WHERE status='pending'`, claims a batch with `FOR UPDATE SKIP LOCKED`, dispatches by channel type, marks processed.

### New: `run_control_event_rule` ARQ job (alert worker)

Executes one rule target (Task or Workflow) per invocation. Must be idempotent.

### Modified: `process_alert_analysis` ARQ job

Two new event emission points, both transactional:

- **On success**: INSERT `disposition:ready` control event in the same tx as marking analysis `status='complete'`
- **On failure**: INSERT `analysis:failed` control event in the same tx as marking analysis `status='failed'`

### Modified: `workflow_generation_job`

Two new event emission points, both transactional:

- **On success**: INSERT `workflow:ready` control event in the same tx as marking generation `status='success'`
- **On failure**: INSERT `generation:failed` control event in the same tx as marking generation `status='failed'`

**Replaces**: HTTP POST to `/resume-paused-alerts` (success path) and the retry logic in reconciliation (failure path).

### Modified: `reconcile_paused_alerts`

Sheds event-driven work. Keeps timer-based safety nets. New cadence: 60s.

### Modified: `kea_coordination` router push endpoint

Switches from `try_resume_alert() + enqueue_job()` to INSERT `alert:analyze` control event.

### Unchanged

- `execute_task_build` ARQ job
- `try_resume_alert()` CAS — still called from the consumer, not bypassed
- User-initiated `POST /alerts/{id}/analyze` — direct ARQ enqueue
- Integration worker

---

## Scenarios

### Scenario 1: New Alert, New Analysis Group (Full Lifecycle)

First alert for a rule name the system has never seen. Exercises: workflow generation, `workflow:ready` internal control event, analysis pipeline, `disposition:ready` fan-out to two rules (one Task, one Workflow).

**Actors**: API Server, Alert Worker, PostgreSQL (PG), Valkey

```
[1]  API ← POST /alerts/{id}/analyze (user-initiated)
[2]  API → Valkey: enqueue_job("process_alert_analysis", alert_id=X)
     API → 202 Accepted (no control_events table involved — direct ARQ for user actions)

[3]  Alert Worker picks up process_alert_analysis(alert_id=X)
[4]  Worker → PG: lookup analysis_group for rule_name "brute-force-rdp"
     PG: not found
[5]  Worker → PG (single tx):
       INSERT analysis_groups (title="brute-force-rdp")
       INSERT workflow_generations (analysis_group_id=..., status='running')
     PG: COMMIT
[6]  Worker → PG (single tx):
       UPDATE alerts SET analysis_status='paused'
       UPDATE alert_analyses SET current_step='Workflow Builder'
     PG: COMMIT
[7]  Worker → Valkey: enqueue_job("execute_workflow_generation", wf_gen_id=G)

[8]  Alert Worker picks up execute_workflow_generation(wf_gen_id=G)
     [Kea orchestration runs: ~2-3 minutes, LLM calls, Task building]

[9]  Kea completes → Worker → PG (single tx):
       UPDATE workflow_generations SET status='success', workflow_id=W
       INSERT alert_routing_rules (analysis_group_id, workflow_id=W)
       INSERT control_events (channel='workflow:ready', tenant_id='acme',
                      payload={alert_id:X, analysis_id:A, workflow_id:W})
     PG: COMMIT

[10] consume_control_events fires (≤10s later)
     BEGIN TX
     PG: SELECT FOR UPDATE SKIP LOCKED → claims workflow:ready event
     Handler: try_resume_alert(alert_id=X) → CAS succeeds
       PG: UPDATE alerts SET analysis_status='analyzing'
     → Valkey: enqueue_job("process_alert_analysis", alert_id=X)
     PG: UPDATE control_events SET status='processed'
     COMMIT TX

[11] Alert Worker picks up process_alert_analysis(alert_id=X) [resumed]
     Step 2 (Workflow Builder): finds routing rule → workflow_id=W
     Step 3 (Workflow Execution): execute workflow W → run completes
     Step 4 (Disposition): LLM matches disposition → TRUE_POSITIVE

[12] Worker → PG (single tx):
       UPDATE alert_analyses SET status='complete', disposition='true_positive'
       UPDATE alerts SET analysis_status='completed'
       INSERT control_events (channel='disposition:ready', tenant_id='acme',
                      payload={alert_id:X, analysis_id:A,
                               disposition:'true_positive', severity:'high',
                               summary:'RDP brute force confirmed from ...'})
     PG: COMMIT

[13] consume_control_events fires (≤10s later)
     BEGIN TX
     PG: SELECT FOR UPDATE SKIP LOCKED → claims disposition:ready event
     PG: SELECT control_event_rules WHERE tenant_id='acme'
           AND channel='disposition:ready' AND enabled=true
         → [jira-rule (task), slack-rule (workflow)]
     → Valkey: enqueue_job("run_control_event_rule", rule_id=jira-rule, event_id=E)
     → Valkey: enqueue_job("run_control_event_rule", rule_id=slack-rule, event_id=E)
     PG: UPDATE control_events SET status='processed'
     COMMIT TX

[14] run_control_event_rule(jira-rule, event_id=E) [target_type=task]
     Load control_event_rule config: target_type='task', target_id=jira-sync-task
     Enrich from PG: full alert X + analysis A (title, NAS data, workflow output)
     Merge: {alert: ..., analysis: ..., config: {project:"SEC", issue_type:"Bug"}}
     Execute jira-sync Task (Cy script):
       app::jira::create_issue(project="SEC", summary=..., labels=...,
                               idempotency_key=event_id)
       → JIRA ticket SEC-4821 created
     Log: success

[15] run_control_event_rule(slack-rule, event_id=E) [target_type=workflow]
     Load control_event_rule config: target_type='workflow', target_id=slack-notify-wf
     Enrich from PG: full alert X + analysis A
     Merge: {alert: ..., analysis: ..., config: {channel:"#soc-alerts"}}
     Execute slack-notify Workflow (multi-step: format message → post → confirm):
       → Message posted to #soc-alerts with disposition details
     Log: success
```

**Outcome**: Alert analyzed, JIRA ticket created, Slack workflow executed. The analysis workflow has no idea JIRA or Slack exist.

---

### Scenario 2: Generation Fails, Retry via Event, Eventual Success

Workflow generation fails on first attempt. `generation:failed` event triggers immediate retry with backoff instead of waiting for the 10s reconciliation cycle. Second attempt succeeds.

```
[1]  Alert Worker picks up execute_workflow_generation(wf_gen_id=G, retry_count=0)
     [Kea orchestration runs, LLM call fails after 2 minutes]

[2]  Worker → PG (single tx):
       UPDATE workflow_generations SET status='failed',
              error_message='LLM rate limit exceeded'
       INSERT control_events (channel='generation:failed', tenant_id='acme',
                      payload={alert_id:X, analysis_id:A,
                               workflow_generation_id:G,
                               error_message:'LLM rate limit exceeded',
                               retry_count:0})
     PG: COMMIT

[3]  consume_control_events fires (≤10s later)
     BEGIN TX
     PG: SELECT FOR UPDATE SKIP LOCKED → claims generation:failed event
     Handler: check retry budget
       retry_count=0, max=5 → eligible
       backoff = 5 minutes (exponential: 5, 10, 20, 40, 80 min)
     → Valkey: enqueue_job("execute_workflow_generation", wf_gen_id=G,
                            retry_count=1,
                            _defer_by=300)  ← 5 min delay
     PG: UPDATE control_events SET status='processed'
     COMMIT TX

     [5 minutes pass]

[4]  Alert Worker picks up execute_workflow_generation(wf_gen_id=G, retry_count=1)
     [Kea orchestration runs again, succeeds this time]

[5]  Worker → PG (single tx):
       UPDATE workflow_generations SET status='success', workflow_id=W
       INSERT alert_routing_rules (analysis_group_id, workflow_id=W)
       INSERT control_events (channel='workflow:ready', tenant_id='acme',
                      payload={alert_id:X, analysis_id:A, workflow_id:W})
     PG: COMMIT

[6]  consume_control_events fires → claims workflow:ready event
     try_resume_alert(alert_id=X) → CAS succeeds
     → Valkey: enqueue_job("process_alert_analysis", alert_id=X)

[7]  Analysis continues from Step 3 (Workflow Execution) onward.
```

**Outcome**: Generation failed, retried after 5min backoff, succeeded on second attempt. Alert resumes automatically. No reconciliation cycle involved in the retry — the event drove it immediately.

**What reconciliation still catches**: If the worker crashes during step [2] before committing the event (e.g., OOM kill), no `generation:failed` event is emitted. The stuck generation timeout (>35 min) in reconciliation detects this and marks it failed. On the next reconciliation cycle, it can emit a `generation:failed` event itself or handle the retry directly — either works.

---

### Scenario 3: Analysis Fails, Failure Actions Fire + Crash Recovery

Analysis pipeline fails during workflow execution. `analysis:failed` control event triggers a PagerDuty escalation Workflow. Worker crashes mid-fan-out — demonstrates at-least-once delivery with Workflows.

```
[1]  Alert Worker runs process_alert_analysis(alert_id=X)
     Step 3 (Workflow Execution): workflow run fails
       → WorkflowExecutionError("node 'vt_ip_check' failed: timeout after 60s")

[2]  Worker → PG (single tx):
       UPDATE alert_analyses SET status='failed',
              error_message='Workflow execution failed: node vt_ip_check timeout'
       UPDATE alerts SET analysis_status='failed'
       INSERT control_events (channel='analysis:failed', tenant_id='acme',
                      payload={alert_id:X, analysis_id:A,
                               error_category:'workflow_execution',
                               error_message:'node vt_ip_check timeout'})
     PG: COMMIT

[3]  consume_control_events fires
     BEGIN TX
     PG: SELECT FOR UPDATE SKIP LOCKED → claims analysis:failed event
     PG: SELECT control_event_rules WHERE tenant_id='acme'
           AND channel='analysis:failed' AND enabled=true
         → [pagerduty-rule (workflow), failure-tracker-rule (task)]
     → Valkey: enqueue_job("run_control_event_rule", rule_id=pagerduty-rule, event_id=E)  ✓
     *** WORKER CRASHES ***
     DB: TX ROLLBACK → event E stays 'pending'
     Valkey: PagerDuty job already enqueued

[4]  run_control_event_rule(pagerduty-rule, event_id=E) [target_type=workflow]
     Load control_event_rule: target_type='workflow', target_id=pagerduty-escalation-wf
     Enrich: load full alert X + failed analysis A
     Execute PagerDuty escalation Workflow:
       Step 1: format incident details
       Step 2: app::pagerduty::create_incident(
                 service_id="P12345", severity="high",
                 dedup_key="analysi-event-{event_id}",   ← idempotency
                 title="Analysis failed: brute-force-rdp alert X")
       Step 3: confirm incident created
     Log: success, incident PD-89012 created

[5]  Worker restarts. consume_control_events fires again (≤10s)
     BEGIN TX
     PG: SELECT FOR UPDATE SKIP LOCKED → claims event E again (still 'pending')
     PG: SELECT control_event_rules → [pagerduty-rule, failure-tracker-rule]
     → Valkey: enqueue_job("run_control_event_rule", pagerduty-rule, event_id=E)    ← duplicate
     → Valkey: enqueue_job("run_control_event_rule", failure-tracker-rule, event_id=E) ← first time
     PG: UPDATE control_events SET status='processed'
     COMMIT TX

[6]  run_control_event_rule(pagerduty-rule, event_id=E) [second invocation]
     Execute PagerDuty workflow:
       dedup_key="analysi-event-{event_id}" → incident already exists
       Update existing incident (no duplicate)
     Log: success (idempotent)

[7]  run_control_event_rule(failure-tracker-rule, event_id=E) [first invocation]
     Load control_event_rule: target_type='task', target_id=failure-tracker-task
     Enrich: load full alert X + failed analysis A
     Execute failure-tracker Task:
       Record failure in tracking system with full context
     Log: success
```

**Outcome**: Analysis failed. PagerDuty incident created (handled duplicate from crash). Failure tracker recorded the failure. Both actions completed despite the crash.

---

## Failure Modes

### One rule fails, others unaffected

Each rule is a separate ARQ job. A JIRA API outage does not prevent the Slack notification from completing.

### Worker crashes mid-fan-out

DB transaction rolls back, control event returns to `pending`. Valkey enqueues that already happened stay in Valkey. On next cron tick, all rules are re-enqueued — some may run a second time. Rule targets must be idempotent. See Scenario 3.

### No rules configured for a channel

Control event is claimed, `control_event_rules` returns empty, event is marked `processed`. Silent no-op. Expected for tenants that haven't configured rules yet.

### Control events pile up (consumer stopped)

```sql
SELECT channel, count(*)
FROM control_events
WHERE status = 'pending' AND created_at > now() - interval '10 minutes'
GROUP BY channel;
```

At pre-production volume, a single cron cycle processes 50 control events in milliseconds. The safety net in `reconcile_paused_alerts` catches internal `workflow:ready` control events not consumed within 60s.

---

## File Locations

| Component | Path |
|-----------|------|
| DB Model: control events | `src/analysi/models/control_event.py` |
| DB Model: control event rules | `src/analysi/models/control_event_rule.py` |
| Repository: control events | `src/analysi/repositories/control_event.py` |
| Repository: control event rules | `src/analysi/repositories/control_event_rule.py` |
| `consume_control_events` cron | `src/analysi/alert_analysis/jobs/consume_control_events.py` |
| `run_control_event_rule` job | `src/analysi/alert_analysis/jobs/run_control_event_rule.py` |
| ARQ worker registration | `src/analysi/alert_analysis/worker.py` |
| Router: control event rules | `src/analysi/routers/control_event_rules.py` |
| Migration: control events table | `migrations/flyway/sql/V{next}__create_control_events.sql` |
| Migration: control event rules | `migrations/flyway/sql/V{next+1}__create_control_event_rules.sql` |

---

## Proposed Breakdown

1. **Migration + Models**: `control_events` table (monthly partitioned) and `control_event_rules` table. SQLAlchemy models and repositories for both.
2. **`consume_control_events` cron + internal channels**: Polling loop, internal dispatch (`workflow:ready`, `generation:failed`, `alert:analyze`), registration in `cron_jobs`. Integration test: INSERT control event → cron fires → appropriate handler called → event marked processed.
3. **Fan-out + `run_control_event_rule` job**: Rule config lookup, `run_control_event_rule` ARQ job with payload enrichment, support for both Task and Workflow targets. Integration test: control event emitted → two configured rules (one Task, one Workflow) → two ARQ jobs enqueued independently.
4. **Control event rule REST API**: CRUD endpoints with integration tests.
5. **`process_alert_analysis` control events**: Emit `disposition:ready` on success, `analysis:failed` on failure. Integration test: analysis completes → control event row visible → rules fire.
6. **`workflow_generation_job` control events**: Emit `workflow:ready` on success, `generation:failed` on failure with retry logic. Integration test: generation fails → control event → retry enqueued with backoff.
7. **`reconcile_paused_alerts` cleanup**: Remove event-driven logic, keep timer-based safety nets, slow cadence to 60s.

---

## Future Considerations

- **PG NOTIFY as wake-up hint**: Producer calls `pg_notify('control_events', '')` after INSERT. Consumer wakes immediately instead of waiting for the next poll tick. Average latency drops from ~5s to <100ms.
- **`workflow_run:completed` channel**: Eliminate the polling loop in `process_alert_analysis` Step 3. When the workflow engine completes a run, emit a control event. The pipeline splits into pre-workflow and post-workflow jobs with the control event as the bridge. Frees up worker threads during the minutes-long workflow execution. Bigger architectural change — future version.
- **Rule run history**: Record each `run_control_event_rule` execution (status, duration, error) linked to the rule config and control event. Enables operator dashboards showing connector health.
- **Retry policies per rule**: Max attempts, backoff strategy configured on `control_event_rules`.
- **Per-tenant queuing**: Consumer adds `WHERE tenant_id = ?` and round-robins across tenants, preventing a noisy tenant from starving others. Not needed for single-tenant pre-production.
- **Dead-letter queue**: Control events or rule runs that repeatedly fail moved to a separate table for manual inspection.
