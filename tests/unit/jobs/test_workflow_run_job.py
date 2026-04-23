"""Unit tests for execute_workflow_run ARQ job."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.jobs.workflow_run_job import execute_workflow_run


class TestExecuteWorkflowRun:
    """Tests for the execute_workflow_run ARQ job wrapper."""

    @pytest.mark.asyncio
    async def test_delegates_to_execute_synchronously(self):
        """Job calls WorkflowExecutor._execute_workflow_synchronously."""
        workflow_run_id = str(uuid4())
        tenant_id = "tenant-b"

        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
            new_callable=AsyncMock,
        ) as mock_exec:
            result = await execute_workflow_run({}, workflow_run_id, tenant_id)

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        assert str(call_args[0][0]) == workflow_run_id
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_propagates_exceptions(self):
        """Exceptions from _execute_workflow_synchronously propagate."""
        with patch(
            "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
            new_callable=AsyncMock,
            side_effect=RuntimeError("workflow failed"),
        ):
            with pytest.raises(RuntimeError, match="workflow failed"):
                await execute_workflow_run({}, str(uuid4()), "tenant-b")
