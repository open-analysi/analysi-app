"""Unit tests for DatabaseProgressCallback."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.agentic_orchestration import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.jobs.workflow_generation_job import (
    DatabaseProgressCallback,
)


@pytest.mark.asyncio
class TestDatabaseProgressCallback:
    """Test DatabaseProgressCallback updates current_phase correctly."""

    @pytest.fixture
    def callback(self):
        """Create callback instance for testing."""
        return DatabaseProgressCallback(
            api_base_url="http://test-api:8000",
            tenant_id="test-tenant",
            generation_id=str(uuid4()),
        )

    @pytest.mark.asyncio
    async def test_on_stage_start_updates_progress(self, callback):
        """Test that on_stage_start calls _update_progress."""
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job._update_progress"
        ) as mock_update:
            mock_update.return_value = AsyncMock()

            await callback.on_stage_start(
                WorkflowGenerationStage.RUNBOOK_GENERATION, metadata={}
            )

            mock_update.assert_called_once_with(
                api_base_url=callback.api_base_url,
                tenant_id=callback.tenant_id,
                generation_id=callback.generation_id,
                stage="runbook_generation",
                tasks_count=None,
            )

    @pytest.mark.asyncio
    async def test_on_stage_start_with_tasks_count(self, callback):
        """Test that metadata tasks_count is passed through."""
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job._update_progress"
        ) as mock_update:
            mock_update.return_value = AsyncMock()

            await callback.on_stage_start(
                WorkflowGenerationStage.TASK_BUILDING,
                metadata={"tasks_count": 3},
            )

            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["stage"] == "task_building"
            assert call_kwargs["tasks_count"] == 3

    @pytest.mark.asyncio
    async def test_on_stage_start_handles_errors_gracefully(self, callback):
        """Test that progress update errors don't raise exceptions."""
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job._update_progress"
        ) as mock_update:
            mock_update.side_effect = Exception("API unavailable")

            # Should not raise - errors are logged but swallowed
            await callback.on_stage_start(
                WorkflowGenerationStage.WORKFLOW_ASSEMBLY, metadata={}
            )

            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_stage_complete_is_noop(self, callback):
        """Test that on_stage_complete doesn't trigger updates."""
        metrics = StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=500,
            num_turns=5,
            total_cost_usd=0.05,
            usage={"input_tokens": 100, "output_tokens": 50},
            tool_calls=[],
        )

        # Should not raise or do anything
        await callback.on_stage_complete(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            result="test result",
            metrics=metrics,
        )

    @pytest.mark.asyncio
    async def test_on_stage_error_logs_but_doesnt_update(self, callback):
        """Test that on_stage_error logs but doesn't update database."""
        error = ValueError("Test error")

        # Should not raise - just logs
        await callback.on_stage_error(
            WorkflowGenerationStage.TASK_PROPOSALS,
            error=error,
            partial_result=None,
        )

    @pytest.mark.asyncio
    async def test_tool_callbacks_are_noops(self, callback):
        """Test that tool callbacks don't trigger updates."""
        # Should not raise
        await callback.on_tool_call(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            tool_name="test_tool",
            tool_input={"arg": "value"},
        )

        await callback.on_tool_result(
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            tool_name="test_tool",
            tool_result="result",
            is_error=False,
        )
