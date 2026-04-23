"""
Stuck job detection framework.

Consolidates stuck detection into a config-driven set of detectors with a shared
``mark_rows_as_failed`` utility.  Three simple "fail-immediately" detectors
are defined here; complex detectors (HITL timeout, orphaned analyses)
stay as named functions in reconciliation.py sharing the same utility.

Control-event stuck reset stays inside ``claim_batch()`` because it's
tightly coupled to the claiming atomic-lock pattern.

Usage in reconciliation cron::

    result = await run_all_stuck_detection(
        alert_repo=alert_repo,
        generation_repo=generation_repo,
    )
    # result.counts = {"stuck_running_alerts": 2, "stuck_generations": 0, ...}
    # result.errors = []  (or ["stuck_generations"] on failure)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class StuckDetectionResult:
    """Return value from ``run_all_stuck_detection``.

    Separates counts (always ``int``) from error tracking (``list[str]``)
    so callers can safely iterate counts without mixed-type surprises.
    """

    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StuckJobConfig:
    """Configuration for one stuck-job detection rule.

    Attributes:
        name: Human-readable identifier (e.g. ``"stuck_running_alerts"``).
        timeout_seconds: How long before a row is considered stuck.
        max_attempts: Number of attempts before permanent failure.
            ``1`` means fail immediately (no retry).
        fail_status: Status string to set on permanent failure.
    """

    name: str
    timeout_seconds: int
    max_attempts: int = 1
    fail_status: str = "failed"

    @property
    def timeout_minutes(self) -> int:
        """Convenience: timeout in whole minutes."""
        return self.timeout_seconds // 60

    @property
    def is_retry_enabled(self) -> bool:
        """True when the detector supports retry before failing."""
        return self.max_attempts > 1


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------


async def mark_rows_as_failed(
    rows: list[Any],
    mark_fn: Callable,
    detector_name: str,
    *,
    row_id_fn: Callable[[Any], str] | None = None,
) -> int:
    """Apply *mark_fn* to each row, catching per-row errors.

    Args:
        rows: Rows to process (may be model instances or tuples).
        mark_fn: ``async (row) -> bool | None``.  Return ``False`` to
            signal the row was skipped (already handled).  ``None`` or
            ``True`` count as success.
        detector_name: Used for structured log events.
        row_id_fn: Optional callable to extract a human-readable ID from
            each row for logging.  Defaults to ``getattr(row, "id")``.

    Returns:
        Number of rows successfully marked.
    """
    if not rows:
        return 0

    def _default_row_id(row: Any) -> str:
        return str(getattr(row, "id", None) or "unknown")

    get_id = row_id_fn or _default_row_id

    logger.info(
        "found_stuck_rows",
        detector=detector_name,
        count=len(rows),
    )

    marked = 0
    skipped = 0
    errored = 0
    for row in rows:
        try:
            row_id = get_id(row)
        except Exception:
            row_id = "unknown"
        try:
            result = await mark_fn(row)
            if result is False:
                skipped += 1
            else:
                marked += 1
                logger.info(
                    "marked_stuck_row",
                    detector=detector_name,
                    row_id=row_id,
                )
        except Exception:
            errored += 1
            logger.exception(
                "failed_to_mark_stuck_row",
                detector=detector_name,
                row_id=row_id,
            )

    if marked > 0 or skipped > 0 or errored > 0:
        logger.info(
            "marked_stuck_rows_complete",
            detector=detector_name,
            count=marked,
            skipped=skipped,
            errored=errored,
        )

    return marked


# ---------------------------------------------------------------------------
# Individual detector callables
# ---------------------------------------------------------------------------


async def _detect_stuck_running_alerts(alert_repo: Any) -> int:
    """Detect alerts stuck in 'running' for too long and mark them failed.

    Delegates to AlertRepository.find_stuck_running_alerts() +
    mark_stuck_alert_failed() for dual-table update (AlertAnalysis + Alert).
    """
    from analysi.alert_analysis.config import AlertAnalysisConfig

    timeout_minutes = AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES

    stuck_results = await alert_repo.find_stuck_running_alerts(
        stuck_threshold_minutes=timeout_minutes
    )

    async def _mark(pair: tuple) -> bool:
        alert, analysis = pair
        if not alert.id or not analysis or not analysis.id:
            logger.warning(
                "stuck_running_alert_missing_data",
                alert_id=getattr(alert, "id", None),
                analysis_id=getattr(analysis, "id", None) if analysis else None,
            )
            return False
        error_message = (
            f"Alert analysis timed out after {timeout_minutes} minutes. "
            f"Worker may have crashed or been killed externally."
        )
        return await alert_repo.mark_stuck_alert_failed(
            tenant_id=alert.tenant_id,
            alert_id=str(alert.id),
            analysis_id=str(analysis.id),
            error=error_message,
        )

    return await mark_rows_as_failed(
        stuck_results,
        _mark,
        "running_alerts",
        row_id_fn=lambda pair: str(pair[0].id) if pair[0].id else "unknown",
    )


async def _detect_stuck_generations(generation_repo: Any) -> int:
    """Detect workflow generations stuck in 'running' and mark them failed.

    Delegates to WorkflowGenerationRepository for the complex mark-as-failed
    logic (is_active, orchestration_results, WHERE status guard).
    """
    from analysi.alert_analysis.config import AlertAnalysisConfig

    stuck_generations = await generation_repo.find_stuck_generations(
        timeout_seconds=AlertAnalysisConfig.JOB_TIMEOUT
    )

    timeout_minutes = AlertAnalysisConfig.JOB_TIMEOUT // 60

    async def _mark(generation: Any) -> bool:
        created_at_str = (
            generation.created_at.isoformat() if generation.created_at else "unknown"
        )
        error_message = (
            f"Workflow generation exceeded timeout threshold "
            f"(created_at: {created_at_str}). "
            f"Likely timed out by ARQ worker after {timeout_minutes} minutes."
        )
        return await generation_repo.mark_as_failed(generation, error_message)

    return await mark_rows_as_failed(stuck_generations, _mark, "generations")


async def _detect_stuck_content_reviews() -> int:
    """Detect content reviews stuck in 'pending' and mark them failed.

    Uses its own session (content reviews have independent lifecycle).
    """
    from analysi.alert_analysis.jobs.content_review import (
        reconcile_stuck_content_reviews,
    )

    return await reconcile_stuck_content_reviews()


async def _detect_stuck_task_runs() -> int:
    """Detect task_runs stuck in 'running' and mark them failed.

    A task_run stays ``running`` when:
    - The worker crashed mid-execution and no one updated the row.
    - Redis lost the job after the PG commit (enqueue_or_fail was not
      used, or the enqueue succeeded but Redis data was lost).

    Uses ``updated_at`` to detect staleness — any live job updates
    ``updated_at`` via the ``@tracked_job`` decorator.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select, update

    from analysi.alert_analysis.config import AlertAnalysisConfig
    from analysi.db.session import AsyncSessionLocal
    from analysi.models.task_run import TaskRun

    timeout_minutes = AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES
    threshold = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with AsyncSessionLocal() as session:
        # Find task_runs stuck in running
        stmt = (
            select(TaskRun)
            .where(
                TaskRun.status == "running",
                TaskRun.updated_at < threshold,
            )
            .order_by(TaskRun.updated_at)
        )
        result = await session.execute(stmt)
        stuck_rows = list(result.scalars().all())

        if not stuck_rows:
            return 0

        async def _mark(row: TaskRun) -> bool:
            await session.execute(
                update(TaskRun)
                .where(
                    TaskRun.id == row.id,
                    TaskRun.status == "running",
                )
                .values(
                    status="failed",
                    updated_at=datetime.now(UTC),
                )
            )
            return True

        count = await mark_rows_as_failed(stuck_rows, _mark, "task_runs")
        if count > 0:
            await session.commit()
        return count


async def _detect_stuck_workflow_runs() -> int:
    """Detect workflow_runs stuck in 'running' and mark them failed.

    Same logic as ``_detect_stuck_task_runs`` but for workflow runs.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select, update

    from analysi.alert_analysis.config import AlertAnalysisConfig
    from analysi.db.session import AsyncSessionLocal
    from analysi.models.workflow_execution import WorkflowRun

    timeout_minutes = AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES
    threshold = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.updated_at < threshold,
            )
            .order_by(WorkflowRun.updated_at)
        )
        result = await session.execute(stmt)
        stuck_rows = list(result.scalars().all())

        if not stuck_rows:
            return 0

        error_msg = (
            f"Workflow run timed out after {timeout_minutes} minutes. "
            f"Worker may have crashed or job was lost from queue."
        )

        async def _mark(row: WorkflowRun) -> bool:
            await session.execute(
                update(WorkflowRun)
                .where(
                    WorkflowRun.id == row.id,
                    WorkflowRun.status == "running",
                )
                .values(
                    status="failed",
                    updated_at=datetime.now(UTC),
                    error_message=error_msg,
                )
            )
            return True

        count = await mark_rows_as_failed(stuck_rows, _mark, "workflow_runs")
        if count > 0:
            await session.commit()
        return count


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_all_stuck_detection(
    *,
    alert_repo: Any,
    generation_repo: Any,
) -> StuckDetectionResult:
    """Run all registered stuck detectors and return per-detector counts.

    Called by the reconciliation cron to consolidate stuck detection.

    Args:
        alert_repo: AlertRepository instance.
        generation_repo: WorkflowGenerationRepository instance.

    Returns:
        ``StuckDetectionResult`` with counts and any error detector names.
    """
    result = StuckDetectionResult()

    try:
        result.counts["stuck_running_alerts"] = await _detect_stuck_running_alerts(
            alert_repo
        )
    except Exception:
        logger.exception("stuck_detection_failed", detector="stuck_running_alerts")
        result.counts["stuck_running_alerts"] = 0
        result.errors.append("stuck_running_alerts")

    try:
        result.counts["stuck_generations"] = await _detect_stuck_generations(
            generation_repo
        )
    except Exception:
        logger.exception("stuck_detection_failed", detector="stuck_generations")
        result.counts["stuck_generations"] = 0
        result.errors.append("stuck_generations")

    try:
        result.counts["stuck_content_reviews"] = await _detect_stuck_content_reviews()
    except Exception:
        logger.exception("stuck_detection_failed", detector="stuck_content_reviews")
        result.counts["stuck_content_reviews"] = 0
        result.errors.append("stuck_content_reviews")

    try:
        result.counts["stuck_task_runs"] = await _detect_stuck_task_runs()
    except Exception:
        logger.exception("stuck_detection_failed", detector="stuck_task_runs")
        result.counts["stuck_task_runs"] = 0
        result.errors.append("stuck_task_runs")

    try:
        result.counts["stuck_workflow_runs"] = await _detect_stuck_workflow_runs()
    except Exception:
        logger.exception("stuck_detection_failed", detector="stuck_workflow_runs")
        result.counts["stuck_workflow_runs"] = 0
        result.errors.append("stuck_workflow_runs")

    if result.total > 0 or result.has_errors:
        logger.info(
            "stuck_detection_complete",
            counts=result.counts,
            total=result.total,
            errors=result.errors or None,
        )

    return result
