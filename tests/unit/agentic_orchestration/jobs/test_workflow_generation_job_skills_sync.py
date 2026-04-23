"""TDD tests for workflow generation job with skills sync integration.

These tests verify that the job layer correctly:
1. Creates a TenantSkillsSyncer (when USE_DB_SKILLS=true)
2. Creates a database session
3. Passes both to StageStrategyProvider
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Common patch path prefix
_JOB_MODULE = "analysi.agentic_orchestration.jobs.workflow_generation_job"


def _mock_credential_factory():
    """Mock AgentCredentialFactory to bypass IntegrationRepository DB calls.

    The job creates IntegrationRepository(session) from AsyncSessionLocal, then
    calls credential_factory.get_agent_credentials(). Without this mock, the
    AsyncMock session causes 'coroutine' object has no attribute 'all' when
    IntegrationRepository.list_integrations() calls result.scalars().all().
    """
    mock_factory = MagicMock()
    mock_factory.return_value.get_agent_credentials = AsyncMock(
        return_value={"oauth_token": "test-oauth-token"}
    )
    return patch(f"{_JOB_MODULE}.AgentCredentialFactory", mock_factory)


class TestWorkflowGenerationJobSkillsSync:
    """Tests for workflow generation job with skills_syncer integration."""

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock ARQ context."""
        return {}

    @pytest.fixture
    def generation_id(self):
        return str(uuid4())

    @pytest.fixture
    def tenant_id(self):
        return "test-tenant"

    @pytest.fixture
    def alert_data(self):
        return {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2024-01-15T10:00:00Z",
            "raw_alert": "test raw alert content",
        }

    @pytest.mark.asyncio
    async def test_job_creates_skills_syncer(
        self, mock_ctx, generation_id, tenant_id, alert_data
    ):
        """Job should create TenantSkillsSyncer when USE_DB_SKILLS=true."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch(f"{_JOB_MODULE}.AlertAnalysisConfig.USE_DB_SKILLS", True),
            patch(f"{_JOB_MODULE}.create_executor"),
            patch(f"{_JOB_MODULE}.StageStrategyProvider") as MockProvider,
            patch(f"{_JOB_MODULE}.run_orchestration_with_stages") as mock_orchestration,
            patch(f"{_JOB_MODULE}._update_workflow_generation"),
            patch(f"{_JOB_MODULE}.TenantSkillsSyncer") as MockSyncer,
            patch(f"{_JOB_MODULE}.AsyncSessionLocal") as MockSession,
            _mock_credential_factory(),
        ):
            mock_provider = MagicMock()
            mock_provider.mode.value = "production"
            mock_provider.get_stages.return_value = []
            MockProvider.return_value = mock_provider

            mock_orchestration.return_value = {"workflow_id": None, "error": None}

            mock_syncer = MagicMock()
            MockSyncer.return_value = mock_syncer

            mock_session = AsyncMock()
            MockSession.return_value.__aenter__.return_value = mock_session

            await execute_workflow_generation(
                ctx=mock_ctx,
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify TenantSkillsSyncer was created
            MockSyncer.assert_called_once()
            call_kwargs = MockSyncer.call_args[1]
            assert call_kwargs["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_job_passes_skills_syncer_to_provider(
        self, mock_ctx, generation_id, tenant_id, alert_data
    ):
        """Job should pass skills_syncer to StageStrategyProvider when USE_DB_SKILLS=true."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch(f"{_JOB_MODULE}.AlertAnalysisConfig.USE_DB_SKILLS", True),
            patch(f"{_JOB_MODULE}.create_executor"),
            patch(f"{_JOB_MODULE}.StageStrategyProvider") as MockProvider,
            patch(f"{_JOB_MODULE}.run_orchestration_with_stages") as mock_orchestration,
            patch(f"{_JOB_MODULE}._update_workflow_generation"),
            patch(f"{_JOB_MODULE}.TenantSkillsSyncer") as MockSyncer,
            patch(f"{_JOB_MODULE}.AsyncSessionLocal") as MockSession,
            _mock_credential_factory(),
        ):
            mock_provider = MagicMock()
            mock_provider.mode.value = "production"
            mock_provider.get_stages.return_value = []
            MockProvider.return_value = mock_provider

            mock_orchestration.return_value = {"workflow_id": None, "error": None}

            mock_syncer = MagicMock()
            MockSyncer.return_value = mock_syncer

            mock_session = AsyncMock()
            MockSession.return_value.__aenter__.return_value = mock_session

            await execute_workflow_generation(
                ctx=mock_ctx,
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify StageStrategyProvider was called with skills_syncer
            MockProvider.assert_called_once()
            call_kwargs = MockProvider.call_args[1]
            assert "skills_syncer" in call_kwargs
            assert call_kwargs["skills_syncer"] == mock_syncer

    @pytest.mark.asyncio
    async def test_job_passes_session_to_provider(
        self, mock_ctx, generation_id, tenant_id, alert_data
    ):
        """Job should pass database session to StageStrategyProvider when USE_DB_SKILLS=true."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch(f"{_JOB_MODULE}.AlertAnalysisConfig.USE_DB_SKILLS", True),
            patch(f"{_JOB_MODULE}.create_executor"),
            patch(f"{_JOB_MODULE}.StageStrategyProvider") as MockProvider,
            patch(f"{_JOB_MODULE}.run_orchestration_with_stages") as mock_orchestration,
            patch(f"{_JOB_MODULE}._update_workflow_generation"),
            patch(f"{_JOB_MODULE}.TenantSkillsSyncer") as MockSyncer,
            patch(f"{_JOB_MODULE}.AsyncSessionLocal") as MockSession,
            _mock_credential_factory(),
        ):
            mock_provider = MagicMock()
            mock_provider.mode.value = "production"
            mock_provider.get_stages.return_value = []
            MockProvider.return_value = mock_provider

            mock_orchestration.return_value = {"workflow_id": None, "error": None}

            mock_syncer = MagicMock()
            MockSyncer.return_value = mock_syncer

            mock_session = AsyncMock()
            MockSession.return_value.__aenter__.return_value = mock_session

            await execute_workflow_generation(
                ctx=mock_ctx,
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify StageStrategyProvider was called with session
            MockProvider.assert_called_once()
            call_kwargs = MockProvider.call_args[1]
            assert "session" in call_kwargs
            assert call_kwargs["session"] == mock_session

    @pytest.mark.asyncio
    async def test_job_commits_session_on_success(
        self, mock_ctx, generation_id, tenant_id, alert_data
    ):
        """Job should commit session after successful orchestration when USE_DB_SKILLS=true."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch(f"{_JOB_MODULE}.AlertAnalysisConfig.USE_DB_SKILLS", True),
            patch(f"{_JOB_MODULE}.create_executor"),
            patch(f"{_JOB_MODULE}.StageStrategyProvider") as MockProvider,
            patch(f"{_JOB_MODULE}.run_orchestration_with_stages") as mock_orchestration,
            patch(f"{_JOB_MODULE}._update_workflow_generation"),
            patch(f"{_JOB_MODULE}._create_routing_rule", return_value="test-group-id"),
            patch(f"{_JOB_MODULE}._resume_paused_alerts"),
            patch(f"{_JOB_MODULE}.TenantSkillsSyncer") as MockSyncer,
            patch(f"{_JOB_MODULE}.AsyncSessionLocal") as MockSession,
            _mock_credential_factory(),
        ):
            mock_provider = MagicMock()
            mock_provider.mode.value = "production"
            mock_provider.get_stages.return_value = []
            MockProvider.return_value = mock_provider

            mock_orchestration.return_value = {
                "workflow_id": "test-workflow-id",
                "error": None,
            }

            mock_syncer = MagicMock()
            MockSyncer.return_value = mock_syncer

            mock_session = AsyncMock()
            MockSession.return_value.__aenter__.return_value = mock_session

            await execute_workflow_generation(
                ctx=mock_ctx,
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify session was committed
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_job_rollbacks_session_on_error(
        self, mock_ctx, generation_id, tenant_id, alert_data
    ):
        """Job should rollback session if orchestration fails (Project Leros: raise after cleanup)."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch(f"{_JOB_MODULE}.AlertAnalysisConfig.USE_DB_SKILLS", True),
            patch(f"{_JOB_MODULE}.create_executor"),
            patch(f"{_JOB_MODULE}.StageStrategyProvider") as MockProvider,
            patch(f"{_JOB_MODULE}.run_orchestration_with_stages") as mock_orchestration,
            patch(f"{_JOB_MODULE}._update_workflow_generation"),
            patch(f"{_JOB_MODULE}._mark_triggering_analysis_failed"),
            patch(f"{_JOB_MODULE}.TenantSkillsSyncer") as MockSyncer,
            patch(f"{_JOB_MODULE}.AsyncSessionLocal") as MockSession,
            _mock_credential_factory(),
        ):
            mock_provider = MagicMock()
            mock_provider.mode.value = "production"
            mock_provider.get_stages.return_value = []
            MockProvider.return_value = mock_provider

            # Simulate orchestration failure
            mock_orchestration.side_effect = RuntimeError("Orchestration failed")

            mock_syncer = MagicMock()
            MockSyncer.return_value = mock_syncer

            mock_session = AsyncMock()
            MockSession.return_value.__aenter__.return_value = mock_session

            with pytest.raises(RuntimeError, match="Orchestration failed"):
                await execute_workflow_generation(
                    ctx=mock_ctx,
                    generation_id=generation_id,
                    tenant_id=tenant_id,
                    alert_data=alert_data,
                )

            # Verify session was rolled back
            mock_session.rollback.assert_called()

    # Removed test_job_skips_skills_syncer_when_disabled
    # USE_DB_SKILLS is now deprecated and defaults to true
    # Syncer is always created
