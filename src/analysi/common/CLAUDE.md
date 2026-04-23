# Common Module — Shared Utilities

## Job Tracking

`job_tracking.py` — `@tracked_job` decorator for ARQ jobs. Provides correlation IDs, tenant context, `asyncio.timeout()`, structured logging, and `job_tracking` JSONB persistence.

`stuck_detection.py` — Config-driven stuck-job detectors with `mark_rows_as_failed` utility. Called by the reconciliation cron.

`arq_enqueue.py` — `enqueue_arq_job()` helper with a shared Redis pool (lazy singleton). The pool is created on first use and reused across all subsequent calls. `close_pool()` for graceful shutdown, `reset_pool()` for test teardown. All enqueued functions run on the alert-analysis worker.

### Known Limitation: Partition Pruning on job_tracking Writes

`_pk_column()` in `job_tracking.py` returns only the **first** primary key column. Four tracked models use composite PKs for partitioning:

| Model | PK Columns | `_pk_column` returns |
|-------|-----------|---------------------|
| `WorkflowRun` | `(id, created_at)` | `id` only |
| `AlertAnalysis` | `(id, created_at)` | `id` only |
| `ControlEvent` | `(id, created_at)` | `id` only |
| `IntegrationRun` | `(run_id, created_at)` | `run_id` only |

**Impact**: `WHERE id = :uuid` queries scan all partitions instead of pruning to the correct one. Since `id`/`run_id` is a UUID (globally unique), the correct row is always found — this is a performance issue, not a correctness bug.

**Why it's acceptable today**: `job_tracking` writes are fire-and-forget diagnostic data. Rows are fresh (current month's partition), so the scan touches ~3 partition indexes that are hot in the buffer cache. Overhead is negligible for the current write volume.

**To fix properly**: The decorator API would need to support composite keys — either by accepting a second `extract_partition_key` callable, or by changing `_write_tracking_*` to use a raw `UPDATE ... SET job_tracking = jsonb_set(...)` with only the `id` column in the WHERE clause (avoiding the SELECT entirely). The raw-UPDATE approach would also eliminate the read-modify-write pattern, but loses the ability to merge into the existing JSONB (e.g., appending to the errors array).
