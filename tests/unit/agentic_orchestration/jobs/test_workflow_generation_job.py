"""Unit tests for workflow generation job helper functions.

Note: These tests focus on the core logic of _update_progress().
Retry behavior (provided by tenacity decorator) is tested separately in integration tests.
"""

from concurrent.futures import Future
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from tenacity import RetryCallState

from analysi.agentic_orchestration.jobs.workflow_generation_job import (
    _resume_paused_alerts,
    _should_retry_progress_update,
    _update_progress,
)


def _make_retry_state(exception: BaseException) -> RetryCallState:
    """Create a RetryCallState with a failed outcome containing the given exception."""
    retry_state = RetryCallState(retry_object=MagicMock(), fn=None, args=(), kwargs={})
    future: Future = Future()
    future.set_exception(exception)
    retry_state.outcome = future
    return retry_state


class TestShouldRetryProgressUpdate:
    """Test _should_retry_progress_update() retry logic function."""

    def test_should_retry_on_timeout_exception(self):
        """Test that TimeoutException triggers retry."""
        from httpx import TimeoutException

        state = _make_retry_state(TimeoutException("Connection timeout"))
        assert _should_retry_progress_update(state) is True

    def test_should_retry_on_5xx_server_errors(self):
        """Test that 5xx server errors trigger retry."""
        from httpx import HTTPStatusError

        # 500 Internal Server Error
        response_500 = AsyncMock(status_code=500)
        error_500 = HTTPStatusError(
            "500 Internal Server Error",
            request=AsyncMock(),
            response=response_500,
        )
        assert _should_retry_progress_update(_make_retry_state(error_500)) is True

        # 503 Service Unavailable
        response_503 = AsyncMock(status_code=503)
        error_503 = HTTPStatusError(
            "503 Service Unavailable",
            request=AsyncMock(),
            response=response_503,
        )
        assert _should_retry_progress_update(_make_retry_state(error_503)) is True

    def test_should_not_retry_on_404_not_found(self):
        """Test that 404 Not Found does NOT trigger retry (permanent error)."""
        from httpx import HTTPStatusError

        response = AsyncMock(status_code=404)
        error = HTTPStatusError(
            "404 Not Found",
            request=AsyncMock(),
            response=response,
        )
        assert _should_retry_progress_update(_make_retry_state(error)) is False

    def test_should_not_retry_on_4xx_client_errors(self):
        """Test that 4xx client errors do NOT trigger retry."""
        from httpx import HTTPStatusError

        # 400 Bad Request
        response_400 = AsyncMock(status_code=400)
        error_400 = HTTPStatusError(
            "400 Bad Request",
            request=AsyncMock(),
            response=response_400,
        )
        assert _should_retry_progress_update(_make_retry_state(error_400)) is False

        # 401 Unauthorized
        response_401 = AsyncMock(status_code=401)
        error_401 = HTTPStatusError(
            "401 Unauthorized",
            request=AsyncMock(),
            response=response_401,
        )
        assert _should_retry_progress_update(_make_retry_state(error_401)) is False

        # 403 Forbidden
        response_403 = AsyncMock(status_code=403)
        error_403 = HTTPStatusError(
            "403 Forbidden",
            request=AsyncMock(),
            response=response_403,
        )
        assert _should_retry_progress_update(_make_retry_state(error_403)) is False

    def test_should_not_retry_on_other_exceptions(self):
        """Test that non-HTTP exceptions do NOT trigger retry."""
        # ValueError
        assert (
            _should_retry_progress_update(
                _make_retry_state(ValueError("Invalid input"))
            )
            is False
        )

        # Generic Exception
        assert (
            _should_retry_progress_update(_make_retry_state(Exception("Unknown error")))
            is False
        )


class TestUpdateProgress:
    """Test _update_progress() helper function with mocked HTTP calls."""

    @pytest.mark.asyncio
    async def test_update_progress_success_with_all_params(self):
        """Test successful progress update with all parameters including tasks_count."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "task_building"
        tasks_count = 5

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
                tasks_count=tasks_count,
            )

            # Assert
            mock_client.patch.assert_called_once()
            call_args = mock_client.patch.call_args

            # Verify URL
            expected_url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}/progress"
            assert call_args[0][0] == expected_url

            # Verify payload structure - now just stage and tasks_count
            payload = call_args[1]["json"]
            assert payload["stage"] == stage
            assert payload["tasks_count"] == tasks_count

            mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_success_without_tasks_count(self):
        """Test successful progress update without optional tasks_count parameter."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "runbook_generation"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
                tasks_count=None,  # Explicitly None
            )

            # Assert
            call_args = mock_client.patch.call_args
            payload = call_args[1]["json"]

            # Verify tasks_count is NOT included in payload when None
            assert payload["stage"] == stage
            assert "tasks_count" not in payload

    @pytest.mark.asyncio
    async def test_update_progress_url_construction(self):
        """Test that URL is correctly constructed from parameters."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "workflow_assembly"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
            )

            # Assert URL is correctly formatted
            expected_url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}/progress"
            mock_client.patch.assert_called_once()
            actual_url = mock_client.patch.call_args[0][0]
            assert actual_url == expected_url

    @pytest.mark.asyncio
    async def test_update_progress_payload_structure(self):
        """Test that payload contains correct structure with stage and timestamp."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "task_building"
        tasks_count = 5

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
                tasks_count=tasks_count,
            )

            # Assert payload structure - now simplified
            mock_client.patch.assert_called_once()
            call_kwargs = mock_client.patch.call_args[1]
            payload = call_kwargs["json"]

            assert payload["stage"] == stage
            assert payload["tasks_count"] == tasks_count

    @pytest.mark.asyncio
    async def test_update_progress_http_method_and_headers(self):
        """Test that correct HTTP method (PATCH) is used."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "runbook_generation"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
            )

            # Assert PATCH method is called (not POST, PUT, etc.)
            mock_client.patch.assert_called_once()
            (
                mock_client.post.assert_not_called()
                if hasattr(mock_client, "post")
                else None
            )
            mock_client.put.assert_not_called() if hasattr(mock_client, "put") else None

    @pytest.mark.asyncio
    async def test_update_progress_uses_correct_timeout(self):
        """Test that HTTP client uses configured timeout values."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "workflow_assembly"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
            )

            # Assert - verify AsyncClient was created with correct timeout
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert "timeout" in call_kwargs

            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, httpx.Timeout)
            # Timeout(30.0, connect=5.0) from implementation
            assert timeout.connect == 5.0

    @pytest.mark.asyncio
    async def test_update_progress_calls_raise_for_status(self):
        """Test that raise_for_status() is called to check HTTP response."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())
        stage = "task_building"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _update_progress(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                stage=stage,
            )

            # Assert - raise_for_status should be called to validate HTTP response
            mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_all_workflow_stages(self):
        """Test progress updates for all 4 workflow generation stages."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        generation_id = str(uuid4())

        stages = [
            "runbook_generation",
            "task_proposals",
            "task_building",
            "workflow_assembly",
        ]

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        # Act & Assert
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_client_class.return_value = mock_client

            for stage in stages:
                await _update_progress(
                    api_base_url=api_base_url,
                    tenant_id=tenant_id,
                    generation_id=generation_id,
                    stage=stage,
                )

            # Verify all 4 stages were called
            assert mock_client.patch.call_count == 4

            # Verify each call used the correct stage
            for i, stage in enumerate(stages):
                call_args = mock_client.patch.call_args_list[i]
                payload = call_args[1]["json"]
                assert payload["stage"] == stage


class TestResumePausedAlerts:
    """Test _resume_paused_alerts() helper function for push-based resume."""

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_success(self):
        """Test successful push-based resume with alerts resumed."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = AsyncMock()
        mock_response.json.return_value = {
            "resumed_count": 3,
            "skipped_count": 1,
            "alert_ids": ["alert-1", "alert-2", "alert-3"],
        }

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Should not raise - test passes if no exception
            await _resume_paused_alerts(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                analysis_group_id=analysis_group_id,
            )

            # Assert correct URL was called
            expected_url = f"{api_base_url}/v1/{tenant_id}/analysis-groups/{analysis_group_id}/resume-paused-alerts"
            mock_client.post.assert_called_once_with(expected_url)

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_no_alerts(self):
        """Test push-based resume when no alerts are paused."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = AsyncMock()
        mock_response.json.return_value = {
            "resumed_count": 0,
            "skipped_count": 0,
            "alert_ids": [],
        }

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Should not raise even when no alerts
            await _resume_paused_alerts(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                analysis_group_id=analysis_group_id,
            )

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_http_error_is_swallowed(self):
        """Test that HTTP errors are swallowed (best-effort)."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=AsyncMock(),
            response=mock_response,
        )

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Should NOT raise - errors are swallowed
            await _resume_paused_alerts(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                analysis_group_id=analysis_group_id,
            )

            # Assert it was called (error was handled internally)
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_timeout_error_is_swallowed(self):
        """Test that timeout errors are swallowed (best-effort)."""
        # Arrange
        api_base_url = "http://test-api:8000"
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client_class.return_value = mock_client

            # Should NOT raise - errors are swallowed
            await _resume_paused_alerts(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                analysis_group_id=analysis_group_id,
            )

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_paused_alerts_url_construction(self):
        """Test that URL is correctly constructed."""
        # Arrange
        api_base_url = "http://api-server:8080"
        tenant_id = "my-tenant"
        analysis_group_id = "group-uuid-123"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json.return_value = {
            "resumed_count": 0,
            "skipped_count": 0,
            "alert_ids": [],
        }

        # Act
        with patch(
            "analysi.agentic_orchestration.jobs.workflow_generation_job.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await _resume_paused_alerts(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                analysis_group_id=analysis_group_id,
            )

            # Assert URL format
            expected_url = "http://api-server:8080/v1/my-tenant/analysis-groups/group-uuid-123/resume-paused-alerts"
            mock_client.post.assert_called_once_with(expected_url)


class TestWorkflowGenerationCredentialFactory:
    """Tests for credential factory integration in workflow generation.

    These tests verify that execute_workflow_generation uses AgentCredentialFactory
    to retrieve credentials instead of environment variables.
    """

    @pytest.mark.asyncio
    async def test_job_gets_credentials_from_factory(self):
        """T1: Test that job uses AgentCredentialFactory for credentials."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.create_executor"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.run_orchestration_with_stages"
            ) as mock_orchestration,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.StageStrategyProvider"
            ) as mock_provider,
        ):
            # Setup mocks
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "sk-ant-test-token",
                "settings": {"max_turns": 100},
            }
            mock_factory_class.return_value = mock_factory

            mock_orchestration.return_value = {"workflow_id": "wf-123"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            mock_provider_instance = MagicMock()
            mock_provider_instance.get_stages.return_value = []
            mock_provider_instance.mode.value = "test"
            mock_provider.return_value = mock_provider_instance

            await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify credential factory was used
            mock_factory.get_agent_credentials.assert_called_once_with(tenant_id)

    @pytest.mark.asyncio
    async def test_job_no_integration_raises(self):
        """T2: No anthropic_agent integration → raises ValueError (Project Leros: raise after cleanup)."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._mark_triggering_analysis_failed"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
        ):
            # Setup factory to raise ValueError (no integration)
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.side_effect = ValueError(
                "No anthropic_agent integration configured"
            )
            mock_factory_class.return_value = mock_factory

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            with pytest.raises(ValueError, match="anthropic_agent"):
                await execute_workflow_generation(
                    ctx={},
                    generation_id=generation_id,
                    tenant_id=tenant_id,
                    alert_data=alert_data,
                )

    @pytest.mark.asyncio
    async def test_job_passes_oauth_token_to_executor(self):
        """T3: Test that oauth_token from factory is passed to executor."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.create_executor"
            ) as mock_create_executor,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.run_orchestration_with_stages"
            ) as mock_orchestration,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.StageStrategyProvider"
            ) as mock_provider,
        ):
            # Setup mocks
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "sk-ant-specific-token-12345",
                "settings": {"max_turns": 100},
            }
            mock_factory_class.return_value = mock_factory

            mock_orchestration.return_value = {"workflow_id": "wf-123"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            mock_provider_instance = MagicMock()
            mock_provider_instance.get_stages.return_value = []
            mock_provider_instance.mode.value = "test"
            mock_provider.return_value = mock_provider_instance

            await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # Verify create_executor was called with oauth_token
            mock_create_executor.assert_called_once()
            call_kwargs = mock_create_executor.call_args[1]
            assert call_kwargs.get("oauth_token") == "sk-ant-specific-token-12345"


class TestRoutingRuleFailureHandling:
    """Tests for Issue #10: Routing rule failure should NOT overwrite successful generation.

    Bug: If _create_routing_rule() fails after generation is updated to status="completed"
    with workflow_id, the exception propagates to the catch-all which overwrites the
    generation to status="failed" and workflow_id=None.
    """

    @pytest.mark.asyncio
    async def test_routing_rule_failure_keeps_generation_completed(self):
        """Routing rule failure should NOT cause _update_workflow_generation to be
        called again with status='failed'."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.create_executor"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.run_orchestration_with_stages"
            ) as mock_orchestration,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ) as mock_update_gen,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._create_routing_rule"
            ) as mock_create_rule,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.StageStrategyProvider"
            ) as mock_provider,
        ):
            # Setup mocks
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "sk-ant-test-token",
                "settings": {"max_turns": 100},
            }
            mock_factory_class.return_value = mock_factory

            mock_orchestration.return_value = {"workflow_id": "wf-123"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            mock_provider_instance = MagicMock()
            mock_provider_instance.get_stages.return_value = []
            mock_provider_instance.mode.value = "test"
            mock_provider.return_value = mock_provider_instance

            # Routing rule creation FAILS
            mock_create_rule.side_effect = Exception("Routing rule API down")

            await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            # _update_workflow_generation should be called ONCE with status="completed"
            # and should NOT be called again with status="failed"
            update_calls = mock_update_gen.call_args_list
            failed_calls = [
                c
                for c in update_calls
                if c.kwargs.get("update_data", {}).get("status") == "failed"
                or (
                    len(c.args) > 3
                    and isinstance(c.args[3], dict)
                    and c.args[3].get("status") == "failed"
                )
            ]
            assert len(failed_calls) == 0, (
                f"Generation should NOT be overwritten to 'failed' when routing rule fails. "
                f"Got {len(failed_calls)} failed update calls."
            )

    @pytest.mark.asyncio
    async def test_routing_rule_failure_preserves_workflow_id(self):
        """Return dict should still have workflow_id even if routing rule fails."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.create_executor"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.run_orchestration_with_stages"
            ) as mock_orchestration,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._create_routing_rule"
            ) as mock_create_rule,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.StageStrategyProvider"
            ) as mock_provider,
        ):
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "sk-ant-test-token",
                "settings": {},
            }
            mock_factory_class.return_value = mock_factory
            mock_orchestration.return_value = {"workflow_id": "wf-abc-123"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            mock_provider_instance = MagicMock()
            mock_provider_instance.get_stages.return_value = []
            mock_provider_instance.mode.value = "test"
            mock_provider.return_value = mock_provider_instance

            mock_create_rule.side_effect = Exception("Routing rule API down")

            result = await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            assert result["workflow_id"] == "wf-abc-123", (
                f"workflow_id should be preserved even if routing rule fails. Got: {result['workflow_id']}"
            )

    @pytest.mark.asyncio
    async def test_routing_rule_failure_returns_completed_status(self):
        """Return dict should have status='completed' even if routing rule fails."""
        from analysi.agentic_orchestration.jobs.workflow_generation_job import (
            execute_workflow_generation,
        )

        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        alert_data = {
            "title": "Test Alert",
            "severity": "high",
            "triggering_event_time": "2025-01-01T00:00:00Z",
            "raw_alert": '{"test": "data"}',
        }

        with (
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AgentCredentialFactory"
            ) as mock_factory_class,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.IntegrationService"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.create_executor"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.run_orchestration_with_stages"
            ) as mock_orchestration,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._update_workflow_generation"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job._create_routing_rule"
            ) as mock_create_rule,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.AsyncSessionLocal"
            ) as mock_session_local,
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.workflow_generation_job.StageStrategyProvider"
            ) as mock_provider,
        ):
            mock_factory = AsyncMock()
            mock_factory.get_agent_credentials.return_value = {
                "oauth_token": "sk-ant-test-token",
                "settings": {},
            }
            mock_factory_class.return_value = mock_factory
            mock_orchestration.return_value = {"workflow_id": "wf-xyz"}

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_local.return_value = mock_session

            mock_provider_instance = MagicMock()
            mock_provider_instance.get_stages.return_value = []
            mock_provider_instance.mode.value = "test"
            mock_provider.return_value = mock_provider_instance

            mock_create_rule.side_effect = Exception("Routing rule API down")

            result = await execute_workflow_generation(
                ctx={},
                generation_id=generation_id,
                tenant_id=tenant_id,
                alert_data=alert_data,
            )

            assert result["status"] == "completed", (
                f"Status should be 'completed' even if routing rule fails. Got: {result['status']}"
            )
