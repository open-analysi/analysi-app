"""Tests for LangGraph metrics collection module.

Verify metrics collection and conversion to StageExecutionMetrics.
"""

import time

from analysi.agentic_orchestration.langgraph.metrics import LangGraphMetricsCollector
from analysi.agentic_orchestration.observability import StageExecutionMetrics


class TestMetricsCollectorStart:
    """Tests for LangGraphMetricsCollector.start() method."""

    def test_metrics_collector_start_records_time(self):
        """Start time is recorded when start() is called."""
        collector = LangGraphMetricsCollector()
        before = time.time()

        collector.start()

        after = time.time()
        assert before <= collector.start_time <= after

    def test_metrics_collector_start_can_be_called_multiple_times(self):
        """Calling start() again resets the start time."""
        collector = LangGraphMetricsCollector()
        collector.start()
        first_start = collector.start_time

        time.sleep(0.01)  # Small delay
        collector.start()

        assert collector.start_time > first_start


class TestMetricsCollectorRecordNode:
    """Tests for LangGraphMetricsCollector.record_node() method."""

    def test_metrics_collector_record_node_duration(self):
        """Node durations are tracked correctly."""
        collector = LangGraphMetricsCollector()

        collector.record_node("analyze_gaps", 1500.0)
        collector.record_node("match_runbooks", 2000.0)

        assert collector.node_durations["analyze_gaps"] == 1500.0
        assert collector.node_durations["match_runbooks"] == 2000.0

    def test_metrics_collector_record_node_overwrites_same_node(self):
        """Recording the same node again overwrites the previous duration."""
        collector = LangGraphMetricsCollector()

        collector.record_node("analyze_gaps", 1500.0)
        collector.record_node("analyze_gaps", 2500.0)

        assert collector.node_durations["analyze_gaps"] == 2500.0


class TestMetricsCollectorRecordLLMCall:
    """Tests for LangGraphMetricsCollector.record_llm_call() method."""

    def test_metrics_collector_record_llm_call(self):
        """LLM calls with tokens are tracked correctly."""
        collector = LangGraphMetricsCollector()

        collector.record_llm_call("analyze_gaps", input_tokens=1000, output_tokens=500)

        assert len(collector.llm_calls) == 1
        assert collector.llm_calls[0]["node"] == "analyze_gaps"
        assert collector.llm_calls[0]["input_tokens"] == 1000
        assert collector.llm_calls[0]["output_tokens"] == 500

    def test_metrics_collector_record_multiple_llm_calls(self):
        """Multiple LLM calls are tracked as separate entries."""
        collector = LangGraphMetricsCollector()

        collector.record_llm_call("node_a", input_tokens=1000, output_tokens=500)
        collector.record_llm_call("node_b", input_tokens=2000, output_tokens=1000)
        collector.record_llm_call("node_a", input_tokens=500, output_tokens=250)

        assert len(collector.llm_calls) == 3


class TestMetricsCollectorCostCalculation:
    """Tests for cost calculation logic."""

    def test_metrics_collector_cost_calculation_sonnet_pricing(self):
        """Cost is estimated correctly using Sonnet pricing."""
        collector = LangGraphMetricsCollector()

        # Record an LLM call
        collector.record_llm_call("test_node", input_tokens=1000, output_tokens=500)

        # Convert to stage metrics
        collector.start_time = time.time() - 1.0  # 1 second ago
        metrics = collector.to_stage_metrics()

        # Sonnet pricing: $3/1M input, $15/1M output
        # 1000 input tokens = $0.003
        # 500 output tokens = $0.0075
        # Total = $0.0105
        expected_cost = (1000 * 3.0 / 1_000_000) + (500 * 15.0 / 1_000_000)
        assert abs(metrics.total_cost_usd - expected_cost) < 0.0001


class TestToStageMetrics:
    """Tests for LangGraphMetricsCollector.to_stage_metrics() method."""

    def test_to_stage_metrics_total_duration(self):
        """Total duration calculated from start time to now."""
        collector = LangGraphMetricsCollector()
        collector.start_time = time.time() - 2.5  # 2.5 seconds ago

        metrics = collector.to_stage_metrics()

        # Duration should be approximately 2500ms
        assert 2400 <= metrics.duration_ms <= 3000

    def test_to_stage_metrics_aggregates_tokens(self):
        """Input and output tokens are summed across all LLM calls."""
        collector = LangGraphMetricsCollector()
        collector.start()
        collector.record_llm_call("node_a", input_tokens=1000, output_tokens=500)
        collector.record_llm_call("node_b", input_tokens=2000, output_tokens=1000)

        metrics = collector.to_stage_metrics()

        assert metrics.usage["input_tokens"] == 3000
        assert metrics.usage["output_tokens"] == 1500

    def test_to_stage_metrics_aggregates_cost(self):
        """Total cost is summed across all LLM calls."""
        collector = LangGraphMetricsCollector()
        collector.start()
        collector.record_llm_call("node_a", input_tokens=1000, output_tokens=500)
        collector.record_llm_call("node_b", input_tokens=2000, output_tokens=1000)

        metrics = collector.to_stage_metrics()

        # Total tokens: 3000 input, 1500 output
        # Sonnet pricing: $3/1M input, $15/1M output
        expected_cost = (3000 * 3.0 / 1_000_000) + (1500 * 15.0 / 1_000_000)
        assert abs(metrics.total_cost_usd - expected_cost) < 0.0001

    def test_to_stage_metrics_counts_turns(self):
        """Number of LLM calls equals num_turns."""
        collector = LangGraphMetricsCollector()
        collector.start()
        collector.record_llm_call("node_a", input_tokens=1000, output_tokens=500)
        collector.record_llm_call("node_b", input_tokens=2000, output_tokens=1000)
        collector.record_llm_call("node_c", input_tokens=500, output_tokens=250)

        metrics = collector.to_stage_metrics()

        assert metrics.num_turns == 3

    def test_to_stage_metrics_returns_stage_execution_metrics(self):
        """Returns a StageExecutionMetrics instance."""
        collector = LangGraphMetricsCollector()
        collector.start()

        metrics = collector.to_stage_metrics()

        assert isinstance(metrics, StageExecutionMetrics)

    def test_to_stage_metrics_with_no_llm_calls(self):
        """Handles case with no LLM calls."""
        collector = LangGraphMetricsCollector()
        collector.start()

        metrics = collector.to_stage_metrics()

        assert metrics.num_turns == 0
        assert metrics.total_cost_usd == 0.0
        assert metrics.usage["input_tokens"] == 0
        assert metrics.usage["output_tokens"] == 0

    def test_to_stage_metrics_duration_api_ms_aggregates_node_durations(self):
        """duration_api_ms is sum of node durations (time spent in API calls)."""
        collector = LangGraphMetricsCollector()
        collector.start()
        collector.record_node("node_a", 1000.0)
        collector.record_node("node_b", 1500.0)

        metrics = collector.to_stage_metrics()

        assert metrics.duration_api_ms == 2500

    def test_to_stage_metrics_tool_calls_empty_for_langgraph(self):
        """tool_calls is empty list for LangGraph (tools tracked differently)."""
        collector = LangGraphMetricsCollector()
        collector.start()

        metrics = collector.to_stage_metrics()

        # LangGraph doesn't track individual tool calls the same way SDK does
        assert metrics.tool_calls == []


class TestMetricsCollectorEdgeCases:
    """Edge case tests for LangGraphMetricsCollector."""

    def test_to_stage_metrics_without_start_raises(self):
        """Calling to_stage_metrics() without start() handles gracefully."""
        collector = LangGraphMetricsCollector()
        # start_time is 0.0 by default

        # Should not raise, but duration will be calculated from epoch
        metrics = collector.to_stage_metrics()

        # Duration will be very large (seconds since epoch)
        assert metrics.duration_ms > 0

    def test_metrics_collector_dataclass_defaults(self):
        """Default values are set correctly."""
        collector = LangGraphMetricsCollector()

        assert collector.start_time == 0.0
        assert collector.node_durations == {}
        assert collector.llm_calls == []
