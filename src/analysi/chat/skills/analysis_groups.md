# Analysis Groups & Dynamic Workflow Generation

Analysis groups are the mechanism behind Analysi's core capability: **automatically generating investigation workflows for new alert types**. When an alert arrives with a `rule_name` the system hasn't seen before, it creates an analysis group, generates a custom workflow, and routes all future alerts of that type through it.

## Key Assumption

**All alerts with the same `rule_name` require the same investigation workflow.** A "Suspicious Login Attempt" alert from Splunk always needs the same investigation steps — regardless of which user or IP triggered it. The workflow is generated once for the first alert of that type and reused for every subsequent instance. Individual alert data (the specific IP, user, timestamp) is passed as input to the workflow at execution time, but the investigation structure stays the same.

This is what makes the system scalable: instead of generating a new workflow per alert (expensive, slow), we generate one per alert *type* and amortize the cost across all future instances.

## The Problem

Security teams get alerts from many detection rules. Each rule type needs a different investigation workflow — a phishing alert needs email header analysis, sender reputation, and URL detonation; a brute force alert needs login pattern analysis, geo-IP lookup, and account lockout status. Building workflows manually for every rule type doesn't scale.

## How Analysis Groups Solve It

```
Alert arrives (rule_name = "Suspicious Login Attempt")
  → System checks: do we have a workflow for this rule_name?
  ├→ YES: route alert to existing workflow, execute immediately
  └→ NO:
      → Create analysis group (title = rule_name)
      → Pause alert (status = "paused_workflow_building")
      → Start AI-powered workflow generation (4-stage pipeline)
      → When done: create routing rule, resume all paused alerts
      → Future alerts with same rule_name use the generated workflow
```

Over time, the library of reusable tasks and workflows grows organically as the system encounters new alert types.

## Core Concepts

### Analysis Group
A grouping entity for alerts of the same type. One group per `(tenant, rule_name)`.

- **Created automatically** when a new alert type is first encountered
- **Title** matches the alert's `rule_name` field
- **Unique per tenant** — each tenant has independent groups

### Workflow Generation
The AI-powered process that creates a custom investigation workflow for an analysis group. Goes through 4 stages:

| Stage | What happens |
|-------|-------------|
| **Runbook generation** | AI analyzes the alert type and generates an investigation runbook (markdown) |
| **Task proposals** | AI extracts concrete task proposals from the runbook |
| **Task building** | Each proposed task is built as a Cy script (runs in parallel) |
| **Workflow assembly** | Tasks are composed into a DAG workflow with proper data flow |

Generation status: `running` → `completed` or `failed`.

### Alert Routing Rule
Maps an analysis group to a workflow. Once a routing rule exists, all future alerts with that `rule_name` are routed to the generated workflow without any AI calls.

- One routing rule per analysis group
- Created automatically when workflow generation completes
- **Authoritative source** for workflow mapping (takes priority over generation records)

## Lifecycle

### First Alert of a New Type

1. Alert ingested with `rule_name = "Suspicious Login Attempt"`
2. `WorkflowBuilderStep` checks cache → miss
3. API call: `POST /analysis-groups/with-workflow-generation` (atomic creation)
4. Alert marked `paused_workflow_building`
5. AI orchestration job runs the 4-stage pipeline
6. On completion: routing rule created, `POST /analysis-groups/{id}/resume-paused-alerts`
7. All paused alerts for this group resume and execute with the new workflow

### Subsequent Alerts of the Same Type

1. Alert ingested with same `rule_name`
2. `WorkflowBuilderStep` checks cache → hit (group exists, routing rule exists)
3. Alert routed directly to the existing workflow — no AI, no generation, no pause

### Race Conditions

Multiple alerts with the same new `rule_name` may arrive simultaneously:
- Database UNIQUE constraint `(tenant_id, title)` prevents duplicate groups
- Second worker catches `IntegrityError`, looks up the existing group instead
- All concurrent alerts pause on the same group, resume together when generation completes

## Progress Tracking

Track generation progress via the API:

```
GET /v1/{tenant_id}/workflow-generations/{generation_id}
```

Response includes `progress.phases` — an array of 4 stages, each with:
- `status`: `not_started` | `in_progress` | `completed`
- `started_at` / `completed_at`: timestamps
- `tasks_count`: (task_building stage only) number of tasks being built

When generation finishes, `orchestration_results` contains:
- `runbook`: the generated investigation runbook
- `task_proposals`: proposed tasks extracted from the runbook
- `tasks_built`: results of task building
- `workflow_composition`: the final workflow structure
- `metrics`: execution stats (duration, cost, number of LLM turns)

## API Reference

### Analysis Groups

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/{tenant_id}/analysis-groups` | Create group |
| `GET` | `/v1/{tenant_id}/analysis-groups` | List groups |
| `GET` | `/v1/{tenant_id}/analysis-groups/{id}` | Get group |
| `DELETE` | `/v1/{tenant_id}/analysis-groups/{id}` | Delete group (cascades to generations + rules) |
| `POST` | `/v1/{tenant_id}/analysis-groups/with-workflow-generation` | Atomic: create group + start generation |
| `GET` | `/v1/{tenant_id}/analysis-groups/active-workflow?title={rule_name}` | Check if workflow exists for a rule_name |
| `POST` | `/v1/{tenant_id}/analysis-groups/{id}/resume-paused-alerts` | Resume alerts paused for this group |

### Workflow Generations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/{tenant_id}/workflow-generations` | List generations |
| `GET` | `/v1/{tenant_id}/workflow-generations/{id}` | Get generation with progress + results |
| `PATCH` | `/v1/{tenant_id}/workflow-generations/{id}/progress` | Update stage progress |
| `PUT` | `/v1/{tenant_id}/workflow-generations/{id}/results` | Set final results |

### Alert Routing Rules

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/{tenant_id}/alert-routing-rules` | List routing rules |
| `POST` | `/v1/{tenant_id}/alert-routing-rules` | Create routing rule |
| `GET` | `/v1/{tenant_id}/alert-routing-rules/{id}` | Get routing rule |
| `DELETE` | `/v1/{tenant_id}/alert-routing-rules/{id}` | Delete routing rule |

## Regeneration

If a generated workflow isn't working well, you can regenerate it:
- The old generation is deactivated (`is_active = false`) but preserved for audit
- A new generation runs the 4-stage pipeline again
- The routing rule is updated to point to the new workflow
- Only one generation is active per group at a time

## Safety Nets

- **Reconciliation job** (10-second cadence): finds alerts stuck in `paused_workflow_building` and checks if their workflow is ready
- **Stuck generation detection**: generations in `running` state for >60 minutes are marked failed
- **Retry with backoff**: failed generations retry with exponential backoff (5m, 10m, 20m, 40m)
- **Push-based resume**: generation job immediately resumes paused alerts on completion (doesn't wait for reconciliation polling)

## Caching

An in-memory cache maps `(tenant_id, rule_name)` → `(group_id, workflow_id)` to avoid database lookups for known alert types. The cache is tenant-isolated and invalidated when workflow generation completes.
