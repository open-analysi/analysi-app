"""Unit tests for workflow_assembly_node LangGraph reducer pattern.

This test suite verifies the CORRECT LangGraph pattern for Send + operator.add reducers:

CORRECT PATTERN:
- Parallel nodes (task_building_node) return {"tasks_built": [result]}
- LangGraph reducer (operator.add) automatically accumulates: [] + [r1] + [r2] + ... = [r1, r2, ...]
- Aggregator node (workflow_assembly_node) should NOT return tasks_built
- tasks_built is automatically in the final state via the reducer

INCORRECT PATTERN (old bug):
- Aggregator node returns {"tasks_built": state.get("tasks_built", [])}
- This causes duplication: [r1, r2, r3] + [r1, r2, r3] = [r1, r2, r3, r1, r2, r3]

Bug ID: tasks_built_duplication_bug
Fix: Removed "tasks_built" from all return statements in workflow_assembly_node
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.nodes.workflow_assembly import (
    workflow_assembly_node,
)
from analysi.agentic_orchestration.observability import StageExecutionMetrics
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor


@pytest.mark.asyncio
class TestWorkflowAssemblyReducerPattern:
    """Test that workflow_assembly_node follows correct LangGraph reducer pattern."""

    @pytest.fixture(autouse=True)
    def _mock_generate_workflow_name(self):
        """Mock generate_unique_workflow_name to avoid DB calls in unit tests."""
        with patch(
            "analysi.agentic_orchestration.nodes.workflow_assembly.generate_unique_workflow_name",
            new_callable=AsyncMock,
            return_value="Test Alert Analysis Workflow",
        ):
            yield

    @pytest.fixture
    def mock_executor(self):
        """Create a mock AgentOrchestrationExecutor."""
        return MagicMock(spec=AgentOrchestrationExecutor)

    @pytest.fixture
    def sample_tasks_built(self):
        """Sample tasks_built list (already accumulated by reducer)."""
        return [
            {
                "proposal_name": "Task 1",
                "success": True,
                "task_id": "task-1",
                "cy_name": "task_one",
                "error": None,
            },
            {
                "proposal_name": "Task 2",
                "success": True,
                "task_id": "task-2",
                "cy_name": "task_two",
                "error": None,
            },
        ]

    @pytest.fixture
    def base_state(self, sample_tasks_built):
        """Base state with tasks_built already accumulated by reducer."""
        return {
            "task_proposals": [
                {"name": "Task 1", "designation": "new"},
                {"name": "Task 2", "designation": "new"},
            ],
            "tasks_built": sample_tasks_built,  # Already accumulated by reducer
            "alert": {"id": "test-alert", "rule_name": "test_rule"},
            "runbook": "Test runbook",
            "workspace": None,
            "metrics": [],
            "run_id": "test-run",
            "tenant_id": "test-tenant",
        }

    @pytest.mark.asyncio
    async def test_early_exit_does_not_return_tasks_built(
        self, mock_executor, base_state
    ):
        """Test that early exit does NOT return tasks_built (reducer handles it)."""
        state_with_error = {**base_state, "error": "Previous stage failed"}

        result = await workflow_assembly_node(
            state_with_error, mock_executor, callback=None
        )

        # CORRECT: tasks_built should NOT be in return value
        assert "tasks_built" not in result
        # Other fields should be present
        assert "workflow_id" in result
        assert result["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_no_tasks_does_not_return_tasks_built(
        self, mock_executor, base_state
    ):
        """Test that 'no tasks available' path does NOT return tasks_built."""
        # Empty task proposals and no successfully built tasks
        state_no_tasks = {
            **base_state,
            "task_proposals": [],
            "tasks_built": [],  # Empty, already accumulated by reducer
        }

        result = await workflow_assembly_node(
            state_no_tasks, mock_executor, callback=None
        )

        # CORRECT: tasks_built should NOT be in return value
        assert "tasks_built" not in result
        assert (
            result["workflow_error"]
            == "No tasks available for workflow assembly - all task builds failed"
        )

    @pytest.mark.asyncio
    async def test_success_path_does_not_return_tasks_built(
        self, mock_executor, base_state
    ):
        """Test that successful workflow assembly does NOT return tasks_built."""
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": '{"workflow_id": "wf-123", "composition": ["task_one", "task_two"]}'
                },
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=900,
                    num_turns=5,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        state_with_workspace = {**base_state, "workspace": mock_workspace}

        result = await workflow_assembly_node(
            state_with_workspace, mock_executor, callback=None
        )

        # CORRECT: tasks_built should NOT be in return value
        assert "tasks_built" not in result

        # Other fields should be present
        assert result["workflow_id"] == "wf-123"
        assert result["workflow_composition"] == ["task_one", "task_two"]

        # Metrics should be returned (as a list for reducer to accumulate)
        assert "metrics" in result
        assert isinstance(result["metrics"], list)
        assert len(result["metrics"]) == 1  # Just this stage's metrics

    @pytest.mark.asyncio
    async def test_agent_error_does_not_return_tasks_built(
        self, mock_executor, base_state
    ):
        """Test that agent error path does NOT return tasks_built."""
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": '{"error": "Agent failed to compose workflow"}'
                },
                StageExecutionMetrics(
                    duration_ms=500,
                    duration_api_ms=400,
                    num_turns=2,
                    total_cost_usd=0.01,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        state_with_workspace = {**base_state, "workspace": mock_workspace}

        result = await workflow_assembly_node(
            state_with_workspace, mock_executor, callback=None
        )

        # CORRECT: tasks_built should NOT be in return value
        assert "tasks_built" not in result

        # Error should be present
        assert result["workflow_error"] == "Agent failed to compose workflow"
        assert result["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_exception_does_not_return_tasks_built(
        self, mock_executor, base_state
    ):
        """Test that exception path does NOT return tasks_built."""
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        state_with_workspace = {**base_state, "workspace": mock_workspace}

        result = await workflow_assembly_node(
            state_with_workspace, mock_executor, callback=None
        )

        # CORRECT: tasks_built should NOT be in return value
        assert "tasks_built" not in result

        # Error should be captured
        assert "Unexpected error" in result["workflow_error"]
        assert result["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_metrics_returned_as_list_for_reducer(
        self, mock_executor, base_state
    ):
        """Test that metrics are returned as a list (not accumulated) for reducer."""
        mock_workspace = MagicMock()
        stage_metrics = StageExecutionMetrics(
            duration_ms=1000,
            duration_api_ms=900,
            num_turns=5,
            total_cost_usd=0.05,
            usage={},
            tool_calls=[],
        )
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": '{"workflow_id": "wf-123", "composition": ["task_one"]}'
                },
                stage_metrics,
            )
        )

        # State already has metrics from previous stages (accumulated by reducer)
        state_with_metrics = {
            **base_state,
            "workspace": mock_workspace,
            "metrics": [
                {"duration_ms": 100},  # From stage 1
                {"duration_ms": 200},  # From stage 2
            ],
        }

        result = await workflow_assembly_node(
            state_with_metrics, mock_executor, callback=None
        )

        # Metrics should be a list with just THIS stage's metrics
        # The reducer will add it to the accumulated list
        assert "metrics" in result
        assert isinstance(result["metrics"], list)
        assert len(result["metrics"]) == 1  # Just this stage
        assert result["metrics"][0].duration_ms == 1000


@pytest.mark.asyncio
async def test_correct_pattern_explanation():
    """Documentation test explaining the correct LangGraph pattern.

    This is not a real test, but documentation of how the pattern works:

    1. Parallel nodes (task_building_node) return:
       {"tasks_built": [single_result]}

    2. LangGraph reducer (operator.add) accumulates:
       Initial: []
       After task 1: [] + [result1] = [result1]
       After task 2: [result1] + [result2] = [result1, result2]
       After task 3: [result1, result2] + [result3] = [result1, result2, result3]

    3. Aggregator node (workflow_assembly) receives state with:
       state["tasks_built"] = [result1, result2, result3]

    4. Aggregator returns OTHER fields but NOT tasks_built:
       {"workflow_id": "wf-123", "workflow_composition": [...]}
       # tasks_built is already in state, don't return it!

    5. Final state has tasks_built from reducer accumulation:
       state["tasks_built"] = [result1, result2, result3]  ✅ CORRECT

    WRONG PATTERN (causes duplication):
    - Aggregator returns: {"tasks_built": state.get("tasks_built", [])}
    - Reducer adds: [r1, r2, r3] + [r1, r2, r3] = [r1, r2, r3, r1, r2, r3]  ❌ WRONG
    """
    pass  # This is just documentation
