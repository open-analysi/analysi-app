"""Shared ARQ job enqueue utility.

Maintains a **shared Redis pool** for enqueuing ARQ jobs.  The pool is
created lazily on first use and reused across all subsequent calls,
avoiding the overhead of creating and tearing down a connection pool
per enqueue.

Pool lifecycle:
    - ``get_pool()``   — returns the cached pool, creating it on first call
    - ``close_pool()`` — gracefully closes the pool (e.g. on shutdown)
    - ``reset_pool()`` — clears the cached ref without closing (for tests)

Enqueue failure safety:
    - ``enqueue_or_fail()`` — enqueue with automatic row-status rollback
      on Redis failure.  When the PG row has already been committed before
      enqueue, a Redis error would orphan the row in ``running`` status.
      This helper marks the row ``failed`` so stuck detection is not the
      only safety net.

Uses the test-aware Redis settings so integration tests automatically
route to the test DB.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Module-level shared pool (lazy singleton)
_pool = None
_pool_lock = asyncio.Lock()


async def get_pool():
    """Return the shared ArqRedis pool, creating it on first call.

    Uses an asyncio.Lock to prevent duplicate pool creation when
    multiple coroutines race on the first call.
    """
    global _pool

    if _pool is not None:
        return _pool

    async with _pool_lock:
        # Double-check after acquiring the lock
        if _pool is not None:
            return _pool

        from arq import create_pool

        from analysi.alert_analysis.worker import WorkerSettings

        _pool = await create_pool(WorkerSettings.get_redis_settings())
        logger.debug("arq_pool_created")
        return _pool


async def close_pool() -> None:
    """Gracefully close the shared pool.

    Safe to call multiple times or when no pool exists.
    """
    global _pool

    if _pool is None:
        return

    pool = _pool
    _pool = None
    await pool.aclose()
    logger.debug("arq_pool_closed")


def reset_pool() -> None:
    """Clear the cached pool reference without closing it.

    For use in test teardown where the event loop context may differ
    from the one that created the pool.
    """
    global _pool
    _pool = None


async def enqueue_arq_job(
    function: str,
    *args: Any,
    _job_id: str | None = None,
    _defer_by: timedelta | None = None,
) -> str | None:
    """Enqueue an ARQ job on the alert-processing worker.

    Uses the shared Redis pool (created lazily on first call).

    Args:
        function: Full module path of the ARQ job function.
        *args: Positional arguments forwarded to the job.
        _job_id: Optional explicit job ID for idempotency.
        _defer_by: Optional delay before the job becomes eligible
            for execution.  Used by the retry mechanism to avoid
            hammering transient errors.

    Returns:
        The ARQ job ID string, or ``None`` if the job was a duplicate
        (same ``_job_id`` already enqueued).
    """
    pool = await get_pool()
    job = await pool.enqueue_job(function, *args, _job_id=_job_id, _defer_by=_defer_by)
    job_id = job.job_id if job else None
    logger.debug(
        "arq_job_enqueued",
        function=function,
        job_id=job_id or "duplicate",
    )
    return job_id


async def enqueue_or_fail(
    function: str,
    *args: Any,
    model_class: type,
    row_id: Any,
) -> str | None:
    """Enqueue an ARQ job, marking the DB row ``failed`` if Redis is down.

    After ``session.commit()``, the row is visible in PG with
    ``status='running'``.  If the Redis enqueue fails, no worker will
    ever pick the job up — the row would stay ``running`` forever.

    This helper catches the enqueue error, writes ``status='failed'``
    to the row (using a fresh session so the original request's session
    is not affected), and then re-raises so the caller can return an
    appropriate error response.

    Args:
        function: Full module path of the ARQ job function.
        *args: Positional arguments forwarded to the job.
        model_class: SQLAlchemy model (e.g. ``TaskRun``, ``WorkflowRun``).
        row_id: Primary key value for the row to update on failure.

    Returns:
        The ARQ job ID string (or ``None`` for duplicates).

    Raises:
        The original Redis/connection error after marking the row failed.
    """
    try:
        return await enqueue_arq_job(function, *args)
    except Exception as exc:
        logger.error(
            "enqueue_failed_marking_row",
            function=function,
            row_id=str(row_id),
            error=str(exc),
        )
        # Best-effort: mark the row failed. _mark_row_failed has its own
        # try/except, but guard here too in case of unexpected errors.
        try:
            await _mark_row_failed(model_class, row_id, str(exc))
        except Exception:
            logger.exception(
                "enqueue_or_fail_mark_failed_error",
                row_id=str(row_id),
            )
        raise


async def _mark_row_failed(
    model_class: type,
    row_id: Any,
    error: str,
) -> None:
    """Best-effort update of a row's status to ``failed``.

    Uses a dedicated session so that failures here don't affect the
    caller's session state.
    """
    try:
        from datetime import UTC, datetime

        from sqlalchemy import update

        from analysi.db.session import AsyncSessionLocal

        pk_col = next(iter(model_class.__table__.primary_key.columns))
        values: dict[str, Any] = {
            "status": "failed",
            "updated_at": datetime.now(UTC),
        }
        # Write error message if the model has the column
        if hasattr(model_class, "error_message"):
            values["error_message"] = f"Failed to enqueue job: {error}"

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(model_class).where(pk_col == str(row_id)).values(**values)
            )
            await session.commit()
        logger.info(
            "enqueue_failure_row_marked_failed",
            row_id=str(row_id),
        )
    except Exception:
        logger.exception(
            "enqueue_failure_row_mark_failed_error",
            row_id=str(row_id),
        )
