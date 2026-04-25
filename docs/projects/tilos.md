# Project Tilos — Control Event Bus

## Key Points

- **Transactional outbox**: A PostgreSQL `control_events` table acts as a durable event bus — producers INSERT a control event in the same DB transaction as their business logic, guaranteeing atomicity. "Control events" are system-internal coordination signals, not security events (SIEM telemetry, EDR alerts).
- **Control event rules (fan-out)**: A `control_event_rules` table lets operators configure Tasks or Workflows that fire in response to control events (e.g., `disposition:ready` → JIRA sync + Slack notification), added at runtime with zero code changes.
- **Two channel types**: Fan-out channels (`disposition:ready`, `analysis:failed`) dispatch to configured rules; internal channels (`workflow:ready`, `generation:failed`, `alert:analyze`) have a single hardcoded handler each.
- **`consume_control_events` ARQ cron**: Polls the control events table every 5-10s with `FOR UPDATE SKIP LOCKED`, dispatches by channel type, and marks events processed — competing workers get disjoint batches for free.
- **At-least-once delivery**: On crash the DB transaction rolls back and events return to pending, but Valkey enqueues already sent survive — so rule targets (Tasks/Workflows) must be idempotent using `event_id` as dedup key.
- **Reconciliation becomes safety-net only**: All event-driven work (resume paused alerts, retry failed generations) moves to control events; `reconcile_paused_alerts` keeps only timer-based stuck detection and orphan cleanup, cadence drops from 10s to 60s.
- **Generation retry via events**: `generation:failed` drives immediate retry with exponential backoff (5→10→20→40→80 min, max 5 attempts), replacing the polling-based retry logic buried in reconciliation.
- **Spec**: `docs/specs/ControlEventBus.md`

## Terminology

| Term | Definition |
|------|-----------|
| **Control event** | A row in the `control_events` table representing something that happened inside the system (e.g., analysis completed, generation failed). Inserted atomically with the business transaction. Distinct from security events (SIEM/EDR telemetry). |
| **Channel** | A string label on a control event that determines how it's dispatched (e.g., `disposition:ready`, `workflow:ready`). Analogous to a topic in pub/sub systems. |
| **Fan-out channel** | A channel whose events are dispatched to zero or more configured **control event rules**. Used for extensible reactions like output connectors. Channels: `disposition:ready`, `analysis:failed`. |
| **Internal channel** | A channel with a single hardcoded handler inside `consume_control_events`. Used for system coordination. Channels: `workflow:ready`, `generation:failed`, `alert:analyze`. |
| **Control event rule** | A row in the `control_event_rules` table that binds a (tenant, channel) pair to a Task or Workflow to execute when that event fires. Configured by operators at runtime. |
| **Target** | The Task or Workflow referenced by a control event rule. Identified by `target_type` (`task` \| `workflow`) and `target_id`. |
| **Producer** | Code that INSERTs a control event row — always within the same DB transaction as the business state change (e.g., `process_alert_analysis` emits `disposition:ready` in the same tx as marking analysis complete). |
| **Consumer** | The `consume_control_events` ARQ cron that polls `control_events WHERE status='pending'`, claims a batch with `FOR UPDATE SKIP LOCKED`, and dispatches each event. |
| **`run_control_event_rule`** | The ARQ job that executes a single rule's target (Task or Workflow) with an enriched payload. One job per rule per event. |
| **Enrichment** | The step inside `run_control_event_rule` that loads the full alert + analysis from DB before executing the target. Event payloads carry only IDs and summary; targets need full context. |
| **Idempotency key** | The `event_id` passed to every rule target. Targets must use it to deduplicate (e.g., check if JIRA ticket with this key exists before creating). Required because delivery is at-least-once. |
| **Safety net** | The remaining role of `reconcile_paused_alerts` after Tilos: timer-based detection of stuck/orphaned work that never emitted a control event (e.g., worker crash before commit). Runs at 60s cadence. |
