+++
version = "2.0"
status = "active"

[[changelog]]
version = "2.0"
summary = "v2 — @tracked_job decorator, RunStatus (Project Leros)"
+++

# Unified Job Execution Framework

Spec Version: 2
Project Codename: Leros

## Problem Statement

The Analysi backend has 8 distinct async/scheduled execution patterns across 9 database tables, each independently implementing status tracking, stuck detection, retry logic, error storage, timeout handling, and structured logging. This duplication (estimated ~200 lines of repeated boilerplate across 6 ARQ job functions) increases maintenance cost, creates inconsistent observability, and makes it harder to reason about system health. Additionally, two execution paths (`asyncio.create_task()` in the API process) have zero durability — a pod restart silently loses in-flight work.

## Goals

- **G1**: A `@tracked_job` decorator eliminates cross-cutting boilerplate (correlation ID, tenant context, structured logging, timeout, duration, `job_tracking` JSONB persistence) from all ARQ job functions — estimated 60% of per-job boilerplate.
- **G2**: A shared `RunStatus` enum and a standardized `job_tracking JSONB` column on every run/status table. Each domain table keeps its own columns; Leros adds one JSONB sidecar for framework metadata (`attempt`, `errors`, `worker_id`, `duration_ms`, etc.). No individual column sprawl — new tracking fields go into the JSONB without migrations.
- **G3**: A config-driven stuck detection function replaces the simple threshold-based detectors in reconciliation, with `max_attempts` support for retry-then-fail semantics. Complex detectors (HITL timeout with cross-table joins, orphaned analyses) stay as named functions sharing a small utility.
- **G4**: Task execution and workflow execution move from `asyncio.create_task()` to ARQ jobs, gaining durability, retry, and visibility.
- **G5**: Kalymnos's pause/resume/checkpoint patterns (already merged via PR #29) integrate cleanly with the shared abstractions. Former Phase 4 dissolved — items distributed across Phases 1-2.

## Non-Goals

- Replacing ARQ with another queue (Celery, Temporal, DBOS). ARQ + Valkey stays.
- Full durable execution with deterministic replay (Temporal-style). Step checkpointing at the Cy interpreter level (Kalymnos) is sufficient.
- Changing the control event bus architecture (Project Tilos). It stays as the trigger/dispatch layer.
- Real-time job streaming or WebSocket-based progress (future work).
- Changing the `reconcile_paused_alerts` cron cadence or the `consume_control_events` cron. Their scheduling stays the same.
- A unified `job_runs` table replacing per-domain tables. The federated approach (separate tables, shared `job_tracking` JSONB) gives 80% of the benefit at 20% of the cost. Domain tables keep their domain columns and relationships naturally.

---

## Architecture: Tilos × Leros

Tilos (control event bus) and Leros (job execution framework) are complementary layers
in the same stack:

```
┌─────────────────────────────────────────────┐
│  Trigger Layer (REST API, Slack, Cron)      │  "something happened"
├─────────────────────────────────────────────┤
│  Tilos — Control Event Bus                  │  "who needs to know?"
│  • emit event → poll → dispatch to rules    │
│  • idempotency via dispatch table           │
│  • fan-out (N rules) or internal (1 handler)│
├─────────────────────────────────────────────┤
│  Leros — Job Execution                      │  "do the work reliably"
│  • @tracked_job (logging, timeout, context) │
│  • job_tracking JSONB persistence           │
│  • stuck detection with max_attempts        │
│  • ARQ as durable dispatch mechanism        │
└─────────────────────────────────────────────┘
```

### `execute_control_event` — the boundary job

`execute_control_event` sits at the boundary between the two systems. It is a **Tilos
component** (dispatches events to handlers and rules) that is also one of **Leros's 6
target jobs** (gets `@tracked_job` for observability). When wrapped with the decorator,
we're tracking the dispatch lifecycle ("did the event get processed?"), not the
task/workflow execution inside it.

### Nested jobs after Phase 3

Today, `_execute_task_rule` and `_execute_workflow_rule` call task/workflow execution
**synchronously inside** the control event job. The control event blocks for the full
execution duration (up to 60min):

```
consume_control_events (Tilos cron, polls every 30s)
  → execute_control_event (Tilos dispatch, @tracked_job)
    → rule matches
      → _execute_task_rule → execute_single_task() [synchronous, blocks]
      → event can't complete until task finishes
```

After Phase 3, rule execution will **enqueue an ARQ job** instead of blocking:

```
consume_control_events (Tilos cron)
  → execute_control_event (Tilos dispatch, @tracked_job)
    → rule matches
      → _execute_task_rule → redis.enqueue_job("execute_task_run") [returns immediately]
      → event completes in milliseconds
        → execute_task_run (@tracked_job, separate ARQ job)
```

This creates two nested Leros jobs: the outer one tracks dispatch, the inner one tracks
execution. Both get `@tracked_job`. Both get stuck detection. If the inner job fails,
the outer job still completes (dispatch worked).

### Semantic change in Phase 3

This is a deliberate behavior change:

| Aspect | Today (pre-Phase 3) | After Phase 3 |
|--------|---------------------|---------------|
| Control event blocks for | Full task/workflow execution | Just the enqueue |
| Control event failure means | Task failed OR dispatch failed | Only dispatch failed |
| Task failure tracking | Via control event status | Via TaskRun status (separate) |
| Task failure retry | Control event re-claimed by cron | Stuck detection on TaskRun |
| Control event completion time | Minutes | Milliseconds |

This is acceptable because:
- The control event's responsibility is **dispatch**, not execution
- Task/workflow failures are already tracked in their own run tables
- Stuck detection (Phase 2) catches orphaned TaskRuns/WorkflowRuns
- The system becomes more resilient — a slow task no longer blocks the event queue

### What each system owns

| Concern | Owner | Notes |
|---------|-------|-------|
| Event emission | Tilos | `control_events` table rows |
| Event dispatch + idempotency | Tilos | `consume_control_events` cron + dispatch table |
| Rule matching | Tilos | `control_event_rules` table |
| Job observability | Leros | `@tracked_job` on both dispatch and execution jobs |
| Job stuck detection | Leros | `STUCK_JOB_REGISTRY` entries for both |
| Task/workflow execution | Domain | `TaskExecutionService`, `WorkflowExecutor` |
| Pause/resume (HITL) | Kalymnos | Checkpoint storage, three-layer propagation |

---

## Current Landscape (Audit Summary)

### 9 Run/Status Tables

| Table | Status Values | Has `attempt`? | Has `max_attempts`? | Has `errors` JSONB? | Has `claimed_at`? | Has `error_message`? | Partitioned? |
|-------|--------------|----------------|--------------------|--------------------|-------------------|---------------------|--------------|
| `task_runs` | pending, running, completed, failed, paused_by_user, cancelled | No | No | No | No | No (uses execution_context) | Daily |
| `workflow_runs` | pending, running, completed, failed, cancelled | No | No | No | No | Yes (TEXT) | Daily |
| `workflow_node_instances` | pending, running, completed, failed, cancelled | No | No | No | No | Yes (TEXT) | Daily |
| `integration_runs` | running, completed, failed, paused_by_user, cancelled | **Yes** | **Yes** | No | No | No (uses run_details JSONB) | Monthly |
| `task_building_runs` | pending, in_progress, completed, failed, cancelled | No | No | No | No | No (uses result JSONB) | None |
| `content_reviews` | pending, approved, flagged, applied, rejected, failed | No | No | No | No | Yes (TEXT) + error_code + error_detail | None |
| `control_events` | pending, claimed, completed, failed | No (has retry_count) | No | No | **Yes** | No | Monthly |
| `workflow_generations` | running, completed, failed | No | No | No | No | No (uses orchestration_results JSONB) | None |
| `alert_analysis` | running, paused_workflow_building, paused_human_review, completed, failed, cancelled | No | No | No | No | No (uses steps_progress JSONB) | Daily |

### 6 Status Enums (Fragmented)

| Enum | Location | Values |
|------|----------|--------|
| `TaskConstants.Status` | `constants.py` | pending, running, completed, failed, paused |
| `WorkflowConstants.Status` | `constants.py` | pending, running, completed, failed, cancelled, paused |
| `IntegrationRunStatus` | `schemas/integration.py` | running, completed, failed, paused_by_user, cancelled |
| `AnalysisStatus` | `schemas/alert.py` | running, paused_workflow_building, paused_human_review, completed, failed, cancelled |
| `ContentReviewStatus` | `models/content_review.py` | pending, approved, flagged, applied, rejected, failed |
| `ControlEventConstants.Status` | `constants.py` | pending, claimed, completed, failed |

### 6 ARQ Job Functions — Repeated Boilerplate

Every job function repeats 5 patterns:

| Pattern | process_alert_analysis | execute_workflow_generation | execute_task_build | execute_control_event | execute_content_review | run_integration |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| set_correlation_id() | Yes | Yes | **No** | Yes (partial) | Yes | Yes |
| set_tenant_id() | Yes | Yes | **No** | **No** | Yes | Yes |
| Start logging | Yes | Yes | Yes | **No** | Yes | Yes |
| try/except + status update | Yes | Yes | Yes | Yes | Yes | Yes |
| Completion logging | Yes | Yes | Yes | **No** | Yes | Yes |

**Missing from some jobs**: `execute_task_build` has no correlation/tenant setup. `execute_control_event` has no tenant context or start/completion logging.

### 4+ Stuck Detectors (Hand-Rolled)

| Detector | Table | Status Check | Timeout | Action | Generic? |
|----------|-------|-------------|---------|--------|----------|
| Stuck workflow generations | `workflow_generations` | `running` | 60min | Mark `failed` | Yes |
| Stuck running alerts | `alert_analyses` | `running` | 60min | Mark `failed` | Yes |
| Stuck content reviews | `content_reviews` | `pending` | 20min | Mark `failed` | Yes |
| Stuck control events | `control_events` | `claimed` | 1h | Reset to `pending` (retry) | Yes |
| Orphaned analyses | `alert_analyses` | `running` + no progress | 2min | Mark `failed` | No (extra SQL condition) |
| HITL-paused analyses | `alert_analyses` | `paused_human_review` | 24h | Mark `failed` | No (cross-table join + race guard) |
| Mismatched statuses | `alerts` + `alert_analyses` | Cross-table mismatch | N/A | Sync | No (domain-specific) |

**Key insight**: The first 3 detectors mark as `failed` (terminal — the job is dead). The 4th (control events) resets to `pending` (retry — put it back in the queue). Today the retry has no cap — infinite re-queue. Leros adds `max_attempts` to support both patterns in a single config.

### 2 Fire-and-Forget `asyncio.create_task()` (No Durability)

| Location | What's Spawned | DB Status If Pod Restarts |
|----------|---------------|--------------------------|
| `routers/task_execution.py:207,283` | `execute_and_persist()` | TaskRun stuck `running` forever |
| `services/workflow_execution.py:220` | `_execute_workflow_synchronously_delayed()` | WorkflowRun stuck `pending` forever |

### 3 Retry Mechanisms (Incompatible)

| Mechanism | Used By | How It Works |
|-----------|---------|-------------|
| Database-backed + cron re-queue | Workflow generation | `retry_count` column, exponential backoff (5/10/20 min), reconciliation cron re-queues |
| Database-backed + cron re-claim | Control events | `retry_count` column, `consume_control_events` cron re-claims failed events |
| No retry | Content review, task build, integration runs | Fire once, mark failed on exception |

### 5 Tenacity Retry Policies (Well-Structured, Keep As-Is)

| Policy | Max Attempts | Backoff | Used For |
|--------|-------------|---------|----------|
| `http_retry_policy` | 3 | 1-10s exponential | REST API calls from jobs |
| `storage_retry_policy` | 3 | 2-10s exponential | S3/MinIO operations |
| `database_retry_policy` | 3 | 1-10s exponential | DB connection errors |
| `llm_retry_policy` | 5 | 2-60s exponential | LLM API calls |
| `polling_retry_policy` | time-based (120s) | 0.5-2s exponential | Workflow polling |

These are fine-grained operation-level retries. They stay as-is. Leros addresses **job-level** retry (the whole job failed, should we re-run it?).

---

## Requirements

### Phase 1: `@tracked_job` Decorator + `RunStatus` Enum + `job_tracking` JSONB

- **R1**: `@tracked_job` decorator wraps an ARQ job function. Before execution: generates correlation ID, sets tenant context, reads current `job_tracking` from DB (increments `attempt`), logs structured start event. After execution: writes `job_tracking` JSONB with final state (duration, status, errors), logs structured completion event. On exception: logs structured failure event with error type, duration, and exc_info. On recognized pause exception: logs structured pause event.
- **R2**: Pause exception recognition: the decorator accepts an optional `pause_exceptions` parameter (tuple of exception types). When the job raises one of these, the decorator logs `job_paused` instead of `job_failed` and re-raises. Domain code handles pause state (checkpoint storage, HITL question creation). Jobs without pause semantics omit this parameter. **Important caveat**: `process_alert_analysis` handles pause via return values, not exceptions — the pipeline catches `WorkflowPausedForHumanInput` internally and returns a status dict. The decorator sees this as a normal completion, which is correct: from ARQ's perspective the worker is free and the job completed. Domain-level pause state is tracked in the `alert_analysis.status` column, not in `job_tracking`. The `pause_exceptions` mechanism exists for future jobs or if this pattern is refactored.
- **R3**: ARQ `on_job_start` hook (in both WorkerSettings) sets universal context: correlation ID, worker_id in `ctx`. ARQ `after_job_end` hook logs universal completion with duration.
- **R4**: Structured log events use consistent field names across all jobs: `job.id`, `job.type`, `job.attempt`, `job.duration_ms`, `job.status`, `job.error_type`, `tenant_id`, `correlation_id`.
- **R5**: Existing behavior of all 6 jobs is preserved. The decorator handles setup/teardown and `job_tracking` JSONB persistence; domain-specific error handling (status API calls, database updates) remains in the job function body. **Exception standardization**: during migration, jobs that swallow exceptions and return failure dicts (4 of 6: `execute_control_event`, `execute_content_review`, `execute_task_build`, `execute_workflow_generation`) are refactored to raise after domain cleanup — same pattern `run_integration` and `process_alert_analysis` already use. This ensures the decorator can reliably distinguish success from failure. **Pause path note**: `process_alert_analysis` handles pause states (HITL, workflow building) via return values, not exceptions. The pipeline catches `WorkflowPausedForHumanInput` internally and returns `{"status": "paused_human_review"}`. The worker function checks the result dict and returns normally. The decorator sees this as a successful completion — which is correct, since the ARQ worker is free. No refactoring needed; domain pause state is tracked in `alert_analysis.status`.
- **R6**: Actor user ID propagation (`set_actor_user_id`) is supported via an optional `extract_actor_id` parameter on the decorator.
- **R7**: `RunStatus` StrEnum in `constants.py` with values: `pending`, `running`, `completed`, `failed`, `paused`, `cancelled`. Domain-specific statuses (e.g., `approved`, `flagged`, `claimed`, `paused_workflow_building`, `paused_human_review`) remain on their respective models. `RunStatus` is the framework's vocabulary; domain code maps to/from it where needed.
- **R8**: Flyway migration adds a single `job_tracking JSONB NOT NULL DEFAULT '{}'` column to every table that represents a unit of work dispatched to a worker: `task_runs`, `workflow_runs`, `integration_runs`, `content_reviews`, `control_events`, `task_building_runs`, `workflow_generations`, `alert_analysis` (8 tables). Additive only — no column removals or renames. Existing domain columns (`error_message`, `run_details`, etc.) remain unchanged.
- **R9**: The `job_tracking` JSONB stores framework metadata managed by the decorator. Schema:
  ```json
  {
    "attempt": 1,
    "max_attempts": 3,
    "errors": [{"attempt": 1, "error": "...", "error_type": "TimeoutError", "at": "2026-04-26T..."}],
    "worker_id": "alert-worker-pod-7f8b9",
    "claimed_at": "2026-04-26T10:00:00Z",
    "duration_ms": 14523,
    "correlation_id": "uuid-abc",
    "timeout_seconds": 900
  }
  ```
  The `errors` array follows the River pattern — one entry per failed attempt. Capped at 10 entries. Domain-specific error columns (`error_message TEXT`, `run_details JSONB`, etc.) remain as-is for backward compatibility.
- **R10**: A contract test verifies all 8 tracked tables have the `job_tracking` column and that the decorator populates it correctly. New tracking fields can be added to the JSONB without schema migrations.
- **R11**: DB access pattern: the decorator uses a short-lived session (via `AsyncSessionLocal()` context manager) independent of the domain code's session. At job start: reads current `job_tracking` to get attempt count, increments it, writes back. At job end: writes final state (duration, status, errors). This is two small UPDATEs per job run. The decorator needs `model_class` and `extract_row_id` parameters to know which row to update. **Note on `integration_runs`**: this table already has `attempt` and `max_attempts` columns managed by domain code. `job_tracking.attempt` is the framework-level counter (incremented by the decorator). The two are independent — existing domain columns stay for backward compatibility. Long-term, domain code could read from `job_tracking.attempt` instead.

### Phase 2: Stuck Detection

- **R12**: `StuckJobConfig` dataclass for threshold-based detectors with retry support: `name`, `model_class`, `stuck_status`, `timeout_seconds`, `target_status`, `target_message`, `timestamp_column`, `max_attempts` (default 1), `retry_status` (optional), `use_skip_locked`.
- **R13**: `STUCK_JOB_REGISTRY: dict[str, StuckJobConfig]` — one entry per genericizable detector. Configurable via environment variables for timeout overrides. Covers: stuck workflow generations, stuck running alerts, stuck content reviews, stuck control events.
- **R14**: `detect_and_mark_stuck(session, config) -> dict[str, int]` — generic function that queries `WHERE status = :stuck_status AND :timestamp_column < now() - :timeout`. For each matching row, reads `job_tracking.attempt`:
  - If `attempt < max_attempts` AND `retry_status` is set → set status to `retry_status` (re-queue for another attempt)
  - Otherwise → set status to `target_status`, append error to `job_tracking.errors` (give up)

  Returns `{"retried": N, "failed": M}`. Uses `FOR UPDATE SKIP LOCKED` where configured.
- **R15**: `run_all_stuck_detection(session) -> dict[str, dict[str, int]]` — iterates `STUCK_JOB_REGISTRY`, calls `detect_and_mark_stuck` for each, returns nested counts.
- **R16**: Complex detectors stay as named functions in `reconciliation.py`: `mark_expired_hitl_paused_analyses` (24h timeout + cross-table join to check answered-question race guard), `detect_orphaned_analyses` (running + `steps_progress IS NULL`). They share the `mark_rows_as_failed(session, model, ids, status, message)` utility with the generic detector but are NOT forced through `StuckJobConfig`.
- **R17**: Domain-specific reconciliation logic that is NOT stuck detection (resume paused alerts, sync mismatched statuses, cleanup orphaned workspaces) remains in `reconciliation.py` unchanged.

### Phase 3: Migrate `asyncio.create_task()` to ARQ

- **R18**: New ARQ job function `execute_task_run(ctx, task_run_id, tenant_id)` wraps `TaskExecutionService.execute_and_persist()`. Registered in alert worker's `WorkerSettings.functions`.
- **R19**: New ARQ job function `execute_workflow_run(ctx, workflow_run_id)` wraps `WorkflowExecutor._execute_workflow_synchronously()`. The 1-second `asyncio.sleep()` delay hack is removed — ARQ naturally dequeues after the API transaction commits.
- **R20**: Both new jobs use `@tracked_job` decorator. Both get entries in `STUCK_JOB_REGISTRY`.
- **R21**: The API endpoints (POST `/tasks/{task_id}/run`, POST `/tasks/run`, workflow execution) continue to return 202 Accepted with `Location` and `Retry-After` headers. The only change is the execution mechanism (ARQ queue instead of in-process).
- **R22**: `asyncio.create_task()` calls in `routers/task_execution.py` and `services/workflow_execution.py` are replaced with `redis.enqueue_job()` calls. The `_execute_workflow_synchronously_delayed` method is removed.
- **R23**: Parallel node execution within a workflow (`asyncio.gather()` in `monitor_execution`) remains as-is — it runs inside the ARQ worker process, not in the API process. This is correctly awaited and does not need migration.
- **R24**: **Retry story**: After Phase 3, task/workflow failures are decoupled from control event retry. Failed TaskRuns and WorkflowRuns are caught by stuck detection (marks as failed) but are NOT automatically retried. Manual re-run via API is the recovery path. Automatic job-level retry is deferred — retry semantics differ too much per job type (control events: re-claim; integrations: re-schedule; others: none).

### ~~Phase 4: Retrofit Kalymnos HITL~~ — DISSOLVED (Kalymnos merged via PR #29)

Former Phase 4 requirements are now distributed:
- `RunStatus.PAUSED` included from day one → Phase 1 (R7). Maps to Kalymnos's `paused` (TaskRun, WorkflowRun), `paused_human_review` (AlertAnalysis), and `paused_workflow_building` (AlertAnalysis).
- HITL timeout in stuck detection → Phase 2 (R16). `mark_expired_hitl_paused_analyses` stays as named function (complex cross-table logic).
- `@tracked_job` applied to all 6 existing jobs → Phase 1 (R1). `pause_exceptions` parameter available (R2) but currently unused — `process_alert_analysis` handles pauses via return values (see R2/R5 caveats). Future refactoring could switch to exception-based pause detection.
- `hitl_questions` stays separate — tracks questions (domain concept), not jobs.
- Full Kalymnos test suite (286+ tests) verified after each job migration → Phase 1 testing.

### ~~Phase 5: Unified `job_runs` Table~~ — REJECTED

Decided: federated tables with shared `job_tracking` JSONB. Rationale:
- Only 4 of 8 tables are called "runs" — the others are reviews, events, analyses, node instances
- Domain-specific columns (cy_script, connector, pipeline_result) stay as real typed columns
- Parent-child relationships (workflow_node_instances → workflow_runs) stay natural
- A SQL VIEW can union all tables for dashboards if needed
- One JSONB column per table gives 80% of the unified table's benefit at 20% of the cost

---

## Data Model

### `@tracked_job` Decorator Signature

```python
def tracked_job(
    *,
    job_name: str,                                        # e.g., "content_review"
    timeout_seconds: int | None = None,                   # asyncio.timeout enforcement
    extract_tenant_id: Callable[..., str] | None = None,  # pull tenant_id from args
    extract_actor_id: Callable[..., str | None] | None = None,  # pull actor_id from args
    pause_exceptions: tuple[type[Exception], ...] = (),   # e.g., (ExecutionPaused,)
    model_class: type[Base] | None = None,                # SQLAlchemy model for job_tracking writes
    extract_row_id: Callable[..., str | UUID] | None = None,  # pull row PK from args
) -> Callable: ...
```

The decorator handles both in-memory concerns (correlation, tenant, logging, timeout,
duration) and DB persistence (`job_tracking` JSONB). When `model_class` and
`extract_row_id` are provided, it opens a short-lived session to read/write the
`job_tracking` column. When omitted, it operates in-memory only (useful for future
jobs that don't have a DB table yet). Domain-specific status management (HTTP API
calls, repository updates) stays in the job function body.

#### Example: `execute_content_review` with decorator

```python
@tracked_job(
    job_name="content_review",
    timeout_seconds=900,
    extract_tenant_id=lambda ctx, review_id, tenant_id: tenant_id,
    model_class=ContentReview,
    extract_row_id=lambda ctx, review_id, tenant_id: review_id,
)
async def execute_content_review(ctx, review_id: str, tenant_id: str):
    # Domain code — handles its own status updates as before.
    # The decorator handles correlation, tenant, logging, timeout, job_tracking.
    ...
```

#### DB write pattern inside the decorator

```python
# At job start: read current tracking, increment attempt
# Note: uses WHERE filter (not session.get) because partitioned tables have composite PKs
async with AsyncSessionLocal() as session:
    stmt = select(model_class).where(model_class.id == row_id)
    row = (await session.execute(stmt)).scalar_one()
    tracking = row.job_tracking or {}
    tracking["attempt"] = tracking.get("attempt", 0) + 1
    tracking["worker_id"] = ctx.get("worker_id")
    tracking["claimed_at"] = utcnow().isoformat()
    tracking["timeout_seconds"] = timeout_seconds
    tracking["correlation_id"] = get_correlation_id()
    row.job_tracking = tracking
    await session.commit()

# ... job body runs ...

# At job end: write final state
async with AsyncSessionLocal() as session:
    stmt = select(model_class).where(model_class.id == row_id)
    row = (await session.execute(stmt)).scalar_one()
    tracking = row.job_tracking or {}
    tracking["duration_ms"] = duration_ms
    if failed:
        tracking.setdefault("errors", []).append({
            "attempt": tracking["attempt"],
            "error": str(exc),
            "error_type": type(exc).__name__,
            "at": utcnow().isoformat(),
        })
        tracking["errors"] = tracking["errors"][-10:]  # cap at 10
    row.job_tracking = tracking
    await session.commit()
```

### Structured Log Fields (R4)

```json
{
  "event": "job_started",
  "job.id": "arq-job-uuid",
  "job.type": "content_review",
  "job.attempt": 1,
  "tenant_id": "tenant-abc",
  "correlation_id": "uuid",
  "timestamp": "2026-04-26T10:00:00Z"
}

{
  "event": "job_completed",
  "job.id": "arq-job-uuid",
  "job.type": "content_review",
  "job.duration_ms": 14523,
  "job.status": "completed",
  "tenant_id": "tenant-abc",
  "correlation_id": "uuid"
}

{
  "event": "job_failed",
  "job.id": "arq-job-uuid",
  "job.type": "content_review",
  "job.duration_ms": 3201,
  "job.status": "failed",
  "job.error_type": "TimeoutError",
  "job.error": "Pipeline timed out after 900s",
  "tenant_id": "tenant-abc",
  "correlation_id": "uuid"
}

{
  "event": "job_paused",
  "job.id": "arq-job-uuid",
  "job.type": "alert_analysis",
  "job.duration_ms": 8412,
  "job.status": "paused",
  "job.pause_reason": "human_input_required",
  "tenant_id": "tenant-abc",
  "correlation_id": "uuid"
}
```

### StuckJobConfig (R12)

```python
@dataclass(frozen=True)
class StuckJobConfig:
    name: str                          # human-readable: "stuck_control_events"
    model_class: type                  # SQLAlchemy model
    stuck_status: str                  # status to look for: "claimed"
    timeout_seconds: int               # threshold: 3600
    target_status: str                 # terminal status when giving up: "failed"
    target_message: str                # error message when giving up
    timestamp_column: str              # "updated_at" or "created_at"
    max_attempts: int = 1              # 1 = fail immediately (no retry)
    retry_status: str | None = None    # status to set when retrying: "pending"
    use_skip_locked: bool = False      # FOR UPDATE SKIP LOCKED
```

#### Stuck detection: fail-immediately vs retry-then-fail

The 3 existing detectors (stuck alerts, stuck generations, stuck content reviews) mark
jobs as `failed` on first detection. They say: **"this job has been running too long —
it's dead, mark it failed."**

```python
# Stuck alerts: fail immediately (max_attempts=1, no retry_status)
StuckJobConfig(
    name="stuck_running_alerts",
    model_class=AlertAnalysis,
    stuck_status="running",
    timeout_seconds=3600,           # 60 min
    target_status="failed",
    target_message="Exceeded 60-minute timeout",
    timestamp_column="updated_at",
    max_attempts=1,                 # fail on first detection
)
```

Control events work differently. Today they reset to `pending` with no cap — infinite
retry. With Leros, they get `max_attempts` so the system eventually gives up. They say:
**"this event got stuck mid-processing — put it back in the queue, but give up after
3 attempts."**

```python
# Control events: retry up to 3 times, then fail
StuckJobConfig(
    name="stuck_control_events",
    model_class=ControlEvent,
    stuck_status="claimed",
    timeout_seconds=3600,           # 1 hour
    target_status="failed",
    target_message="Exceeded max attempts after stuck detection",
    timestamp_column="updated_at",
    max_attempts=3,                 # retry twice, fail on third
    retry_status="pending",         # reset to pending for re-processing
    use_skip_locked=True,
)
```

The generic `detect_and_mark_stuck` function handles both patterns:

```python
for row in stuck_rows:
    attempt = row.job_tracking.get("attempt", 1)
    if config.retry_status and attempt < config.max_attempts:
        # "Put it back in the queue for another try"
        row.status = config.retry_status
    else:
        # "It's dead — mark it failed"
        row.status = config.target_status
        row.job_tracking["errors"].append({"error": config.target_message, ...})
```

### RunStatus Enum (R7)

```python
class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
```

6 values. No `SCHEDULED` (nothing uses it), no `RETRYABLE` (retries use `failed` +
`attempt` counter). Add more values when a real use case appears.

Domain-specific status values that intentionally do NOT map to `RunStatus`:
- `Alert.analysis_status = "new"` — user-facing lifecycle, separate concern
- `ContentReviewStatus` values (`approved`, `flagged`, `applied`, `rejected`) — approval workflow, not execution
- `ControlEvent.status = "claimed"` — intermediate lock state for outbox pattern
- `AlertAnalysis.status` paused variants (`paused_workflow_building`, `paused_human_review`) — both map to `RunStatus.PAUSED` in `job_tracking`; the *reason* lives in the domain column
- `TaskBuildingRun.status = "in_progress"` — naming variant of `running`; domain column stays as-is, `job_tracking` uses `RunStatus.RUNNING`
- `HITLQuestion.status` (`pending`, `answered`, `expired`) — tracks human responses, not job execution

### Flyway Migration — `job_tracking` JSONB (R8)

```sql
-- Add job_tracking JSONB to every table that represents a worker-dispatched job.
-- One column, one migration. New tracking fields go into the JSONB without schema changes.
ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE integration_runs ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE content_reviews ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE control_events ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE task_building_runs ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE workflow_generations ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
ALTER TABLE alert_analysis ADD COLUMN IF NOT EXISTS job_tracking JSONB NOT NULL DEFAULT '{}';
```

Note: `workflow_node_instances` is excluded — nodes execute within a `workflow_run`, not
as independently dispatched ARQ jobs. `workflow_generations` IS included — `execute_workflow_generation`
is an independently dispatched ARQ job with its own stuck detector.

### `job_tracking` JSONB Schema (R9)

```json
{
  "attempt": 1,
  "max_attempts": 3,
  "errors": [
    {"attempt": 1, "error": "TimeoutError: exceeded 900s", "error_type": "TimeoutError", "at": "2026-04-26T10:05:00Z"}
  ],
  "worker_id": "alert-worker-pod-7f8b9",
  "claimed_at": "2026-04-26T10:00:00Z",
  "duration_ms": 14523,
  "correlation_id": "uuid-abc",
  "timeout_seconds": 900
}
```

Owned by the `@tracked_job` decorator. Domain code should not read or write this column.
The `errors` array is capped at 10 entries.

**Note on `integration_runs`**: This table already has `attempt` (default 1) and `max_attempts`
(default 3) as real columns managed by domain code. `job_tracking.attempt` is the framework
counter managed by the decorator. They track the same concept independently. Both remain
for backward compatibility; future refactoring may consolidate.

---

## Constraints

- **C1**: All changes are additive. No existing columns are removed or renamed. New columns have defaults so existing code continues to work.
- **C2**: The decorator must be opt-in per job function. We migrate one job at a time (integration → content review → task build → control event → workflow gen → alert analysis).
- **C3**: Tenacity retry policies (`http_retry_policy`, `storage_retry_policy`, etc.) are operation-level retries and remain unchanged. Leros addresses job-level retry only.
- **C4**: Domain-specific error handling (status API calls, database updates for specific models) stays in the job function body. The decorator handles cross-cutting concerns and `job_tracking` JSONB.
- **C5**: The `asyncio.create_task()` → ARQ migration (Phase 3) must preserve the 202 Accepted + polling pattern for API consumers. No breaking API changes.
- **C6**: Federated table approach — each domain keeps its own table. No unified `job_runs` table. The `job_tracking` JSONB column is the standardization mechanism.
- **C7**: All timestamps timezone-aware. All new tables partitioned. Same Docker image for all containers.
- **C8**: Never edit existing Flyway migrations. New migration files only.

---

## Error Handling

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| `@tracked_job` decorator catches exception | Logs structured failure event, writes failure to `job_tracking` JSONB, re-raises to ARQ | Job marked failed; domain error handler in job body has already run |
| `@tracked_job` catches pause exception | Logs structured pause event, writes pause to `job_tracking` JSONB, re-raises to caller | Job not marked failed; domain code handles pause state (checkpoint storage, HITL question creation) |
| Job swallows exception (pre-migration) | Decorator logs `job_completed` even on failure | **Known gap** — fixed during migration by refactoring jobs to raise after cleanup |
| Stuck job detected: `attempt < max_attempts` | Row status set to `retry_status` (re-queued) | Job re-runs after next cron poll |
| Stuck job detected: `attempt >= max_attempts` | Row status set to `target_status` (failed), error appended to `job_tracking.errors` | Dashboard shows failure; API returns failed status |
| Stuck job detected by named function (HITL/orphan) | Same terminal behavior, but detector has custom SQL logic | Reconciliation logs count |
| `job_tracking` DB write fails | Decorator logs error but does NOT fail the job — job result takes priority | Tracking data lost for this run; job itself succeeds/fails normally |
| ARQ job enqueue fails after DB record created | Reconciler detects `pending` row older than threshold, re-enqueues | Slight delay (reconciler cadence) before job runs |
| Pod restart during ARQ job execution | ARQ detects missing worker, job becomes available for re-execution | Job may run twice — domain handlers must be idempotent (existing requirement) |
| Phase 3 migration: API enqueue fails | Return 500 to client (same as current `create_task` failure) | Client retries |
| Phase 3: task fails after control event completed | Control event stays `completed` (dispatch succeeded). TaskRun marked `failed` by stuck detection. | Manual re-run via API. No automatic retry. |

---

## Testing Checklist

### Phase 1
- [ ] Unit: `@tracked_job` sets correlation ID and tenant context before job runs
- [ ] Unit: `@tracked_job` logs structured start event with correct fields
- [ ] Unit: `@tracked_job` logs structured completion event with duration
- [ ] Unit: `@tracked_job` logs structured failure event with error type on exception
- [ ] Unit: `@tracked_job` logs structured pause event when `pause_exceptions` matched
- [ ] Unit: `@tracked_job` enforces `asyncio.timeout()` when `timeout_seconds` set
- [ ] Unit: `@tracked_job` writes `job_tracking` JSONB on start (attempt, worker_id, correlation_id)
- [ ] Unit: `@tracked_job` writes `job_tracking` JSONB on completion (duration_ms)
- [ ] Unit: `@tracked_job` writes `job_tracking` JSONB on failure (errors array appended)
- [ ] Unit: `@tracked_job` increments `attempt` on each invocation (reads existing value)
- [ ] Unit: `@tracked_job` `errors` array capped at 10 entries
- [ ] Unit: `@tracked_job` DB write failure does not fail the job
- [ ] Unit: `RunStatus` enum has all 6 values (pending, running, completed, failed, paused, cancelled)
- [ ] Unit: Flyway migration applies cleanly to dev and test databases
- [ ] Unit: `job_tracking` JSONB column has correct default (`'{}'`)
- [ ] Contract test: all 8 tracked tables have `job_tracking` column
- [ ] Integration: `run_integration` with `@tracked_job` produces identical behavior and structured logs
- [ ] Integration: all 6 migrated jobs pass their existing test suites
- [ ] Integration: jobs that previously swallowed exceptions now raise (decorator sees failure correctly)
- [ ] Integration: existing job functions still work with new `job_tracking` column present
- [ ] Regression: full Kalymnos HITL test suite (286+ tests) passes after each migration

### Phase 2
- [ ] Unit: `StuckJobConfig` for each of 4 detectors (generations, alerts, content reviews, control events)
- [ ] Unit: `detect_and_mark_stuck` marks matching rows as `target_status` when `attempt >= max_attempts`
- [ ] Unit: `detect_and_mark_stuck` resets to `retry_status` when `attempt < max_attempts`
- [ ] Unit: `detect_and_mark_stuck` with `use_skip_locked` does not deadlock
- [ ] Unit: `detect_and_mark_stuck` appends error to `job_tracking.errors` when failing
- [ ] Unit: control events retry up to `max_attempts` then fail
- [ ] Unit: `mark_expired_hitl_paused_analyses` (named function) skips answered questions (Bug #4 guard)
- [ ] Unit: `detect_orphaned_analyses` (named function) checks `steps_progress IS NULL`
- [ ] Integration: `run_all_stuck_detection` + named functions match previous reconciliation behavior

### Phase 3
- [ ] Unit: `execute_task_run` ARQ job wraps `execute_and_persist` correctly
- [ ] Unit: `execute_workflow_run` ARQ job wraps `_execute_workflow_synchronously` correctly
- [ ] Integration: POST `/tasks/{id}/run` returns 202, task executes via ARQ worker
- [ ] Integration: workflow execution via ARQ survives simulated pod restart (task completes)
- [ ] Integration: 1-second sleep hack is removed, workflow still executes correctly
- [ ] Integration: task failure after Phase 3 is caught by stuck detection (not control event retry)
- [ ] Integration: control event completes successfully even when enqueued task fails (semantic change: dispatch success ≠ execution success)
- [ ] Integration: update existing tests that assert task failure = control event failure

---

## Open Questions

- **Q1** ~~(resolved)~~: Should `@tracked_job` handle ARQ's `Retry` exception? **No** — leave to domain code. No job currently uses ARQ `Retry`. If needed later, the decorator just lets it propagate.
- **Q2** ~~(resolved)~~: For Phase 3, should task/workflow execution go to the alert worker or a new dedicated worker? **Alert worker** — fewer moving parts, task execution is already lightweight, and the alert worker already handles `execute_task_build` and `execute_workflow_generation` (both task/workflow execution). A dedicated worker adds operational complexity (extra container, health checks, Valkey DB) without clear benefit. If scaling is needed later, it's easy to split.
- **Q3** ~~(resolved)~~: Should the `errors` array cap at N entries? **Yes** — capped at 10 entries inside `job_tracking` JSONB.
- **Q4** ~~(resolved)~~: Unified `job_runs` table? **No** — federated tables with shared `job_tracking` JSONB. Domain tables keep their domain columns and relationships naturally.
- **Q5** ~~(resolved)~~: Pause handling? **Yes** — `pause_exceptions` parameter on `@tracked_job`. Decorator logs `job_paused` and re-raises. Domain code handles checkpoint storage and commit timing.
- **Q6** ~~(resolved)~~: Separate `@db_tracked_job` decorator? **No** — single `@tracked_job` handles both in-memory concerns and `job_tracking` JSONB writes. When `model_class` + `extract_row_id` are provided, it writes to DB. When omitted, in-memory only.

---

## Future Work

- **OpenTelemetry trace context propagation**: Serialize trace context into `enqueue_job` args, extract in worker. Enables end-to-end request tracing from API → queue → worker.
- **Job argument validation**: Pydantic models at enqueue time to catch type errors before they reach the worker.
- **Job type registry with versioning**: `@register_job(name, version, input_schema)` for schema evolution of job arguments.
- **Dead letter pattern**: Jobs that exhaust `max_attempts` moved to a dead letter queue for manual inspection/replay.
- **Job dashboard**: Web UI showing all running/stuck/failed jobs across all types. Aggregates across per-domain tables using `job_tracking` JSONB (or a SQL VIEW unioning all tables).
- **Periodic job scheduling via DB**: User-configurable schedules for any job type (not just integrations), stored in a `job_schedules` table, polled by a generic schedule executor.
- **Automatic job-level retry**: Beyond stuck detection reset, proactive re-enqueue of failed jobs with exponential backoff. Requires per-job retry policies that don't yet exist.
- **Open-source extraction**: If `@tracked_job` + `StuckJobConfig` + `job_tracking` JSONB proves itself, extract into a standalone Python library (e.g., `arq-lifecycle`). The pattern is ~300 lines and queue-agnostic in principle. No equivalent exists in the Python ecosystem — Go has River, Node.js has pg-boss/Graphile Worker, Python has nothing.

---

## File Locations

| Component | Path |
|-----------|------|
| Spec | `docs/specs/UnifiedJobFramework.md` |
| Plan | `docs/planning/leros/PLAN.md` |
| Decorator module | `src/analysi/common/job_tracking.py` (new) |
| Stuck detection module | `src/analysi/common/stuck_detection.py` (new) |
| RunStatus enum | `src/analysi/constants.py` (extend) |
| Flyway migration (Phase 1) | `migrations/flyway/sql/V001__baseline.sql` (new) |
| ARQ task execution job | `src/analysi/services/task_execution.py` (extend) or new file |
| ARQ workflow execution job | `src/analysi/services/workflow_execution.py` (extend) or new file |
| Alert worker settings | `src/analysi/alert_analysis/worker.py` (extend) |
| Integration worker settings | `src/analysi/integrations/worker.py` (extend) |
| Reconciliation | `src/analysi/alert_analysis/jobs/reconciliation.py` (refactor) |
| Content review stuck detection | `src/analysi/alert_analysis/jobs/content_review.py` (refactor) |
| WorkflowGeneration model | `src/analysi/models/kea_coordination.py` (extend — add `job_tracking` column) |
| WorkflowGeneration repository | `src/analysi/repositories/kea_coordination_repository.py` (stuck detection) |
| Config | `src/analysi/alert_analysis/config.py` (extend) |
| Retry policies (unchanged) | `src/analysi/common/retry_config.py` |
