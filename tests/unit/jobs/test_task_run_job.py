"""Unit tests for execute_task_run ARQ job."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.jobs.task_run_job import execute_task_run


class TestExecuteTaskRun:
    """Tests for the execute_task_run ARQ job wrapper."""

    @pytest.mark.asyncio
    async def test_delegates_to_execute_and_persist(self):
        """Job calls TaskExecutionService.execute_and_persist with correct args."""
        task_run_id = str(uuid4())
        tenant_id = "tenant-a"

        mock_service = AsyncMock()

        with patch(
            "analysi.services.task_execution.TaskExecutionService",
            return_value=mock_service,
        ):
            result = await execute_task_run({}, task_run_id, tenant_id)

        mock_service.execute_and_persist.assert_called_once()
        call_args = mock_service.execute_and_persist.call_args
        assert str(call_args[0][0]) == task_run_id  # UUID conversion
        assert call_args[0][1] == tenant_id
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """@tracked_job swallows exception and re-enqueues when retries remain."""
        mock_service = AsyncMock()
        mock_service.execute_and_persist.side_effect = RuntimeError("task failed")

        with (
            patch(
                "analysi.services.task_execution.TaskExecutionService",
                return_value=mock_service,
            ),
            patch(
                "analysi.common.job_tracking.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            # max_retries=2, attempt 1: should swallow and re-enqueue
            result = await execute_task_run({}, str(uuid4()), "tenant-a")

        assert result is None  # Swallowed for retry
        mock_enqueue.assert_called_once()
