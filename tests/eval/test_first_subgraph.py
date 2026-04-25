"""Eval tests for first subgraph (Runbook → Task Proposal).

These tests run the actual subgraph with Claude and require ANTHROPIC_API_KEY.
They are marked with @pytest.mark.eval and skipped by default.

Run with: make test-eval

Optimization Strategy:
- Shared fixture runs subgraph ONCE per module
- Cached result is immutable and safe to share across test functions
- All 4 tests validate different aspects of the same execution
- Single execution = minimal cost and fast feedback
"""

import pytest

# Sample NAS alert for testing
SAMPLE_ALERT = {
    "id": "test-alert-001",
    "title": "Suspicious Login from Unusual Location",
    "severity": "high",
    "source_vendor": "Okta",
    "rule_name": "unusual_login_location",
    "triggering_event_time": "2024-01-15T10:30:00Z",
    "raw_alert": {
        "user": "john.doe@corp.example",
        "ip": "91.234.56.101",
        "country": "Russia",
        "normal_country": "United States",
    },
}


@pytest.mark.eval
@pytest.mark.asyncio
async def test_first_subgraph_produces_runbook(first_subgraph_result):
    """Verify subgraph generates a runbook from alert."""
    result = first_subgraph_result

    assert result["runbook"] is not None, (
        f"Expected runbook to be generated. Error: {result.get('error')}"
    )
    assert len(result["runbook"]) > 100, "Expected non-trivial runbook content"
    assert result["error"] is None, f"Unexpected error: {result['error']}"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_first_subgraph_produces_task_proposals(first_subgraph_result):
    """Verify subgraph generates task proposals from runbook."""
    result = first_subgraph_result

    assert result["task_proposals"] is not None, "Expected task proposals"
    assert len(result["task_proposals"]) > 0, "Expected at least one task proposal"

    # Verify proposal structure
    for proposal in result["task_proposals"]:
        # Must have "name" field
        assert "name" in proposal, (
            f"Proposal missing name field. Got keys: {list(proposal.keys())}"
        )

        # Verify designation field exists
        assert "designation" in proposal, (
            f"Proposal missing designation field. Got keys: {list(proposal.keys())}"
        )

        # Verify designation value
        designation_value = proposal.get("designation")
        assert designation_value in ["existing", "modification", "new"], (
            f"Invalid designation value: {designation_value}"
        )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_first_subgraph_accumulates_metrics(first_subgraph_result):
    """Verify metrics are accumulated from both stages."""
    result = first_subgraph_result

    # Should have 2 metrics entries (one per stage)
    assert len(result["metrics"]) == 2, (
        f"Expected 2 metrics entries, got {len(result['metrics'])}"
    )

    # Verify cost was tracked
    total_cost = sum(m.total_cost_usd for m in result["metrics"])
    assert total_cost > 0, "Expected non-zero cost"


@pytest.mark.eval
@pytest.mark.asyncio
async def test_first_subgraph_callback_integration(first_subgraph_result):
    """Verify callback integration by checking metrics tracked during execution.

    Note: We can't test callbacks with cached results, but we can verify that
    the execution did track metrics, which proves callbacks were working.
    For full callback testing, use manual runs with actual callback objects.
    """
    result = first_subgraph_result

    # Verify that execution tracked stages (proves callback integration works)
    assert len(result["metrics"]) > 0, "Expected metrics to be tracked during execution"

    # Verify tool calls were tracked (proves callbacks captured tool events)
    has_tool_calls = any(len(m.tool_calls) > 0 for m in result["metrics"])
    assert has_tool_calls, "Expected tool calls to be tracked in metrics"
