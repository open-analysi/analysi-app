"""
Configuration for Alert Analysis Worker.

Centralizes all alert analysis and workflow generation parameters.
"""

import os


class AlertAnalysisConfig:
    """Configuration for alert analysis and workflow generation."""

    # Worker Configuration
    MAX_JOBS = int(os.getenv("ALERT_WORKER_MAX_JOBS", 10))
    """Maximum number of concurrent alert analysis jobs."""

    JOB_TIMEOUT = int(os.getenv("ALERT_WORKER_TIMEOUT", 3600))
    """
    Job timeout in seconds (default: 3600 = 60 minutes).

    Workflow generation involves multiple stages:
    - First subgraph: Runbook generation + task proposals (~5-10 min)
    - Second subgraph: Task building (parallel) + workflow assembly (~20-40 min)

    Complex workflows with multiple task builds can take up to 50 minutes.
    60 minutes provides buffer for these cases. Must match reconciliation timeout.
    """

    # Retry Configuration (ARQ job-level - not currently used)
    MAX_RETRIES = int(os.getenv("ALERT_WORKER_MAX_RETRIES", 3))
    """Maximum number of retries for failed jobs."""

    RETRY_DELAY = int(os.getenv("ALERT_WORKER_RETRY_DELAY", 60))
    """Delay between retries in seconds."""

    # Workflow Generation Retry Configuration
    MAX_WORKFLOW_GEN_RETRIES = int(os.getenv("MAX_WORKFLOW_GEN_RETRIES", 3))
    """Maximum number of workflow generation retry attempts before marking alert as failed."""

    WORKFLOW_GEN_BACKOFF_BASE_MINUTES = int(
        os.getenv("WORKFLOW_GEN_BACKOFF_BASE_MINUTES", 5)
    )
    """
    Base backoff interval in minutes for workflow generation retries.
    Uses exponential backoff: 5min, 10min, 20min for retries 0, 1, 2.
    """

    # Stuck Alert Detection
    STUCK_ALERT_TIMEOUT_MINUTES = int(os.getenv("STUCK_ALERT_TIMEOUT_MINUTES", 60))
    """Minutes after which an alert stuck in 'running' status is marked as failed."""

    # Workflow Execution Polling (derived from JOB_TIMEOUT)
    WORKFLOW_EXECUTION_POLL_TIMEOUT = JOB_TIMEOUT - 300
    """
    Timeout for polling workflow execution status during Step 3.

    Derived from JOB_TIMEOUT minus 300s buffer for pipeline steps 1, 2, and 4.
    Must be less than JOB_TIMEOUT to prevent ARQ killing the job during polling
    (external kill = no exception handler = analysis stuck in 'running').
    """

    @classmethod
    def validate_timeout_alignment(cls):
        """Validate that timeout values are internally consistent.

        Call this at worker startup to catch misconfigurations early.

        Raises:
            ValueError: If timeouts are misaligned
        """
        if cls.WORKFLOW_EXECUTION_POLL_TIMEOUT <= 0:
            raise ValueError(
                f"Poll timeout must be positive, got {cls.WORKFLOW_EXECUTION_POLL_TIMEOUT}s. "
                f"JOB_TIMEOUT ({cls.JOB_TIMEOUT}s) is too small (need > 300s)."
            )

        if cls.WORKFLOW_EXECUTION_POLL_TIMEOUT >= cls.JOB_TIMEOUT:
            raise ValueError(
                f"Poll timeout ({cls.WORKFLOW_EXECUTION_POLL_TIMEOUT}s) must be less than "
                f"job timeout ({cls.JOB_TIMEOUT}s) to prevent ARQ timeout race."
            )

        if cls.STUCK_ALERT_TIMEOUT_MINUTES * 60 < cls.JOB_TIMEOUT:
            raise ValueError(
                f"Stuck alert timeout ({cls.STUCK_ALERT_TIMEOUT_MINUTES} min = "
                f"{cls.STUCK_ALERT_TIMEOUT_MINUTES * 60}s) must be >= "
                f"job timeout ({cls.JOB_TIMEOUT}s) to avoid false positives."
            )

    # Workflow Generation Configuration
    WORKFLOW_GENERATION_TIMEOUT = int(
        os.getenv("WORKFLOW_GENERATION_TIMEOUT", JOB_TIMEOUT)
    )
    """
    Specific timeout for workflow generation jobs (defaults to JOB_TIMEOUT).
    Can be overridden independently if workflow generation needs different timeout.
    """

    MAX_TASKS_TO_BUILD = int(
        os.getenv("ANALYSI_WORKFLOW_GENERATION_MAX_TASKS_TO_BUILD", 2)
    )
    """
    Optional limit on parallel task building during workflow generation.

    Use this for cost control during testing/development. When set, only the first N
    tasks needing building (designation="new" or "modification") will be built in parallel.
    Existing tasks are always included in the workflow composition.

    Example: Set to "2" to build only 2 new tasks per workflow generation.
    None (no limit, build all proposed tasks)
    """

    # Control Event Bus (Project Tilos)
    MAX_CONTROL_EVENT_RETRIES = int(os.getenv("MAX_CONTROL_EVENT_RETRIES", 3))
    """
    Maximum number of retry attempts for a failed control event before leaving it
    permanently failed for operator inspection.  Retry is handled by the
    consume_control_events cron (picks up failed events with retry_count < limit).
    """

    CONTROL_EVENT_STUCK_HOURS = int(os.getenv("CONTROL_EVENT_STUCK_HOURS", 1))
    """
    Hours after which a claimed control event is reset back to pending.
    Covers the case where Valkey was restarted before the ARQ job dequeued the event.
    Safe at 1 hour because v1 rule targets are fast automations only.
    """

    # Reconciliation Job Configuration
    RECONCILIATION_INTERVAL = int(os.getenv("RECONCILIATION_INTERVAL", 10))
    """Interval in seconds between reconciliation job runs."""

    PAUSE_TIMEOUT_HOURS = int(os.getenv("PAUSE_TIMEOUT_HOURS", 24))
    """Hours after which paused alerts are considered stale."""

    # API Configuration
    BACKEND_API_HOST = os.getenv("BACKEND_API_HOST", "api")
    BACKEND_API_PORT = int(os.getenv("BACKEND_API_PORT", 8000))
    API_BASE_URL = f"http://{BACKEND_API_HOST}:{BACKEND_API_PORT}"
    """Base URL for REST API calls from worker (constructed from host + port)."""

    # SDK Skills Integration (DB-only skills)
    USE_DB_SKILLS: bool = os.getenv("ANALYSI_USE_DB_SKILLS", "true").lower() == "true"
    """
    DEPRECATED: This flag will be removed in a future release.

    Skills are now always loaded from the database (tenant-isolated).
    Filesystem skills have been removed. Set to 'false' only for testing
    without database skills (not recommended for production).

    Skills must be installed into the tenant via a content pack
    (e.g., `analysi packs install foundation -t <tenant>`) before Kea
    can function. See `content/CLAUDE.md` and `docs/projects/delos.md`.
    """
