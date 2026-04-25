"""Tests for task building node.

The task_building_node now handles a SINGLE proposal (designed for parallel execution).
The second_subgraph uses asyncio.gather() to run multiple instances in parallel.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.nodes.task_building import (
    filter_proposals_for_building,
    task_building_node,
)
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
)


class TestFilterProposalsForBuilding:
    """Tests for filter_proposals_for_building function."""

    def test_filter_proposals_returns_only_new_and_modify(self):
        """Verify only new and modification proposals are returned."""
        proposals = [
            {"name": "Task 1", "designation": "new"},
            {"name": "Task 2", "designation": "modification"},
            {"name": "Task 3", "designation": "existing"},
        ]

        result = filter_proposals_for_building(proposals)

        assert len(result) == 2
        assert result[0]["name"] == "Task 1"
        assert result[1]["name"] == "Task 2"

    def test_filter_proposals_excludes_existing(self):
        """Verify existing proposals are excluded."""
        proposals = [
            {"name": "Task 1", "designation": "existing"},
            {"name": "Task 2", "designation": "existing"},
        ]

        result = filter_proposals_for_building(proposals)

        assert result == []

    def test_filter_proposals_handles_empty_list(self):
        """Verify empty list returns empty list."""
        result = filter_proposals_for_building([])

        assert result == []

    def test_filter_proposals_handles_none(self):
        """Verify None input returns empty list."""
        result = filter_proposals_for_building(None)

        assert result == []

    def test_filter_proposals_with_max_tasks_limit(self):
        """Verify max_tasks parameter limits the number of proposals returned."""
        proposals = [
            {"name": "Task 1", "designation": "new"},
            {"name": "Task 2", "designation": "modification"},
            {"name": "Task 3", "designation": "new"},
            {"name": "Task 4", "designation": "new"},
        ]

        result = filter_proposals_for_building(proposals, max_tasks=2)

        assert len(result) == 2
        assert result[0]["name"] == "Task 1"
        assert result[1]["name"] == "Task 2"

    def test_filter_proposals_max_tasks_exceeds_available(self):
        """Verify max_tasks larger than available proposals returns all proposals."""
        proposals = [
            {"name": "Task 1", "designation": "new"},
            {"name": "Task 2", "designation": "modification"},
        ]

        result = filter_proposals_for_building(proposals, max_tasks=10)

        assert len(result) == 2

    def test_filter_proposals_max_tasks_zero(self):
        """Verify max_tasks=0 is treated as no limit (returns all filtered)."""
        proposals = [
            {"name": "Task 1", "designation": "new"},
            {"name": "Task 2", "designation": "modification"},
        ]

        result = filter_proposals_for_building(proposals, max_tasks=0)

        # max_tasks=0 is treated as no limit, so returns all that match designation filter
        assert len(result) == 2

    def test_filter_proposals_max_tasks_none_no_limit(self):
        """Verify max_tasks=None applies no limit (default behavior)."""
        proposals = [
            {"name": "Task 1", "designation": "new"},
            {"name": "Task 2", "designation": "modification"},
            {"name": "Task 3", "designation": "new"},
            {"name": "Task 4", "designation": "existing"},  # Should be filtered out
        ]

        result = filter_proposals_for_building(proposals, max_tasks=None)

        # All non-existing proposals should be returned
        assert len(result) == 3

    def test_filter_proposals_max_tasks_filters_designation_first(self):
        """Verify max_tasks is applied AFTER filtering by designation."""
        proposals = [
            {"name": "Existing 1", "designation": "existing"},
            {"name": "New 1", "designation": "new"},
            {"name": "Existing 2", "designation": "existing"},
            {"name": "New 2", "designation": "new"},
            {"name": "Modify 1", "designation": "modification"},
        ]

        result = filter_proposals_for_building(proposals, max_tasks=2)

        # Should filter out "existing" first, then limit to 2
        assert len(result) == 2
        assert result[0]["name"] == "New 1"
        assert result[1]["name"] == "New 2"


class TestTaskBuildingNode:
    """Tests for task_building_node function.

    The node now handles a SINGLE proposal (state.proposal),
    designed to be called in parallel via asyncio.gather().
    """

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        return MagicMock()

    @pytest.fixture
    def single_proposal_state(self):
        """State with a single proposal (as sent via Send pattern)."""
        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"task-result.json": None},
                StageExecutionMetrics(
                    duration_ms=0,
                    duration_api_ms=0,
                    num_turns=0,
                    total_cost_usd=0.0,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        mock_workspace.cleanup = MagicMock()

        return {
            "proposal": {
                "name": "IP Reputation Check",
                "description": "Check IP reputation using VirusTotal",
                "designation": "new",
                "existing_cy_name": None,
                "integration_tools": ["virustotal::ip_reputation"],
            },
            "alert": {"id": "test-alert-001", "title": "Test Alert"},
            "runbook": "# Test Runbook\n\nInvestigation steps...",
            "run_id": "test-run-uuid",
            "tenant_id": "test-tenant",
            "workspace": mock_workspace,
        }

    @pytest.mark.asyncio
    async def test_task_building_node_success(
        self, mock_executor, single_proposal_state
    ):
        """Verify node successfully builds a task with REST API pre/post-flight checks."""
        # Mock httpx client for REST API calls
        mock_response_pre = MagicMock()
        mock_response_pre.status_code = 200
        mock_response_pre.json.return_value = []  # Pre-flight: not found

        mock_response_post = MagicMock()
        mock_response_post.status_code = 200
        mock_response_post.json.return_value = [
            {
                "id": "uuid-new-task",
                "cy_name": "ip_reputation_check",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_pre,  # Pre-flight: check by cy_name (not found)
                    mock_response_pre,  # Pre-flight: check by name (not found)
                    mock_response_post,  # Post-flight: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            metrics = StageExecutionMetrics(
                duration_ms=5000,
                duration_api_ms=4500,
                num_turns=3,
                total_cost_usd=0.05,
                usage={},
                tool_calls=[],
            )

            single_proposal_state["workspace"].run_agent = AsyncMock(
                return_value=({}, metrics)
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # Result should have tasks_built list with single result (for reducer)
        assert "tasks_built" in result
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is True
        assert result["tasks_built"][0]["task_id"] == "uuid-new-task"
        assert result["tasks_built"][0]["cy_name"] == "ip_reputation_check"

    @pytest.mark.asyncio
    async def test_task_building_node_missing_proposal(self, mock_executor):
        """Verify node fails fast when proposal is missing (programming error)."""
        mock_workspace = MagicMock()
        mock_workspace.cleanup = MagicMock()

        state = {
            "alert": {"id": "test-alert"},
            "runbook": "# Runbook",
            "run_id": "test-run",
            "tenant_id": "test-tenant",
            "workspace": mock_workspace,
            # No proposal!
        }

        # Should raise ValueError with clear message
        with pytest.raises(ValueError) as exc_info:
            await task_building_node(state, mock_executor)

        error_message = str(exc_info.value)
        assert "proposal" in error_message.lower()
        assert "parallel task" in error_message.lower()
        assert (
            "programming error" in error_message.lower()
            or "bug" in error_message.lower()
        )

    @pytest.mark.asyncio
    async def test_task_building_node_agent_failure(
        self, mock_executor, single_proposal_state
    ):
        """Verify node handles agent execution failure."""
        # Mock REST API - task doesn't exist
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Override workspace mock to simulate failure
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("Agent crashed")
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is False
        assert "Agent crashed" in result["tasks_built"][0]["error"]

    @pytest.mark.asyncio
    async def test_task_building_node_post_flight_failure(
        self, mock_executor, single_proposal_state
    ):
        """Verify node detects when agent completed but didn't create the task (post-flight check)."""
        # Mock REST API - task doesn't exist in pre-flight or post-flight
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            metrics = StageExecutionMetrics(
                duration_ms=5000,
                duration_api_ms=4500,
                num_turns=3,
                total_cost_usd=0.05,
                usage={},
                tool_calls=[],
            )

            single_proposal_state["workspace"].run_agent = AsyncMock(
                return_value=({}, metrics)
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is False
        assert "was not found in system" in result["tasks_built"][0]["error"]
        assert (
            "may have failed to call create_task" in result["tasks_built"][0]["error"]
        )

    @pytest.mark.asyncio
    async def test_task_building_node_pre_flight_skip_existing_by_name(
        self, mock_executor, single_proposal_state
    ):
        """Verify pre-flight check skips task if it already exists by name."""
        # Mock REST API - task found by cy_name search
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "uuid-existing",
                "cy_name": "existing_ip_reputation",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await task_building_node(single_proposal_state, mock_executor)

        # Should skip generation and return existing task
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is True
        assert result["tasks_built"][0]["skipped"] is True
        assert (
            result["tasks_built"][0]["skip_reason"] == "Task already exists in system"
        )
        assert result["tasks_built"][0]["task_id"] == "uuid-existing"
        assert result["tasks_built"][0]["cy_name"] == "existing_ip_reputation"

    @pytest.mark.asyncio
    async def test_task_building_node_pre_flight_skip_existing_by_cy_name(
        self, mock_executor, single_proposal_state
    ):
        """Verify pre-flight check skips task if it already exists by cy_name."""
        # Add cy_name to proposal (for modification designation)
        single_proposal_state["proposal"]["cy_name"] = "ip_reputation_v1"

        # Mock REST API - not found by name, but found by cy_name
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-existing",
                "cy_name": "ip_reputation_v1",
                "name": "IP Reputation Check V1",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # _check_task_exists(name): cy_name search (not found)
                    mock_response_not_found,  # _check_task_exists(name): name search (not found)
                    mock_response_not_found,  # _check_task_exists(name): derived cy_name (not found)
                    mock_response_found,  # _check_task_exists(cy_name): cy_name search (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await task_building_node(single_proposal_state, mock_executor)

        # Should skip generation
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is True
        assert result["tasks_built"][0]["skipped"] is True
        assert result["tasks_built"][0]["task_id"] == "uuid-existing"

    @pytest.mark.asyncio
    async def test_task_building_node_includes_metrics(
        self, mock_executor, single_proposal_state
    ):
        """Verify node returns metrics from agent execution."""
        # Mock REST API - pre-flight: not found, post-flight: created
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-123",
                "cy_name": "test_task",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    mock_response_found,  # Post-flight: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            expected_metrics = StageExecutionMetrics(
                duration_ms=5000,
                duration_api_ms=4500,
                num_turns=3,
                total_cost_usd=0.05,
                usage={"input_tokens": 1000, "output_tokens": 500},
                tool_calls=[],
            )

            single_proposal_state["workspace"].run_agent = AsyncMock(
                return_value=({}, expected_metrics)
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        assert "metrics" in result
        assert len(result["metrics"]) == 1
        assert result["metrics"][0].total_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_task_building_node_calls_callback(
        self, mock_executor, single_proposal_state
    ):
        """Verify node calls progress callback.

        Note: on_stage_start is NOT called from task_building_node, only on_stage_complete.
        on_stage_start is called once from fan_out_entrypoint to avoid N duplicate callbacks
        for N parallel tasks (see task_building.py line 62 comment).
        """
        mock_callback = AsyncMock()

        # Mock REST API - pre-flight: not found, post-flight: created
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-123",
                "cy_name": "test_task",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    mock_response_found,  # Post-flight: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            metrics = StageExecutionMetrics(
                duration_ms=5000,
                duration_api_ms=4500,
                num_turns=3,
                total_cost_usd=0.05,
                usage={},
                tool_calls=[],
            )

            single_proposal_state["workspace"].run_agent = AsyncMock(
                return_value=({}, metrics)
            )

            await task_building_node(
                single_proposal_state, mock_executor, callback=mock_callback
            )

        # Callback should only be called for stage complete (not stage start)
        mock_callback.on_stage_start.assert_not_called()
        mock_callback.on_stage_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_building_node_workspace_cleanup(
        self, mock_executor, single_proposal_state
    ):
        """Verify workspace is cleaned up even on failure."""
        # Mock REST API - task doesn't exist
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Override workspace mock to simulate failure
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("Agent crashed")
            )

            await task_building_node(single_proposal_state, mock_executor)

        # Workspace from state should be cleaned up
        single_proposal_state["workspace"].cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_task_building_node_modify_category(self, mock_executor):
        """Verify node handles modification designation proposals."""
        # Mock REST API - pre-flight: not found, post-flight: created
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-modified",
                "cy_name": "old_task",
                "name": "Update Existing Task",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight name: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight name: check by name (not found)
                    mock_response_not_found,  # Pre-flight name: check by derived cy_name (not found)
                    mock_response_not_found,  # Pre-flight cy_name: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight cy_name: check by name (not found)
                    mock_response_not_found,  # Pre-flight cy_name: check by derived cy_name (not found)
                    mock_response_found,  # Post-flight: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            metrics = StageExecutionMetrics(
                duration_ms=5000,
                duration_api_ms=4500,
                num_turns=3,
                total_cost_usd=0.05,
                usage={},
                tool_calls=[],
            )

            mock_workspace = MagicMock()
            mock_workspace.run_agent = AsyncMock(return_value=({}, metrics))
            mock_workspace.cleanup = MagicMock()

            state = {
                "proposal": {
                    "name": "Update Existing Task",
                    "designation": "modification",
                    "cy_name": "old_task",
                },
                "alert": {"id": "test-alert"},
                "runbook": "# Runbook",
                "run_id": "test-run",
                "tenant_id": "test-tenant",
                "workspace": mock_workspace,
            }

            result = await task_building_node(state, mock_executor)

        assert result["tasks_built"][0]["designation"] == "modification"
        assert result["tasks_built"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_task_building_node_result_format_for_reducer(
        self, mock_executor, single_proposal_state
    ):
        """Verify result format is compatible with list accumulation pattern."""
        # Mock REST API - pre-flight: not found, post-flight: created
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-123",
                "cy_name": "test_task",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    mock_response_found,  # Post-flight: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            single_proposal_state["workspace"].run_agent = AsyncMock(
                return_value=(
                    {},
                    StageExecutionMetrics(
                        duration_ms=5000,
                        duration_api_ms=4500,
                        num_turns=3,
                        total_cost_usd=0.05,
                        usage={},
                        tool_calls=[],
                    ),
                )
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # tasks_built must be a list for operator.add reducer
        assert isinstance(result["tasks_built"], list)
        # metrics must be a list for operator.add reducer
        assert isinstance(result["metrics"], list)

    @pytest.mark.asyncio
    async def test_task_building_node_recovery_when_task_exists(
        self, mock_executor, single_proposal_state
    ):
        """Verify recovery succeeds when agent crashes but task was already created."""
        # Mock REST API:
        # - Pre-flight checks: not found (task doesn't exist yet)
        # - Agent crashes after creating task
        # - Recovery check: task exists!
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-recovered-task",
                "cy_name": "recovered_ip_reputation",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    # Agent crashes here (after creating task via MCP)
                    mock_response_found,  # Recovery: check by cy_name (found!)
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Simulate agent crash (e.g., SDK cancel scope exception)
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError(
                    "Attempted to exit cancel scope in a different task"
                )
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # Recovery should succeed
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is True
        assert result["tasks_built"][0]["recovered"] is True
        assert result["tasks_built"][0]["task_id"] == "uuid-recovered-task"
        assert result["tasks_built"][0]["cy_name"] == "recovered_ip_reputation"
        assert result["tasks_built"][0]["error"] is None

    @pytest.mark.asyncio
    async def test_task_building_node_no_recovery_when_task_missing(
        self, mock_executor, single_proposal_state
    ):
        """Verify genuine failure when agent crashes and task doesn't exist."""
        # Mock REST API: task never exists (genuine agent failure before MCP call)
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response_not_found)
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Simulate agent crash
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("Agent initialization failed")
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # Should be genuine failure (no recovery)
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is False
        assert result["tasks_built"][0].get("recovered") is None
        assert result["tasks_built"][0]["task_id"] is None
        assert result["tasks_built"][0]["cy_name"] is None
        assert "Agent initialization failed" in result["tasks_built"][0]["error"]

    @pytest.mark.asyncio
    async def test_task_building_node_recovery_check_fails(
        self, mock_executor, single_proposal_state
    ):
        """Verify graceful fallback when recovery check itself fails."""
        # Mock REST API:
        # - Pre-flight: not found
        # - Agent crashes
        # - Recovery check: network error
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    # Agent crashes here
                    Exception(
                        "Network timeout during recovery check"
                    ),  # Recovery fails
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Simulate agent crash
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("Agent crashed")
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # Should fall back to genuine failure (recovery check failed)
        assert len(result["tasks_built"]) == 1
        assert result["tasks_built"][0]["success"] is False
        assert result["tasks_built"][0].get("recovered") is None
        assert result["tasks_built"][0]["task_id"] is None
        assert "Agent crashed" in result["tasks_built"][0]["error"]

    @pytest.mark.asyncio
    async def test_task_building_node_recovery_with_callback(
        self, mock_executor, single_proposal_state
    ):
        """Verify callback is called with recovered task info."""
        mock_callback = AsyncMock()

        # Mock REST API for successful recovery
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-recovered",
                "cy_name": "recovered_task",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    mock_response_found,  # Recovery: found!
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            # Agent crashes
            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("SDK error")
            )

            await task_building_node(
                single_proposal_state, mock_executor, callback=mock_callback
            )

        # Callback should NOT be called (recovery doesn't trigger callback)
        # Only successful normal execution calls callback
        mock_callback.on_stage_complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_building_node_recovery_flag_observable(
        self, mock_executor, single_proposal_state
    ):
        """Verify recovered flag is set for observability/metrics."""
        # Mock REST API for successful recovery
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "uuid-123",
                "cy_name": "test_task",
                "name": "IP Reputation Check",
            }
        ]

        with patch("analysi.common.internal_client.InternalAsyncClient") as mock_client:
            mock_get = AsyncMock(
                side_effect=[
                    mock_response_not_found,  # Pre-flight: check by cy_name (not found)
                    mock_response_not_found,  # Pre-flight: check by name (not found)
                    mock_response_not_found,  # Pre-flight: check by derived cy_name (not found)
                    mock_response_found,  # Recovery: found!
                ]
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            single_proposal_state["workspace"].run_agent = AsyncMock(
                side_effect=RuntimeError("Crash after MCP call")
            )

            result = await task_building_node(single_proposal_state, mock_executor)

        # Recovered flag should be present for observability
        assert result["tasks_built"][0]["recovered"] is True
        # This flag allows monitoring/alerting on recovery frequency
