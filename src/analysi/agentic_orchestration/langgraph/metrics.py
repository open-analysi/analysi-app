"""Metrics collection for LangGraph executions.

Collects timing, token usage, and cost metrics during LangGraph phase execution,
then converts to StageExecutionMetrics for compatibility with SDK-based reporting.

TODO: Token counting integration
Currently, only duration tracking is implemented. To enable token counting:
1. Modify execute_substep() to extract usage_metadata from LLM responses
2. Return token counts in SubStepResult
3. Pass metrics_collector through Phase1State
4. Have each graph node call record_llm_call() after execute_substep()

For now, duration_ms is accurate but token/cost metrics will be zero.
"""

import time
from dataclasses import dataclass, field

from analysi.agentic_orchestration.observability import StageExecutionMetrics

# Sonnet pricing (per million tokens)
SONNET_INPUT_COST_PER_MILLION = 3.0
SONNET_OUTPUT_COST_PER_MILLION = 15.0


@dataclass
class LangGraphMetricsCollector:
    """Collect metrics during LangGraph execution.

    Usage:
        collector = LangGraphMetricsCollector()
        collector.start()

        # During execution
        collector.record_node("analyze_gaps", 1500.0)
        collector.record_llm_call("analyze_gaps", input_tokens=1000, output_tokens=500)

        # After execution
        metrics = collector.to_stage_metrics()
    """

    start_time: float = 0.0
    node_durations: dict[str, float] = field(default_factory=dict)
    llm_calls: list[dict] = field(default_factory=list)

    def start(self) -> None:
        """Record execution start time."""
        self.start_time = time.time()

    def record_node(self, node_name: str, duration_ms: float) -> None:
        """Record duration for a graph node.

        Args:
            node_name: Name of the node that executed.
            duration_ms: Execution time in milliseconds.
        """
        self.node_durations[node_name] = duration_ms

    def record_llm_call(self, node: str, input_tokens: int, output_tokens: int) -> None:
        """Record an LLM call with token usage.

        Args:
            node: Name of the node that made the call.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
        """
        self.llm_calls.append(
            {
                "node": node,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )

    def to_stage_metrics(self) -> StageExecutionMetrics:
        """Convert collected metrics to StageExecutionMetrics.

        Returns:
            StageExecutionMetrics compatible with SDK reporting.
        """
        # Calculate total duration
        duration_ms = int((time.time() - self.start_time) * 1000)

        # Sum node durations for API time
        duration_api_ms = int(sum(self.node_durations.values()))

        # Aggregate token usage
        total_input_tokens = sum(call["input_tokens"] for call in self.llm_calls)
        total_output_tokens = sum(call["output_tokens"] for call in self.llm_calls)

        # Calculate cost using Sonnet pricing
        input_cost = total_input_tokens * SONNET_INPUT_COST_PER_MILLION / 1_000_000
        output_cost = total_output_tokens * SONNET_OUTPUT_COST_PER_MILLION / 1_000_000
        total_cost = input_cost + output_cost

        return StageExecutionMetrics(
            duration_ms=duration_ms,
            duration_api_ms=duration_api_ms,
            num_turns=len(self.llm_calls),
            total_cost_usd=total_cost,
            usage={
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
            tool_calls=[],  # LangGraph doesn't track tools the same way SDK does
        )
