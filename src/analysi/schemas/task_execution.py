"""Schemas for task execution results."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class TaskExecutionStatus(StrEnum):
    """Status of a completed task execution.

    Uses StrEnum so values compare equal to plain strings, preserving
    compatibility with existing code that checks status == "completed" etc.

    PAUSED signals that a task needs human input before proceeding.
    The WorkflowExecutor suspends the branch (does not mark it as failed).
    A real HITL node type will resume the branch via an external callback.
    Tasks always run to completion; PAUSED suspends the DAG branch.
    """

    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"  # Reserved HITL hook


@dataclass
class LLMUsage:
    """Aggregated token usage and estimated cost for all llm_run() calls in a task.

    cost_usd is None when the model is not found in LLMPricingRegistry
    (unknown/custom models). We never let missing pricing break execution.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None

    def add(self, other: "LLMUsage") -> "LLMUsage":
        """Return a new LLMUsage with accumulated totals from self + other."""
        cost: float | None = None
        if self.cost_usd is not None and other.cost_usd is not None:
            cost = self.cost_usd + other.cost_usd
        elif self.cost_usd is not None:
            cost = self.cost_usd
        elif other.cost_usd is not None:
            cost = other.cost_usd
        return LLMUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=cost,
        )


@dataclass
class TaskExecutionResult:
    """Pure data result returned by TaskExecutionService.execute_single_task().

    The service no longer writes to the database — callers receive this
    object and are responsible for persisting the outcome.
    """

    status: TaskExecutionStatus
    output_data: dict[str, Any] | None
    error_message: str | None
    execution_time_ms: int
    task_run_id: UUID
    log_entries: list[str | dict] = field(default_factory=list)
    llm_usage: "LLMUsage | None" = None  # None when no llm_run() calls made
