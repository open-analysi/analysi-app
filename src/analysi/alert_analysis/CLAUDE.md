# Alert Analysis - Reconciliation Job

**Reconciliation Job** (`jobs/reconciliation.py`): Runs every 10 seconds via ARQ cron. Finds alerts paused at `paused_workflow_building` status, checks if their workflow generation completed (via Kea API), and **re-queues** them for processing (does not process immediately). Uses atomic database updates (`try_resume_alert`) for race-free claiming across multiple workers. Also performs maintenance: marks stuck workflow generations as failed (>60min, matching JOB_TIMEOUT) and cleans up orphaned workspace directories.

**Design Note**: If N alerts wait for the same workflow, all N are re-queued in one reconciliation run. Kea API calls are deduplicated per `(tenant_id, rule_name)` so N alerts with the same rule trigger only 1 API call.
