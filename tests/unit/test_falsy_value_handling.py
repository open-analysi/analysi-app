"""
Unit tests for proper handling of falsy values in task execution.

Tests that falsy values (False, 0, empty string) are properly stored
and returned, not converted to None/null.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.models.task_run import TaskRun
from analysi.services.task_run import TaskRunService


class TestFalsyValueHandling:
    """Test suite for ensuring falsy values are preserved in task execution."""

    @pytest.fixture
    def mock_task_run(self):
        """Create a mock TaskRun object."""
        task_run = MagicMock(spec=TaskRun)
        task_run.id = uuid4()
        task_run.tenant_id = "test-tenant"
        task_run.status = "running"
        task_run.started_at = None
        task_run.completed_at = None
        task_run.duration = None
        task_run.output_type = None
        task_run.output_location = None
        return task_run

    @pytest.fixture
    def mock_storage_manager(self):
        """Create a mock StorageManager."""
        storage_manager = MagicMock()
        storage_manager.store = AsyncMock(
            return_value={
                "storage_type": "database",
                "location": "task_run_outputs:123",
                "content_type": "application/json",
            }
        )
        return storage_manager

    @pytest.fixture
    def task_run_service(self, mock_storage_manager):
        """Create TaskRunService with mocked dependencies."""
        service = TaskRunService()
        service.storage_manager = mock_storage_manager
        service.repository = MagicMock()
        service.repository.update = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_store_output_with_false_value(self, task_run_service, mock_task_run):
        """Test that False value is properly stored, not skipped."""
        # Store False as output
        await task_run_service.store_output_data(mock_task_run, False)

        # Verify storage was called with False
        task_run_service.storage_manager.store.assert_called_once()
        call_args = task_run_service.storage_manager.store.call_args

        # The content should be JSON string "false" (without quotes in JSON)
        assert "false" in call_args.kwargs["content"].lower()

    @pytest.mark.asyncio
    async def test_store_output_with_zero_value(self, task_run_service, mock_task_run):
        """Test that 0 value is properly stored, not skipped."""
        # Store 0 as output
        await task_run_service.store_output_data(mock_task_run, 0)

        # Verify storage was called with 0
        task_run_service.storage_manager.store.assert_called_once()
        call_args = task_run_service.storage_manager.store.call_args

        # The content should be JSON string "0"
        assert "0" in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_store_output_with_empty_string(
        self, task_run_service, mock_task_run
    ):
        """Test that empty string is properly stored, not skipped."""
        # Store empty string as output
        await task_run_service.store_output_data(mock_task_run, "")

        # Verify storage was called with empty string
        task_run_service.storage_manager.store.assert_called_once()
        call_args = task_run_service.storage_manager.store.call_args

        # The content should be JSON string '""'
        assert '""' in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_update_status_with_false_output(
        self, task_run_service, mock_task_run
    ):
        """Test that update_status properly handles False output."""
        # Mock session and task run retrieval
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_task_run
        )

        # Call update_status with False output
        await task_run_service.update_status(
            mock_session, mock_task_run.id, "completed", output_data=False
        )

        # Verify store_output_data was called (not skipped)
        task_run_service.storage_manager.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_with_zero_output(
        self, task_run_service, mock_task_run
    ):
        """Test that update_status properly handles 0 output."""
        # Mock session and task run retrieval
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_task_run
        )

        # Call update_status with 0 output
        await task_run_service.update_status(
            mock_session, mock_task_run.id, "completed", output_data=0
        )

        # Verify store_output_data was called (not skipped)
        task_run_service.storage_manager.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_with_empty_string_output(
        self, task_run_service, mock_task_run
    ):
        """Test that update_status properly handles empty string output."""
        # Mock session and task run retrieval
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_task_run
        )

        # Call update_status with empty string output
        await task_run_service.update_status(
            mock_session, mock_task_run.id, "completed", output_data=""
        )

        # Verify store_output_data was called (not skipped)
        task_run_service.storage_manager.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_with_none_output(
        self, task_run_service, mock_task_run
    ):
        """Test that update_status properly skips None output."""
        # Mock session and task run retrieval
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_task_run
        )

        # Call update_status with None output
        await task_run_service.update_status(
            mock_session, mock_task_run.id, "completed", output_data=None
        )

        # Verify store_output_data was NOT called for None
        task_run_service.storage_manager.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_falsy_dict_values_preserved(self, task_run_service, mock_task_run):
        """Test that falsy values in dict outputs are preserved."""
        output = {
            "success": False,
            "count": 0,
            "message": "",
            "data": None,
            "items": [],
        }

        await task_run_service.store_output_data(mock_task_run, output)

        # Verify storage was called
        task_run_service.storage_manager.store.assert_called_once()
        call_args = task_run_service.storage_manager.store.call_args
        content = call_args.kwargs["content"]

        # Verify all falsy values are preserved in JSON
        assert '"success": false' in content
        assert '"count": 0' in content
        assert '"message": ""' in content
        assert '"data": null' in content
        assert '"items": []' in content
