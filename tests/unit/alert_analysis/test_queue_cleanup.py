"""Unit tests for queue cleanup utilities."""

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.jobs import JobDef

from analysi.alert_analysis.queue_cleanup import (
    ARQ_JOB_PREFIX,
    QueueCleanupResult,
    _get_job_tenant,
    get_queue_stats,
    purge_tenant_queue,
)


def _mock_job_info(args: list, function: str = "process_alert") -> JobDef:
    """Create a mock JobDef for testing."""
    from datetime import datetime

    return JobDef(
        function=function,
        args=tuple(args),
        kwargs={},
        job_try=1,
        enqueue_time=datetime.now(UTC),
        score=None,
        job_id=None,
    )


class TestGetJobTenant:
    """Test _get_job_tenant function."""

    @pytest.mark.asyncio
    async def test_extracts_tenant_from_job_data(self):
        """Successfully extracts tenant_id via ARQ Job API."""
        mock_redis = AsyncMock()
        job_info = _mock_job_info(["tenant-123", "alert-id", "analysis-id"])

        with patch("analysi.alert_analysis.queue_cleanup.Job") as MockJob:
            mock_job_instance = AsyncMock()
            mock_job_instance.info.return_value = job_info
            MockJob.return_value = mock_job_instance

            tenant = await _get_job_tenant(mock_redis, "job-001")

        assert tenant == "tenant-123"
        MockJob.assert_called_once_with("job-001", mock_redis)

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_job(self):
        """Returns None when job data doesn't exist."""
        mock_redis = AsyncMock()

        with patch("analysi.alert_analysis.queue_cleanup.Job") as MockJob:
            mock_job_instance = AsyncMock()
            mock_job_instance.info.return_value = None
            MockJob.return_value = mock_job_instance

            tenant = await _get_job_tenant(mock_redis, "nonexistent-job")

        assert tenant is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_args(self):
        """Returns None when job has no args."""
        mock_redis = AsyncMock()
        job_info = _mock_job_info([])

        with patch("analysi.alert_analysis.queue_cleanup.Job") as MockJob:
            mock_job_instance = AsyncMock()
            mock_job_instance.info.return_value = job_info
            MockJob.return_value = mock_job_instance

            tenant = await _get_job_tenant(mock_redis, "job-empty")

        assert tenant is None

    @pytest.mark.asyncio
    async def test_handles_corrupt_job_data(self):
        """Handles corrupt/unreadable job data gracefully."""
        mock_redis = AsyncMock()

        with patch("analysi.alert_analysis.queue_cleanup.Job") as MockJob:
            mock_job_instance = AsyncMock()
            mock_job_instance.info.side_effect = Exception("unable to deserialize")
            MockJob.return_value = mock_job_instance

            tenant = await _get_job_tenant(mock_redis, "job-corrupt")

        assert tenant is None


def _setup_mock_redis_with_jobs(mock_redis, jobs: dict, job_prefix=ARQ_JOB_PREFIX):
    """Set up mock redis and Job API for purge/stats tests.

    Returns a patcher for the Job class that resolves job_id to tenant via info().
    """

    async def mock_job_info_lookup(job_id, redis):
        mock_instance = AsyncMock()
        if job_id in jobs:
            data = jobs[job_id]
            mock_instance.info.return_value = _mock_job_info(data["a"])
        else:
            mock_instance.info.return_value = None
        return mock_instance

    return mock_job_info_lookup


class TestPurgeTenantQueue:
    """Test purge_tenant_queue function."""

    @pytest.mark.asyncio
    async def test_removes_matching_jobs(self):
        """Removes all jobs belonging to the specified tenant."""
        jobs = {
            "job-1": {"a": ["tenant-a", "alert-1", "analysis-1"]},
            "job-2": {"a": ["tenant-a", "alert-2", "analysis-2"]},
            "job-3": {"a": ["tenant-b", "alert-3", "analysis-3"]},
        }

        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = [b"job-1", b"job-2", b"job-3"]
        mock_redis.keys.return_value = []
        mock_redis.zrem = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.aclose = AsyncMock()

        def make_job(job_id, redis):
            instance = AsyncMock()
            if job_id in jobs:
                instance.info.return_value = _mock_job_info(jobs[job_id]["a"])
            else:
                instance.info.return_value = None
            return instance

        with (
            patch(
                "analysi.alert_analysis.queue_cleanup.create_pool",
                return_value=mock_redis,
            ),
            patch("analysi.alert_analysis.queue_cleanup.Job", side_effect=make_job),
        ):
            result = await purge_tenant_queue(
                redis_settings=MagicMock(),
                tenant_id="tenant-a",
                abort_in_progress=False,
            )

        assert result.queued_jobs_removed == 2
        assert result.in_progress_jobs_aborted == 0
        assert len(result.errors) == 0
        assert mock_redis.zrem.call_count == 2
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_leaves_other_tenant_jobs(self):
        """Does not remove jobs from other tenants."""
        jobs = {
            "job-other": {"a": ["other-tenant", "alert-x", "analysis-x"]},
        }

        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = [b"job-other"]
        mock_redis.keys.return_value = []
        mock_redis.aclose = AsyncMock()

        def make_job(job_id, redis):
            instance = AsyncMock()
            if job_id in jobs:
                instance.info.return_value = _mock_job_info(jobs[job_id]["a"])
            else:
                instance.info.return_value = None
            return instance

        with (
            patch(
                "analysi.alert_analysis.queue_cleanup.create_pool",
                return_value=mock_redis,
            ),
            patch("analysi.alert_analysis.queue_cleanup.Job", side_effect=make_job),
        ):
            result = await purge_tenant_queue(
                redis_settings=MagicMock(),
                tenant_id="target-tenant",
                abort_in_progress=False,
            )

        assert result.queued_jobs_removed == 0
        mock_redis.zrem.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_queue(self):
        """Handles empty queue gracefully."""
        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = []
        mock_redis.keys.return_value = []
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.alert_analysis.queue_cleanup.create_pool",
            return_value=mock_redis,
        ):
            result = await purge_tenant_queue(
                redis_settings=MagicMock(),
                tenant_id="any-tenant",
                abort_in_progress=False,
            )

        assert result.queued_jobs_removed == 0
        assert result.in_progress_jobs_aborted == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_aborts_in_progress_jobs_when_requested(self):
        """Aborts in-progress jobs when abort_in_progress=True."""
        jobs = {
            "job-running": {"a": ["tenant-x", "alert-r", "analysis-r"]},
        }

        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = []
        mock_redis.keys.return_value = [
            b"arq:in-progress:worker1:job-running",
        ]
        mock_redis.delete = AsyncMock()
        mock_redis.aclose = AsyncMock()

        def make_job(job_id, redis):
            instance = AsyncMock()
            if job_id in jobs:
                instance.info.return_value = _mock_job_info(jobs[job_id]["a"])
            else:
                instance.info.return_value = None
            return instance

        with (
            patch(
                "analysi.alert_analysis.queue_cleanup.create_pool",
                return_value=mock_redis,
            ),
            patch("analysi.alert_analysis.queue_cleanup.Job", side_effect=make_job),
        ):
            result = await purge_tenant_queue(
                redis_settings=MagicMock(),
                tenant_id="tenant-x",
                abort_in_progress=True,
            )

        assert result.in_progress_jobs_aborted == 1

    @pytest.mark.asyncio
    async def test_skips_cron_markers(self):
        """Does not abort cron markers (they're not real jobs)."""
        mock_redis = AsyncMock()
        mock_redis.zrange.return_value = []
        mock_redis.keys.return_value = [
            b"arq:in-progress:worker1:cron:reconcile",
        ]
        mock_redis.aclose = AsyncMock()

        with patch(
            "analysi.alert_analysis.queue_cleanup.create_pool",
            return_value=mock_redis,
        ):
            result = await purge_tenant_queue(
                redis_settings=MagicMock(),
                tenant_id="any-tenant",
                abort_in_progress=True,
            )

        assert result.in_progress_jobs_aborted == 0


class TestGetQueueStats:
    """Test get_queue_stats function."""

    @pytest.mark.asyncio
    async def test_returns_queue_statistics(self):
        """Returns correct queue statistics."""
        jobs = {
            "job-1": {"a": ["tenant-a", "alert-1", "analysis-1"]},
            "job-2": {"a": ["tenant-a", "alert-2", "analysis-2"]},
            "job-3": {"a": ["tenant-b", "alert-3", "analysis-3"]},
        }

        mock_redis = AsyncMock()
        mock_redis.zcard.return_value = 3
        mock_redis.zrange.return_value = [b"job-1", b"job-2", b"job-3"]
        mock_redis.keys.return_value = [
            b"arq:in-progress:worker1:job-running",
            b"arq:in-progress:worker1:cron:reconcile",
        ]
        mock_redis.aclose = AsyncMock()

        def make_job(job_id, redis):
            instance = AsyncMock()
            if job_id in jobs:
                instance.info.return_value = _mock_job_info(jobs[job_id]["a"])
            else:
                instance.info.return_value = None
            return instance

        with (
            patch(
                "analysi.alert_analysis.queue_cleanup.create_pool",
                return_value=mock_redis,
            ),
            patch("analysi.alert_analysis.queue_cleanup.Job", side_effect=make_job),
        ):
            stats = await get_queue_stats(redis_settings=MagicMock())

        assert stats["queue_length"] == 3
        assert stats["in_progress_jobs"] == 1  # Excludes cron marker
        assert stats["cron_markers"] == 1
        assert stats["jobs_by_tenant"] == {"tenant-a": 2, "tenant-b": 1}


class TestQueueCleanupResult:
    """Test QueueCleanupResult dataclass."""

    def test_total_removed_calculation(self):
        """total_removed property calculates correctly."""
        result = QueueCleanupResult(
            queued_jobs_removed=5,
            in_progress_jobs_aborted=2,
            errors=[],
        )
        assert result.total_removed == 7

    def test_total_removed_with_zeros(self):
        """total_removed works with zero counts."""
        result = QueueCleanupResult(
            queued_jobs_removed=0,
            in_progress_jobs_aborted=0,
            errors=[],
        )
        assert result.total_removed == 0
