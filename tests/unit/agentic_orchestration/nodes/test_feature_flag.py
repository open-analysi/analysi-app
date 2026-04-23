"""Tests for LangGraph feature flag parsing and dispatch logic."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from analysi.agentic_orchestration.nodes.runbook_generation import (
    _use_langgraph,
    runbook_generation_node,
)


class TestUseLangGraphFlag:
    """Tests for _use_langgraph() feature flag function."""

    def test_use_langgraph_false_when_not_set(self):
        """Default is False when environment variable is not set."""
        env_without_flag = {
            k: v for k, v in os.environ.items() if k != "ANALYSI_USE_LANGGRAPH_PHASE1"
        }
        with patch.dict(os.environ, env_without_flag, clear=True):
            result = _use_langgraph()

            assert result is False

    def test_use_langgraph_false_when_empty(self):
        """Empty string equals False."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": ""}):
            result = _use_langgraph()

            assert result is False

    def test_use_langgraph_true_when_true(self):
        """'true' equals True."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            result = _use_langgraph()

            assert result is True

    def test_use_langgraph_true_case_insensitive(self):
        """'TRUE', 'True' all equal True."""
        for value in ["TRUE", "True", "tRuE"]:
            with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": value}):
                result = _use_langgraph()

                assert result is True, f"Expected True for value '{value}'"

    def test_use_langgraph_false_when_other_value(self):
        """'false', '1', 'yes', other values equal False."""
        for value in ["false", "False", "1", "yes", "0", "no", "enabled"]:
            with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": value}):
                result = _use_langgraph()

                assert result is False, f"Expected False for value '{value}'"

    def test_flag_with_whitespace(self):
        """Whitespace is trimmed correctly."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": " true "}):
            result = _use_langgraph()

            assert result is True

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "  TRUE  "}):
            result = _use_langgraph()

            assert result is True


class TestFeatureFlagDispatch:
    """Tests for feature flag dispatch in runbook_generation_node()."""

    @pytest.fixture
    def mock_state(self):
        """Create mock state for testing."""
        return {
            "alert": {
                "title": "Test Alert",
                "source_event_id": "test-123",
                "severity": "high",
            },
            "workspace": AsyncMock(),
            "run_id": "test-run-id",
            "tenant_id": "test-tenant",
        }

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_feature_flag_dispatches_to_langgraph(self, mock_state):
        """Flag=true uses LangGraph implementation."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.runbook_generation_node_langgraph"
            ) as mock_langgraph:
                mock_langgraph.return_value = {
                    "runbook": "# Test Runbook",
                    "matching_report": '{"decision": "matched"}',
                    "metrics": [],
                }

                result = await runbook_generation_node(mock_state, None)

                mock_langgraph.assert_called_once()
                assert result["runbook"] == "# Test Runbook"

    @pytest.mark.asyncio
    async def test_feature_flag_dispatches_to_sdk(self, mock_state, mock_executor):
        """Flag=false uses SDK implementation."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            # Mock the workspace.run_agent to avoid actual SDK call
            mock_state["workspace"].run_agent = AsyncMock(
                return_value=(
                    {
                        "matched-runbook.md": "# SDK Runbook",
                        "matching-report.json": "{}",
                    },
                    AsyncMock(),  # metrics
                )
            )

            await runbook_generation_node(mock_state, mock_executor)

            # Should have called workspace.run_agent (SDK path)
            mock_state["workspace"].run_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_langgraph_error_returned_in_result(self, mock_state):
        """When LangGraph returns error dict, it's passed through to caller.

        The LangGraph function handles its own exceptions and returns {error: ...}.
        This tests that the error dict is passed through correctly.
        """
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.runbook_generation_node_langgraph"
            ) as mock_langgraph:
                # LangGraph function returns error dict (as it should on failure)
                mock_langgraph.return_value = {
                    "runbook": None,
                    "matching_report": None,
                    "error": "LangGraph runbook generation failed: Graph execution failed",
                }

                result = await runbook_generation_node(mock_state, None)

                # Error dict should be passed through directly
                assert result.get("error") is not None
                assert "Graph execution failed" in result["error"]
                assert result.get("runbook") is None

    @pytest.mark.asyncio
    async def test_sdk_works_independently(self, mock_state, mock_executor):
        """SDK path works independently when flag is false."""
        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            mock_metrics = AsyncMock()
            mock_metrics.duration_ms = 1000
            mock_state["workspace"].run_agent = AsyncMock(
                return_value=(
                    {
                        "matched-runbook.md": "# SDK Runbook",
                        "matching-report.json": "{}",
                    },
                    mock_metrics,
                )
            )

            result = await runbook_generation_node(mock_state, mock_executor)

            assert result["runbook"] == "# SDK Runbook"
