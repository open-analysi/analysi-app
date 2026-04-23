"""Unit tests for metrics serialization in workflow_generation_job.py"""

from analysi.agentic_orchestration.jobs.workflow_generation_job import (
    _serialize_metrics,
)
from analysi.agentic_orchestration.observability import StageExecutionMetrics


def test_serialize_metrics_with_single_stage():
    """Test serializing metrics from one stage."""
    metrics = [
        StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=5,
            total_cost_usd=0.05,
            usage={
                "total_input_tokens": 100,
                "total_output_tokens": 200,
            },
            tool_calls=[],
        )
    ]

    result = _serialize_metrics(metrics)

    assert "stages" in result
    assert len(result["stages"]) == 1
    assert result["stages"][0]["total_cost_usd"] == 0.05
    assert result["stages"][0]["total_input_tokens"] == 100
    assert result["stages"][0]["total_output_tokens"] == 200
    assert result["total_cost_usd"] == 0.05


def test_serialize_metrics_with_multiple_stages():
    """Test serializing metrics from multiple stages."""
    metrics = [
        StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=5,
            total_cost_usd=0.05,
            usage={
                "total_input_tokens": 100,
                "total_output_tokens": 200,
            },
            tool_calls=[],
        ),
        StageExecutionMetrics(
            duration_ms=2000,
            duration_api_ms=1800,
            num_turns=3,
            total_cost_usd=0.03,
            usage={
                "total_input_tokens": 50,
                "total_output_tokens": 100,
            },
            tool_calls=[],
        ),
    ]

    result = _serialize_metrics(metrics)

    assert "stages" in result
    assert len(result["stages"]) == 2
    assert result["total_cost_usd"] == 0.08


def test_serialize_metrics_empty_list():
    """Test serializing empty metrics list."""
    result = _serialize_metrics([])
    assert result == {}
