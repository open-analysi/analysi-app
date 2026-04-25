"""Unit tests for JobRun status mirroring callbacks."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from analysi.scheduler.callbacks import update_job_run_status


@pytest.mark.asyncio
class TestUpdateJobRunStatus:
    """Tests for update_job_run_status()."""

    @patch("analysi.scheduler.callbacks.AsyncSessionLocal")
    async def test_updates_status_to_completed(self, mock_session_local):
        """Updates JobRun status to completed."""
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("analysi.scheduler.callbacks.JobRunRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.update_status.return_value = AsyncMock()  # non-None means found
            mock_repo_cls.return_value = mock_repo

            now = datetime.now(UTC)
            result = await update_job_run_status(
                tenant_id="test-tenant",
                job_run_id=uuid4(),
                job_run_created_at=now,
                status="completed",
                started_at=now,
                completed_at=now,
            )
            assert result is True
            mock_repo.update_status.assert_called_once()

    @patch("analysi.scheduler.callbacks.AsyncSessionLocal")
    async def test_updates_status_to_failed(self, mock_session_local):
        """Updates JobRun status to failed."""
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("analysi.scheduler.callbacks.JobRunRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.update_status.return_value = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            now = datetime.now(UTC)
            result = await update_job_run_status(
                tenant_id="test-tenant",
                job_run_id=uuid4(),
                job_run_created_at=now,
                status="failed",
                completed_at=now,
            )
            assert result is True

    @patch("analysi.scheduler.callbacks.AsyncSessionLocal")
    async def test_returns_false_when_not_found(self, mock_session_local):
        """Returns False when JobRun does not exist."""
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("analysi.scheduler.callbacks.JobRunRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.update_status.return_value = None  # not found
            mock_repo_cls.return_value = mock_repo

            result = await update_job_run_status(
                tenant_id="test-tenant",
                job_run_id=uuid4(),
                job_run_created_at=datetime.now(UTC),
                status="completed",
            )
            assert result is False
