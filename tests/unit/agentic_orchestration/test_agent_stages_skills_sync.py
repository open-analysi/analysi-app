"""TDD tests for AgentRunbookStage with skills sync and Hydra integration.

These tests verify the 6-step SDK flow is implemented in the stages path:
1. Create workspace
2. Sync skills from DB
3. Run agent
4. Detect new files
5. Submit to Hydra
6. Cleanup
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestAgentRunbookStageSkillsSync:
    """Tests for AgentRunbookStage with skills_syncer integration."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor."""
        executor = MagicMock()
        executor.skills_project_dir = None
        return executor

    @pytest.fixture
    def mock_skills_syncer(self):
        """Create a mock TenantSkillsSyncer."""
        syncer = MagicMock()
        # sync_all_skills is called by setup_skills() when no skill_names provided
        syncer.sync_all_skills = AsyncMock(return_value={"runbooks-manager": "db"})
        syncer.sync_skills = AsyncMock(return_value={"runbooks-manager": "db"})
        syncer.detect_new_files = MagicMock(return_value=[])
        syncer._baseline_manifest = {}
        return syncer

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def base_state(self):
        """Create base state for stage execution."""
        return {
            "alert": {"title": "Test Alert", "severity": "high"},
            "run_id": str(uuid4()),
            "tenant_id": "test-tenant",
        }

    @pytest.mark.asyncio
    async def test_stage_accepts_skills_syncer_parameter(self, mock_executor):
        """AgentRunbookStage should accept skills_syncer in constructor."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        # Should not raise
        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=MagicMock(),
        )

        assert stage.skills_syncer is not None

    @pytest.mark.asyncio
    async def test_stage_accepts_session_parameter(self, mock_executor):
        """AgentRunbookStage should accept session in constructor."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        mock_session = AsyncMock()
        stage = AgentRunbookStage(
            executor=mock_executor,
            session=mock_session,
        )

        assert stage.session is not None

    @pytest.mark.asyncio
    async def test_stage_syncs_skills_before_agent_execution(
        self, mock_executor, mock_skills_syncer, base_state
    ):
        """Stage should sync ALL skills to workspace before running agent."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
        )

        # Mock the node to avoid actual agent execution
        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }

            await stage.execute(base_state)

        # Verify ALL skills were synced (via sync_all_skills)
        mock_skills_syncer.sync_all_skills.assert_called_once()

    @pytest.mark.asyncio
    async def test_stage_sets_executor_skills_project_dir(
        self, mock_executor, mock_skills_syncer, base_state
    ):
        """Stage should set executor.skills_project_dir to workspace."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }

            await stage.execute(base_state)

        # Verify executor was configured for tenant-isolated skills
        assert mock_executor.skills_project_dir is not None

    @pytest.mark.asyncio
    async def test_stage_detects_new_files_after_agent(
        self, mock_executor, mock_skills_syncer, mock_session, base_state
    ):
        """Stage should detect new files created by agent."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        # Simulate agent creating a new file
        new_file = MagicMock()
        new_file.name = "new-runbook.md"
        mock_skills_syncer.detect_new_files.return_value = [new_file]

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
            session=mock_session,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }
            with patch(
                "analysi.agentic_orchestration.stages.agent_stages.ContentPolicy"
            ) as MockPolicy:
                MockPolicy.return_value.filter_new_files.return_value = ([], [])

                await stage.execute(base_state)

        # Verify new file detection was called
        mock_skills_syncer.detect_new_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_stage_submits_approved_files_to_hydra(
        self, mock_executor, mock_skills_syncer, mock_session, base_state
    ):
        """Stage should submit approved files to Hydra."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        # Simulate agent creating a new file
        new_file = Path("/tmp/new-runbook.md")
        mock_skills_syncer.detect_new_files.return_value = [new_file]

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
            session=mock_session,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }
            with patch(
                "analysi.agentic_orchestration.stages.agent_stages.ContentPolicy"
            ) as MockPolicy:
                # File passes content policy
                MockPolicy.return_value.filter_new_files.return_value = (
                    [new_file],
                    [],
                )

                with patch(
                    "analysi.agentic_orchestration.stages.agent_stages.submit_new_files_to_hydra"
                ) as mock_submit:
                    mock_submit.return_value = [{"status": "applied"}]

                    await stage.execute(base_state)

                    # Verify Hydra submission was called
                    mock_submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_stage_blocks_suspicious_files(
        self, mock_executor, mock_skills_syncer, mock_session, base_state
    ):
        """Stage should block suspicious files via ContentPolicy."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        # Simulate agent creating a suspicious file
        suspicious_file = Path("/tmp/malicious.md")
        mock_skills_syncer.detect_new_files.return_value = [suspicious_file]

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
            session=mock_session,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }
            with patch(
                "analysi.agentic_orchestration.stages.agent_stages.ContentPolicy"
            ) as MockPolicy:
                # File is rejected by content policy
                MockPolicy.return_value.filter_new_files.return_value = (
                    [],
                    [{"file": "malicious.md", "reason": "Suspicious pattern"}],
                )

                with patch(
                    "analysi.agentic_orchestration.stages.agent_stages.submit_new_files_to_hydra"
                ) as mock_submit:
                    await stage.execute(base_state)

                    # Verify Hydra submission was NOT called (no approved files)
                    mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_stage_works_without_skills_syncer(self, mock_executor, base_state):
        """Stage should work normally when skills_syncer is not provided."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        stage = AgentRunbookStage(executor=mock_executor)

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }

            result = await stage.execute(base_state)

        # Should complete without error
        assert result["runbook"] == "# Test Runbook"

    @pytest.mark.asyncio
    async def test_stage_cleans_up_workspace_on_success(
        self, mock_executor, mock_skills_syncer, base_state
    ):
        """Stage should cleanup workspace after successful execution."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.return_value = {
                "runbook": "# Test Runbook",
                "matching_report": "{}",
                "metrics": [],
            }
            with patch(
                "analysi.agentic_orchestration.stages.agent_stages.AgentWorkspace"
            ) as MockWorkspace:
                mock_workspace = MagicMock()
                mock_workspace.work_dir = Path("/tmp/test-workspace")
                mock_workspace.skills_dir = Path("/tmp/test-workspace/.claude/skills")
                mock_workspace.setup_skills = AsyncMock(return_value={})
                mock_workspace.detect_new_files = MagicMock(return_value=[])
                MockWorkspace.return_value = mock_workspace

                await stage.execute(base_state)

                # Verify cleanup was called
                mock_workspace.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stage_cleans_up_workspace_on_error(
        self, mock_executor, mock_skills_syncer, base_state
    ):
        """Stage should cleanup workspace even when agent fails."""
        from analysi.agentic_orchestration.stages.agent_stages import (
            AgentRunbookStage,
        )

        stage = AgentRunbookStage(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
        )

        with patch(
            "analysi.agentic_orchestration.stages.agent_stages.runbook_generation_node"
        ) as mock_node:
            mock_node.side_effect = RuntimeError("Agent failed")

            with patch(
                "analysi.agentic_orchestration.stages.agent_stages.AgentWorkspace"
            ) as MockWorkspace:
                mock_workspace = MagicMock()
                mock_workspace.work_dir = Path("/tmp/test-workspace")
                mock_workspace.skills_dir = Path("/tmp/test-workspace/.claude/skills")
                mock_workspace.setup_skills = AsyncMock(return_value={})
                MockWorkspace.return_value = mock_workspace

                with pytest.raises(RuntimeError):
                    await stage.execute(base_state)

                # Verify cleanup was still called
                mock_workspace.cleanup.assert_called_once()


class TestStageStrategyProviderSkillsSync:
    """Tests for StageStrategyProvider with skills_syncer integration."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor."""
        return MagicMock()

    @pytest.fixture
    def mock_skills_syncer(self):
        """Create a mock TenantSkillsSyncer."""
        return MagicMock()

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    def test_provider_accepts_skills_syncer(self, mock_executor, mock_skills_syncer):
        """StageStrategyProvider should accept skills_syncer parameter."""
        from analysi.agentic_orchestration.stages.provider import (
            StageStrategyProvider,
        )

        provider = StageStrategyProvider(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
        )

        assert provider.skills_syncer is not None

    def test_provider_accepts_session(self, mock_executor, mock_session):
        """StageStrategyProvider should accept session parameter."""
        from analysi.agentic_orchestration.stages.provider import (
            StageStrategyProvider,
        )

        provider = StageStrategyProvider(
            executor=mock_executor,
            session=mock_session,
        )

        assert provider.session is not None

    def test_provider_passes_skills_syncer_to_runbook_stage(
        self, mock_executor, mock_skills_syncer, mock_session
    ):
        """Provider should pass skills_syncer to AgentRunbookStage."""
        from analysi.agentic_orchestration.stages.provider import (
            StageStrategyProvider,
        )

        provider = StageStrategyProvider(
            executor=mock_executor,
            skills_syncer=mock_skills_syncer,
            session=mock_session,
        )

        stages = provider.get_stages()

        # Find the runbook stage
        runbook_stage = None
        for stage in stages:
            if hasattr(stage, "skills_syncer"):
                runbook_stage = stage
                break

        assert runbook_stage is not None
        assert runbook_stage.skills_syncer == mock_skills_syncer
        assert runbook_stage.session == mock_session

    def test_provider_works_without_skills_syncer(self, mock_executor):
        """Provider should work normally without skills_syncer."""
        from analysi.agentic_orchestration.stages.provider import (
            StageStrategyProvider,
        )

        provider = StageStrategyProvider(executor=mock_executor)

        stages = provider.get_stages()

        # Should return stages (4 in production mode)
        assert len(stages) > 0
