"""Unit tests for the post-execution health check hook.

Project Symi: Verifies that _maybe_update_integration_health() correctly
identifies health check tasks and updates Integration.health_status.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.task_execution import TaskExecutionService

# Patches target the source modules (the method uses local imports)
_PATCHES = {
    "session_local": "analysi.db.session.AsyncSessionLocal",
    "repo": "analysi.repositories.integration_repository.IntegrationRepository",
}


def _session_returning(integration_id_or_none):
    """Mock session whose execute() returns integration_id from the JOIN query.

    The hook does a single JOIN query (TaskRun→Task) filtered to
    managed_resource_key='health_check'.  If the task isn't a health
    check, the query returns no rows (scalar_one_or_none → None).
    """
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = integration_id_or_none
    session.execute.return_value = exec_result
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
class TestMaybeUpdateIntegrationHealth:
    """Tests for _maybe_update_integration_health fire-and-forget hook."""

    async def test_updates_health_for_completed_healthy(self):
        """completed + healthy=true → Integration.health_status = 'healthy'."""
        session = _session_returning("splunk-prod")

        with (
            patch(_PATCHES["session_local"]) as mock_sl,
            patch(_PATCHES["repo"]) as mock_repo_cls,
        ):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            svc = TaskExecutionService()
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="completed",
                output_data={"healthy": True},
            )

            mock_repo.update_health_status.assert_called_once()
            kw = mock_repo.update_health_status.call_args[1]
            assert kw["health_status"] == "healthy"
            assert kw["integration_id"] == "splunk-prod"
            assert kw["tenant_id"] == "t-test"

    async def test_unhealthy_when_healthy_false(self):
        """completed + healthy=false → unhealthy."""
        session = _session_returning("splunk-prod")

        with (
            patch(_PATCHES["session_local"]) as mock_sl,
            patch(_PATCHES["repo"]) as mock_repo_cls,
        ):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            svc = TaskExecutionService()
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="completed",
                output_data={"healthy": False},
            )

            kw = mock_repo.update_health_status.call_args[1]
            assert kw["health_status"] == "unhealthy"

    async def test_unknown_when_task_failed(self):
        """failed → unknown health status."""
        session = _session_returning("splunk-prod")

        with (
            patch(_PATCHES["session_local"]) as mock_sl,
            patch(_PATCHES["repo"]) as mock_repo_cls,
        ):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            svc = TaskExecutionService()
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="failed",
                output_data=None,
            )

            kw = mock_repo.update_health_status.call_args[1]
            assert kw["health_status"] == "unknown"

    async def test_skips_non_health_check_task(self):
        """Non-health-check tasks: JOIN query returns None → no update."""
        session = _session_returning(None)  # query finds no matching health_check task

        with (
            patch(_PATCHES["session_local"]) as mock_sl,
            patch(_PATCHES["repo"]) as mock_repo_cls,
        ):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            svc = TaskExecutionService()
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="completed",
                output_data={"created": 5},
            )

            mock_repo.update_health_status.assert_not_called()

    async def test_skips_when_no_task_run_found(self):
        """If TaskRun doesn't exist, JOIN returns None → no update."""
        session = _session_returning(None)

        with (
            patch(_PATCHES["session_local"]) as mock_sl,
            patch(_PATCHES["repo"]) as mock_repo_cls,
        ):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            svc = TaskExecutionService()
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="completed",
                output_data={"healthy": True},
            )

            mock_repo.update_health_status.assert_not_called()

    async def test_failure_does_not_propagate(self):
        """DB errors in the hook are swallowed (fire-and-forget)."""
        with patch(_PATCHES["session_local"]) as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("DB down")
            )
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = TaskExecutionService()
            # Should not raise
            await svc._maybe_update_integration_health(
                task_run_id=uuid4(),
                tenant_id="t-test",
                status="completed",
                output_data={"healthy": True},
            )
