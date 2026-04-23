"""Unit tests for enqueue_arq_job helper.

Tests both the enqueue behavior and the shared pool lifecycle,
plus the enqueue_or_fail safety wrapper.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import analysi.common.arq_enqueue as arq_enqueue_module
from analysi.common.arq_enqueue import (
    close_pool,
    enqueue_arq_job,
    enqueue_or_fail,
    get_pool,
    reset_pool,
)


@pytest.fixture(autouse=True)
def _clean_pool():
    """Reset the shared pool before and after each test."""
    reset_pool()
    yield
    reset_pool()


class TestEnqueueArqJob:
    """Tests for the shared ARQ enqueue helper."""

    @pytest.mark.asyncio
    async def test_enqueues_job_and_returns_job_id(self):
        """Successful enqueue returns the job ID."""
        mock_job = MagicMock()
        mock_job.job_id = "arq:test-123"

        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await enqueue_arq_job(
                "analysi.jobs.task_run_job.execute_task_run",
                "run-id-1",
                "tenant-a",
            )

        assert result == "arq:test-123"
        mock_pool.enqueue_job.assert_called_once_with(
            "analysi.jobs.task_run_job.execute_task_run",
            "run-id-1",
            "tenant-a",
            _job_id=None,
            _defer_by=None,
        )

    @pytest.mark.asyncio
    async def test_returns_none_for_duplicate_job(self):
        """Duplicate job (enqueue_job returns None) returns None."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=None)

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await enqueue_arq_job(
                "some.job.function",
                "arg1",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_job_id_for_idempotency(self):
        """_job_id kwarg is forwarded to enqueue_job."""
        mock_job = MagicMock(job_id="custom-id")
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            await enqueue_arq_job("some.job", "a", _job_id="custom-id")

        call_kwargs = mock_pool.enqueue_job.call_args[1]
        assert call_kwargs["_job_id"] == "custom-id"

    @pytest.mark.asyncio
    async def test_propagates_enqueue_errors(self):
        """Enqueue errors propagate to the caller."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(side_effect=ConnectionError("Redis down"))

        with (
            patch(
                "arq.create_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            pytest.raises(ConnectionError, match="Redis down"),
        ):
            await enqueue_arq_job("some.job", "arg")


class TestSharedPool:
    """Tests for the lazy singleton pool lifecycle."""

    @pytest.mark.asyncio
    async def test_get_pool_creates_pool_on_first_call(self):
        """First call to get_pool creates a new ArqRedis pool."""
        mock_pool = AsyncMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ) as mock_create:
            pool = await get_pool()

        assert pool is mock_pool
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_pool_reuses_pool_on_subsequent_calls(self):
        """Subsequent calls reuse the cached pool — no new create_pool."""
        mock_pool = AsyncMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ) as mock_create:
            pool1 = await get_pool()
            pool2 = await get_pool()
            pool3 = await get_pool()

        assert pool1 is pool2 is pool3
        # create_pool called exactly once
        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_reuses_pool_across_calls(self):
        """Multiple enqueue_arq_job calls share the same pool."""
        mock_job = MagicMock(job_id="j1")
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ) as mock_create:
            await enqueue_arq_job("job.a", "x")
            await enqueue_arq_job("job.b", "y")
            await enqueue_arq_job("job.c", "z")

        # Pool created once, enqueue called three times
        mock_create.assert_awaited_once()
        assert mock_pool.enqueue_job.await_count == 3

    @pytest.mark.asyncio
    async def test_close_pool_closes_connection(self):
        """close_pool() closes the underlying Redis connection."""
        mock_pool = AsyncMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            await get_pool()
            await close_pool()

        mock_pool.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_pool_is_idempotent(self):
        """close_pool() on an already-closed (or never-opened) pool is a no-op."""
        # No pool created yet — should not raise
        await close_pool()
        await close_pool()

    @pytest.mark.asyncio
    async def test_get_pool_after_close_creates_new_pool(self):
        """After close_pool(), next get_pool() creates a fresh pool."""
        mock_pool_1 = AsyncMock()
        mock_pool_2 = AsyncMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            side_effect=[mock_pool_1, mock_pool_2],
        ) as mock_create:
            pool1 = await get_pool()
            await close_pool()
            pool2 = await get_pool()

        assert pool1 is mock_pool_1
        assert pool2 is mock_pool_2
        assert mock_create.await_count == 2

    @pytest.mark.asyncio
    async def test_reset_pool_clears_without_closing(self):
        """reset_pool() clears the cached ref without awaiting aclose.

        This is for test teardown where the event loop may differ.
        """
        mock_pool = AsyncMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            await get_pool()

        reset_pool()
        mock_pool.aclose.assert_not_awaited()

        # Module-level ref is cleared
        assert arq_enqueue_module._pool is None

    @pytest.mark.asyncio
    async def test_enqueue_after_close_reconnects(self):
        """If pool is closed, next enqueue transparently reconnects."""
        mock_job = MagicMock(job_id="j1")
        mock_pool_1 = AsyncMock()
        mock_pool_1.enqueue_job = AsyncMock(return_value=mock_job)
        mock_pool_2 = AsyncMock()
        mock_pool_2.enqueue_job = AsyncMock(return_value=mock_job)

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            side_effect=[mock_pool_1, mock_pool_2],
        ):
            await enqueue_arq_job("job.a", "x")
            await close_pool()
            await enqueue_arq_job("job.b", "y")

        mock_pool_1.enqueue_job.assert_awaited_once()
        mock_pool_2.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concurrent_get_pool_creates_only_one(self):
        """Concurrent get_pool() calls should not create duplicate pools."""
        import asyncio

        call_count = 0
        mock_pool = AsyncMock()

        async def slow_create_pool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate network latency
            return mock_pool

        with patch("arq.create_pool", side_effect=slow_create_pool):
            pools = await asyncio.gather(
                get_pool(), get_pool(), get_pool(), get_pool(), get_pool()
            )

        # All should get the same pool, created exactly once
        assert all(p is mock_pool for p in pools)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_pool_not_closed_on_enqueue_failure(self):
        """Enqueue failure should NOT close the shared pool."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(side_effect=ConnectionError("transient"))

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            with pytest.raises(ConnectionError):
                await enqueue_arq_job("some.job", "arg")

            # Pool should still be cached — not closed
            mock_pool.aclose.assert_not_awaited()
            assert arq_enqueue_module._pool is mock_pool


class TestEnqueueOrFail:
    """Tests for the enqueue_or_fail safety wrapper."""

    @pytest.mark.asyncio
    async def test_success_returns_job_id(self):
        """On success, behaves identically to enqueue_arq_job."""
        mock_job = MagicMock(job_id="arq:ok-123")
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
        mock_model = MagicMock()

        with patch(
            "arq.create_pool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ):
            result = await enqueue_or_fail(
                "some.job",
                "arg1",
                "arg2",
                model_class=mock_model,
                row_id="run-id-1",
            )

        assert result == "arq:ok-123"

    @pytest.mark.asyncio
    async def test_redis_failure_marks_row_failed_and_reraises(self):
        """When Redis is down, the row is marked failed and the error re-raised."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(
            side_effect=ConnectionError("Redis connection refused")
        )

        mock_mark = AsyncMock()

        with (
            patch(
                "arq.create_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "analysi.common.arq_enqueue._mark_row_failed",
                mock_mark,
            ),
            pytest.raises(ConnectionError, match="Redis connection refused"),
        ):
            from analysi.models.task_run import TaskRun

            await enqueue_or_fail(
                "some.job",
                "run-id-1",
                "tenant",
                model_class=TaskRun,
                row_id="test-uuid-123",
            )

        # Verify _mark_row_failed was called with correct args
        mock_mark.assert_awaited_once_with(
            TaskRun, "test-uuid-123", "Redis connection refused"
        )

    @pytest.mark.asyncio
    async def test_mark_row_failure_is_best_effort(self):
        """If marking the row fails too, the original error still propagates."""
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock(side_effect=ConnectionError("Redis down"))

        with (
            patch(
                "arq.create_pool",
                new_callable=AsyncMock,
                return_value=mock_pool,
            ),
            patch(
                "analysi.common.arq_enqueue._mark_row_failed",
                new_callable=AsyncMock,
                side_effect=Exception("PG also down"),
            ),
            pytest.raises(ConnectionError, match="Redis down"),
        ):
            from analysi.models.task_run import TaskRun

            await enqueue_or_fail(
                "some.job",
                "arg",
                model_class=TaskRun,
                row_id="test-uuid",
            )
