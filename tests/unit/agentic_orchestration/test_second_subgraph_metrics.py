"""Unit tests for second subgraph metrics collection.

Tests verify that metrics from Task Building and Workflow Assembly
are properly collected and combined in the final result.

Related to LangGraph removal: These tests ensure the asyncio.gather() based
implementation correctly propagates metrics through all stages.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from analysi.agentic_orchestration.observability import StageExecutionMetrics
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph import (
    run_parallel_task_building,
    run_second_subgraph,
    run_workflow_assembly_independent,
)
from analysi.models.auth import SYSTEM_USER_ID


@pytest.fixture
def mock_executor():
    """Create mock executor for testing."""
    executor = Mock(spec=AgentOrchestrationExecutor)
    executor.isolated_project_dir = None
    return executor


@pytest.fixture
def sample_alert():
    """Sample alert for testing."""
    return {
        "id": "test-alert-001",
        "title": "Test Alert",
        "severity": "high",
        "rule_name": "test_rule",
        "triggering_event_time": "2024-01-15T10:30:00Z",
        "raw_alert": {"source": "test"},
    }


@pytest.fixture
def task_building_metrics():
    """Sample metrics from Task Building stage."""
    return StageExecutionMetrics(
        duration_ms=1000,
        duration_api_ms=800,
        num_turns=5,
        total_cost_usd=0.05,
        usage={"input_tokens": 1000, "output_tokens": 500},
        tool_calls=["mcp__analysi__create_task"],
    )


@pytest.fixture
def workflow_assembly_metrics():
    """Sample metrics from Workflow Assembly stage."""
    return StageExecutionMetrics(
        duration_ms=500,
        duration_api_ms=400,
        num_turns=3,
        total_cost_usd=0.02,
        usage={"input_tokens": 500, "output_tokens": 200},
        tool_calls=["mcp__analysi__compose_workflow"],
    )


class TestWorkflowAssemblyIndependentMetrics:
    """Test that run_workflow_assembly_independent properly returns metrics."""

    @pytest.mark.asyncio
    async def test_returns_metrics_from_workflow_assembly_node(
        self, mock_executor, sample_alert, workflow_assembly_metrics
    ):
        """Verify metrics from workflow_assembly_node are included in return value."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.workflow_assembly_node"
        ) as mock_assembly_node:
            mock_assembly_node.return_value = {
                "workflow_id": "wf-123",
                "workflow_composition": ["task1", "task2"],
                "workflow_error": None,
                "metrics": [workflow_assembly_metrics],
            }

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.AgentWorkspace"
            ) as mock_workspace_cls:
                mock_workspace = MagicMock()
                mock_workspace.work_dir = "/tmp/test-workspace"
                mock_workspace.cleanup = Mock()
                mock_workspace_cls.return_value = mock_workspace

                result = await run_workflow_assembly_independent(
                    task_proposals=[
                        {
                            "name": "Task 1",
                            "designation": "existing",
                            "cy_name": "task1",
                        }
                    ],
                    tasks_built=[],
                    alert=sample_alert,
                    runbook="# Test Runbook",
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                    created_by=str(SYSTEM_USER_ID),
                    executor=mock_executor,
                )

                # Key assertion: metrics are included in return value
                assert "metrics" in result
                assert len(result["metrics"]) == 1
                assert result["metrics"][0].duration_ms == 500
                assert result["metrics"][0].total_cost_usd == 0.02

    @pytest.mark.asyncio
    async def test_returns_empty_metrics_on_exception(
        self, mock_executor, sample_alert
    ):
        """Verify empty metrics list returned when exception occurs."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.workflow_assembly_node"
        ) as mock_assembly_node:
            mock_assembly_node.side_effect = RuntimeError("Unexpected error")

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.AgentWorkspace"
            ) as mock_workspace_cls:
                mock_workspace = MagicMock()
                mock_workspace.work_dir = "/tmp/test-workspace"
                mock_workspace.cleanup = Mock()
                mock_workspace_cls.return_value = mock_workspace

                result = await run_workflow_assembly_independent(
                    task_proposals=[],
                    tasks_built=[],
                    alert=sample_alert,
                    runbook="# Test Runbook",
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                    created_by=str(SYSTEM_USER_ID),
                    executor=mock_executor,
                )

                # Should have empty metrics on exception
                assert "metrics" in result
                assert result["metrics"] == []
                assert "Unexpected error" in result["workflow_error"]


class TestSecondSubgraphMetricsCombination:
    """Test that run_second_subgraph combines Task Building and Workflow Assembly metrics."""

    @pytest.mark.asyncio
    async def test_combines_task_building_and_workflow_assembly_metrics(
        self,
        mock_executor,
        sample_alert,
        task_building_metrics,
        workflow_assembly_metrics,
    ):
        """Verify final result contains metrics from both stages."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_parallel_task_building"
        ) as mock_task_building:
            # Task Building returns 2 task results with 2 metrics
            mock_task_building.return_value = (
                [
                    {"proposal_name": "Task A", "success": True, "cy_name": "task_a"},
                    {"proposal_name": "Task B", "success": True, "cy_name": "task_b"},
                ],
                [
                    task_building_metrics,
                    task_building_metrics,
                ],  # 2 metrics from 2 tasks
            )

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_workflow_assembly_independent"
            ) as mock_wf_assembly:
                # Workflow Assembly returns workflow result with 1 metric
                mock_wf_assembly.return_value = {
                    "workflow_id": "wf-123",
                    "workflow_composition": ["task_a", "task_b"],
                    "workflow_error": None,
                    "workspace_path": "/tmp/test",
                    "metrics": [workflow_assembly_metrics],
                }

                result = await run_second_subgraph(
                    task_proposals=[
                        {"name": "Task A", "designation": "new"},
                        {"name": "Task B", "designation": "new"},
                    ],
                    runbook="# Test Runbook",
                    alert=sample_alert,
                    executor=mock_executor,
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                )

                # Key assertion: metrics from both stages are combined
                assert "metrics" in result
                assert (
                    len(result["metrics"]) == 3
                )  # 2 from Task Building + 1 from Workflow Assembly

                # Verify Task Building metrics (first 2)
                assert result["metrics"][0].duration_ms == 1000
                assert result["metrics"][1].duration_ms == 1000

                # Verify Workflow Assembly metrics (last 1)
                assert result["metrics"][2].duration_ms == 500

    @pytest.mark.asyncio
    async def test_handles_empty_workflow_assembly_metrics(
        self, mock_executor, sample_alert, task_building_metrics
    ):
        """Verify graceful handling when Workflow Assembly returns no metrics."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_parallel_task_building"
        ) as mock_task_building:
            mock_task_building.return_value = (
                [{"proposal_name": "Task A", "success": True, "cy_name": "task_a"}],
                [task_building_metrics],
            )

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_workflow_assembly_independent"
            ) as mock_wf_assembly:
                # Workflow Assembly returns no metrics (edge case)
                mock_wf_assembly.return_value = {
                    "workflow_id": "wf-123",
                    "workflow_composition": ["task_a"],
                    "workflow_error": None,
                    "workspace_path": "/tmp/test",
                    # No metrics key at all
                }

                result = await run_second_subgraph(
                    task_proposals=[{"name": "Task A", "designation": "new"}],
                    runbook="# Test Runbook",
                    alert=sample_alert,
                    executor=mock_executor,
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                )

                # Should still have Task Building metrics
                assert "metrics" in result
                assert len(result["metrics"]) == 1
                assert result["metrics"][0].duration_ms == 1000

    @pytest.mark.asyncio
    async def test_handles_empty_task_building_metrics(
        self, mock_executor, sample_alert, workflow_assembly_metrics
    ):
        """Verify graceful handling when Task Building returns no metrics (all existing tasks)."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_parallel_task_building"
        ) as mock_task_building:
            # No tasks built (all existing), so no metrics
            mock_task_building.return_value = ([], [])

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_workflow_assembly_independent"
            ) as mock_wf_assembly:
                mock_wf_assembly.return_value = {
                    "workflow_id": "wf-123",
                    "workflow_composition": ["existing_task"],
                    "workflow_error": None,
                    "workspace_path": "/tmp/test",
                    "metrics": [workflow_assembly_metrics],
                }

                result = await run_second_subgraph(
                    task_proposals=[
                        {
                            "name": "Existing Task",
                            "designation": "existing",
                            "cy_name": "existing_task",
                        }
                    ],
                    runbook="# Test Runbook",
                    alert=sample_alert,
                    executor=mock_executor,
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                )

                # Should have only Workflow Assembly metrics
                assert "metrics" in result
                assert len(result["metrics"]) == 1
                assert result["metrics"][0].duration_ms == 500

    @pytest.mark.asyncio
    async def test_metrics_can_calculate_total_cost(
        self,
        mock_executor,
        sample_alert,
        task_building_metrics,
        workflow_assembly_metrics,
    ):
        """Verify combined metrics can be used for cost calculation."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_parallel_task_building"
        ) as mock_task_building:
            mock_task_building.return_value = (
                [{"proposal_name": "Task", "success": True, "cy_name": "task"}],
                [task_building_metrics],  # $0.05
            )

            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.run_workflow_assembly_independent"
            ) as mock_wf_assembly:
                mock_wf_assembly.return_value = {
                    "workflow_id": "wf-123",
                    "workflow_composition": ["task"],
                    "workflow_error": None,
                    "workspace_path": "/tmp/test",
                    "metrics": [workflow_assembly_metrics],  # $0.02
                }

                result = await run_second_subgraph(
                    task_proposals=[{"name": "Task", "designation": "new"}],
                    runbook="# Test Runbook",
                    alert=sample_alert,
                    executor=mock_executor,
                    run_id="test-run-id",
                    tenant_id="test-tenant",
                )

                # Calculate total cost from all metrics
                total_cost = sum(m.total_cost_usd for m in result["metrics"])
                assert total_cost == pytest.approx(0.07)  # $0.05 + $0.02 = $0.07

                # Calculate total duration
                total_duration = sum(m.duration_ms for m in result["metrics"])
                assert total_duration == 1500  # 1000 + 500 = 1500ms


class TestCallbackMetricsAggregation:
    """Test that callback receives properly aggregated metrics from parallel task building."""

    @pytest.fixture
    def sample_metrics(self):
        """Create sample metrics for aggregation testing."""
        from analysi.agentic_orchestration.observability import ToolCallTrace

        return [
            StageExecutionMetrics(
                duration_ms=1000,
                duration_api_ms=800,
                num_turns=5,
                total_cost_usd=0.50,
                usage={"total_input_tokens": 1000, "total_output_tokens": 500},
                tool_calls=[
                    ToolCallTrace(
                        tool_name="mcp__analysi__compile_script",
                        input_args={"script": "test"},
                        result="ok",
                        is_error=False,
                    )
                ],
            ),
            StageExecutionMetrics(
                duration_ms=2000,
                duration_api_ms=1500,
                num_turns=10,
                total_cost_usd=1.00,
                usage={"total_input_tokens": 2000, "total_output_tokens": 1000},
                tool_calls=[
                    ToolCallTrace(
                        tool_name="mcp__analysi__create_task",
                        input_args={"name": "test"},
                        result="ok",
                        is_error=False,
                    ),
                    ToolCallTrace(
                        tool_name="mcp__analysi__run_script",
                        input_args={"script": "test"},
                        result="ok",
                        is_error=False,
                    ),
                ],
            ),
        ]

    @pytest.mark.asyncio
    async def test_callback_receives_aggregated_metrics(
        self, mock_executor, sample_alert, sample_metrics
    ):
        """Verify callback.on_stage_complete receives properly aggregated metrics."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )

        mock_callback = AsyncMock()

        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.asyncio.gather",
            new_callable=AsyncMock,
        ) as mock_gather:
            # Simulate asyncio.gather returning successful task results with metrics
            mock_gather.return_value = [
                (
                    {
                        "proposal_name": "Task A",
                        "success": True,
                        "cy_name": "task_a",
                        "task_id": "id-1",
                        "designation": "new",
                    },
                    [sample_metrics[0]],
                ),
                (
                    {
                        "proposal_name": "Task B",
                        "success": True,
                        "cy_name": "task_b",
                        "task_id": "id-2",
                        "designation": "new",
                    },
                    [sample_metrics[1]],
                ),
            ]

            await run_parallel_task_building(
                task_proposals=[
                    {"name": "Task A", "designation": "new"},
                    {"name": "Task B", "designation": "new"},
                ],
                runbook="# Test Runbook",
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-id",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
                callback=mock_callback,
            )

            # Verify callback.on_stage_complete was called
            mock_callback.on_stage_complete.assert_called_once()

            # Get the aggregated metrics from the call
            call_args = mock_callback.on_stage_complete.call_args
            stage, result_data, aggregated_metrics = call_args[0]

            # Verify stage is correct
            assert stage == WorkflowGenerationStage.TASK_BUILDING

            # Verify result data
            assert result_data["tasks_count"] == 2
            assert result_data["successful"] == 2
            assert result_data["failed"] == 0

            # Verify ALL required fields are present in aggregated metrics
            assert aggregated_metrics.duration_ms == 3000  # 1000 + 2000
            assert aggregated_metrics.duration_api_ms == 2300  # 800 + 1500
            assert aggregated_metrics.num_turns == 15  # 5 + 10
            assert aggregated_metrics.total_cost_usd == 1.50  # 0.50 + 1.00
            assert aggregated_metrics.usage["total_input_tokens"] == 3000  # 1000 + 2000
            assert aggregated_metrics.usage["total_output_tokens"] == 1500  # 500 + 1000
            assert len(aggregated_metrics.tool_calls) == 3  # 1 + 2 tool calls

    @pytest.mark.asyncio
    async def test_no_callback_when_no_tasks_to_build(
        self, mock_executor, sample_alert
    ):
        """Verify callback is NOT called when there are no tasks to build.

        When task_proposals is empty (all existing tasks), the function
        returns early without starting or completing the stage.
        """
        mock_callback = AsyncMock()

        tasks_built, metrics = await run_parallel_task_building(
            task_proposals=[],  # No tasks to build (all existing)
            runbook="# Test Runbook",
            alert=sample_alert,
            executor=mock_executor,
            run_id="test-run-id",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            callback=mock_callback,
        )

        # Verify callback was NOT called (no stage to start/complete)
        mock_callback.on_stage_start.assert_not_called()
        mock_callback.on_stage_complete.assert_not_called()

        # Verify empty results
        assert tasks_built == []
        assert metrics == []

    @pytest.mark.asyncio
    async def test_callback_receives_empty_metrics_when_all_tasks_fail(
        self, mock_executor, sample_alert
    ):
        """Verify callback receives zero values when all task builds fail (no metrics)."""
        mock_callback = AsyncMock()

        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.asyncio.gather",
            new_callable=AsyncMock,
        ) as mock_gather:
            # Simulate all tasks failing (return exceptions)
            mock_gather.return_value = [
                RuntimeError("Task A failed"),
                RuntimeError("Task B failed"),
            ]

            await run_parallel_task_building(
                task_proposals=[
                    {"name": "Task A", "designation": "new"},
                    {"name": "Task B", "designation": "new"},
                ],
                runbook="# Test Runbook",
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-id",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
                callback=mock_callback,
            )

            # Verify callback.on_stage_complete was called
            mock_callback.on_stage_complete.assert_called_once()

            # Get the aggregated metrics from the call
            call_args = mock_callback.on_stage_complete.call_args
            _, result_data, aggregated_metrics = call_args[0]

            # Verify result data shows failures
            assert result_data["tasks_count"] == 2
            assert result_data["successful"] == 0
            assert result_data["failed"] == 2

            # Verify zero values when no metrics (all failed)
            assert aggregated_metrics.duration_ms == 0
            assert aggregated_metrics.duration_api_ms == 0
            assert aggregated_metrics.num_turns == 0
            assert aggregated_metrics.total_cost_usd == 0.0
            assert aggregated_metrics.usage["total_input_tokens"] == 0
            assert aggregated_metrics.usage["total_output_tokens"] == 0
            assert aggregated_metrics.tool_calls == []


class TestCancelledErrorHandling:
    """Test handling of CancelledError in parallel task building.

    In Python 3.8+, CancelledError is a BaseException, NOT an Exception.
    asyncio.gather(return_exceptions=True) returns CancelledError in the results,
    and we must handle it gracefully instead of trying to unpack it as a tuple.

    Bug reproduction: When a task is cancelled (e.g., due to SDK cancel scope issues),
    the old code checked `isinstance(result, Exception)` which returned False for
    CancelledError, causing a crash when trying to unpack it as a tuple.
    """

    @pytest.mark.asyncio
    async def test_handles_cancelled_error_gracefully(
        self, mock_executor, sample_alert
    ):
        """Test that CancelledError from asyncio.gather is handled gracefully.

        BUG: CancelledError is a BaseException, not Exception.
        The check `isinstance(result, Exception)` returns False for CancelledError,
        so the code tries to unpack it as a tuple and crashes with:
        TypeError: cannot unpack non-iterable CancelledError object
        """
        # Mock asyncio.gather directly to simulate what happens when tasks return
        # mixed results including CancelledError
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.asyncio.gather",
            new_callable=AsyncMock,
        ) as mock_gather:
            # Simulate asyncio.gather returning mixed results:
            # - First task returns a valid tuple (success)
            # - Second task returns CancelledError (should be handled, not crash)
            mock_gather.return_value = [
                (
                    {
                        "proposal_name": "Task A",
                        "success": True,
                        "cy_name": "task_a",
                        "task_id": "id-1",
                        "designation": "new",
                    },
                    [],  # Empty metrics
                ),
                asyncio.CancelledError("Task was cancelled"),
            ]

            # This should NOT crash - it should handle the CancelledError gracefully
            tasks_built, metrics = await run_parallel_task_building(
                task_proposals=[
                    {"name": "Task A", "designation": "new"},
                    {"name": "Task B", "designation": "new"},
                ],
                runbook="# Test Runbook",
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-id",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
            )

            # Should have 2 results - one success, one failure
            assert len(tasks_built) == 2

            # First task succeeded
            assert tasks_built[0]["success"] is True
            assert tasks_built[0]["cy_name"] == "task_a"

            # Second task failed due to cancellation
            assert tasks_built[1]["success"] is False
            assert "CancelledError" in tasks_built[1]["error"]

    @pytest.mark.asyncio
    async def test_handles_keyboard_interrupt_gracefully(
        self, mock_executor, sample_alert
    ):
        """Test that KeyboardInterrupt (another BaseException) is handled gracefully."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.asyncio.gather",
            new_callable=AsyncMock,
        ) as mock_gather:
            # Simulate KeyboardInterrupt returned by asyncio.gather
            mock_gather.return_value = [
                KeyboardInterrupt("User interrupted"),
            ]

            # This should NOT crash
            tasks_built, metrics = await run_parallel_task_building(
                task_proposals=[{"name": "Task A", "designation": "new"}],
                runbook="# Test Runbook",
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-id",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
            )

            # Should have 1 result - failed due to KeyboardInterrupt
            assert len(tasks_built) == 1
            assert tasks_built[0]["success"] is False
            assert "KeyboardInterrupt" in tasks_built[0]["error"]

    @pytest.mark.asyncio
    async def test_handles_unexpected_result_type_gracefully(
        self, mock_executor, sample_alert
    ):
        """Test that unexpected result types (not tuple, not exception) are handled gracefully."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.asyncio.gather",
            new_callable=AsyncMock,
        ) as mock_gather:
            # Simulate an unexpected result type (e.g., None, string, or wrong tuple size)
            mock_gather.return_value = [
                None,  # Unexpected: None instead of tuple
                "unexpected string",  # Unexpected: string instead of tuple
                (1, 2, 3),  # Unexpected: tuple with wrong length
            ]

            # This should NOT crash
            tasks_built, metrics = await run_parallel_task_building(
                task_proposals=[
                    {"name": "Task A", "designation": "new"},
                    {"name": "Task B", "designation": "new"},
                    {"name": "Task C", "designation": "new"},
                ],
                runbook="# Test Runbook",
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-id",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
            )

            # Should have 3 results - all failed due to unexpected types
            assert len(tasks_built) == 3
            for task in tasks_built:
                assert task["success"] is False
                assert "Unexpected result type" in task["error"]


class TestBaseExceptionRecovery:
    """Test recovery when BaseException (CancelledError) occurs after task was created.

    The Claude Agent SDK can raise CancelledError during cleanup even after the task
    was successfully created. We need to check the database to see if the task exists
    before reporting failure.

    Bug reproduced: Task was created successfully ($1.25 cost, 24 tool calls) but
    CancelledError during SDK cleanup caused the whole task to be marked as failed.
    """

    @pytest.mark.asyncio
    async def test_recovers_from_cancelled_error_when_task_was_created(
        self, mock_executor, sample_alert
    ):
        """Test that we recover when task was created but CancelledError during cleanup."""
        from analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph import (
            _build_single_task_with_recovery,
        )

        # Mock workspace
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.AgentWorkspace"
        ):
            # Mock task_building_node to raise CancelledError (simulating SDK cleanup failure)
            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.task_building_node"
            ) as mock_task_node:
                mock_task_node.side_effect = asyncio.CancelledError("SDK cleanup error")

                # Mock _check_task_exists in the task_building module (where it's imported from)
                with patch(
                    "analysi.agentic_orchestration.nodes.task_building._check_task_exists"
                ) as mock_check:
                    # Make it an async function that returns the mocked task
                    async def mock_check_task_exists(*args, **kwargs):
                        return {
                            "id": "task-123",
                            "cy_name": "test_task",
                            "name": "Test Task",
                        }

                    mock_check.side_effect = mock_check_task_exists

                    proposal = {
                        "name": "Test Task",
                        "designation": "new",
                    }

                    result, metrics = await _build_single_task_with_recovery(
                        proposal=proposal,
                        alert=sample_alert,
                        runbook="# Test Runbook",
                        run_id="test-run",
                        tenant_id="test-tenant",
                        created_by=str(SYSTEM_USER_ID),
                        executor=mock_executor,
                        callback=None,
                        task_index=0,
                    )

                    # Should recover and report success
                    assert result["success"] is True
                    assert result["task_id"] == "task-123"
                    assert result["cy_name"] == "test_task"
                    assert result.get("recovered") is True

    @pytest.mark.asyncio
    async def test_reports_failure_when_task_not_created_and_cancelled(
        self, mock_executor, sample_alert
    ):
        """Test that we report failure when task was NOT created and CancelledError occurred."""
        from analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph import (
            _build_single_task_with_recovery,
        )

        # Mock workspace
        with patch(
            "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.AgentWorkspace"
        ):
            # Mock task_building_node to raise CancelledError
            with patch(
                "analysi.agentic_orchestration.subgraphs.second_subgraph_no_langgraph.task_building_node"
            ) as mock_task_node:
                mock_task_node.side_effect = asyncio.CancelledError("SDK cleanup error")

                # Mock _check_task_exists to return that task was NOT created
                with patch(
                    "analysi.agentic_orchestration.nodes.task_building._check_task_exists"
                ) as mock_check:
                    # Make it an async function that returns None (task not found)
                    async def mock_check_task_not_found(*args, **kwargs):
                        return None

                    mock_check.side_effect = mock_check_task_not_found

                    proposal = {
                        "name": "Test Task",
                        "designation": "new",
                    }

                    result, metrics = await _build_single_task_with_recovery(
                        proposal=proposal,
                        alert=sample_alert,
                        runbook="# Test Runbook",
                        run_id="test-run",
                        tenant_id="test-tenant",
                        created_by=str(SYSTEM_USER_ID),
                        executor=mock_executor,
                        callback=None,
                        task_index=0,
                    )

                    # Should report failure
                    assert result["success"] is False
                    assert result["task_id"] is None
                    assert "CancelledError" in result["error"]

    @pytest.mark.asyncio
    async def test_recovery_import_works(self):
        """Test that _check_task_exists can be imported from task_building module."""
        # This import should work without circular import issues
        from analysi.agentic_orchestration.nodes.task_building import (
            _check_task_exists,
        )

        assert callable(_check_task_exists)
