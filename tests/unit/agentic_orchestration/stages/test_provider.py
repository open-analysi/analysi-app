"""Unit tests for StageStrategyProvider."""

from unittest.mock import MagicMock

import pytest

from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor
from analysi.agentic_orchestration.stages import StageStrategyProvider


class TestStageStrategyProvider:
    """Tests for StageStrategyProvider."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        return MagicMock(spec=AgentOrchestrationExecutor)

    def test_requires_executor(self):
        """Verify provider without executor raises error."""
        provider = StageStrategyProvider()

        with pytest.raises(ValueError) as exc_info:
            provider.get_stages()

        assert "executor" in str(exc_info.value).lower()

    def test_with_executor_returns_agent_stages(self, mock_executor):
        """Verify provider with executor returns agent stages."""
        provider = StageStrategyProvider(executor=mock_executor)
        stages = provider.get_stages()

        assert len(stages) == 4

        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
            AgentTaskBuildingStage,
            AgentTaskProposalStage,
            AgentWorkflowAssemblyStage,
        )

        assert isinstance(stages[0], AgentRunbookStage)
        assert isinstance(stages[1], AgentTaskProposalStage)
        assert isinstance(stages[2], AgentTaskBuildingStage)
        assert isinstance(stages[3], AgentWorkflowAssemblyStage)

    def test_stage_order(self, mock_executor):
        """Verify stages are returned in correct pipeline order."""
        provider = StageStrategyProvider(executor=mock_executor)
        stages = provider.get_stages()

        expected_order = [
            WorkflowGenerationStage.RUNBOOK_GENERATION,
            WorkflowGenerationStage.TASK_PROPOSALS,
            WorkflowGenerationStage.TASK_BUILDING,
            WorkflowGenerationStage.WORKFLOW_ASSEMBLY,
        ]

        actual_order = [stage.stage for stage in stages]
        assert actual_order == expected_order

    def test_max_tasks_to_build_passed_to_stage(self, mock_executor):
        """Verify max_tasks_to_build is passed to task building stage."""
        provider = StageStrategyProvider(
            executor=mock_executor,
            max_tasks_to_build=5,
        )
        stages = provider.get_stages()

        # Task building is stage 3 (index 2)
        task_building_stage = stages[2]
        assert task_building_stage.max_tasks_to_build == 5
