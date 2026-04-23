"""Alert Analysis ARQ Worker Implementation"""

import os
from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from analysi.alert_analysis.clients import BackendAPIClient
from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
from analysi.common.job_tracking import tracked_job
from analysi.config.logging import configure_logging, get_logger
from analysi.config.valkey_db import ValkeyDBConfig
from analysi.models.alert import AlertAnalysis
from analysi.schemas.alert import AlertStatus, AnalysisStatus

# Unified logging — same structlog config as API (Project Syros AD-5)
configure_logging()

try:
    from analysi.config.telemetry import configure_telemetry

    configure_telemetry(service_name="analysi-alert-worker")
except ImportError:
    pass  # opentelemetry not installed — tracing disabled

logger = get_logger(__name__)


class WorkerSettings:
    """Configuration for ARQ worker"""

    @classmethod
    def get_redis_settings(cls) -> RedisSettings:
        """Get Redis settings with appropriate database for test/production."""
        is_test = os.getenv("PYTEST_CURRENT_TEST") is not None
        db_num = (
            ValkeyDBConfig.TEST_ALERT_PROCESSING_DB
            if is_test
            else ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        return ValkeyDBConfig.get_redis_settings(database=db_num, test_mode=is_test)

    # ARQ expects redis_settings to be a simple attribute, not a property
    # Calculate it once at class definition time
    redis_settings = ValkeyDBConfig.get_redis_settings(
        database=ValkeyDBConfig.ALERT_PROCESSING_DB
    )

    # Worker settings
    max_jobs = AlertAnalysisConfig.MAX_JOBS
    job_timeout = AlertAnalysisConfig.JOB_TIMEOUT
    max_tries = (
        1  # No ARQ retries — domain logic handles retry/stuck detection (Project Leros)
    )
    poll_delay = 2.0  # Poll every 2 seconds (default: 0.5s). Reduces log spam since cron runs every 10s

    # Functions this worker can run (must be full module paths)
    functions = [  # noqa: RUF012
        "analysi.alert_analysis.worker.process_alert_analysis",
        "analysi.agentic_orchestration.jobs.workflow_generation_job.execute_workflow_generation",
        "analysi.agentic_orchestration.jobs.task_build_job.execute_task_build",
        "analysi.alert_analysis.jobs.control_events.execute_control_event",
        "analysi.alert_analysis.jobs.content_review.execute_content_review",
        "analysi.jobs.task_run_job.execute_task_run",
        "analysi.jobs.workflow_run_job.execute_workflow_run",
    ]

    # Number of worker processes (for Docker container scaling)
    worker_processes = int(os.getenv("ALERT_WORKER_PROCESSES", 1))

    # Cron jobs
    cron_jobs = [  # noqa: RUF012
        cron(
            "analysi.alert_analysis.jobs.reconciliation.reconcile_paused_alerts",
            second={0, 10, 20, 30, 40, 50},  # Every 10 seconds
        ),
        cron(
            "analysi.alert_analysis.jobs.control_events.consume_control_events",
            second={0, 30},  # Every 30 seconds
        ),
    ]

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        """Log worker configuration on startup and verify connectivity."""
        # Inject worker_id for job tracking (Project Leros)
        ctx["worker_id"] = f"arq:{os.getpid()}"

        # Validate timeout alignment before anything else — fail fast on misconfiguration
        AlertAnalysisConfig.validate_timeout_alignment()

        # Single structured event replaces verbose startup banner
        logger.info(
            "worker_started",
            worker="alert-analysis",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            max_jobs=AlertAnalysisConfig.MAX_JOBS,
            job_timeout_s=AlertAnalysisConfig.JOB_TIMEOUT,
            workflow_poll_timeout_s=AlertAnalysisConfig.WORKFLOW_EXECUTION_POLL_TIMEOUT,
            stuck_alert_timeout_min=AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES,
            poll_delay_s=2.0,
            worker_processes=int(os.getenv("ALERT_WORKER_PROCESSES", "1")),
            redis_host=os.getenv("REDIS_HOST", "valkey"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=ValkeyDBConfig.ALERT_PROCESSING_DB,
            functions=WorkerSettings.functions,
            cron_jobs=["reconcile_paused_alerts/10s", "consume_control_events/30s"],
            max_tasks_to_build=AlertAnalysisConfig.MAX_TASKS_TO_BUILD,
        )

        # Verify Valkey connectivity — fail fast if the queue is unreachable
        try:
            pong = await ctx["redis"].ping()
            logger.info("valkey_connected", ping=pong)
        except Exception as exc:
            logger.error("valkey_connection_failed", error=str(exc))
            raise


@tracked_job(
    job_type="process_alert_analysis",
    timeout_seconds=AlertAnalysisConfig.JOB_TIMEOUT,
    model_class=AlertAnalysis,
    extract_row_id=lambda ctx, tenant_id, alert_id, analysis_id, actor_user_id=None: (
        analysis_id
    ),
    # No retry: the pipeline makes REST API status updates (running → failed)
    # that a blind retry cannot undo.  Proper retry needs the pipeline to be
    # idempotent w.r.t. its own status transitions first.
)
async def process_alert_analysis(  # noqa: C901
    ctx: dict[str, Any],
    tenant_id: str,
    alert_id: str,
    analysis_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """
    Main ARQ job function for processing alert analysis.

    Args:
        ctx: ARQ context (contains redis pool, job info)
        tenant_id: Tenant identifier
        alert_id: Alert UUID to analyze
        analysis_id: Analysis UUID for tracking
        actor_user_id: UUID of the user who triggered analysis (for audit attribution).
            None for system-initiated triggers (reconciliation, control events).

    Returns:
        Dict with job results
    """
    # Correlation + tenant context set by @tracked_job (Project Leros)

    logger.info(
        "alert_analysis_job_started",
        alert_id=alert_id,
        analysis_id=analysis_id,
    )

    # Propagate actor identity for the entire job context.
    # All downstream internal_auth_headers() calls will automatically
    # include X-Actor-User-Id without explicit threading.
    from analysi.common.internal_auth import set_actor_user_id

    set_actor_user_id(actor_user_id)

    db = None
    api_client = BackendAPIClient()

    async def update_status_on_failure(error_msg: str) -> None:
        """Helper to update status via REST API on failure."""
        try:
            await api_client.update_analysis_status(
                tenant_id, analysis_id, AnalysisStatus.FAILED.value, error=error_msg
            )
            await api_client.update_alert_analysis_status(
                tenant_id, alert_id, AlertStatus.FAILED.value
            )
        except Exception as update_error:
            logger.error("failed_to_update_status_via_api", error=str(update_error))

    try:
        # Create database connection (for read operations and pipeline internal use)
        db = AlertAnalysisDB()
        await db.initialize()

        # Update analysis status to running via REST API.
        # Returns None (specifically) when the API returns 409, meaning the
        # analysis was cancelled by the user between enqueue and execution.
        # Returns False for other non-retryable errors (log and continue).
        claimed = await api_client.update_analysis_status(
            tenant_id, analysis_id, "running"
        )
        if claimed is None:
            logger.warning(
                "analysis_cancelled_before_start",
                analysis_id=analysis_id,
            )
            return {"status": "cancelled", "analysis_id": analysis_id}

        # Create pipeline instance
        pipeline = AlertAnalysisPipeline(
            tenant_id=tenant_id,
            alert_id=alert_id,
            analysis_id=analysis_id,
            actor_user_id=actor_user_id,
        )

        # Initialize pipeline with database connection (for reads)
        pipeline.db = db

        # Execute the 4-step pipeline
        result = await pipeline.execute()

        # Pipeline handles its own status updates (completed, paused_workflow_building, etc.)
        # Only update alert status if pipeline actually completed (not paused)
        result_status = result.get("status")
        if result_status == AnalysisStatus.COMPLETED.value:
            # Update alert's denormalized status to completed via REST API
            await api_client.update_alert_analysis_status(
                tenant_id, alert_id, AlertStatus.COMPLETED.value
            )
            logger.info(
                "alert_analysis_completed_successfully_analysis",
                analysis_id=analysis_id,
            )
        elif result_status == AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value:
            # Pipeline already updated analysis status to paused_workflow_building
            # Alert status already set to in_progress by pipeline
            logger.info(
                "alert_analysis_paused_for_workflow_generation",
                analysis_id=analysis_id,
            )
        elif result_status == AnalysisStatus.PAUSED_HUMAN_REVIEW.value:
            # HITL — Project Kalymnos: workflow paused waiting for human input.
            # Pipeline already set analysis status to paused_human_review.
            # Alert.analysis_status stays as in_progress (user-facing simplified status).
            # Control event handler (human:responded) will re-queue after answer.
            logger.info(
                "alert_analysis_paused_for_human_review",
                analysis_id=analysis_id,
                workflow_run_id=result.get("workflow_run_id"),
            )

        return {
            "status": result_status or AnalysisStatus.COMPLETED.value,
            "analysis_id": analysis_id,
            "result": result,
        }

    except TimeoutError:
        error_msg = "Alert analysis timed out after maximum execution time"
        logger.error("alert_analysis_timeout_analysis", analysis_id=analysis_id)
        await update_status_on_failure(error_msg)
        raise

    except ModuleNotFoundError as e:
        error_msg = f"Missing required dependency: {e!s}"
        logger.error(
            "alert_analysis_dependency_error_analysis_error",
            analysis_id=analysis_id,
            error_msg=error_msg,
        )
        await update_status_on_failure(error_msg)
        raise

    except ConnectionError as e:
        error_msg = f"Failed to connect to external service: {e!s}"
        logger.error(
            "alert_analysis_connection_error_analysis_error",
            analysis_id=analysis_id,
            error_msg=error_msg,
        )
        await update_status_on_failure(error_msg)
        raise

    except ValueError as e:
        error_msg = f"Invalid data or configuration: {e!s}"
        logger.error(
            "alert_analysis_value_error_analysis_error",
            analysis_id=analysis_id,
            error_msg=error_msg,
        )
        await update_status_on_failure(error_msg)
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        error_type = type(e).__name__
        error_msg = f"Unexpected error in alert analysis worker ({error_type}): {e!s}"

        # Special handling for common error patterns
        if "LLM" in str(e) or "OpenAI" in str(e) or "langchain" in str(e).lower():
            error_msg = f"LLM service error: {e!s}"
        elif "database" in str(e).lower() or "connection pool" in str(e).lower():
            error_msg = f"Database connection error: {e!s}"
        elif "workflow" in str(e).lower():
            error_msg = f"Workflow execution error: {e!s}"
        elif "timeout" in str(e).lower():
            error_msg = f"Operation timeout: {e!s}"
        elif "memory" in str(e).lower():
            error_msg = f"Memory allocation error: {e!s}"

        logger.error(
            "alert_analysis_failed",
            analysis_id=analysis_id,
            error_msg=error_msg,
            exc_info=True,
        )
        await update_status_on_failure(error_msg)
        raise  # Let ARQ handle retries

    finally:
        # Clean up database connection
        if db:
            await db.close()


async def queue_alert_analysis(
    tenant_id: str,
    alert_id: str,
    analysis_id: str,
    actor_user_id: str | None = None,
) -> str:
    """
    Helper function to queue an alert analysis job.
    Used by the main API to enqueue work.

    Args:
        tenant_id: Tenant identifier
        alert_id: Alert UUID
        analysis_id: Analysis UUID
        actor_user_id: UUID of the user who triggered analysis (for audit attribution).
            None for system-initiated triggers (reconciliation, control events).
    """
    from arq import create_pool

    logger.info(
        "queueing_analysis_job_for_alert_analysis",
        alert_id=alert_id,
        analysis_id=analysis_id,
    )

    # Create Redis/Valkey connection with dynamic settings
    redis = await create_pool(WorkerSettings.get_redis_settings())

    try:
        # Queue the job (must use full module path)
        job = await redis.enqueue_job(
            "analysi.alert_analysis.worker.process_alert_analysis",  # Full module path
            tenant_id,
            alert_id,
            analysis_id,
            actor_user_id,  # For audit attribution
        )

        logger.info(
            "queued_job_for_analysis", job_id=job.job_id, analysis_id=analysis_id
        )
        return job.job_id

    finally:
        await redis.aclose()
