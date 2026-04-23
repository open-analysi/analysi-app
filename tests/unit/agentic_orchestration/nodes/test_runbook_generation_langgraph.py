"""Tests for LangGraph wrapper node for runbook generation.

Verify LangGraph wrapper node matches SDK interface.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.nodes.runbook_generation_langgraph import (
    runbook_generation_node_langgraph,
)
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)

# Module path for patching dependencies of the node under test
_MOD = "analysi.agentic_orchestration.nodes.runbook_generation_langgraph"


@pytest.fixture(autouse=True)
def dummy_env(monkeypatch):
    """Set a dummy ANTHROPIC_API_KEY so ChatAnthropic instantiates without error.

    ChatAnthropic only validates the key at API call time, not at instantiation.
    We also patch get_db_skills_store to avoid importing AsyncSessionLocal in unit tests.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key-for-unit-tests")
    with patch(f"{_MOD}.get_db_skills_store", return_value=MagicMock()):
        yield


@pytest.fixture
def mock_state():
    """Create mock state for testing."""
    return {
        "alert": {
            "title": "SQL Injection Detected",
            "source_event_id": "alert-123",
            "severity": "high",
            "detection_rule": "rule_001",
        },
        "run_id": "test-run-id",
        "tenant_id": "test-tenant",
    }


@pytest.fixture
def mock_callback():
    """Create mock ProgressCallback."""
    callback = AsyncMock()
    callback.on_stage_start = AsyncMock()
    callback.on_stage_complete = AsyncMock()
    callback.on_stage_error = AsyncMock()
    return callback


class TestReturnsExpectedFields:
    """Tests for output structure matching SDK interface."""

    @pytest.mark.asyncio
    async def test_returns_runbook_field(self, mock_state):
        """Output contains 'runbook' key."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Test Runbook\n\nContent here.",
                "matching_report": {"decision": "matched", "confidence": "HIGH"},
            }

            result = await runbook_generation_node_langgraph(mock_state)

            assert "runbook" in result
            assert result["runbook"] == "# Test Runbook\n\nContent here."

    @pytest.mark.asyncio
    async def test_returns_matching_report_as_json_string(self, mock_state):
        """matching_report is JSON string, not dict."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {
                    "decision": "matched",
                    "confidence": "HIGH",
                    "score": 85,
                },
            }

            result = await runbook_generation_node_langgraph(mock_state)

            assert "matching_report" in result
            # Should be a JSON string
            assert isinstance(result["matching_report"], str)
            # Should be valid JSON
            parsed = json.loads(result["matching_report"])
            assert parsed["decision"] == "matched"
            assert parsed["confidence"] == "HIGH"

    @pytest.mark.asyncio
    async def test_returns_metrics_list(self, mock_state):
        """Output contains 'metrics' as list."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched"},
            }

            result = await runbook_generation_node_langgraph(mock_state)

            assert "metrics" in result
            assert isinstance(result["metrics"], list)


class TestEmptyMatchingReportHandling:
    """Tests for edge cases in matching_report serialization."""

    @pytest.mark.asyncio
    async def test_empty_dict_matching_report_serialized_correctly(self, mock_state):
        """Empty dict {} should serialize to '{}', not None.

        Bug fix: Empty dict is falsy in Python, so 'if matching_report' returns False.
        We must use 'if matching_report is not None' instead.
        """
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {},  # Empty dict - should NOT become None
            }

            result = await runbook_generation_node_langgraph(mock_state)

            # Should be "{}", not None
            assert result["matching_report"] is not None
            assert result["matching_report"] == "{}"
            # Should be valid JSON
            parsed = json.loads(result["matching_report"])
            assert parsed == {}

    @pytest.mark.asyncio
    async def test_none_matching_report_stays_none(self, mock_state):
        """None matching_report should stay None (not serialize to 'null')."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": None,  # Explicit None
            }

            result = await runbook_generation_node_langgraph(mock_state)

            assert result["matching_report"] is None


class TestLoggingBehavior:
    """Tests for logging decisions correctly."""

    @pytest.mark.asyncio
    async def test_matched_decision_logs_correctly(self, mock_state, caplog):
        """Logs 'matched' when decision=matched."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched", "confidence": "HIGH"},
            }

            import logging

            with caplog.at_level(logging.INFO):
                await runbook_generation_node_langgraph(mock_state)

            assert any("matched" in record.message.lower() for record in caplog.records)

    @pytest.mark.asyncio
    async def test_composed_decision_logs_correctly(self, mock_state, caplog):
        """Logs 'composed' when decision=composed."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Composed Runbook",
                "matching_report": {"decision": "composed", "confidence": "MEDIUM"},
            }

            import logging

            with caplog.at_level(logging.INFO):
                await runbook_generation_node_langgraph(mock_state)

            assert any(
                "composed" in record.message.lower() for record in caplog.records
            )


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_error_returns_error_field(self, mock_state):
        """Exceptions caught, returned as {'error': msg}."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.side_effect = RuntimeError("LangGraph execution failed")

            result = await runbook_generation_node_langgraph(mock_state)

            assert "error" in result
            assert "LangGraph execution failed" in result["error"]

    @pytest.mark.asyncio
    async def test_error_returns_none_runbook(self, mock_state):
        """Error case has runbook=None."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.side_effect = Exception("Something went wrong")

            result = await runbook_generation_node_langgraph(mock_state)

            assert result.get("runbook") is None

    @pytest.mark.asyncio
    async def test_error_returns_none_matching_report(self, mock_state):
        """Error case has matching_report=None."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.side_effect = Exception("Something went wrong")

            result = await runbook_generation_node_langgraph(mock_state)

            assert result.get("matching_report") is None


class TestCallbackIntegration:
    """Tests for ProgressCallback integration."""

    @pytest.mark.asyncio
    async def test_calls_callback_on_start(self, mock_state, mock_callback):
        """ProgressCallback.on_stage_start called."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched"},
            }

            await runbook_generation_node_langgraph(mock_state, callback=mock_callback)

            mock_callback.on_stage_start.assert_called_once()
            call_args = mock_callback.on_stage_start.call_args
            assert call_args[0][0] == WorkflowGenerationStage.RUNBOOK_GENERATION

    @pytest.mark.asyncio
    async def test_calls_callback_on_complete(self, mock_state, mock_callback):
        """ProgressCallback.on_stage_complete called."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched"},
            }

            await runbook_generation_node_langgraph(mock_state, callback=mock_callback)

            mock_callback.on_stage_complete.assert_called_once()
            call_args = mock_callback.on_stage_complete.call_args
            assert call_args[0][0] == WorkflowGenerationStage.RUNBOOK_GENERATION

    @pytest.mark.asyncio
    async def test_calls_callback_on_error(self, mock_state, mock_callback):
        """ProgressCallback.on_stage_error called when exception occurs."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.side_effect = RuntimeError("Graph failed")

            await runbook_generation_node_langgraph(mock_state, callback=mock_callback)

            mock_callback.on_stage_error.assert_called_once()
            call_args = mock_callback.on_stage_error.call_args
            assert call_args[0][0] == WorkflowGenerationStage.RUNBOOK_GENERATION

    @pytest.mark.asyncio
    async def test_no_callback_no_error(self, mock_state):
        """Works correctly without callback (callback=None)."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched"},
            }

            # Should not raise
            result = await runbook_generation_node_langgraph(mock_state, callback=None)

            assert result["runbook"] is not None


class TestMetricsCollection:
    """Tests for metrics collection from LangGraph execution."""

    @pytest.mark.asyncio
    async def test_metrics_contain_stage_execution_metrics(self, mock_state):
        """Metrics list contains StageExecutionMetrics."""
        with patch(f"{_MOD}.run_phase1") as mock_run:
            mock_run.return_value = {
                "runbook": "# Runbook",
                "matching_report": {"decision": "matched"},
            }
            # Mock the metrics collector
            with patch(f"{_MOD}.LangGraphMetricsCollector") as mock_collector_class:
                mock_collector = MagicMock()
                mock_metrics = StageExecutionMetrics(
                    duration_ms=1500,
                    duration_api_ms=1200,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={"input_tokens": 5000, "output_tokens": 2000},
                    tool_calls=[],
                )
                mock_collector.to_stage_metrics.return_value = mock_metrics
                mock_collector_class.return_value = mock_collector

                result = await runbook_generation_node_langgraph(mock_state)

                assert len(result["metrics"]) >= 1

    @pytest.mark.asyncio
    async def test_metrics_duration_is_captured_without_token_data(self, mock_state):
        """Duration is tracked even without LLM token data.

        The real LangGraphMetricsCollector tracks duration via start() and to_stage_metrics(),
        even when no LLM calls are recorded. This test verifies duration is positive.
        """
        import asyncio

        with patch(f"{_MOD}.run_phase1") as mock_run:

            async def slow_run(*args, **kwargs):
                await asyncio.sleep(0.05)  # 50ms
                return {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }

            mock_run.side_effect = slow_run

            result = await runbook_generation_node_langgraph(mock_state)

            # Metrics should have captured duration
            assert len(result["metrics"]) == 1
            metrics = result["metrics"][0]
            assert isinstance(metrics, StageExecutionMetrics)
            # Duration should be at least 50ms (our sleep time)
            assert metrics.duration_ms >= 50
            # Token data should be zero (not recorded)
            assert metrics.usage.get("input_tokens", 0) == 0
            assert metrics.usage.get("output_tokens", 0) == 0


class TestConfigIntegration:
    """Tests for config module integration."""

    @pytest.mark.asyncio
    async def test_uses_create_langgraph_llm(self, mock_state):
        """Uses create_langgraph_llm() to create LLM."""
        with patch(f"{_MOD}.create_langgraph_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm

            with patch(f"{_MOD}.run_phase1") as mock_run:
                mock_run.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }

                await runbook_generation_node_langgraph(mock_state)

                mock_get_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_get_db_skills_store(self, mock_state):
        """Uses get_db_skills_store() to create ResourceStore."""
        # Override the autouse patch to assert on this specific call
        with patch(f"{_MOD}.get_db_skills_store") as mock_get_store:
            mock_get_store.return_value = MagicMock()

            with patch(f"{_MOD}.run_phase1") as mock_run:
                mock_run.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }

                await runbook_generation_node_langgraph(mock_state)

                mock_get_store.assert_called_once()

    # Removed test_uses_get_runbooks_repository_path - DB-only skills
