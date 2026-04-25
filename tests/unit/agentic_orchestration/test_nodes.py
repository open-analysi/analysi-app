"""Tests for orchestration node functions."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration import (
    StageExecutionMetrics,
)
from analysi.agentic_orchestration.nodes import (
    runbook_generation_node,
    task_proposal_node,
)
from analysi.agentic_orchestration.nodes.task_proposal import parse_task_proposals


class TestRunbookGenerationNode:
    """Tests for runbook_generation_node function."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        executor = MagicMock()
        executor.execute_stage = AsyncMock(
            return_value=(
                "Agent completed",
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        return executor

    @pytest.fixture
    def sample_state(self):
        """Create sample workflow state."""
        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"matched-runbook.md": "# Runbook", "matching-report.json": "{}"},
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        mock_workspace.cleanup = MagicMock()

        return {
            "alert": {
                "id": "alert-123",
                "title": "Suspicious Login",
                "severity": "high",
            },
            "run_id": "test-run-123",
            "workspace": mock_workspace,  # Add workspace to state
            "runbook": None,
            "task_proposals": None,
            "metrics": [],
            "error": None,
        }

    @pytest.fixture
    def agent_file(self, tmp_path):
        """Create test agent file."""
        agent_path = tmp_path / "runbook-match-agent.md"
        agent_path.write_text("# Test Runbook Agent\n\nMatch runbooks to alerts.")
        return agent_path

    @pytest.mark.asyncio
    async def test_runbook_generation_node_calls_executor(
        self, mock_executor, sample_state, agent_file, tmp_path
    ):
        """Verify node calls executor.execute_stage with correct stage."""
        # Patch get_agent_path to return our test file
        with patch(
            "analysi.agentic_orchestration.nodes.runbook_generation.get_agent_path",
            return_value=agent_file,
        ):
            result = await runbook_generation_node(sample_state, mock_executor)

            assert result["runbook"] == "# Runbook"
            # Workspace from state should be used
            sample_state["workspace"].run_agent.assert_called_once()
            # Cleanup should NOT be called (that's the subgraph's job)
            sample_state["workspace"].cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_runbook_generation_node_triggers_callbacks(
        self, mock_executor, sample_state, agent_file
    ):
        """Verify node calls on_stage_start and on_stage_complete."""
        mock_callback = AsyncMock()

        with patch(
            "analysi.agentic_orchestration.nodes.runbook_generation.get_agent_path",
            return_value=agent_file,
        ):
            await runbook_generation_node(sample_state, mock_executor, mock_callback)

            mock_callback.on_stage_start.assert_called_once()
            mock_callback.on_stage_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_runbook_generation_node_calls_on_stage_error_on_failure(
        self, mock_executor, sample_state, agent_file
    ):
        """Verify node calls on_stage_error when execution fails."""
        mock_callback = AsyncMock()

        # Make workspace.run_agent raise an exception
        sample_state["workspace"].run_agent = AsyncMock(
            side_effect=RuntimeError("Agent execution failed")
        )

        with patch(
            "analysi.agentic_orchestration.nodes.runbook_generation.get_agent_path",
            return_value=agent_file,
        ):
            result = await runbook_generation_node(
                sample_state, mock_executor, mock_callback
            )

            # Should call on_stage_start before the error
            mock_callback.on_stage_start.assert_called_once()
            # Should NOT call on_stage_complete
            mock_callback.on_stage_complete.assert_not_called()
            # Should call on_stage_error
            mock_callback.on_stage_error.assert_called_once()
            # Should return error in result
            assert result.get("error") is not None
            assert "Agent execution failed" in result["error"]


class TestTaskProposalNode:
    """Tests for task_proposal_node function."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        executor = MagicMock()
        executor.execute_stage = AsyncMock(
            return_value=(
                "Agent completed",
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        return executor

    @pytest.fixture
    def sample_state(self):
        """Create sample workflow state with runbook."""
        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"task-proposals.json": "[]"},
                StageExecutionMetrics(
                    duration_ms=2000,
                    duration_api_ms=1600,
                    num_turns=5,
                    total_cost_usd=0.10,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        mock_workspace.cleanup = MagicMock()

        return {
            "alert": {
                "id": "alert-123",
                "title": "Suspicious Login",
                "severity": "high",
            },
            "run_id": "test-run-123",
            "workspace": mock_workspace,  # Add workspace to state
            "runbook": "# Investigation Runbook\n\n## Steps\n1. Check IP reputation",
            "task_proposals": None,
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
            "error": None,
        }

    @pytest.fixture
    def agent_file(self, tmp_path):
        """Create test agent file."""
        agent_path = tmp_path / "runbook-to-task-proposals.md"
        agent_path.write_text("# Task Proposal Agent\n\nPropose tasks from runbooks.")
        return agent_path

    @pytest.mark.asyncio
    async def test_task_proposal_node_calls_executor(
        self, mock_executor, sample_state, agent_file
    ):
        """Verify node calls executor.execute_stage with correct stage."""
        # Override workspace mock for this test
        sample_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {"task-proposals.json": '[{"name": "Test", "category": "new"}]'},
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        with patch(
            "analysi.agentic_orchestration.nodes.task_proposal.get_agent_path",
            return_value=agent_file,
        ):
            result = await task_proposal_node(sample_state, mock_executor)

            assert result["task_proposals"] == [{"name": "Test", "category": "new"}]
            sample_state["workspace"].run_agent.assert_called_once()
            # Cleanup should NOT be called (that's the subgraph's job)
            sample_state["workspace"].cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_proposal_node_accumulates_metrics(
        self, mock_executor, sample_state, agent_file
    ):
        """Verify metrics list grows with each stage."""
        with patch(
            "analysi.agentic_orchestration.nodes.task_proposal.get_agent_path",
            return_value=agent_file,
        ):
            result = await task_proposal_node(sample_state, mock_executor)

            # Should have previous metrics + new metrics
            assert len(result["metrics"]) == 2
            assert result["metrics"][0].total_cost_usd == 0.05  # Previous
            assert result["metrics"][1].total_cost_usd == 0.10  # New


class TestParseTaskProposals:
    """Tests for parse_task_proposals helper function."""

    def test_parse_task_proposals_valid_json_list(self):
        """Verify parser handles valid JSON list output."""
        json_output = json.dumps(
            [
                {
                    "name": "Check IP",
                    "description": "Check IP reputation",
                    "category": "new",
                    "required_integrations": ["virustotal"],
                }
            ]
        )

        result = parse_task_proposals(json_output)

        assert len(result) == 1
        assert result[0]["name"] == "Check IP"
        assert result[0]["category"] == "new"

    def test_parse_task_proposals_valid_json_object(self):
        """Verify parser handles JSON object with proposals key."""
        json_output = json.dumps(
            {
                "proposals": [
                    {
                        "name": "Check IP",
                        "description": "Check IP reputation",
                        "category": "existing",
                        "existing_task_id": "task-456",
                        "required_integrations": [],
                    }
                ],
                "analysis_summary": "Found 1 task",
            }
        )

        result = parse_task_proposals(json_output)

        assert len(result) == 1
        assert result[0]["name"] == "Check IP"
        assert result[0]["existing_task_id"] == "task-456"

    def test_parse_task_proposals_empty_list(self):
        """Verify parser handles empty list."""
        result = parse_task_proposals("[]")
        assert result == []

    def test_parse_task_proposals_empty_proposals(self):
        """Verify parser handles empty proposals in object."""
        json_output = json.dumps(
            {
                "proposals": [],
                "analysis_summary": "No tasks needed",
            }
        )

        result = parse_task_proposals(json_output)
        assert result == []

    def test_parse_task_proposals_none_input(self):
        """Verify parser handles None input."""
        result = parse_task_proposals(None)
        assert result == []

    def test_parse_task_proposals_invalid_json(self):
        """Verify parser handles malformed JSON gracefully."""
        result = parse_task_proposals("not valid json {")
        assert result == []

    def test_parse_task_proposals_multiple_tasks(self):
        """Verify parser handles multiple task proposals."""
        json_output = json.dumps(
            [
                {
                    "name": "Task 1",
                    "description": "First",
                    "category": "new",
                    "required_integrations": ["vt"],
                },
                {
                    "name": "Task 2",
                    "description": "Second",
                    "category": "modify",
                    "existing_task_id": "task-123",
                    "required_integrations": ["splunk"],
                },
                {
                    "name": "Task 3",
                    "description": "Third",
                    "category": "existing",
                    "existing_task_id": "task-456",
                    "required_integrations": [],
                },
            ]
        )

        result = parse_task_proposals(json_output)

        assert len(result) == 3
        assert result[0]["category"] == "new"
        assert result[1]["category"] == "modify"
        assert result[2]["category"] == "existing"

    def test_parse_task_proposals_unexpected_format(self):
        """Verify parser handles unexpected JSON format."""
        # Not a list and no 'proposals' key
        result = parse_task_proposals('{"foo": "bar"}')
        assert result == []
