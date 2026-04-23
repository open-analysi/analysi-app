"""Queue cleanup utilities for alert analysis.

Provides functions to purge queued jobs for specific tenants,
useful when cleaning up tenant data or stopping retries.
"""

from dataclasses import dataclass
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# ARQ queue key names
ARQ_QUEUE_KEY = "arq:queue"
ARQ_JOB_PREFIX = "arq:job:"
ARQ_IN_PROGRESS_PREFIX = "arq:in-progress:"


@dataclass
class QueueCleanupResult:
    """Result of queue cleanup operation."""

    queued_jobs_removed: int
    in_progress_jobs_aborted: int
    errors: list[str]

    @property
    def total_removed(self) -> int:
        return self.queued_jobs_removed + self.in_progress_jobs_aborted


async def purge_tenant_queue(
    redis_settings: RedisSettings,
    tenant_id: str,
    abort_in_progress: bool = False,
) -> QueueCleanupResult:
    """
    Remove all queued jobs for a specific tenant from the ARQ queue.

    This is useful when:
    - Cleaning up a tenant completely
    - Stopping all retries for a tenant's alerts
    - Resetting alert processing state

    Args:
        redis_settings: Redis connection settings
        tenant_id: Tenant ID to purge jobs for
        abort_in_progress: If True, also mark in-progress jobs as aborted

    Returns:
        QueueCleanupResult with counts and any errors
    """
    redis = await create_pool(redis_settings)
    errors: list[str] = []
    queued_removed = 0
    in_progress_aborted = 0

    try:
        # 1. Get all jobs from the queue (sorted set)
        # ARQ stores job_id in the sorted set, actual job data in arq:job:<job_id>
        job_ids = await redis.zrange(ARQ_QUEUE_KEY, 0, -1)

        logger.info(
            "scanning_queued_jobs_for_tenant",
            job_ids_count=len(job_ids),
            tenant_id=tenant_id,
        )

        # 2. Check each job and remove if it belongs to the tenant
        jobs_to_remove = []

        for job_id_bytes in job_ids:
            job_id = (
                job_id_bytes.decode()
                if isinstance(job_id_bytes, bytes)
                else job_id_bytes
            )

            try:
                job_tenant = await _get_job_tenant(redis, job_id)
                if job_tenant == tenant_id:
                    jobs_to_remove.append(job_id)
            except Exception as e:
                errors.append(f"Failed to inspect job {job_id}: {e}")

        # 3. Remove matching jobs from queue and delete job data
        for job_id in jobs_to_remove:
            try:
                # Remove from sorted set (queue)
                await redis.zrem(ARQ_QUEUE_KEY, job_id)
                # Delete job data
                await redis.delete(f"{ARQ_JOB_PREFIX}{job_id}")
                queued_removed += 1
                logger.debug(
                    "removed_queued_job_for_tenant", job_id=job_id, tenant_id=tenant_id
                )
            except Exception as e:
                errors.append(f"Failed to remove job {job_id}: {e}")

        # 4. Optionally handle in-progress jobs
        if abort_in_progress:
            in_progress_keys = await redis.keys(f"{ARQ_IN_PROGRESS_PREFIX}*")
            # Filter out cron markers
            worker_keys = [k for k in (in_progress_keys or []) if b":cron:" not in k]

            for key in worker_keys:
                try:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Extract job_id from key (format: arq:in-progress:<worker_id>:<job_id>)
                    parts = key_str.split(":")
                    if len(parts) >= 4:
                        job_id = parts[3]  # arq:in-progress:worker:job_id
                        job_tenant = await _get_job_tenant(redis, job_id)
                        if job_tenant == tenant_id:
                            # Delete in-progress marker (job will be considered aborted)
                            await redis.delete(key)
                            in_progress_aborted += 1
                            logger.debug(
                                "aborted_in_progress_job",
                                job_id=job_id,
                                tenant_id=tenant_id,
                            )
                except Exception as e:
                    errors.append(f"Failed to abort in-progress job: {e}")

        logger.info(
            "queue_cleanup_complete",
            tenant_id=tenant_id,
            queued_removed=queued_removed,
            in_progress_aborted=in_progress_aborted,
            error_count=len(errors),
        )

        return QueueCleanupResult(
            queued_jobs_removed=queued_removed,
            in_progress_jobs_aborted=in_progress_aborted,
            errors=errors,
        )

    finally:
        await redis.aclose()


async def _get_job_tenant(redis: Any, job_id: str) -> str | None:
    """
    Extract tenant_id from a job's stored data.

    Uses ARQ's Job API to safely deserialize job data instead of raw pickle.
    For alert analysis jobs, tenant_id is the first positional argument.

    Args:
        redis: Redis connection
        job_id: Job ID to inspect

    Returns:
        tenant_id if found, None otherwise
    """
    try:
        job = Job(job_id, redis)
        job_info = await job.info()
        if job_info is None:
            return None
        if job_info.args and len(job_info.args) > 0:
            return job_info.args[0]
    except Exception as e:
        logger.warning("job_data_parse_failed", job_id=job_id, error=str(e))

    return None


async def get_queue_stats(redis_settings: RedisSettings) -> dict[str, Any]:
    """
    Get queue statistics by tenant.

    Returns breakdown of queued and in-progress jobs per tenant.

    Args:
        redis_settings: Redis connection settings

    Returns:
        Dict with queue statistics
    """
    redis = await create_pool(redis_settings)

    try:
        # Get queue length
        queue_length = await redis.zcard(ARQ_QUEUE_KEY)

        # Get queued jobs by tenant
        job_ids = await redis.zrange(ARQ_QUEUE_KEY, 0, -1)
        tenant_counts: dict[str, int] = {}

        for job_id_bytes in job_ids:
            job_id = (
                job_id_bytes.decode()
                if isinstance(job_id_bytes, bytes)
                else job_id_bytes
            )
            try:
                tenant = await _get_job_tenant(redis, job_id)
                if tenant:
                    tenant_counts[tenant] = tenant_counts.get(tenant, 0) + 1
            except Exception:
                tenant_counts["unknown"] = tenant_counts.get("unknown", 0) + 1

        # Get in-progress jobs
        all_keys = await redis.keys(f"{ARQ_IN_PROGRESS_PREFIX}*")
        worker_jobs = [k for k in (all_keys or []) if b":cron:" not in k]
        cron_markers = len(all_keys or []) - len(worker_jobs)

        return {
            "queue_length": queue_length,
            "in_progress_jobs": len(worker_jobs),
            "cron_markers": cron_markers,
            "jobs_by_tenant": tenant_counts,
        }

    finally:
        await redis.aclose()
