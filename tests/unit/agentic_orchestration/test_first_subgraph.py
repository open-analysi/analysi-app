"""Tests for first subgraph structure and creation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration import (
    AgentOrchestrationExecutor,
    StageExecutionMetrics,
)
from analysi.agentic_orchestration.subgraphs import (
    WorkflowGenerationState,
    run_first_subgraph,
)


class TestWorkflowGenerationState:
    """Tests for WorkflowGenerationState TypedDict."""

    def test_workflow_generation_state_fields(self):
        """Verify TypedDict has all required fields."""
        # Create a valid state dict
        state: WorkflowGenerationState = {
            "alert": {"id": "test-123"},
            "runbook": None,
            "task_proposals": None,
            "metrics": [],
            "error": None,
        }

        assert "alert" in state
        assert "runbook" in state
        assert "task_proposals" in state
        assert "metrics" in state
        assert "error" in state

    def test_workflow_generation_state_with_values(self):
        """Verify state can hold actual values."""
        metrics = StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=3,
            total_cost_usd=0.05,
            usage={},
            tool_calls=[],
        )

        state: WorkflowGenerationState = {
            "alert": {"id": "test-123", "title": "Test Alert"},
            "runbook": "# Runbook\n\nSteps here",
            "task_proposals": [{"name": "Task 1", "category": "new"}],
            "metrics": [metrics],
            "error": None,
        }

        assert state["runbook"] == "# Runbook\n\nSteps here"
        assert len(state["task_proposals"]) == 1
        assert len(state["metrics"]) == 1


class TestRunFirstSubgraph:
    """Tests for run_first_subgraph function."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        executor = MagicMock(spec=AgentOrchestrationExecutor)
        return executor

    @pytest.fixture
    def sample_alert(self):
        """Create sample NAS alert."""
        return {
            "id": "alert-123",
            "title": "Suspicious Login from Unusual Location",
            "severity": "high",
            "source_vendor": "Okta",
            "rule_name": "unusual_login_location",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "raw_alert": {
                "user": "john.doe@company.com",
                "ip": "185.220.101.1",
                "country": "Russia",
            },
        }

    @pytest.mark.asyncio
    async def test_run_first_subgraph_initial_state(self, mock_executor, sample_alert):
        """Verify initial state is properly constructed."""
        from unittest.mock import patch

        # Mock both nodes to avoid file system access
        with patch(
            "analysi.agentic_orchestration.subgraphs.first_subgraph.runbook_generation_node"
        ) as mock_runbook_node:
            with patch(
                "analysi.agentic_orchestration.subgraphs.first_subgraph.task_proposal_node"
            ) as mock_proposal_node:
                mock_runbook_node.return_value = {
                    "runbook": "# Test Runbook",
                    "matching_report": "{}",
                    "metrics": [
                        StageExecutionMetrics(
                            duration_ms=1000,
                            duration_api_ms=800,
                            num_turns=3,
                            total_cost_usd=0.05,
                            usage={},
                            tool_calls=[],
                        )
                    ],
                }
                mock_proposal_node.return_value = {
                    "task_proposals": [{"name": "Test", "category": "new"}],
                    "metrics": [
                        StageExecutionMetrics(
                            duration_ms=1000,
                            duration_api_ms=800,
                            num_turns=3,
                            total_cost_usd=0.05,
                            usage={},
                            tool_calls=[],
                        ),
                        StageExecutionMetrics(
                            duration_ms=2000,
                            duration_api_ms=1600,
                            num_turns=5,
                            total_cost_usd=0.10,
                            usage={},
                            tool_calls=[],
                        ),
                    ],
                }

                result = await run_first_subgraph(
                    sample_alert, mock_executor, run_id="test-run-123"
                )

                # Verify alert was passed through
                assert result["alert"] == sample_alert
                # Verify run_id was propagated
                assert result["run_id"] == "test-run-123"

    @pytest.mark.asyncio
    async def test_run_first_subgraph_with_callback(self, mock_executor, sample_alert):
        """Verify subgraph accepts optional callback."""
        from unittest.mock import patch

        mock_callback = AsyncMock()

        with patch(
            "analysi.agentic_orchestration.subgraphs.first_subgraph.runbook_generation_node"
        ) as mock_runbook_node:
            with patch(
                "analysi.agentic_orchestration.subgraphs.first_subgraph.task_proposal_node"
            ) as mock_proposal_node:
                mock_runbook_node.return_value = {
                    "runbook": "# Test",
                    "matching_report": "{}",
                    "metrics": [
                        StageExecutionMetrics(
                            duration_ms=1000,
                            duration_api_ms=800,
                            num_turns=3,
                            total_cost_usd=0.05,
                            usage={},
                            tool_calls=[],
                        )
                    ],
                }
                mock_proposal_node.return_value = {
                    "task_proposals": [],
                    "metrics": [
                        StageExecutionMetrics(
                            duration_ms=1000,
                            duration_api_ms=800,
                            num_turns=3,
                            total_cost_usd=0.05,
                            usage={},
                            tool_calls=[],
                        ),
                        StageExecutionMetrics(
                            duration_ms=2000,
                            duration_api_ms=1600,
                            num_turns=5,
                            total_cost_usd=0.10,
                            usage={},
                            tool_calls=[],
                        ),
                    ],
                }

                result = await run_first_subgraph(
                    sample_alert,
                    mock_executor,
                    run_id="test-run-123",
                    callback=mock_callback,
                )

                assert result is not None
