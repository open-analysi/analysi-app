"""Unit tests for @tracked_job decorator (Project Leros).

Tests follow TDD: written before implementation. The decorator wraps ARQ job
functions with correlation/tenant context, timeout enforcement, structured logging,
and job_tracking JSONB persistence.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.common.job_tracking import tracked_job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "analysi.common.job_tracking"


def _arq_ctx(worker_id: str = "arq:test:1") -> dict:
    """Minimal ARQ context dict."""
    return {"redis": MagicMock(), "job_id": "test-job-123", "worker_id": worker_id}


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackedJobPositive:
    """Decorator behaviour on successful job execution."""

    @pytest.mark.asyncio
    async def test_returns_decorated_function_result(self):
        """Return value of the wrapped function passes through unchanged."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            return {"status": "success", "count": 42}

        result = await my_job(_arq_ctx(), "tenant-1")
        assert result == {"status": "success", "count": 42}

    @pytest.mark.asyncio
    async def test_sets_correlation_id(self):
        """Decorator generates and sets a correlation ID."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            return "ok"

        with (
            patch(
                f"{MODULE}.generate_correlation_id", return_value="corr-123"
            ) as mock_gen,
            patch(f"{MODULE}.set_correlation_id") as mock_set,
        ):
            await my_job(_arq_ctx(), "tenant-1")
            mock_gen.assert_called_once()
            mock_set.assert_called_once_with("corr-123")

    @pytest.mark.asyncio
    async def test_sets_tenant_id(self):
        """Decorator sets tenant context from positional arg."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id, other_arg):
            return "ok"

        with patch(f"{MODULE}.set_tenant_id") as mock_set:
            await my_job(_arq_ctx(), "tenant-abc", "other")
            mock_set.assert_called_once_with("tenant-abc")

    @pytest.mark.asyncio
    async def test_sets_tenant_id_from_kwargs(self):
        """Decorator extracts tenant_id from kwargs when not positional."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, **kwargs):
            return "ok"

        with patch(f"{MODULE}.set_tenant_id") as mock_set:
            await my_job(_arq_ctx(), tenant_id="tenant-kw")
            mock_set.assert_called_once_with("tenant-kw")

    @pytest.mark.asyncio
    async def test_logs_job_started(self):
        """Decorator emits a structured 'job_started' log."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            return "ok"

        with patch(f"{MODULE}.logger") as mock_logger:
            await my_job(_arq_ctx(), "tenant-1")
            # Find the job_started call
            started_calls = [
                c
                for c in mock_logger.info.call_args_list
                if c.args and c.args[0] == "job_started"
            ]
            assert len(started_calls) == 1

    @pytest.mark.asyncio
    async def test_logs_job_completed(self):
        """Decorator emits a 'job_completed' log with duration_ms."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            return "ok"

        with patch(f"{MODULE}.logger") as mock_logger:
            await my_job(_arq_ctx(), "tenant-1")
            completed_calls = [
                c
                for c in mock_logger.info.call_args_list
                if c.args and c.args[0] == "job_completed"
            ]
            assert len(completed_calls) == 1
            kw = completed_calls[0].kwargs
            assert "duration_ms" in kw
            assert kw["job_type"] == "test_job"

    @pytest.mark.asyncio
    async def test_tracks_duration_ms(self):
        """duration_ms is positive for a job that takes measurable time."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            await asyncio.sleep(0.01)
            return "ok"

        with patch(f"{MODULE}.logger") as mock_logger:
            await my_job(_arq_ctx(), "tenant-1")
            completed_calls = [
                c
                for c in mock_logger.info.call_args_list
                if c.args and c.args[0] == "job_completed"
            ]
            assert completed_calls[0].kwargs["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_writes_job_tracking_on_start(self):
        """When model_class provided, _write_tracking_start is called with correct args."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
        )
        async def my_job(ctx, row_id):
            return "ok"

        with patch(
            f"{MODULE}._write_tracking_start", new_callable=AsyncMock
        ) as mock_start:
            await my_job(_arq_ctx(), "row-123")
            mock_start.assert_called_once()
            call_args = mock_start.call_args
            assert call_args[0][0] is mock_model  # model_class
            assert call_args[0][1] == "row-123"  # row_id

    @pytest.mark.asyncio
    async def test_writes_job_tracking_on_success(self):
        """On success, _write_tracking_success is called with duration_ms."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
        )
        async def my_job(ctx, row_id):
            return "ok"

        with (
            patch(f"{MODULE}._write_tracking_start", new_callable=AsyncMock),
            patch(
                f"{MODULE}._write_tracking_success", new_callable=AsyncMock
            ) as mock_success,
        ):
            await my_job(_arq_ctx(), "row-123")
            mock_success.assert_called_once()
            call_args = mock_success.call_args
            assert call_args[0][0] is mock_model  # model_class
            assert call_args[0][1] == "row-123"  # row_id
            assert isinstance(call_args[0][2], int)  # duration_ms

    @pytest.mark.asyncio
    async def test_worker_id_from_ctx(self):
        """worker_id from ARQ ctx is passed to _write_tracking_start."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
        )
        async def my_job(ctx, row_id):
            return "ok"

        with patch(
            f"{MODULE}._write_tracking_start", new_callable=AsyncMock
        ) as mock_start:
            await my_job(_arq_ctx(worker_id="arq:worker:42"), "row-123")
            mock_start.assert_called_once()
            # worker_id is the 4th positional arg
            assert mock_start.call_args[0][3] == "arq:worker:42"


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackedJobFailure:
    """Decorator behaviour when the job raises an exception."""

    @pytest.mark.asyncio
    async def test_logs_failure(self):
        """Failure log includes error_type and job_type."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            raise ValueError("something broke")

        with patch(f"{MODULE}.logger") as mock_logger:
            with pytest.raises(ValueError, match="something broke"):
                await my_job(_arq_ctx(), "tenant-1")

            error_calls = [
                c
                for c in mock_logger.error.call_args_list
                if c.args and c.args[0] == "job_failed"
            ]
            assert len(error_calls) == 1
            kw = error_calls[0].kwargs
            assert kw["error_type"] == "ValueError"
            assert kw["job_type"] == "test_job"

    @pytest.mark.asyncio
    async def test_reraises_exception(self):
        """Original exception propagates to ARQ for retry/failure handling."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            await my_job(_arq_ctx(), "tenant-1")

    @pytest.mark.asyncio
    async def test_writes_job_tracking_on_failure(self):
        """_write_tracking_failure is called with error details."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
        )
        async def my_job(ctx, row_id):
            raise ValueError("bad input")

        with (
            patch(f"{MODULE}._write_tracking_start", new_callable=AsyncMock),
            patch(
                f"{MODULE}._write_tracking_failure", new_callable=AsyncMock
            ) as mock_fail,
        ):
            with pytest.raises(ValueError, match="bad input"):
                await my_job(_arq_ctx(), "row-123")

            mock_fail.assert_called_once()
            call_args = mock_fail.call_args[0]
            assert call_args[0] is mock_model  # model_class
            assert call_args[1] == "row-123"  # row_id
            assert isinstance(call_args[2], int)  # duration_ms
            assert call_args[3] == "ValueError"  # error_type
            assert call_args[4] == "bad input"  # error_message

    @pytest.mark.asyncio
    async def test_errors_capped_at_ten(self):
        """_write_tracking_failure caps errors at 10 — tested via the function directly."""
        from analysi.common.job_tracking import _MAX_ERRORS, _write_tracking_failure

        # Build a mock model with proper __table__ for _pk_column
        existing_errors = [
            {
                "type": "ValueError",
                "message": f"error-{i}",
                "timestamp": "2026-01-01T00:00:00Z",
            }
            for i in range(10)
        ]

        mock_row = MagicMock()
        mock_row.job_tracking = {"attempt": 10, "errors": existing_errors}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_ctx_mgr = AsyncMock()
        mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx_mgr.__aexit__ = AsyncMock(return_value=False)

        mock_model = MagicMock()
        mock_pk_col = MagicMock()
        mock_model.__table__ = MagicMock()
        mock_model.__table__.primary_key.columns = [mock_pk_col]

        with patch(f"{MODULE}.AsyncSessionLocal", return_value=mock_ctx_mgr):
            await _write_tracking_failure(
                mock_model, "row-123", 100, "RuntimeError", "eleventh error"
            )

        # Verify the errors were capped
        updated_tracking = mock_row.job_tracking
        assert len(updated_tracking.get("errors", [])) <= _MAX_ERRORS


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackedJobTimeout:
    """Timeout enforcement via asyncio.timeout()."""

    @pytest.mark.asyncio
    async def test_enforces_timeout(self):
        """Job exceeding timeout_seconds raises TimeoutError."""

        @tracked_job(job_type="test_job", timeout_seconds=0.05)
        async def my_job(ctx, tenant_id):
            await asyncio.sleep(10)
            return "should not reach"

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await my_job(_arq_ctx(), "tenant-1")

    @pytest.mark.asyncio
    async def test_timeout_logged_as_failure(self):
        """Timeout is logged with error_type containing 'Timeout'."""

        @tracked_job(job_type="test_job", timeout_seconds=0.05)
        async def my_job(ctx, tenant_id):
            await asyncio.sleep(10)

        with patch(f"{MODULE}.logger") as mock_logger:
            with pytest.raises((asyncio.TimeoutError, TimeoutError)):
                await my_job(_arq_ctx(), "tenant-1")

            error_calls = [
                c
                for c in mock_logger.error.call_args_list
                if c.args and c.args[0] == "job_failed"
            ]
            assert len(error_calls) == 1
            assert "Timeout" in error_calls[0].kwargs.get("error_type", "")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackedJobEdgeCases:
    """Edge cases and defensive behaviour."""

    @pytest.mark.asyncio
    async def test_without_model_class(self):
        """No DB writes when model_class is None — just logging + timeout."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            return "ok"

        # Should work without any DB mocking
        result = await my_job(_arq_ctx(), "tenant-1")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_db_write_failure_does_not_break_job(self):
        """If DB write fails, job still succeeds — failure only logged."""
        mock_model = MagicMock(__tablename__="test_table")

        # Session that raises on execute
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB is down")
        mock_ctx_mgr = AsyncMock()
        mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx_mgr.__aexit__ = AsyncMock(return_value=False)

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
        )
        async def my_job(ctx, row_id):
            return {"status": "success"}

        with (
            patch(f"{MODULE}.AsyncSessionLocal", return_value=mock_ctx_mgr),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            result = await my_job(_arq_ctx(), "row-123")

        assert result == {"status": "success"}
        # DB failure should be logged as warning
        warning_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and "job_tracking" in str(c.args[0]).lower()
        ]
        assert len(warning_calls) >= 1

    @pytest.mark.asyncio
    async def test_no_tenant_id_available(self):
        """When no tenant_id in args or kwargs, set_tenant_id is not called."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx):
            return "ok"

        with patch(f"{MODULE}.set_tenant_id") as mock_set:
            await my_job(_arq_ctx())
            mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_exception_logged_as_paused(self):
        """Pause exceptions are logged as status='paused', not 'failed'."""

        class MyPauseError(Exception):
            pass

        @tracked_job(job_type="test_job", pause_exceptions=(MyPauseError,))
        async def my_job(ctx, tenant_id):
            raise MyPauseError("waiting for human")

        with patch(f"{MODULE}.logger") as mock_logger:
            with pytest.raises(MyPauseError):
                await my_job(_arq_ctx(), "tenant-1")

            # Should NOT have a job_failed log
            failed_calls = [
                c
                for c in mock_logger.error.call_args_list
                if c.args and c.args[0] == "job_failed"
            ]
            assert len(failed_calls) == 0

            # Should have a job_paused log
            paused_calls = [
                c
                for c in mock_logger.info.call_args_list
                if c.args and c.args[0] == "job_paused"
            ]
            assert len(paused_calls) == 1

    @pytest.mark.asyncio
    async def test_extract_row_id_returns_none(self):
        """When extract_row_id returns None, no DB writes happen."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, **kw: None,
        )
        async def my_job(ctx):
            return "ok"

        # Should work without DB mocking since row_id is None
        result = await my_job(_arq_ctx())
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_tenant_id_arg_skips_tenant_context(self):
        """Jobs without a tenant_id parameter skip tenant context."""

        @tracked_job(
            job_type="test_job",
        )
        async def my_job(ctx, event_id):
            return "ok"

        with patch(f"{MODULE}.set_tenant_id") as mock_set:
            await my_job(_arq_ctx(), "evt-123")
            mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackedJobRetry:
    """Decorator retry behaviour when max_retries > 0."""

    @pytest.mark.asyncio
    async def test_default_max_retries_is_zero(self):
        """By default, max_retries=0 — failures propagate immediately."""

        @tracked_job(job_type="test_job")
        async def my_job(ctx, tenant_id):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await my_job(_arq_ctx(), "tenant-1")

    @pytest.mark.asyncio
    async def test_retry_reenqueues_on_first_failure(self):
        """With max_retries=2, first failure re-enqueues instead of raising."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id, tenant_id: row_id,
            max_retries=2,
        )
        async def my_job(ctx, row_id, tenant_id):
            raise ValueError("transient error")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,  # first attempt
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock),
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock) as mock_enqueue,
        ):
            # Should NOT raise — swallowed for retry
            result = await my_job(_arq_ctx(), "row-123", "tenant-1")

        assert result is None
        mock_enqueue.assert_awaited_once()
        # Verify re-enqueue uses the function's module path and args (without ctx)
        call_args = mock_enqueue.call_args
        assert "my_job" in call_args[0][0]  # function path
        assert call_args[0][1] == "row-123"  # first real arg
        assert call_args[0][2] == "tenant-1"  # second real arg

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_exception(self):
        """When attempt > max_retries, exception propagates (permanent failure)."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=2,
        )
        async def my_job(ctx, row_id):
            raise ValueError("still broken")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=3,  # 3rd attempt, max_retries=2 → exhausted
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            pytest.raises(ValueError, match="still broken"),
        ):
            await my_job(_arq_ctx(), "row-123")

    @pytest.mark.asyncio
    async def test_retry_resets_row_status(self):
        """On retry, _reset_row_for_retry is called before re-enqueue."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=1,
        )
        async def my_job(ctx, row_id):
            raise RuntimeError("fail")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(
                f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock
            ) as mock_reset,
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock),
        ):
            await my_job(_arq_ctx(), "row-123")

        mock_reset.assert_awaited_once_with(mock_model, "row-123")

    @pytest.mark.asyncio
    async def test_retry_enqueue_failure_reraises_original(self):
        """If re-enqueue fails (Redis down), original exception propagates."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=2,
        )
        async def my_job(ctx, row_id):
            raise ValueError("original error")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock),
            patch(
                f"{MODULE}.enqueue_arq_job",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Redis down"),
            ),
            pytest.raises(ValueError, match="original error"),
        ):
            await my_job(_arq_ctx(), "row-123")

    @pytest.mark.asyncio
    async def test_retry_logs_job_retrying(self):
        """Retry emits a 'job_retrying' log, not 'job_failed'."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=1,
        )
        async def my_job(ctx, row_id):
            raise ValueError("transient")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock),
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock),
            patch(f"{MODULE}.logger") as mock_logger,
        ):
            await my_job(_arq_ctx(), "row-123")

        # Should have job_retrying, not job_failed
        retrying_calls = [
            c
            for c in mock_logger.info.call_args_list
            if c.args and c.args[0] == "job_retrying"
        ]
        assert len(retrying_calls) == 1
        kw = retrying_calls[0].kwargs
        assert kw["attempt"] == 1
        assert kw["max_retries"] == 1

        failed_calls = [
            c
            for c in mock_logger.error.call_args_list
            if c.args and c.args[0] == "job_failed"
        ]
        assert len(failed_calls) == 0

    @pytest.mark.asyncio
    async def test_retry_not_applied_to_pause_exceptions(self):
        """Pause exceptions bypass retry logic — always re-raised."""

        class PauseError(Exception):
            pass

        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=5,
            pause_exceptions=(PauseError,),
        )
        async def my_job(ctx, row_id):
            raise PauseError("waiting for human")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock) as mock_enqueue,
            pytest.raises(PauseError, match="waiting for human"),
        ):
            await my_job(_arq_ctx(), "row-123")

        # Should NOT have attempted re-enqueue
        mock_enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_uses_defer_by(self):
        """Re-enqueue passes _defer_by for delayed retry."""
        mock_model = MagicMock(__tablename__="test_table")

        @tracked_job(
            job_type="test_job",
            model_class=mock_model,
            extract_row_id=lambda ctx, row_id: row_id,
            max_retries=1,
        )
        async def my_job(ctx, row_id):
            raise ValueError("fail")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock),
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock) as mock_enqueue,
        ):
            await my_job(_arq_ctx(), "row-123")

        # Verify _defer_by was passed
        call_kwargs = mock_enqueue.call_args[1]
        assert "_defer_by" in call_kwargs
        assert call_kwargs["_defer_by"].total_seconds() > 0

    @pytest.mark.asyncio
    async def test_retry_without_model_class_still_reenqueues(self):
        """Retry works even without model_class — just no status reset."""

        @tracked_job(
            job_type="test_job",
            max_retries=1,
        )
        async def my_job(ctx, tenant_id):
            raise ValueError("fail")

        with (
            patch(
                f"{MODULE}._write_tracking_start",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(f"{MODULE}._write_tracking_failure", new_callable=AsyncMock),
            patch(
                f"{MODULE}._reset_row_for_retry", new_callable=AsyncMock
            ) as mock_reset,
            patch(f"{MODULE}.enqueue_arq_job", new_callable=AsyncMock) as mock_enqueue,
        ):
            result = await my_job(_arq_ctx(), "tenant-1")

        assert result is None
        mock_enqueue.assert_awaited_once()
        # _reset_row_for_retry still called but it's a no-op (model_class=None)
        mock_reset.assert_awaited_once()
