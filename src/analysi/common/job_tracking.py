"""
Unified job tracking decorator for ARQ jobs (Project Leros).

Provides cross-cutting concerns:
- Correlation ID generation + context propagation
- Tenant context propagation (by convention: ``tenant_id`` argument)
- asyncio.timeout() enforcement
- Structured start/end/fail logging
- Duration tracking
- job_tracking JSONB persistence
- Optional automatic retry on failure (``max_retries``)

Usage:
    @tracked_job(
        job_type="run_integration",
        timeout_seconds=300,
        model_class=IntegrationRun,
        extract_row_id=lambda ctx, tenant_id, integration_id, **kw: kw.get("run_id"),
    )
    async def run_integration(ctx, tenant_id, integration_id, ...):
        ...

Retry usage:
    @tracked_job(
        job_type="execute_task_run",
        timeout_seconds=3600,
        model_class=TaskRun,
        extract_row_id=lambda ctx, task_run_id, tenant_id: task_run_id,
        max_retries=2,  # retry up to 2 times on failure
    )
    async def execute_task_run(ctx, task_run_id, tenant_id):
        ...

Tenant ID is extracted automatically from the wrapped function's
``tenant_id`` argument (positional or keyword).  Jobs without a
``tenant_id`` parameter (e.g. cross-tenant cron jobs) simply skip
tenant context — no special configuration needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from analysi.common.arq_enqueue import enqueue_arq_job
from analysi.common.correlation import (
    generate_correlation_id,
    set_correlation_id,
    set_tenant_id,
)
from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal

logger = get_logger(__name__)

# Maximum number of error entries stored in job_tracking.errors
_MAX_ERRORS = 10

# Delay between retry attempts (seconds).  Provides breathing room for
# transient errors (Redis hiccup, LLM rate-limit) without a full backoff
# strategy.  Kept as a module constant so it's easy to tune later.
_RETRY_DELAY_SECONDS = 30


def tracked_job(
    *,
    job_type: str,
    timeout_seconds: int = 3600,
    model_class: type | None = None,
    extract_row_id: Callable[..., Any] | None = None,
    pause_exceptions: tuple[type[Exception], ...] = (),
    max_retries: int = 0,
) -> Callable:
    """Decorator that wraps an ARQ job function with lifecycle tracking.

    Args:
        job_type: Human-readable name for the job (e.g., "run_integration").
        timeout_seconds: Maximum execution time before asyncio.TimeoutError.
        model_class: SQLAlchemy model with a ``job_tracking`` JSONB column.
            When provided together with *extract_row_id*, the decorator writes
            lifecycle metadata to the row.
        extract_row_id: Callable ``(ctx, *args, **kwargs) -> row_id`` that
            returns the primary key value for the tracked row.
        pause_exceptions: Exception types that indicate the job paused (not
            failed).  Forward-looking — currently unused by any job.
        max_retries: Number of retry attempts after the first failure.
            ``0`` (default) means no retries — failures propagate immediately.
            When > 0, the decorator re-enqueues the job on failure (up to
            *max_retries* times) with a 30-second delay.  The row's status
            is reset to ``running`` before re-enqueue.

    Tenant ID is extracted by convention from the wrapped function's
    ``tenant_id`` parameter (positional or keyword).  Jobs without
    this parameter simply skip tenant context.
    """

    def decorator(fn: Callable) -> Callable:
        # Cache tenant_id positional index at decoration time (not per call)
        _tenant_idx: int | None = None
        try:
            params = list(inspect.signature(fn).parameters.keys())
            _tenant_idx = params.index("tenant_id")
        except (ValueError, TypeError):
            _tenant_idx = None

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # args[0] is the ARQ ctx dict
            ctx = args[0] if args else kwargs.get("ctx", {})

            # --- Correlation ID ---
            correlation_id = generate_correlation_id()
            set_correlation_id(correlation_id)

            # --- Tenant ID ---
            tenant_id = _extract_tenant(_tenant_idx, args, kwargs)
            if tenant_id is not None:
                set_tenant_id(tenant_id)

            # --- Row ID for DB tracking ---
            row_id = None
            if model_class is not None and extract_row_id is not None:
                try:
                    row_id = extract_row_id(*args, **kwargs)
                except Exception:
                    row_id = None

            worker_id = (
                ctx.get("worker_id", "unknown") if isinstance(ctx, dict) else "unknown"
            )

            # --- DB: mark start (returns current attempt number) ---
            current_attempt = await _write_tracking_start(
                model_class, row_id, correlation_id, worker_id
            )

            logger.info(
                "job_started",
                job_type=job_type,
                row_id=str(row_id) if row_id else None,
                worker_id=worker_id,
            )

            start_ns = time.monotonic_ns()
            try:
                async with asyncio.timeout(timeout_seconds):
                    result = await fn(*args, **kwargs)

                duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

                # --- DB: mark success ---
                await _write_tracking_success(model_class, row_id, duration_ms)

                logger.info(
                    "job_completed",
                    job_type=job_type,
                    duration_ms=duration_ms,
                    row_id=str(row_id) if row_id else None,
                )
                return result

            except pause_exceptions as exc:
                duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
                logger.info(
                    "job_paused",
                    job_type=job_type,
                    duration_ms=duration_ms,
                    pause_type=type(exc).__name__,
                )
                raise

            except Exception as exc:
                duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
                error_type = type(exc).__name__

                # --- DB: mark failure ---
                await _write_tracking_failure(
                    model_class, row_id, duration_ms, error_type, str(exc)
                )

                # --- Retry if attempts remain ---
                if max_retries > 0 and current_attempt <= max_retries:
                    retried = await _attempt_retry(
                        fn,
                        args,
                        model_class,
                        row_id,
                        job_type,
                        current_attempt,
                        max_retries,
                        error_type,
                    )
                    if retried:
                        return None  # Swallow — ARQ considers job "done"

                # --- Permanent failure ---
                logger.error(
                    "job_failed",
                    job_type=job_type,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    error_message=str(exc),
                    row_id=str(row_id) if row_id else None,
                )
                raise

            except asyncio.CancelledError as exc:
                # CancelledError (BaseException, not Exception) is raised when
                # ARQ's wait_for() times out or the worker shuts down.  Without
                # this handler, cancellation leaves no failure record in the
                # job_tracking JSONB.
                duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
                error_type = type(exc).__name__

                # Best-effort DB write — must not mask the cancellation.
                # _write_tracking_failure uses `except Exception` internally,
                # but a secondary CancelledError (BaseException) from its async
                # I/O would propagate and prevent the `raise` below.
                with contextlib.suppress(BaseException):
                    await _write_tracking_failure(
                        model_class, row_id, duration_ms, error_type, str(exc)
                    )

                logger.warning(
                    "job_cancelled",
                    job_type=job_type,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    row_id=str(row_id) if row_id else None,
                )
                raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Tenant extraction
# ---------------------------------------------------------------------------


def _extract_tenant(
    tenant_idx: int | None,
    args: tuple,
    kwargs: dict,
) -> str | None:
    """Extract tenant_id from function arguments by convention.

    Checks kwargs first (``tenant_id=...``), then falls back to the
    pre-computed positional index from the function signature.
    """
    if "tenant_id" in kwargs:
        return kwargs["tenant_id"]

    if tenant_idx is not None and tenant_idx < len(args):
        return args[tenant_idx]

    return None


# ---------------------------------------------------------------------------
# DB writes (fire-and-forget — failures never propagate)
# ---------------------------------------------------------------------------


async def _load_tracking(
    model_class: type, row_id: Any, session: Any
) -> tuple[Any, dict] | None:
    """Load a row and its current job_tracking dict.

    Returns ``(row, tracking_dict)`` or ``None`` if the row doesn't exist.
    """
    pk_col = _pk_column(model_class)
    stmt = select(model_class).where(pk_col == str(row_id))
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    tracking = dict(row.job_tracking) if row.job_tracking else {}
    return row, tracking


async def _write_tracking_start(
    model_class: type | None,
    row_id: Any,
    correlation_id: str,
    worker_id: str,
) -> int:
    """Increment attempt counter and set start metadata.

    Returns:
        The current attempt number (1-based).  Returns ``1`` when DB
        tracking is not configured or on write failure.
    """
    if model_class is None or row_id is None:
        return 1
    try:
        async with AsyncSessionLocal() as session:
            loaded = await _load_tracking(model_class, row_id, session)
            if loaded is None:
                return 1
            row, tracking = loaded

            attempt = tracking.get("attempt", 0) + 1
            tracking["attempt"] = attempt
            tracking["started_at"] = datetime.now(UTC).isoformat()
            tracking["worker_id"] = worker_id
            tracking["correlation_id"] = correlation_id

            row.job_tracking = tracking
            await session.commit()
            return attempt
    except Exception as exc:
        logger.warning(
            "job_tracking_write_failed",
            phase="start",
            error=str(exc),
            row_id=str(row_id),
        )
        return 1


async def _write_tracking_success(
    model_class: type | None,
    row_id: Any,
    duration_ms: int,
) -> None:
    """Set completion metadata."""
    if model_class is None or row_id is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            loaded = await _load_tracking(model_class, row_id, session)
            if loaded is None:
                return
            row, tracking = loaded

            tracking["duration_ms"] = duration_ms
            tracking["completed_at"] = datetime.now(UTC).isoformat()

            row.job_tracking = tracking
            await session.commit()
    except Exception as exc:
        logger.warning(
            "job_tracking_write_failed",
            phase="success",
            error=str(exc),
            row_id=str(row_id),
        )


async def _write_tracking_failure(
    model_class: type | None,
    row_id: Any,
    duration_ms: int,
    error_type: str,
    error_message: str,
) -> None:
    """Append to errors array (capped at _MAX_ERRORS) and set duration."""
    if model_class is None or row_id is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            loaded = await _load_tracking(model_class, row_id, session)
            if loaded is None:
                return
            row, tracking = loaded

            errors = list(tracking.get("errors", []))
            errors.append(
                {
                    "type": error_type,
                    "message": error_message[:500],  # cap message length
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            # Keep only the most recent _MAX_ERRORS
            if len(errors) > _MAX_ERRORS:
                errors = errors[-_MAX_ERRORS:]

            tracking["errors"] = errors
            tracking["duration_ms"] = duration_ms
            tracking["completed_at"] = datetime.now(UTC).isoformat()

            row.job_tracking = tracking
            await session.commit()
    except Exception as exc:
        logger.warning(
            "job_tracking_write_failed",
            phase="failure",
            error=str(exc),
            row_id=str(row_id),
        )


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


async def _attempt_retry(
    fn: Callable,
    args: tuple,
    model_class: type | None,
    row_id: Any,
    job_type: str,
    current_attempt: int,
    max_retries: int,
    error_type: str,
) -> bool:
    """Attempt to re-enqueue a failed job for retry.

    Resets the row's status to ``running`` and re-enqueues the job with a
    30-second delay.  Returns ``True`` if the retry was successfully
    enqueued, ``False`` on any failure (caller should fall through to
    permanent failure).
    """
    try:
        from datetime import timedelta

        await _reset_row_for_retry(model_class, row_id)

        function_path = f"{fn.__module__}.{fn.__qualname__}"
        await enqueue_arq_job(
            function_path,
            *args[1:],  # skip ctx — ARQ provides it
            _defer_by=timedelta(seconds=_RETRY_DELAY_SECONDS),
        )

        logger.info(
            "job_retrying",
            job_type=job_type,
            attempt=current_attempt,
            max_retries=max_retries,
            next_attempt=current_attempt + 1,
            error_type=error_type,
            row_id=str(row_id) if row_id else None,
        )
        return True

    except Exception:
        logger.exception(
            "job_retry_enqueue_failed",
            job_type=job_type,
            attempt=current_attempt,
            row_id=str(row_id) if row_id else None,
        )
        return False


async def _reset_row_for_retry(
    model_class: type | None,
    row_id: Any,
) -> None:
    """Reset a row's status to ``running`` before retry re-enqueue.

    The job's own error handler may have already set the status to
    ``failed``.  This resets it so the next attempt starts clean.
    Best-effort — if this fails, the re-enqueue may still work and
    the job function can handle the status itself.
    """
    if model_class is None or row_id is None:
        return
    try:
        from sqlalchemy import update

        pk_col = _pk_column(model_class)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(model_class)
                .where(pk_col == str(row_id))
                .values(
                    status="running",
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "job_retry_status_reset_failed",
            error=str(exc),
            row_id=str(row_id),
        )


def _pk_column(model_class: type):
    """Return the first primary key column of the model."""
    # SQLAlchemy models expose __table__.primary_key
    return next(iter(model_class.__table__.primary_key.columns))
