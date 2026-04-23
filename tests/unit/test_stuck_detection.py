"""Unit tests for stuck detection framework.

Tests the StuckJobConfig, mark_rows_as_failed utility, and run_all_stuck_detection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.common.stuck_detection import (
    StuckDetectionResult,
    StuckJobConfig,
    mark_rows_as_failed,
    run_all_stuck_detection,
)

# ---------------------------------------------------------------------------
# StuckJobConfig
# ---------------------------------------------------------------------------


class TestStuckJobConfig:
    """Tests for the StuckJobConfig dataclass."""

    def test_config_required_fields(self):
        """Config requires name and timeout_seconds."""
        config = StuckJobConfig(name="test", timeout_seconds=3600)
        assert config.name == "test"
        assert config.timeout_seconds == 3600

    def test_config_defaults(self):
        """Config has sensible defaults."""
        config = StuckJobConfig(name="test", timeout_seconds=3600)
        assert config.max_attempts == 1
        assert config.fail_status == "failed"

    def test_config_timeout_minutes_property(self):
        """timeout_minutes is a convenience property."""
        config = StuckJobConfig(name="test", timeout_seconds=1200)
        assert config.timeout_minutes == 20

    def test_config_is_retry_enabled(self):
        """max_attempts > 1 means retry is enabled."""
        fail_fast = StuckJobConfig(name="a", timeout_seconds=60, max_attempts=1)
        assert fail_fast.is_retry_enabled is False

        retry = StuckJobConfig(name="b", timeout_seconds=60, max_attempts=3)
        assert retry.is_retry_enabled is True


# ---------------------------------------------------------------------------
# StuckDetectionResult
# ---------------------------------------------------------------------------


class TestStuckDetectionResult:
    """Tests for the StuckDetectionResult dataclass."""

    def test_empty_result(self):
        """Default result has zero total and no errors."""
        result = StuckDetectionResult()
        assert result.total == 0
        assert result.has_errors is False
        assert result.counts == {}
        assert result.errors == []

    def test_total_sums_counts(self):
        """total sums all count values."""
        result = StuckDetectionResult(counts={"a": 2, "b": 3})
        assert result.total == 5

    def test_has_errors_when_errors_present(self):
        """has_errors is True when errors list is non-empty."""
        result = StuckDetectionResult(errors=["detector_x"])
        assert result.has_errors is True


# ---------------------------------------------------------------------------
# mark_rows_as_failed
# ---------------------------------------------------------------------------


class TestMarkRowsAsFailed:
    """Tests for the mark_rows_as_failed utility."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self):
        """No rows → no work done."""
        result = await mark_rows_as_failed([], AsyncMock(), "test")
        assert result == 0

    @pytest.mark.asyncio
    async def test_marks_all_rows(self):
        """All rows marked successfully."""
        rows = [MagicMock(id="r1"), MagicMock(id="r2"), MagicMock(id="r3")]
        mark_fn = AsyncMock(return_value=True)

        result = await mark_rows_as_failed(rows, mark_fn, "test")

        assert result == 3
        assert mark_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_skips_rows_returning_false(self):
        """Rows where mark_fn returns False are skipped."""
        rows = [MagicMock(id="r1"), MagicMock(id="r2")]
        mark_fn = AsyncMock(side_effect=[True, False])

        result = await mark_rows_as_failed(rows, mark_fn, "test")

        assert result == 1

    @pytest.mark.asyncio
    async def test_continues_on_exception(self):
        """Exceptions on one row don't stop processing of others."""
        rows = [MagicMock(id="r1"), MagicMock(id="r2"), MagicMock(id="r3")]
        mark_fn = AsyncMock(side_effect=[True, RuntimeError("boom"), True])

        result = await mark_rows_as_failed(rows, mark_fn, "test")

        assert result == 2
        assert mark_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_none_return_counts_as_success(self):
        """mark_fn returning None (no explicit return) counts as success."""
        rows = [MagicMock(id="r1")]
        mark_fn = AsyncMock(return_value=None)

        result = await mark_rows_as_failed(rows, mark_fn, "test")
        assert result == 1


# ---------------------------------------------------------------------------
# run_all_stuck_detection
# ---------------------------------------------------------------------------


def _patch_all_detectors(**overrides):
    """Patch all 5 stuck detectors, defaulting to 0 unless overridden.

    Accepts keyword arguments matching detector names to override
    return values or side_effects.
    """
    import contextlib

    detectors = {
        "_detect_stuck_running_alerts": 0,
        "_detect_stuck_generations": 0,
        "_detect_stuck_content_reviews": 0,
        "_detect_stuck_task_runs": 0,
        "_detect_stuck_workflow_runs": 0,
    }
    patches = []
    for name, default in detectors.items():
        val = overrides.get(name, default)
        if isinstance(val, Exception):
            p = patch(
                f"analysi.common.stuck_detection.{name}",
                new_callable=AsyncMock,
                side_effect=val,
            )
        else:
            p = patch(
                f"analysi.common.stuck_detection.{name}",
                new_callable=AsyncMock,
                return_value=val,
            )
        patches.append(p)

    return contextlib.ExitStack(), patches


class TestRunAllStuckDetection:
    """Tests for run_all_stuck_detection orchestrator."""

    @pytest.mark.asyncio
    async def test_returns_results_per_detector(self):
        """Each detector returns its count in the result."""
        stack, patches = _patch_all_detectors(
            _detect_stuck_running_alerts=2,
            _detect_stuck_generations=1,
        )
        with stack:
            for p in patches:
                stack.enter_context(p)
            result = await run_all_stuck_detection(
                alert_repo=AsyncMock(),
                generation_repo=AsyncMock(),
            )

        assert isinstance(result, StuckDetectionResult)
        assert result.counts["stuck_running_alerts"] == 2
        assert result.counts["stuck_generations"] == 1
        assert result.counts["stuck_content_reviews"] == 0
        assert result.counts["stuck_task_runs"] == 0
        assert result.counts["stuck_workflow_runs"] == 0
        assert result.total == 3
        assert result.has_errors is False

    @pytest.mark.asyncio
    async def test_new_detectors_report_counts(self):
        """Task run and workflow run detectors are called and reported."""
        stack, patches = _patch_all_detectors(
            _detect_stuck_task_runs=3,
            _detect_stuck_workflow_runs=1,
        )
        with stack:
            for p in patches:
                stack.enter_context(p)
            result = await run_all_stuck_detection(
                alert_repo=AsyncMock(),
                generation_repo=AsyncMock(),
            )

        assert result.counts["stuck_task_runs"] == 3
        assert result.counts["stuck_workflow_runs"] == 1
        assert result.total == 4

    @pytest.mark.asyncio
    async def test_detector_failure_tracked_in_errors(self):
        """Failed detectors are recorded in errors."""
        stack, patches = _patch_all_detectors(
            _detect_stuck_running_alerts=2,
            _detect_stuck_generations=RuntimeError("DB gone"),
        )
        with stack:
            for p in patches:
                stack.enter_context(p)
            result = await run_all_stuck_detection(
                alert_repo=AsyncMock(),
                generation_repo=AsyncMock(),
            )

        assert result.counts["stuck_running_alerts"] == 2
        assert result.counts["stuck_generations"] == 0
        assert result.errors == ["stuck_generations"]
        assert result.has_errors is True

    @pytest.mark.asyncio
    async def test_all_detectors_fail_returns_all_errors(self):
        """When all detectors fail, all names appear in errors."""
        stack, patches = _patch_all_detectors(
            _detect_stuck_running_alerts=RuntimeError("fail1"),
            _detect_stuck_generations=RuntimeError("fail2"),
            _detect_stuck_content_reviews=RuntimeError("fail3"),
            _detect_stuck_task_runs=RuntimeError("fail4"),
            _detect_stuck_workflow_runs=RuntimeError("fail5"),
        )
        with stack:
            for p in patches:
                stack.enter_context(p)
            result = await run_all_stuck_detection(
                alert_repo=AsyncMock(),
                generation_repo=AsyncMock(),
            )

        assert result.total == 0
        assert set(result.errors) == {
            "stuck_running_alerts",
            "stuck_generations",
            "stuck_content_reviews",
            "stuck_task_runs",
            "stuck_workflow_runs",
        }
