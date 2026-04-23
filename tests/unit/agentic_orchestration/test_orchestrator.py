"""Unit tests for full orchestration (NAS Alert → Workflow pipeline)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from analysi.agentic_orchestration import (
    AgentOrchestrationExecutor,
    StageExecutionMetrics,
    run_full_orchestration,
)
from analysi.schemas.alert import AlertBase, AlertSeverity


class TestRunFullOrchestration:
    """Tests for run_full_orchestration function."""

    @pytest.fixture
    def sample_alert(self):
        """Create sample NAS alert."""
        return AlertBase(
            title="Test Alert",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.HIGH,
            raw_alert='{"test": "data"}',
        )

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        return AsyncMock(spec=AgentOrchestrationExecutor)

    @pytest.fixture
    def first_subgraph_success(self):
        """Mock successful first subgraph result."""
        return {
            "runbook": "# Investigation Runbook\n\nSteps here",
            "task_proposals": [
                {"name": "Task 1", "category": "new"},
                {"name": "Task 2", "category": "existing", "cy_name": "existing_task"},
            ],
            "metrics": [
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=2,
                    total_cost_usd=0.02,
                    usage={},
                    tool_calls=[],
                ),
                StageExecutionMetrics(
                    duration_ms=1500,
                    duration_api_ms=1200,
                    num_turns=3,
                    total_cost_usd=0.03,
                    usage={},
                    tool_calls=[],
                ),
            ],
            "run_id": "test-run-123",  # Added for orchestrator pass-through
            "error": None,
        }

    @pytest.fixture
    def second_subgraph_success(self):
        """Mock successful second subgraph result."""
        return {
            "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
            "workflow_composition": ["existing_task", "new_task_1"],
            "tasks_built": [
                {"success": True, "cy_name": "new_task_1", "task_id": "task-uuid-1"}
            ],
            "metrics": [
                StageExecutionMetrics(
                    duration_ms=2000,
                    duration_api_ms=1800,
                    num_turns=5,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=900,
                    num_turns=2,
                    total_cost_usd=0.02,
                    usage={},
                    tool_calls=[],
                ),
            ],
            "workflow_error": None,
        }

    @pytest.mark.asyncio
    async def test_successful_orchestration(
        self,
        sample_alert,
        mock_executor,
        first_subgraph_success,
        second_subgraph_success,
    ):
        """Test successful end-to-end orchestration."""
        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_subgraph_success
            mock_second.return_value = second_subgraph_success

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify first subgraph was called
            mock_first.assert_called_once()
            call_args = mock_first.call_args
            assert call_args[0][0]["title"] == "Test Alert"  # alert_dict
            assert call_args[0][1] == mock_executor

            # Verify second subgraph was called with first's output
            mock_second.assert_called_once()
            call_kwargs = mock_second.call_args.kwargs
            assert (
                call_kwargs["task_proposals"]
                == first_subgraph_success["task_proposals"]
            )
            assert call_kwargs["runbook"] == first_subgraph_success["runbook"]
            assert call_kwargs["tenant_id"] == "test-tenant"

            # Verify result structure
            assert result["workflow_id"] == "550e8400-e29b-41d4-a716-446655440000"
            assert result["workflow_composition"] == ["existing_task", "new_task_1"]
            assert len(result["tasks_built"]) == 1
            assert result["runbook"] == "# Investigation Runbook\n\nSteps here"
            assert result["error"] is None

            # Verify metrics aggregation (2 from first + 2 from second = 4)
            assert len(result["metrics"]) == 4
            total_cost = sum(m.total_cost_usd for m in result["metrics"])
            assert total_cost == 0.12  # 0.02 + 0.03 + 0.05 + 0.02

    @pytest.mark.asyncio
    async def test_first_subgraph_error(
        self,
        sample_alert,
        mock_executor,
    ):
        """Test error handling when first subgraph fails."""
        first_error_result = {
            "runbook": "",
            "task_proposals": [],
            "metrics": [
                StageExecutionMetrics(
                    duration_ms=500,
                    duration_api_ms=400,
                    num_turns=1,
                    total_cost_usd=0.01,
                    usage={},
                    tool_calls=[],
                )
            ],
            "error": "Failed to generate runbook",
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_error_result

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify first subgraph was called
            mock_first.assert_called_once()

            # Verify second subgraph was NOT called (error in first)
            mock_second.assert_not_called()

            # Verify error propagation
            assert result["error"] == "Failed to generate runbook"
            assert result["workflow_id"] is None
            assert result["workflow_composition"] == []
            assert result["tasks_built"] == []
            assert len(result["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_second_subgraph_error(
        self,
        sample_alert,
        mock_executor,
        first_subgraph_success,
    ):
        """Test error handling when second subgraph fails."""
        second_error_result = {
            "workflow_id": None,
            "workflow_composition": [],
            "tasks_built": [],
            "metrics": [
                StageExecutionMetrics(
                    duration_ms=500,
                    duration_api_ms=400,
                    num_turns=1,
                    total_cost_usd=0.01,
                    usage={},
                    tool_calls=[],
                )
            ],
            "workflow_error": "Failed to assemble workflow",
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_subgraph_success
            mock_second.return_value = second_error_result

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify both subgraphs were called
            mock_first.assert_called_once()
            mock_second.assert_called_once()

            # Verify error from second subgraph
            assert result["error"] == "Failed to assemble workflow"
            assert result["workflow_id"] is None
            assert result["workflow_composition"] == []

            # Verify runbook from first subgraph is preserved
            assert result["runbook"] == "# Investigation Runbook\n\nSteps here"

            # Verify metrics aggregation (2 from first + 1 from second = 3)
            assert len(result["metrics"]) == 3

    @pytest.mark.asyncio
    async def test_alert_conversion_to_dict(
        self,
        sample_alert,
        mock_executor,
        first_subgraph_success,
        second_subgraph_success,
    ):
        """Test that AlertBase is properly converted to dict for subgraphs."""
        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_subgraph_success
            mock_second.return_value = second_subgraph_success

            await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify first subgraph receives dict, not AlertBase
            first_call_args = mock_first.call_args[0]
            alert_arg = first_call_args[0]
            assert isinstance(alert_arg, dict)
            assert alert_arg["title"] == "Test Alert"
            assert alert_arg["severity"] == "high"

            # Verify second subgraph receives same dict
            second_call_kwargs = mock_second.call_args.kwargs
            alert_arg2 = second_call_kwargs["alert"]
            assert isinstance(alert_arg2, dict)
            assert alert_arg2["title"] == "Test Alert"

    @pytest.mark.asyncio
    async def test_data_flow_from_first_to_second_subgraph(
        self,
        sample_alert,
        mock_executor,
    ):
        """Test critical data flows from first subgraph to second subgraph."""
        # First subgraph produces specific task proposals and runbook
        first_result = {
            "runbook": "# Detailed Investigation Runbook\n\nStep 1: Check IP reputation",
            "task_proposals": [
                {
                    "name": "IP Reputation Check",
                    "category": "new",
                    "integration_tools": ["virustotal::ip_reputation"],
                },
                {
                    "name": "User Activity Search",
                    "category": "modify",
                    "existing_cy_name": "splunk_user_search",
                },
                {
                    "name": "Existing Task",
                    "category": "existing",
                    "cy_name": "existing_check",
                },
            ],
            "metrics": [],
            "run_id": "test-run-123",
            "error": None,
        }

        second_result = {
            "workflow_id": "workflow-123",
            "workflow_composition": [
                "existing_check",
                "new_ip_check",
                "modified_user_search",
            ],
            "tasks_built": [],
            "metrics": [],
            "workflow_error": None,
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_result
            mock_second.return_value = second_result

            await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify second subgraph receives EXACT task_proposals from first
            second_call = mock_second.call_args.kwargs
            assert second_call["task_proposals"] == first_result["task_proposals"]
            assert len(second_call["task_proposals"]) == 3

            # Verify second subgraph receives EXACT runbook from first
            assert (
                second_call["runbook"]
                == "# Detailed Investigation Runbook\n\nStep 1: Check IP reputation"
            )

    @pytest.mark.asyncio
    async def test_empty_task_proposals_from_first_subgraph(
        self,
        sample_alert,
        mock_executor,
    ):
        """Test handling when first subgraph produces no task proposals."""
        first_result = {
            "runbook": "# Simple Runbook",
            "task_proposals": [],  # No proposals!
            "metrics": [],
            "run_id": "test-run-123",
            "error": None,
        }

        second_result = {
            "workflow_id": None,
            "workflow_composition": [],
            "tasks_built": [],
            "metrics": [],
            "workflow_error": "No tasks to build",
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_result
            mock_second.return_value = second_result

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify second subgraph still called (it handles empty proposals)
            mock_second.assert_called_once()
            assert mock_second.call_args.kwargs["task_proposals"] == []

            # Verify error from second subgraph is propagated
            assert result["error"] == "No tasks to build"
            assert result["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_large_number_of_task_proposals(
        self,
        sample_alert,
        mock_executor,
    ):
        """Test handling when first subgraph produces many task proposals (parallel execution)."""
        # First subgraph produces 10 task proposals
        task_proposals = [
            {
                "name": f"Task {i}",
                "category": "new" if i % 2 == 0 else "existing",
                "cy_name": f"task_{i}" if i % 2 == 1 else None,
            }
            for i in range(10)
        ]

        first_result = {
            "runbook": "# Complex Investigation",
            "task_proposals": task_proposals,
            "metrics": [],
            "run_id": "test-run-123",
            "error": None,
        }

        # Second subgraph handles all 10 proposals
        second_result = {
            "workflow_id": "workflow-large",
            "workflow_composition": [f"task_{i}" for i in range(10)],
            "tasks_built": [
                {"success": True, "cy_name": f"task_{i}", "task_id": f"id-{i}"}
                for i in range(5)  # Only 5 built (others existing)
            ],
            "metrics": [],
            "workflow_error": None,
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_result
            mock_second.return_value = second_result

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify all 10 proposals passed to second subgraph
            assert len(mock_second.call_args.kwargs["task_proposals"]) == 10

            # Verify workflow composition has all 10 tasks
            assert len(result["workflow_composition"]) == 10

            # Verify only 5 tasks were built (rest were existing)
            assert len(result["tasks_built"]) == 5

    @pytest.mark.asyncio
    async def test_metrics_accumulation_across_stages(
        self,
        sample_alert,
        mock_executor,
    ):
        """Test that metrics from all 4 stages are properly accumulated."""
        # First subgraph: 2 stages (runbook gen + task proposal)
        first_metrics = [
            StageExecutionMetrics(
                duration_ms=1000,
                duration_api_ms=800,
                num_turns=2,
                total_cost_usd=0.02,
                usage={"input_tokens": 100, "output_tokens": 50},
                tool_calls=[{"name": "tool1"}],
            ),
            StageExecutionMetrics(
                duration_ms=1500,
                duration_api_ms=1200,
                num_turns=3,
                total_cost_usd=0.03,
                usage={"input_tokens": 150, "output_tokens": 75},
                tool_calls=[{"name": "tool2"}],
            ),
        ]

        # Second subgraph: 2 stages (task building + workflow assembly)
        second_metrics = [
            StageExecutionMetrics(
                duration_ms=3000,
                duration_api_ms=2800,
                num_turns=10,
                total_cost_usd=0.10,
                usage={"input_tokens": 500, "output_tokens": 300},
                tool_calls=[{"name": "tool3"}, {"name": "tool4"}],
            ),
            StageExecutionMetrics(
                duration_ms=1000,
                duration_api_ms=900,
                num_turns=2,
                total_cost_usd=0.02,
                usage={"input_tokens": 100, "output_tokens": 50},
                tool_calls=[{"name": "tool5"}],
            ),
        ]

        first_result = {
            "runbook": "# Runbook",
            "task_proposals": [{"name": "Task", "category": "new"}],
            "metrics": first_metrics,
            "run_id": "test-run-123",
            "error": None,
        }

        second_result = {
            "workflow_id": "workflow-123",
            "workflow_composition": ["task"],
            "tasks_built": [],
            "metrics": second_metrics,
            "workflow_error": None,
        }

        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_result
            mock_second.return_value = second_result

            result = await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify all 4 metrics are accumulated
            assert len(result["metrics"]) == 4

            # Verify total cost aggregation
            total_cost = sum(m.total_cost_usd for m in result["metrics"])
            assert total_cost == 0.17  # 0.02 + 0.03 + 0.10 + 0.02

            # Verify total turns
            total_turns = sum(m.num_turns for m in result["metrics"])
            assert total_turns == 17  # 2 + 3 + 10 + 2

            # Verify metrics order (first subgraph's first, then second subgraph's)
            assert result["metrics"][0].num_turns == 2
            assert result["metrics"][1].num_turns == 3
            assert result["metrics"][2].num_turns == 10
            assert result["metrics"][3].num_turns == 2

    @pytest.mark.asyncio
    async def test_tenant_id_propagation(
        self,
        sample_alert,
        mock_executor,
        first_subgraph_success,
        second_subgraph_success,
    ):
        """Test that tenant_id is properly propagated to second subgraph."""
        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_subgraph_success
            mock_second.return_value = second_subgraph_success

            # Use specific tenant_id
            await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="acme-corp-prod",
                run_id="test-run-123",
            )

            # Verify tenant_id passed to second subgraph (first doesn't need it)
            second_call = mock_second.call_args.kwargs
            assert second_call["tenant_id"] == "acme-corp-prod"

    @pytest.mark.asyncio
    async def test_executor_reused_across_subgraphs(
        self,
        sample_alert,
        mock_executor,
        first_subgraph_success,
        second_subgraph_success,
    ):
        """Test that same executor instance is used for both subgraphs."""
        with (
            patch(
                "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
            ) as mock_first,
            patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second,
        ):
            mock_first.return_value = first_subgraph_success
            mock_second.return_value = second_subgraph_success

            await run_full_orchestration(
                alert=sample_alert,
                executor=mock_executor,
                tenant_id="test-tenant",
                run_id="test-run-123",
            )

            # Verify same executor passed to both subgraphs
            first_executor = mock_first.call_args[0][1]
            second_executor = mock_second.call_args.kwargs["executor"]

            assert first_executor is mock_executor
            assert second_executor is mock_executor
            assert first_executor is second_executor  # Same instance


class TestRunOrchestrationWithStages:
    """Tests for run_orchestration_with_stages framework function."""

    @pytest.fixture
    def mock_callback(self):
        """Create mock progress callback."""
        callback = AsyncMock()
        callback.on_stage_start = AsyncMock()
        callback.on_stage_complete = AsyncMock()
        callback.on_stage_error = AsyncMock()
        return callback

    @pytest.fixture
    def initial_state(self):
        """Initial state for orchestration."""
        return {
            "alert": {"id": "test-alert", "title": "Test Alert"},
            "tenant_id": "test-tenant",
            "run_id": "test-run",
        }

    @pytest.mark.asyncio
    async def test_successful_execution_all_stages(self, mock_callback, initial_state):
        """Test successful execution through all 4 stages."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        # Create mock stages
        mock_stages = []
        for stage_enum in [
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            WorkflowGenerationStage.TASK_PROPOSALS,
            WorkflowGenerationStage.TASK_BUILDING,
            WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
        ]:
            mock_stage = AsyncMock()
            mock_stage.stage = stage_enum
            mock_stages.append(mock_stage)

        # Configure stage returns
        mock_stages[0].execute.return_value = {"runbook": "# Test Runbook"}
        mock_stages[1].execute.return_value = {"task_proposals": []}
        mock_stages[2].execute.return_value = {"tasks_built": []}
        mock_stages[3].execute.return_value = {
            "workflow_id": "wf-123",
            "workflow_composition": ["task1"],
        }

        result = await run_orchestration_with_stages(
            stages=mock_stages,
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify all stages were executed
        for stage in mock_stages:
            stage.execute.assert_called_once()

        # Verify result contains all stage outputs
        assert result["runbook"] == "# Test Runbook"
        assert result["task_proposals"] == []
        assert result["tasks_built"] == []
        assert result["workflow_id"] == "wf-123"
        assert result["workflow_composition"] == ["task1"]

        # Verify metrics were collected (4 stages)
        assert len(result["metrics"]) == 4

        # Verify callbacks were invoked
        assert mock_callback.on_stage_start.call_count == 4
        assert mock_callback.on_stage_complete.call_count == 4
        mock_callback.on_stage_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_timing_measurement(self, mock_callback, initial_state):
        """Test that framework measures timing for each stage."""
        import asyncio

        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        # Create a slow stage
        mock_stage = AsyncMock()
        mock_stage.stage = WorkflowGenerationStage.RUNBOOK_GENERATION

        async def slow_execute(state):
            await asyncio.sleep(0.1)  # 100ms
            return {"runbook": "done"}

        mock_stage.execute.side_effect = slow_execute

        result = await run_orchestration_with_stages(
            stages=[mock_stage],
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify timing was measured (should be ~100ms or more)
        assert len(result["metrics"]) == 1
        assert result["metrics"][0].duration_ms >= 90  # Allow some variance

    @pytest.mark.asyncio
    async def test_stage_exception_handling(self, mock_callback, initial_state):
        """Test that stage exceptions are caught and reported."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        # Create stages where second one fails
        mock_stage1 = AsyncMock()
        mock_stage1.stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        mock_stage1.execute.return_value = {"runbook": "ok"}

        mock_stage2 = AsyncMock()
        mock_stage2.stage = WorkflowGenerationStage.TASK_PROPOSALS
        mock_stage2.execute.side_effect = ValueError("Stage failed!")

        mock_stage3 = AsyncMock()
        mock_stage3.stage = WorkflowGenerationStage.TASK_BUILDING

        result = await run_orchestration_with_stages(
            stages=[mock_stage1, mock_stage2, mock_stage3],
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify error was captured
        assert result["error"] == "Stage failed!"

        # Verify stage 1 completed, stage 2 started before error
        mock_stage1.execute.assert_called_once()
        mock_stage2.execute.assert_called_once()

        # Verify stage 3 was NOT executed
        mock_stage3.execute.assert_not_called()

        # Verify error callback was invoked
        mock_callback.on_stage_error.assert_called_once()
        error_call = mock_callback.on_stage_error.call_args
        assert error_call[0][0] == WorkflowGenerationStage.TASK_PROPOSALS
        assert isinstance(error_call[0][1], ValueError)

        # Verify partial metrics were collected (2 stages)
        assert len(result["metrics"]) == 2

    @pytest.mark.asyncio
    async def test_sdk_metrics_extraction(self, mock_callback, initial_state):
        """Test that SDK metrics are extracted from stage output."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )
        from analysi.agentic_orchestration.stages.base import SDK_METRICS_KEY

        mock_stage = AsyncMock()
        mock_stage.stage = WorkflowGenerationStage.RUNBOOK_GENERATION

        # Stage returns SDK metrics
        sdk_metrics = StageExecutionMetrics(
            duration_ms=500,
            duration_api_ms=400,
            num_turns=5,
            total_cost_usd=0.05,
            usage={"total_input_tokens": 1000},
            tool_calls=[{"name": "tool1"}],
        )
        mock_stage.execute.return_value = {
            "runbook": "ok",
            SDK_METRICS_KEY: sdk_metrics,
        }

        result = await run_orchestration_with_stages(
            stages=[mock_stage],
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify SDK metrics were extracted and used
        assert len(result["metrics"]) == 1
        assert result["metrics"][0].total_cost_usd == 0.05
        assert result["metrics"][0].num_turns == 5

        # Verify SDK_METRICS_KEY was removed from state
        assert SDK_METRICS_KEY not in result

    @pytest.mark.asyncio
    async def test_state_accumulation(self, mock_callback, initial_state):
        """Test that state accumulates through stages."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        mock_stage1 = AsyncMock()
        mock_stage1.stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        mock_stage1.execute.return_value = {"runbook": "# Runbook"}

        mock_stage2 = AsyncMock()
        mock_stage2.stage = WorkflowGenerationStage.TASK_PROPOSALS

        def check_state(state):
            # Stage 2 should see runbook from stage 1
            assert state["runbook"] == "# Runbook"
            return {"task_proposals": [{"name": "Task 1"}]}

        mock_stage2.execute.side_effect = check_state

        await run_orchestration_with_stages(
            stages=[mock_stage1, mock_stage2],
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify stage 2 was called (assertion in check_state passed)
        mock_stage2.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_stops_on_error_in_state(self, mock_callback, initial_state):
        """Test that orchestration stops if stage sets error in state."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        mock_stage1 = AsyncMock()
        mock_stage1.stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        mock_stage1.execute.return_value = {
            "runbook": None,
            "error": "Failed to generate runbook",
        }

        mock_stage2 = AsyncMock()
        mock_stage2.stage = WorkflowGenerationStage.TASK_PROPOSALS

        result = await run_orchestration_with_stages(
            stages=[mock_stage1, mock_stage2],
            initial_state=initial_state,
            callback=mock_callback,
        )

        # Verify error is in result
        assert result["error"] == "Failed to generate runbook"

        # Verify stage 2 was NOT executed
        mock_stage2.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_callback_works(self, initial_state):
        """Test orchestration works without a callback."""
        from analysi.agentic_orchestration.observability import (
            WorkflowGenerationStage,
        )
        from analysi.agentic_orchestration.orchestrator import (
            run_orchestration_with_stages,
        )

        mock_stage = AsyncMock()
        mock_stage.stage = WorkflowGenerationStage.RUNBOOK_GENERATION
        mock_stage.execute.return_value = {"runbook": "ok"}

        result = await run_orchestration_with_stages(
            stages=[mock_stage],
            initial_state=initial_state,
            callback=None,  # No callback
        )

        # Should complete without error
        assert result["runbook"] == "ok"
        assert result.get("error") is None
