"""Unit tests for workspace sharing across nodes.

Tests verify that workspaces are created once at the subgraph level and shared
across sequential nodes, rather than each node creating/cleaning up its own.
"""

import uuid
from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor

# Note: SecondSubgraphState no longer exists after LangGraph removal
# Keeping import to avoid breaking existing first subgraph tests
from analysi.agentic_orchestration.subgraphs.first_subgraph import (
    run_first_subgraph,
)
from analysi.agentic_orchestration.workspace import AgentWorkspace


# Test fixtures
@pytest.fixture
def mock_executor():
    """Create mock executor for testing."""
    executor = Mock(spec=AgentOrchestrationExecutor)
    executor.isolated_project_dir = None
    return executor


@pytest.fixture
def sample_alert():
    """Sample alert for testing."""
    import json
    from datetime import datetime

    return {
        "id": "alert-123",
        "title": "Suspicious Login",
        "severity": "high",
        "rule_name": "Suspicious Login Attempt",
        "triggering_event_time": datetime.now(UTC).isoformat(),
        "raw_alert": json.dumps({"source": "test"}),
    }


@pytest.fixture
def sample_task_proposals():
    """Sample task proposals for testing."""
    return [
        {
            "name": "Check IP Reputation",
            "category": "existing",
            "cy_name": "vt_ip_reputation",
        },
        {
            "name": "Analyze Login Pattern",
            "designation": "new",
            "task_description": "Analyze login patterns",
        },
    ]


@pytest.fixture
def default_metrics():
    """Default metrics for mocked operations."""
    return StageExecutionMetrics(
        duration_ms=100,
        duration_api_ms=50,
        num_turns=1,
        total_cost_usd=0.001,
        usage={},
        tool_calls=[],
    )


class TestFirstSubgraphWorkspace:
    """Test suite for first subgraph workspace management."""

    @pytest.mark.asyncio
    async def test_workspace_created_once_for_first_subgraph(
        self, mock_executor, sample_alert, default_metrics
    ):
        """Verify workspace is created once and passed to both nodes via state."""
        with patch(
            "analysi.agentic_orchestration.subgraphs.first_subgraph.AgentWorkspace"
        ) as mock_workspace_cls:
            # Setup mock workspace
            mock_workspace = MagicMock()
            mock_workspace.run_agent = AsyncMock(
                return_value=(
                    {
                        "matched-runbook.md": "# Runbook content",
                        "matching-report.json": '{"status": "matched"}',
                    },
                    default_metrics,
                )
            )
            mock_workspace.cleanup = Mock()
            mock_workspace_cls.return_value = mock_workspace

            # Execute
            await run_first_subgraph(
                alert=sample_alert,
                executor=mock_executor,
                run_id="test-run-123",
                tenant_id="test-tenant",
            )

            # Assertions
            # 1. Workspace created exactly once
            assert mock_workspace_cls.call_count == 1

            # 2. Workspace cleaned up exactly once (in finally)
            mock_workspace.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_workspace_cleanup_happens_even_on_error(
        self, mock_executor, sample_alert
    ):
        """Verify workspace cleanup happens even if node execution fails.

        After LangGraph removal, errors are stored in state["error"] rather than raised.
        """
        with patch(
            "analysi.agentic_orchestration.subgraphs.first_subgraph.AgentWorkspace"
        ) as mock_workspace_cls:
            mock_workspace = MagicMock()
            mock_workspace.cleanup = Mock()
            mock_workspace_cls.return_value = mock_workspace

            with patch(
                "analysi.agentic_orchestration.subgraphs.first_subgraph.runbook_generation_node"
            ) as mock_runbook_node:
                # Make node return error in state (new plain asyncio approach)
                mock_runbook_node.return_value = {
                    "runbook": None,
                    "matching_report": None,
                    "metrics": [],
                    "error": "Runbook generation failed: Simulated error",
                }

                # Execute - no exception raised, error in state
                result = await run_first_subgraph(
                    alert=sample_alert,
                    executor=mock_executor,
                    run_id="test-run-123",
                    tenant_id="test-tenant",
                )

                # Workspace should still be cleaned up
                mock_workspace.cleanup.assert_called_once()

                # Error should be in state
                assert result["error"] is not None
                assert "Simulated error" in result["error"]


# Note: TestSecondSubgraphWorkspace class removed after LangGraph removal
# The tests were specific to LangGraph's Send API and graph execution
# New asyncio-based implementation doesn't use LangGraph patterns


class TestWorkspaceIsolatedProjectDir:
    """Test suite for isolated_project_dir handling in workspace."""

    @pytest.mark.asyncio
    async def test_isolated_project_dir_overrides_workspace_cwd(
        self, sample_alert, default_metrics
    ):
        """Verify that when executor has isolated_project_dir, cwd=None is passed to SDK."""

        # Create executor with isolated_project_dir
        mock_executor = Mock(spec=AgentOrchestrationExecutor)
        mock_executor.isolated_project_dir = Path("/tmp/isolated-test")
        mock_executor.execute_stage = AsyncMock(
            return_value=("result", default_metrics)
        )

        workspace = AgentWorkspace(run_id="test-run-id", tenant_id="test-tenant")

        # Mock agent file reading
        with patch("pathlib.Path.read_text", return_value="# Agent prompt"):
            try:
                # Execute
                await workspace.run_agent(
                    executor=mock_executor,
                    agent_prompt_path=Path("test-agent.md"),
                    context={"alert": sample_alert},
                    expected_outputs=["output.json"],
                    stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                )

                # Assertions
                # SDK should be called with cwd=None to let it use isolated_project_dir
                mock_executor.execute_stage.assert_called_once()
                call_kwargs = mock_executor.execute_stage.call_args[1]
                assert call_kwargs["cwd"] is None

            finally:
                workspace.cleanup()

    @pytest.mark.asyncio
    async def test_normal_execution_uses_workspace_cwd(
        self, sample_alert, default_metrics
    ):
        """Verify that without isolated_project_dir, workspace cwd is passed to SDK."""

        # Create executor WITHOUT isolated_project_dir
        mock_executor = Mock(spec=AgentOrchestrationExecutor)
        mock_executor.isolated_project_dir = None
        mock_executor.execute_stage = AsyncMock(
            return_value=("result", default_metrics)
        )

        workspace = AgentWorkspace(run_id="test-run-id", tenant_id="test-tenant")

        # Mock agent file reading
        with patch("pathlib.Path.read_text", return_value="# Agent prompt"):
            try:
                # Execute
                await workspace.run_agent(
                    executor=mock_executor,
                    agent_prompt_path=Path("test-agent.md"),
                    context={"alert": sample_alert},
                    expected_outputs=["output.json"],
                    stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                )

                # Assertions
                # SDK should be called with cwd=workspace directory
                mock_executor.execute_stage.assert_called_once()
                call_kwargs = mock_executor.execute_stage.call_args[1]
                assert call_kwargs["cwd"] == str(workspace.work_dir)

            finally:
                workspace.cleanup()


class TestOrchestratorIntegration:
    """Test suite for orchestrator run_id propagation."""

    @pytest.mark.asyncio
    async def test_orchestrator_passes_run_id_between_subgraphs(
        self, mock_executor, sample_alert
    ):
        """Verify orchestrator passes run_id from first to second subgraph."""
        from analysi.agentic_orchestration.orchestrator import run_full_orchestration
        from analysi.schemas.alert import AlertBase

        alert_model = AlertBase(**sample_alert)

        with patch(
            "analysi.agentic_orchestration.orchestrator.run_first_subgraph"
        ) as mock_first:
            with patch(
                "analysi.agentic_orchestration.orchestrator.run_second_subgraph"
            ) as mock_second:
                # Setup first subgraph mock
                test_run_id = str(uuid.uuid4())
                mock_first.return_value = {
                    "run_id": test_run_id,
                    "runbook": "# Runbook",
                    "task_proposals": [],
                    "metrics": [],
                    "error": None,
                }

                # Setup second subgraph mock
                mock_second.return_value = {
                    "workflow_id": "wf-123",
                    "workflow_composition": [],
                    "tasks_built": [],
                    "metrics": [],
                    "workflow_error": None,
                }

                # Execute
                await run_full_orchestration(
                    alert=alert_model,
                    executor=mock_executor,
                    tenant_id="test-tenant",
                    run_id=test_run_id,
                )

                # Assertions
                # Second subgraph should be called with run_id from first
                mock_second.assert_called_once()
                call_kwargs = mock_second.call_args[1]
                assert call_kwargs["run_id"] == test_run_id


class TestNodeWorkspaceUsage:
    """Test suite verifying nodes use workspace from state."""

    @pytest.fixture(autouse=True)
    def _mock_generate_workflow_name(self):
        """Mock generate_unique_workflow_name to avoid DB calls in unit tests."""
        with patch(
            "analysi.agentic_orchestration.nodes.workflow_assembly.generate_unique_workflow_name",
            new_callable=AsyncMock,
            return_value="Test Alert Analysis Workflow",
        ):
            yield

    @pytest.mark.asyncio
    async def test_runbook_generation_node_uses_state_workspace(
        self, mock_executor, sample_alert, default_metrics
    ):
        """Verify runbook_generation_node uses workspace from state."""
        from analysi.agentic_orchestration.nodes.runbook_generation import (
            runbook_generation_node,
        )

        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "matched-runbook.md": "# Runbook",
                    "matching-report.json": '{"status": "matched"}',
                },
                default_metrics,
            )
        )

        state = {
            "alert": sample_alert,
            "workspace": mock_workspace,
            "run_id": "test-run-id",
            "tenant_id": "test-tenant",
        }

        # Execute
        result = await runbook_generation_node(state, mock_executor)

        # Assertions
        # 1. Workspace run_agent called
        mock_workspace.run_agent.assert_called_once()

        # 2. Workspace NOT cleaned up (that's subgraph's job)
        mock_workspace.cleanup.assert_not_called()

        # 3. Result contains runbook data
        assert result["runbook"] == "# Runbook"

    @pytest.mark.asyncio
    async def test_task_proposal_node_uses_state_workspace(
        self, mock_executor, sample_alert, default_metrics
    ):
        """Verify task_proposal_node uses workspace from state."""
        from analysi.agentic_orchestration.nodes.task_proposal import (
            task_proposal_node,
        )

        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"task-proposals.json": "[]"},
                default_metrics,
            )
        )

        state = {
            "alert": sample_alert,
            "runbook": "# Runbook",
            "workspace": mock_workspace,
            "run_id": "test-run-id",
            "tenant_id": "test-tenant",
            "metrics": [],
        }

        # Execute
        await task_proposal_node(state, mock_executor)

        # Assertions
        mock_workspace.run_agent.assert_called_once()
        mock_workspace.cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_workflow_assembly_node_uses_state_workspace(
        self, mock_executor, sample_alert, default_metrics
    ):
        """Verify workflow_assembly_node uses workspace from state."""
        from analysi.agentic_orchestration.nodes.workflow_assembly import (
            workflow_assembly_node,
        )

        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": '{"workflow_id": "wf-123", "composition": []}'
                },
                default_metrics,
            )
        )

        state = {
            "alert": sample_alert,
            "runbook": "# Runbook",
            "workspace": mock_workspace,
            "run_id": "test-run-id",
            "tenant_id": "test-tenant",
            "task_proposals": [{"designation": "existing", "cy_name": "task1"}],
            "tasks_built": [],
            "metrics": [],
        }

        # Execute
        result = await workflow_assembly_node(state, mock_executor)

        # Assertions
        mock_workspace.run_agent.assert_called_once()
        mock_workspace.cleanup.assert_not_called()
        assert result["workflow_id"] == "wf-123"

    @pytest.mark.asyncio
    async def test_task_building_node_uses_state_workspace_and_cleans_up(
        self, mock_executor, sample_alert, default_metrics
    ):
        """Verify task_building_node uses workspace from state and cleans up after."""
        from analysi.agentic_orchestration.nodes.task_building import (
            task_building_node,
        )

        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(return_value=({}, default_metrics))
        mock_workspace.cleanup = Mock()

        state = {
            "alert": sample_alert,
            "runbook": "# Runbook",
            "workspace": mock_workspace,
            "run_id": "test-run-id",
            "tenant_id": "test-tenant",
            "proposal": {
                "name": "New Task",
                "designation": "new",
                "task_description": "Description",
            },
        }

        # Mock REST API - pre-flight: not found, post-flight: created
        mock_response_not_found = MagicMock()
        mock_response_not_found.status_code = 200
        mock_response_not_found.json.return_value = []

        mock_response_found = MagicMock()
        mock_response_found.status_code = 200
        mock_response_found.json.return_value = [
            {
                "id": "task-123",
                "cy_name": "new_task",
                "name": "New Task",
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

            # Execute
            result = await task_building_node(state, mock_executor)

        # Assertions
        # 1. Workspace run_agent called
        mock_workspace.run_agent.assert_called_once()

        # 2. Workspace IS cleaned up (parallel tasks clean their own sub-workspaces)
        mock_workspace.cleanup.assert_called_once()

        # 3. Result contains task build result
        assert result["tasks_built"][0]["success"] is True
