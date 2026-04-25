"""Integrations worker — schedule executor and action execution."""

from arq import cron

from analysi.config.logging import configure_logging, get_logger
from analysi.integrations.config import IntegrationConfig
from analysi.scheduler.executor import execute_due_schedules

configure_logging()

try:
    from analysi.config.telemetry import configure_telemetry

    configure_telemetry(service_name="analysi-integrations-worker")
except ImportError:
    pass  # opentelemetry not installed — tracing disabled

logger = get_logger(__name__)


# ============================================================================
# WORKER SETTINGS
# ============================================================================


class WorkerSettings:
    """Configuration for Integration ARQ worker."""

    import os

    # Redis settings for ARQ
    redis_settings = IntegrationConfig.get_redis_settings()

    # Worker settings
    max_jobs = IntegrationConfig.MAX_JOBS
    job_timeout = IntegrationConfig.JOB_TIMEOUT
    max_tries = (
        1  # No ARQ retries — domain logic handles retry/stuck detection (Project Leros)
    )

    # Queue configuration
    queue_name = IntegrationConfig.get_queue_name(IntegrationConfig.DEFAULT_TENANT)

    # Functions this worker can run
    functions = []  # noqa: RUF012

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        """Inject worker_id for job tracking (Project Leros)."""
        import os

        ctx["worker_id"] = f"arq:{os.getpid()}"
        logger.info("worker_started", worker="integrations", pid=os.getpid())

    # Cron jobs - disabled during tests
    cron_jobs = (
        []
        if os.getenv("DISABLE_INTEGRATION_WORKER", "false").lower() == "true"
        else [
            # Project Symi: Generic schedule executor (schedules table)
            cron(
                execute_due_schedules,
                second={0, 30},  # Run every 30 seconds
            ),
        ]
    )
