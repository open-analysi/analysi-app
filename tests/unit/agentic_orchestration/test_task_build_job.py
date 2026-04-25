"""Unit tests for task_build_job — standalone task generation/modification."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.agentic_orchestration.jobs.task_build_job import (
    _find_recently_created_task,
    _verify_task_modified,
    execute_task_build,
)

ORIGINAL_SCRIPT = "ip = input.primary_ioc_value\nreturn ip"
MODIFIED_SCRIPT = (
    "ip = input.primary_ioc_value\nresult = app::vt::ip_rep(ip=ip)\nreturn result"
)


class TestVerifyTaskModified:
    """Tests for _verify_task_modified post-flight verification."""

    def _make_mock_client(self, json_response: dict, status_code: int = 200):
        """Create a properly mocked httpx.AsyncClient with sync json()/raise_for_status()."""
        mock_response = MagicMock()  # sync methods: json(), raise_for_status()
        mock_response.json.return_value = json_response
        mock_response.status_code = status_code
        if status_code >= 400:
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
            )
        else:
            mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    def _existing_task(self, script=ORIGINAL_SCRIPT):
        return {
            "cy_name": "vt_ip_reputation",
            "task_id": "abc-123",
            "script": script,
        }

    @pytest.mark.asyncio
    async def test_returns_task_when_script_and_timestamp_changed(self):
        """Both script changed AND updated_at bumped → high-confidence success."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
        mock_client = self._make_mock_client(
            {
                "id": "abc-123",
                "cy_name": "vt_ip_reputation",
                "script": MODIFIED_SCRIPT,
                "updated_at": "2026-02-25T10:05:00+00:00",
            }
        )

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        assert result is not None
        assert result["cy_name"] == "vt_ip_reputation"
        # Verify it fetched by ID, not by cy_name
        mock_client.get.assert_called_once_with(
            "http://localhost:8001/v1/test-tenant/tasks/abc-123"
        )

    @pytest.mark.asyncio
    async def test_returns_task_when_only_timestamp_changed(self):
        """Timestamp bumped but script unchanged — metadata-only change, still accepted."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
        mock_client = self._make_mock_client(
            {
                "id": "abc-123",
                "cy_name": "vt_ip_reputation",
                "script": ORIGINAL_SCRIPT,  # same script
                "updated_at": "2026-02-25T10:05:00+00:00",  # but timestamp bumped
            }
        )

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_only_script_changed_stale_edit(self):
        """Script differs but timestamp old → possible stale edit, rejected."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
        mock_client = self._make_mock_client(
            {
                "id": "abc-123",
                "cy_name": "vt_ip_reputation",
                "script": MODIFIED_SCRIPT,  # script changed
                "updated_at": "2026-02-25T09:55:00+00:00",  # but timestamp old
            }
        )

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        # Stale script diff without temporal evidence is NOT attributed to this run
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_changed(self):
        """Neither script nor timestamp changed → not modified."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
        mock_client = self._make_mock_client(
            {
                "id": "abc-123",
                "cy_name": "vt_ip_reputation",
                "script": ORIGINAL_SCRIPT,
                "updated_at": "2026-02-25T09:55:00+00:00",
            }
        )

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_task_not_found(self):
        """Task not found (404) → None."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)
        mock_client = self._make_mock_client(
            {"detail": "Task not found"}, status_code=404
        )

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_task_id(self):
        """Missing task_id in existing_task → None (graceful)."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)

        result = await _verify_task_modified(
            api_base_url="http://localhost:8001",
            tenant_id="test-tenant",
            existing_task={"cy_name": "vt_ip_reputation"},  # no task_id
            job_start_time=job_start,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        """HTTP error → None (graceful, doesn't raise)."""
        job_start = datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC)

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _verify_task_modified(
                api_base_url="http://localhost:8001",
                tenant_id="test-tenant",
                existing_task=self._existing_task(),
                job_start_time=job_start,
            )

        assert result is None


class TestFindRecentlyCreatedTask:
    """Tests for _find_recently_created_task post-flight verification."""

    def _make_mock_client(self, json_response, status_code: int = 200):
        """Create a mock client whose .json() returns the unwrapped payload."""
        mock_response = MagicMock()
        mock_response.json.return_value = json_response
        mock_response.status_code = status_code
        if status_code >= 400:
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=mock_response
            )
        else:
            mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    @pytest.mark.asyncio
    async def test_finds_task_from_unwrapped_list(self):
        """InternalAsyncClient returns a plain list (Sifnos unwrapped), not {'tasks': [...]}."""
        recent_task = {
            "id": "new-123",
            "cy_name": "vt_ip_reputation",
            "created_at": datetime.now(UTC).isoformat(),
        }
        # InternalAsyncClient unwraps envelope: response.json() → [task, ...]
        mock_client = self._make_mock_client([recent_task])

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _find_recently_created_task(
                "http://localhost:8001", "test-tenant"
            )

        assert result is not None
        assert result["cy_name"] == "vt_ip_reputation"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_list(self):
        """No tasks returned → None."""
        mock_client = self._make_mock_client([])

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _find_recently_created_task(
                "http://localhost:8001", "test-tenant"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_old_task(self):
        """Task created > 5 minutes ago → None."""
        old_task = {
            "id": "old-456",
            "cy_name": "old_task",
            "created_at": "2026-04-26T00:00:00+00:00",
        }
        mock_client = self._make_mock_client([old_task])

        with patch(
            "analysi.agentic_orchestration.jobs.task_build_job.InternalAsyncClient",
            return_value=mock_client,
        ):
            result = await _find_recently_created_task(
                "http://localhost:8001", "test-tenant"
            )

        assert result is None


class TestExecuteTaskBuildModeBranching:
    """Test that execute_task_build correctly branches on existing_task."""

    @pytest.mark.asyncio
    async def test_modify_mode_passes_existing_task_to_agent(self):
        """When input_context has existing_task, it's forwarded to agent_context."""
        existing_task = {
            "task_id": "abc-123",
            "cy_name": "vt_ip_reputation",
            "name": "VT IP Reputation",
            "script": "return input",
            "description": "Check IP",
            "data_samples": [],
            "directive": None,
            "function": "enrichment",
            "scope": "processing",
        }
        input_context = {
            "description": "Add AbuseIPDB check",
            "existing_task": existing_task,
        }

        captured_context = {}

        async def mock_run_agent(workspace, executor, context, callback):
            captured_context.update(context)
            return {}, AsyncMock()

        with (
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.TaskGenerationApiClient"
            ) as mock_client_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AsyncSessionLocal"
            ) as mock_session_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AgentCredentialFactory"
            ) as mock_cred_cls,
            patch("analysi.agentic_orchestration.jobs.task_build_job.create_executor"),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AgentWorkspace"
            ) as mock_workspace_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.run_task_builder_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job._verify_task_modified",
                return_value={
                    "id": "abc-123",
                    "cy_name": "vt_ip_reputation",
                },
            ),
        ):
            # Setup mocks
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_cred = AsyncMock()
            mock_cred.get_agent_credentials.return_value = {"oauth_token": "test-token"}
            mock_cred_cls.return_value = mock_cred

            mock_workspace = AsyncMock()
            mock_workspace_cls.return_value = mock_workspace

            result = await execute_task_build(
                ctx={},
                run_id="run-123",
                tenant_id="test-tenant",
                description="Add AbuseIPDB check",
                alert_id=None,
                input_context=input_context,
            )

        assert result["status"] == "completed"
        assert result["task_id"] == "abc-123"
        # The key assertion: existing_task was forwarded to agent
        assert "existing_task" in captured_context
        assert captured_context["existing_task"]["cy_name"] == "vt_ip_reputation"

    @pytest.mark.asyncio
    async def test_create_mode_does_not_include_existing_task(self):
        """When no existing_task, agent_context should not contain it."""
        input_context = {"description": "Build new IP reputation task"}

        captured_context = {}

        async def mock_run_agent(workspace, executor, context, callback):
            captured_context.update(context)
            return {}, AsyncMock()

        with (
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.TaskGenerationApiClient"
            ) as mock_client_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AsyncSessionLocal"
            ) as mock_session_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AgentCredentialFactory"
            ) as mock_cred_cls,
            patch("analysi.agentic_orchestration.jobs.task_build_job.create_executor"),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.TenantSkillsSyncer"
            ),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.AgentWorkspace"
            ) as mock_workspace_cls,
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job.run_task_builder_agent",
                side_effect=mock_run_agent,
            ),
            patch(
                "analysi.agentic_orchestration.jobs.task_build_job._find_recently_created_task",
                return_value={
                    "id": "new-task-456",
                    "cy_name": "new_ip_check",
                },
            ),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            mock_cred = AsyncMock()
            mock_cred.get_agent_credentials.return_value = {"oauth_token": "test-token"}
            mock_cred_cls.return_value = mock_cred

            mock_workspace = AsyncMock()
            mock_workspace_cls.return_value = mock_workspace

            result = await execute_task_build(
                ctx={},
                run_id="run-456",
                tenant_id="test-tenant",
                description="Build new IP reputation task",
                alert_id=None,
                input_context=input_context,
            )

        assert result["status"] == "completed"
        # The key assertion: no existing_task in agent context
        assert "existing_task" not in captured_context
