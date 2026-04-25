"""Unit tests for _mark_triggering_analysis_failed and its integration with failure paths."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from analysi.agentic_orchestration.jobs.workflow_generation_job import (
    _mark_triggering_analysis_failed,
    execute_workflow_generation,
)

MODULE = "analysi.agentic_orchestration.jobs.workflow_generation_job"

# Minimal valid alert data for AlertBase (avoids validation errors in integration tests)
VALID_ALERT_DATA = {
    "title": "Test Alert",
    "severity": "high",
    "triggering_event_time": "2026-01-01T00:00:00Z",
    "raw_alert": '{"original": "data"}',
}


@pytest.mark.asyncio
class TestMarkTriggeringAnalysisFailed:
    """Tests for the _mark_triggering_analysis_failed helper."""

    @pytest.fixture
    def generation_id(self):
        return str(uuid4())

    @pytest.fixture
    def analysis_id(self):
        return str(uuid4())

    @pytest.fixture
    def alert_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_db(self):
        """Create a mock AlertAnalysisDB."""
        db = AsyncMock()
        db.initialize = AsyncMock()
        db.close = AsyncMock()
        return db

    async def test_happy_path_marks_analysis_and_alert_failed(
        self, generation_id, analysis_id, alert_id
    ):
        """When generation has a triggering analysis, both analysis and alert are marked failed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.return_value = {
            "id": analysis_id,
            "alert_id": alert_id,
            "status": "paused_workflow_building",
        }

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={"X-API-Key": "k"}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="CLI exit code 1",
            )

            # Analysis marked as failed with error message
            mock_db.update_analysis_status.assert_called_once_with(
                analysis_id=analysis_id,
                status="failed",
                error="Workflow generation failed: CLI exit code 1",
            )

            # Alert marked as failed only if this analysis is still current
            mock_db.update_alert_status_if_current.assert_called_once_with(
                alert_id, "failed", analysis_id
            )

            # DB cleaned up
            mock_db.close.assert_called_once()

    async def test_no_triggering_analysis_id_skips_gracefully(self, generation_id):
        """When generation has no triggering_alert_analysis_id, skip without error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": None,
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Should not raise
            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="some error",
            )
            # No DB calls — we returned early

    async def test_analysis_not_found_in_db(self, generation_id, analysis_id):
        """When analysis record doesn't exist in DB, log warning and return."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.return_value = None  # Not found

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="error",
            )

            # Should NOT attempt to update status
            mock_db.update_analysis_status.assert_not_called()
            mock_db.update_alert_status.assert_not_called()
            mock_db.close.assert_called_once()

    async def test_analysis_without_alert_id(self, generation_id, analysis_id):
        """When analysis exists but has no alert_id, mark analysis failed but skip alert."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.return_value = {
            "id": analysis_id,
            "alert_id": None,  # No alert linked
            "status": "paused_workflow_building",
        }

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="error",
            )

            # Analysis still marked failed
            mock_db.update_analysis_status.assert_called_once()
            # Alert NOT updated (no alert_id)
            mock_db.update_alert_status_if_current.assert_not_called()

    async def test_api_fetch_failure_is_best_effort(self, generation_id):
        """When fetching the generation record fails, log warning and don't propagate."""
        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
        ):
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Should NOT raise — best-effort
            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="error",
            )

    async def test_db_failure_is_best_effort(self, generation_id, analysis_id):
        """When DB operations fail, log warning and don't propagate."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.side_effect = Exception("DB connection lost")

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Should NOT raise
            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="error",
            )

            # DB close still called (via finally)
            mock_db.close.assert_called_once()

    async def test_db_close_called_even_on_update_failure(
        self, generation_id, analysis_id, alert_id
    ):
        """DB.close() is always called, even if update_analysis_status raises."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.return_value = {
            "id": analysis_id,
            "alert_id": alert_id,
            "status": "paused_workflow_building",
        }
        mock_db.update_analysis_status.side_effect = Exception("write failed")

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Best-effort: should not raise
            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="error",
            )

            # close() always called via finally
            mock_db.close.assert_called_once()

    async def test_error_message_propagated_to_analysis(
        self, generation_id, analysis_id, alert_id
    ):
        """The original error message is embedded in the analysis error field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "triggering_alert_analysis_id": analysis_id,
        }
        mock_response.raise_for_status = MagicMock()

        mock_db = AsyncMock()
        mock_db.get_analysis.return_value = {
            "id": analysis_id,
            "alert_id": alert_id,
            "status": "paused_workflow_building",
        }

        with (
            patch(f"{MODULE}.InternalAsyncClient") as mock_client_cls,
            patch(f"{MODULE}.internal_auth_headers", return_value={}),
            patch("analysi.alert_analysis.db.AlertAnalysisDB", return_value=mock_db),
        ):
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await _mark_triggering_analysis_failed(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="Command failed with exit code 1",
            )

            call_kwargs = mock_db.update_analysis_status.call_args.kwargs
            assert call_kwargs["status"] == "failed"
            assert "Command failed with exit code 1" in call_kwargs["error"]
            assert "Workflow generation failed:" in call_kwargs["error"]


@pytest.mark.asyncio
class TestExecuteWorkflowGenerationFailurePaths:
    """Test that execute_workflow_generation calls _mark_triggering_analysis_failed on failure."""

    async def test_soft_failure_calls_mark_analysis_failed(self):
        """When orchestration returns an error (soft failure), analysis is marked failed."""
        generation_id = str(uuid4())

        orchestration_result = {
            "error": "Runbook generation failed: CLI exit code 1",
            "workflow_id": None,
            "runbook": None,
            "tasks_built": [],
            "workflow_composition": None,
            "metrics": [],
            "workspace_path": "/tmp/kea-test",
        }

        with (
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(f"{MODULE}.AgentCredentialFactory") as mock_cred_factory,
            patch(f"{MODULE}.create_executor"),
            patch(f"{MODULE}.AlertAnalysisConfig") as mock_config,
            patch(f"{MODULE}.AlertBase"),
            patch(
                f"{MODULE}.run_orchestration_with_stages",
                return_value=orchestration_result,
            ),
            patch(f"{MODULE}._update_workflow_generation", new_callable=AsyncMock),
            patch(
                f"{MODULE}._mark_triggering_analysis_failed", new_callable=AsyncMock
            ) as mock_mark_failed,
            patch(f"{MODULE}.TenantSkillsSyncer"),
            patch(f"{MODULE}.StageStrategyProvider") as mock_provider_cls,
        ):
            mock_config.API_BASE_URL = "http://api:8000"
            mock_config.MAX_TASKS_TO_BUILD = None

            # Setup credential factory
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "test-token"
            }
            mock_cred_factory.return_value = mock_factory

            # Setup session
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            # Setup provider
            mock_provider = MagicMock()
            mock_provider.get_stages.return_value = []
            mock_provider.mode = MagicMock(value="sdk")
            mock_provider_cls.return_value = mock_provider

            result = await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id="tenant-1",
                alert_data=VALID_ALERT_DATA,
            )

            # Verify _mark_triggering_analysis_failed was called
            mock_mark_failed.assert_called_once_with(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="Runbook generation failed: CLI exit code 1",
            )

            assert result["status"] == "failed"
            assert result["error"] is not None

    async def test_hard_crash_calls_mark_analysis_failed(self):
        """When execute_workflow_generation crashes (hard failure), analysis is marked failed.

        Project Leros: Job now raises after domain cleanup instead of returning
        a failure dict. The decorator tracks the failure in job_tracking JSONB.
        """
        generation_id = str(uuid4())

        with (
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(f"{MODULE}.AgentCredentialFactory") as mock_cred_factory,
            patch(f"{MODULE}.AlertAnalysisConfig") as mock_config,
            patch(f"{MODULE}._update_workflow_generation", new_callable=AsyncMock),
            patch(
                f"{MODULE}._mark_triggering_analysis_failed", new_callable=AsyncMock
            ) as mock_mark_failed,
        ):
            mock_config.API_BASE_URL = "http://api:8000"
            mock_config.JOB_TIMEOUT = 3600

            # Credential fetch fails — triggers hard crash path
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.side_effect = ValueError(
                "No anthropic_agent integration configured"
            )
            mock_cred_factory.return_value = mock_factory

            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            with pytest.raises(ValueError, match="anthropic_agent"):
                await execute_workflow_generation(
                    ctx={},
                    generation_id=generation_id,
                    tenant_id="tenant-1",
                    alert_data=VALID_ALERT_DATA,
                )

            # Verify _mark_triggering_analysis_failed was called
            mock_mark_failed.assert_called_once_with(
                api_base_url="http://api:8000",
                tenant_id="tenant-1",
                generation_id=generation_id,
                error_message="No anthropic_agent integration configured",
            )

    async def test_success_path_does_not_call_mark_analysis_failed(self):
        """When orchestration succeeds, _mark_triggering_analysis_failed is NOT called."""
        generation_id = str(uuid4())

        orchestration_result = {
            "error": None,
            "workflow_id": str(uuid4()),
            "runbook": "# Test runbook",
            "tasks_built": [{"success": True, "cy_name": "test_task"}],
            "workflow_composition": ["test_task"],
            "metrics": [],
            "workspace_path": "/tmp/kea-test",
        }

        with (
            patch(f"{MODULE}.AsyncSessionLocal") as mock_session_cls,
            patch(f"{MODULE}.AgentCredentialFactory") as mock_cred_factory,
            patch(f"{MODULE}.create_executor"),
            patch(f"{MODULE}.AlertAnalysisConfig") as mock_config,
            patch(f"{MODULE}.AlertBase"),
            patch(
                f"{MODULE}.run_orchestration_with_stages",
                return_value=orchestration_result,
            ),
            patch(f"{MODULE}._update_workflow_generation", new_callable=AsyncMock),
            patch(f"{MODULE}._create_routing_rule", new_callable=AsyncMock),
            patch(
                f"{MODULE}._mark_triggering_analysis_failed", new_callable=AsyncMock
            ) as mock_mark_failed,
            patch(f"{MODULE}.TenantSkillsSyncer"),
            patch(f"{MODULE}.StageStrategyProvider") as mock_provider_cls,
        ):
            mock_config.API_BASE_URL = "http://api:8000"
            mock_config.MAX_TASKS_TO_BUILD = None

            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "test-token"
            }
            mock_cred_factory.return_value = mock_factory

            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session

            mock_provider = MagicMock()
            mock_provider.get_stages.return_value = []
            mock_provider.mode = MagicMock(value="sdk")
            mock_provider_cls.return_value = mock_provider

            result = await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id="tenant-1",
                alert_data=VALID_ALERT_DATA,
            )

            # Should NOT be called on success
            mock_mark_failed.assert_not_called()
            assert result["status"] == "completed"
