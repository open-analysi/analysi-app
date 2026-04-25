"""
Observability protocols and types for Agentic Orchestration.

This module defines the interfaces for progress reporting and execution metrics
collection during workflow generation stages.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class WorkflowGenerationStage(StrEnum):
    """Which stage of workflow generation we're in."""

    RUNBOOK_GENERATION = "runbook_generation"
    TASK_PROPOSALS = "task_proposals"
    TASK_BUILDING = "task_building"
    WORKFLOW_ASSEMBLY = "workflow_assembly"


class WorkflowGenerationStatus(StrEnum):
    """Status of a workflow generation process."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class ToolCallTrace:
    """Record of a single tool invocation."""

    tool_name: str
    input_args: dict[str, Any]
    result: Any
    is_error: bool
    duration_ms: int | None = None


@dataclass
class StageExecutionMetrics:
    """Metrics from a single stage execution (one query() call).

    These metrics mirror the data available from the Claude Agent SDK's
    ResultMessage, enabling cost tracking and performance analysis.
    """

    duration_ms: int
    duration_api_ms: int
    num_turns: int
    total_cost_usd: float
    usage: dict[str, Any]  # Token usage
    tool_calls: list[ToolCallTrace]


class ProgressCallback(Protocol):
    """Callback interface for stage-level progress reporting.

    Implementations of this protocol receive notifications about:
    - Stage lifecycle (start, complete, error)
    - Individual tool calls within a stage

    Tool call callbacks are optional - implementations can provide
    no-op methods if real-time tracking is not needed.
    """

    async def on_stage_start(
        self, stage: WorkflowGenerationStage, metadata: dict[str, Any]
    ) -> None:
        """Called when a stage begins execution.

        Args:
            stage: The stage that is starting
            metadata: Additional context (e.g., alert_id, rule_name)
        """
        ...

    async def on_stage_complete(
        self,
        stage: WorkflowGenerationStage,
        result: Any,
        metrics: StageExecutionMetrics,
    ) -> None:
        """Called when a stage completes successfully.

        Args:
            stage: The stage that completed
            result: The output from the stage
            metrics: Execution metrics including cost and timing
        """
        ...

    async def on_stage_error(
        self,
        stage: WorkflowGenerationStage,
        error: Exception,
        partial_metrics: StageExecutionMetrics | None,
    ) -> None:
        """Called when a stage fails with an error.

        Args:
            stage: The stage that failed
            error: The exception that caused the failure
            partial_metrics: Metrics collected before the failure, if available
        """
        ...

    async def on_tool_call(
        self,
        stage: WorkflowGenerationStage,
        tool_name: str,
        input_args: dict[str, Any],
    ) -> None:
        """Called when a tool is invoked during stage execution.

        Args:
            stage: The current stage
            tool_name: Name of the tool being called
            input_args: Arguments passed to the tool
        """
        ...

    async def on_tool_result(
        self,
        stage: WorkflowGenerationStage,
        tool_name: str,
        result: Any,
        is_error: bool,
    ) -> None:
        """Called when a tool returns a result.

        Args:
            stage: The current stage
            tool_name: Name of the tool that returned
            result: The tool's output
            is_error: Whether the tool call failed
        """
        ...

    async def on_workspace_created(self, workspace_path: str) -> None:
        """Called when workspace directory is created.

        This enables early tracking of workspace location for debugging
        failed/timed-out workflow generations.

        Args:
            workspace_path: Absolute path to workspace directory
        """
        ...
