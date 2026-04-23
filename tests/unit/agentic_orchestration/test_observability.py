"""
Unit tests for agentic orchestration observability protocol.

Tests validate the structure and functionality of:
- WorkflowGenerationStage enum
- WorkflowGenerationStatus enum
- StageExecutionMetrics dataclass
- ToolCallTrace dataclass
- ProgressCallback protocol
"""

from unittest.mock import AsyncMock

import pytest

from analysi.agentic_orchestration.observability import (
    ProgressCallback,
    StageExecutionMetrics,
    ToolCallTrace,
    WorkflowGenerationStage,
    WorkflowGenerationStatus,
)


class TestWorkflowGenerationStageEnum:
    """Tests for WorkflowGenerationStage enum."""

    def test_workflow_generation_stage_enum_values(self):
        """Verify WorkflowGenerationStage enum has all required stages."""
        assert WorkflowGenerationStage.RUNBOOK_GENERATION == "runbook_generation"
        assert WorkflowGenerationStage.TASK_PROPOSALS == "task_proposals"
        assert WorkflowGenerationStage.TASK_BUILDING == "task_building"
        assert WorkflowGenerationStage.WORKFLOW_ASSEMBLY == "workflow_assembly"

    def test_workflow_generation_stage_is_string_enum(self):
        """Verify enum values are strings for JSON serialization."""
        for stage in WorkflowGenerationStage:
            assert isinstance(stage.value, str)
            assert stage == stage.value  # str, Enum pattern


class TestWorkflowGenerationStatusEnum:
    """Tests for WorkflowGenerationStatus enum."""

    def test_workflow_generation_status_enum_values(self):
        """Verify WorkflowGenerationStatus enum has all required statuses."""
        assert WorkflowGenerationStatus.PENDING == "pending"
        assert WorkflowGenerationStatus.RUNNING == "running"
        assert WorkflowGenerationStatus.COMPLETED == "completed"
        assert WorkflowGenerationStatus.FAILED == "failed"
        assert WorkflowGenerationStatus.PAUSED == "paused"
        assert WorkflowGenerationStatus.CANCELLED == "cancelled"

    def test_workflow_generation_status_is_string_enum(self):
        """Verify enum values are strings for JSON serialization."""
        for status in WorkflowGenerationStatus:
            assert isinstance(status.value, str)
            assert status == status.value  # str, Enum pattern


class TestToolCallTrace:
    """Tests for ToolCallTrace dataclass."""

    def test_tool_call_trace_required_fields(self):
        """Verify ToolCallTrace can be created with required fields."""
        trace = ToolCallTrace(
            tool_name="test_tool",
            input_args={"arg1": "value1"},
            result="success",
            is_error=False,
        )
        assert trace.tool_name == "test_tool"
        assert trace.input_args == {"arg1": "value1"}
        assert trace.result == "success"
        assert trace.is_error is False
        assert trace.duration_ms is None

    def test_tool_call_trace_with_duration(self):
        """Verify ToolCallTrace accepts optional duration_ms."""
        trace = ToolCallTrace(
            tool_name="test_tool",
            input_args={},
            result="result",
            is_error=False,
            duration_ms=150,
        )
        assert trace.duration_ms == 150

    def test_tool_call_trace_error_case(self):
        """Verify ToolCallTrace handles error cases."""
        trace = ToolCallTrace(
            tool_name="failing_tool",
            input_args={"bad": "input"},
            result="Error: something went wrong",
            is_error=True,
        )
        assert trace.is_error is True


class TestStageExecutionMetrics:
    """Tests for StageExecutionMetrics dataclass."""

    def test_stage_execution_metrics_all_fields(self):
        """Verify StageExecutionMetrics captures all SDK metrics."""
        metrics = StageExecutionMetrics(
            duration_ms=5000,
            duration_api_ms=4500,
            num_turns=3,
            total_cost_usd=0.05,
            usage={"input_tokens": 1000, "output_tokens": 500},
            tool_calls=[],
        )
        assert metrics.duration_ms == 5000
        assert metrics.duration_api_ms == 4500
        assert metrics.num_turns == 3
        assert metrics.total_cost_usd == 0.05
        assert metrics.usage == {"input_tokens": 1000, "output_tokens": 500}
        assert metrics.tool_calls == []

    def test_stage_execution_metrics_with_tool_calls(self):
        """Verify StageExecutionMetrics stores tool call traces."""
        traces = [
            ToolCallTrace(
                tool_name="tool1",
                input_args={"x": 1},
                result="ok",
                is_error=False,
            ),
            ToolCallTrace(
                tool_name="tool2",
                input_args={"y": 2},
                result="ok",
                is_error=False,
            ),
        ]
        metrics = StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=900,
            num_turns=2,
            total_cost_usd=0.01,
            usage={},
            tool_calls=traces,
        )
        assert len(metrics.tool_calls) == 2
        assert metrics.tool_calls[0].tool_name == "tool1"


class TestProgressCallback:
    """Tests for ProgressCallback protocol."""

    def test_progress_callback_protocol_definition(self):
        """Verify ProgressCallback protocol defines all required methods."""
        # Check that protocol has the expected methods
        assert hasattr(ProgressCallback, "on_stage_start")
        assert hasattr(ProgressCallback, "on_stage_complete")
        assert hasattr(ProgressCallback, "on_stage_error")
        assert hasattr(ProgressCallback, "on_tool_call")
        assert hasattr(ProgressCallback, "on_tool_result")

    def test_mock_callback_implements_protocol(self):
        """Verify a mock callback correctly implements the protocol."""
        # Create a mock that implements all protocol methods
        mock_callback = AsyncMock(spec=ProgressCallback)

        # Verify all methods exist
        assert hasattr(mock_callback, "on_stage_start")
        assert hasattr(mock_callback, "on_stage_complete")
        assert hasattr(mock_callback, "on_stage_error")
        assert hasattr(mock_callback, "on_tool_call")
        assert hasattr(mock_callback, "on_tool_result")

    @pytest.mark.asyncio
    async def test_callback_receives_stage_metadata(self):
        """Verify on_stage_start receives correct stage and metadata dict."""
        mock_callback = AsyncMock(spec=ProgressCallback)

        stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        metadata = {"alert_id": "123", "rule_name": "test_rule"}

        await mock_callback.on_stage_start(stage, metadata)

        mock_callback.on_stage_start.assert_called_once_with(stage, metadata)

    @pytest.mark.asyncio
    async def test_callback_receives_completion_with_metrics(self):
        """Verify on_stage_complete receives result and StageExecutionMetrics."""
        mock_callback = AsyncMock(spec=ProgressCallback)

        stage = WorkflowGenerationStage.TASK_PROPOSALS
        result = {"tasks": ["task1", "task2"]}
        metrics = StageExecutionMetrics(
            duration_ms=2000,
            duration_api_ms=1800,
            num_turns=2,
            total_cost_usd=0.02,
            usage={"input_tokens": 500},
            tool_calls=[],
        )

        await mock_callback.on_stage_complete(stage, result, metrics)

        mock_callback.on_stage_complete.assert_called_once_with(stage, result, metrics)

    @pytest.mark.asyncio
    async def test_callback_receives_error_on_failure(self):
        """Verify on_stage_error receives the exception and optional partial metrics."""
        mock_callback = AsyncMock(spec=ProgressCallback)

        stage = WorkflowGenerationStage.TASK_BUILDING
        error = ValueError("Task building failed")
        partial_metrics = StageExecutionMetrics(
            duration_ms=500,
            duration_api_ms=400,
            num_turns=1,
            total_cost_usd=0.005,
            usage={},
            tool_calls=[],
        )

        await mock_callback.on_stage_error(stage, error, partial_metrics)

        mock_callback.on_stage_error.assert_called_once_with(
            stage, error, partial_metrics
        )

    @pytest.mark.asyncio
    async def test_callback_receives_tool_call(self):
        """Verify on_tool_call receives stage, tool_name, and input_args."""
        mock_callback = AsyncMock(spec=ProgressCallback)

        stage = WorkflowGenerationStage.WORKFLOW_ASSEMBLY
        tool_name = "mcp__analysi__compose_workflow"
        input_args = {"composition": ["task1", "task2"]}

        await mock_callback.on_tool_call(stage, tool_name, input_args)

        mock_callback.on_tool_call.assert_called_once_with(stage, tool_name, input_args)

    @pytest.mark.asyncio
    async def test_callback_receives_tool_result(self):
        """Verify on_tool_result receives stage, tool_name, result, and is_error flag."""
        mock_callback = AsyncMock(spec=ProgressCallback)

        stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        tool_name = "mcp__analysi__get_task"
        result = {"task_id": "abc123", "script": "..."}
        is_error = False

        await mock_callback.on_tool_result(stage, tool_name, result, is_error)

        mock_callback.on_tool_result.assert_called_once_with(
            stage, tool_name, result, is_error
        )
