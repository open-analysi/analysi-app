# Control Events & Reactions (Automation)

Analysi uses an event-driven automation system called the **Control Event Bus** (Project Tilos). When something significant happens — like an alert analysis completing — the system emits a control event. Users can create **reactions** (rules) that trigger tasks or workflows in response to these events.

## How It Works

```
Alert analysis completes
  → system emits "disposition:ready" event (same DB transaction)
  → consumer cron picks it up (≤30 seconds)
  → looks up all enabled rules for that channel + tenant
  → executes each rule's target (task or workflow) in parallel
```

This is a **transactional outbox pattern** — events are inserted in the same database transaction as the business state change, guaranteeing no events are lost even if the worker crashes.

## Event Channels

Two types of channels:

### Fan-Out Channels (user-configurable reactions)

| Channel | Fires when | Payload fields |
|---------|-----------|----------------|
| `disposition:ready` | Alert analysis completes with a disposition | `alert_id`, `analysis_id`, `disposition_id`, `disposition_display_name`, `confidence` |
| `analysis:failed` | Alert analysis fails | `alert_id`, `analysis_id`, `error` |

Users create **rules** on these channels to trigger downstream actions (JIRA tickets, Slack notifications, webhook calls, enrichment workflows, etc.).

### Internal Channels (system-managed, no user rules)

| Channel | Purpose |
|---------|---------|
| `human:responded` | HITL resume — human answered a paused task's question via Slack |
| `workflow:ready` | Workflow generation completed, resume paused alerts |
| `generation:failed` | Workflow generation failed, retry or mark analysis failed |
| `alert:analyze` | Trigger alert analysis programmatically |

Internal channels have hardcoded handlers — users cannot attach rules to them.

## Reactions (Control Event Rules)

A reaction is a rule that says: "When event X happens, run task/workflow Y."

### Creating a Reaction

```
POST /v1/{tenant_id}/control-event-rules
{
  "name": "Create JIRA ticket on true positive",
  "channel": "disposition:ready",
  "target_type": "task",         // or "workflow"
  "target_id": "<task-uuid>",
  "enabled": true,
  "config": {                    // passed to the task/workflow as input
    "jira_project": "SEC",
    "issue_type": "Bug"
  }
}
```

### What the Target Receives

When a rule fires, the target task or workflow gets this input:

| Field | Source | Description |
|-------|--------|-------------|
| All payload fields | Event | `alert_id`, `analysis_id`, `disposition_id`, etc. |
| `event_id` | Event | Idempotency key — use for deduplication in external systems |
| `config` | Rule | Operator-configured parameters (JIRA project, Slack channel, etc.) |

### Rule Execution

- All rules for an event fire **in parallel** (no ordering guarantees)
- Rules use **at-least-once delivery** with idempotency gates
- Failed rules are retried up to 3 times
- Rules already completed are skipped on retry (dispatch tracking table)
- Secrets (API keys, tokens) are never stored in `config` — they're resolved via credentials at runtime

### Managing Reactions

| Operation | Endpoint |
|-----------|----------|
| Create rule | `POST /v1/{tenant_id}/control-event-rules` |
| List rules | `GET /v1/{tenant_id}/control-event-rules` (filter by `channel`, `enabled_only`) |
| Get rule | `GET /v1/{tenant_id}/control-event-rules/{rule_id}` |
| Update rule | `PATCH /v1/{tenant_id}/control-event-rules/{rule_id}` |
| Delete rule | `DELETE /v1/{tenant_id}/control-event-rules/{rule_id}` |
| List channels | `GET /v1/{tenant_id}/control-event-channels` |

### Testing Reactions

You can manually emit an event to test rules without needing a real analysis:

```
POST /v1/{tenant_id}/control-events
{
  "channel": "disposition:ready",
  "payload": {
    "alert_id": "test-alert-id",
    "analysis_id": "test-analysis-id",
    "disposition_id": "some-uuid",
    "disposition_display_name": "true_positive",
    "confidence": 95
  }
}
```

The event enters the normal pipeline — picked up by the consumer cron, rules looked up, targets executed.

### Viewing Event History

```
GET /v1/{tenant_id}/control-events?channel=disposition:ready&status=completed&limit=20
```

Event statuses: `pending` → `claimed` → `completed` or `failed`.

## Common Use Cases

- **JIRA ticket on true positive**: Rule on `disposition:ready`, target is a Cy task that calls `jira.create_issue()`
- **Slack alert on failure**: Rule on `analysis:failed`, target is a task that calls `slack.send_message()`
- **Enrichment pipeline**: Rule on `disposition:ready`, target is a workflow that runs additional enrichment tasks
- **Webhook notification**: Rule on `disposition:ready`, target is a task that POSTs to an external URL

## Key Concepts

- **Transactional outbox**: Events are created in the same DB transaction as the state change — no lost events
- **At-least-once delivery**: Targets must be idempotent (use `event_id` as dedup key)
- **Fan-out**: One event can trigger many rules in parallel
- **Tenant isolation**: Rules and events are always scoped to a tenant
- **Monthly partitions**: Control events table is partitioned for performance; old events cleaned up by partition drop
