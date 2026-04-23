"""
Unit tests for TaskExecutionStatus and TaskExecutionResult.

Tests the types introduced in src/analysi/schemas/task_execution.py
and the _load_task_run() helper on TaskExecutionService.
"""

import dataclasses
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus


@pytest.mark.unit
class TestTaskExecutionStatus:
    """Tests for TaskExecutionStatus StrEnum."""

    def test_completed_value(self):
        """COMPLETED equals the string 'completed'."""
        assert TaskExecutionStatus.COMPLETED == "completed"

    def test_failed_value(self):
        """FAILED equals the string 'failed'."""
        assert TaskExecutionStatus.FAILED == "failed"

    def test_is_str_subclass(self):
        """TaskExecutionStatus values are str instances (StrEnum behavior)."""
        assert isinstance(TaskExecutionStatus.COMPLETED, str)
        assert isinstance(TaskExecutionStatus.FAILED, str)

    def test_invalid_value_raises(self):
        """Constructing from an unknown string raises ValueError."""
        with pytest.raises(ValueError):
            TaskExecutionStatus("unknown_status")

    def test_can_compare_with_plain_string(self):
        """Status can be compared directly with plain strings."""
        status = TaskExecutionStatus.COMPLETED
        assert status == "completed"
        assert status == "completed"


@pytest.mark.unit
class TestTaskExecutionResult:
    """Tests for TaskExecutionResult dataclass."""

    def test_is_dataclass(self):
        """TaskExecutionResult is a dataclass."""
        assert dataclasses.is_dataclass(TaskExecutionResult)

    def test_success_fields(self):
        """Can create a successful result with all expected fields."""
        task_run_id = uuid4()
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data={"answer": 42},
            error_message=None,
            execution_time_ms=123,
            task_run_id=task_run_id,
        )
        assert result.status == TaskExecutionStatus.COMPLETED
        assert result.output_data == {"answer": 42}
        assert result.error_message is None
        assert result.execution_time_ms == 123
        assert result.task_run_id == task_run_id

    def test_failure_fields(self):
        """Can create a failure result with error_message and no output_data."""
        task_run_id = uuid4()
        result = TaskExecutionResult(
            status=TaskExecutionStatus.FAILED,
            output_data=None,
            error_message="Something went wrong",
            execution_time_ms=50,
            task_run_id=task_run_id,
        )
        assert result.status == TaskExecutionStatus.FAILED
        assert result.output_data is None
        assert result.error_message == "Something went wrong"

    def test_status_field_accepts_str_enum(self):
        """Status field works with TaskExecutionStatus enum values."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data=None,
            error_message=None,
            execution_time_ms=0,
            task_run_id=uuid4(),
        )
        assert result.status == "completed"  # StrEnum compares as string

    def test_task_run_id_is_uuid(self):
        """task_run_id field holds a UUID."""
        uid = uuid4()
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data={},
            error_message=None,
            execution_time_ms=1,
            task_run_id=uid,
        )
        assert isinstance(result.task_run_id, UUID)
        assert result.task_run_id == uid

    def test_zero_execution_time_is_valid(self):
        """execution_time_ms of 0 is a valid value."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data=None,
            error_message=None,
            execution_time_ms=0,
            task_run_id=uuid4(),
        )
        assert result.execution_time_ms == 0


@pytest.mark.unit
class TestTaskExecutionResultLogEntries:
    """Tests for the log_entries field on TaskExecutionResult (log capture)."""

    def test_log_entries_defaults_to_empty_list(self):
        """log_entries defaults to [] when not provided."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data=None,
            error_message=None,
            execution_time_ms=0,
            task_run_id=uuid4(),
        )
        assert result.log_entries == []

    def test_log_entries_can_be_set(self):
        """log_entries stores the provided list of strings."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data={"x": 1},
            error_message=None,
            execution_time_ms=10,
            task_run_id=uuid4(),
            log_entries=["first message", "second message"],
        )
        assert result.log_entries == ["first message", "second message"]

    def test_log_entries_on_failure_result(self):
        """log_entries is available on failed results too."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.FAILED,
            output_data=None,
            error_message="boom",
            execution_time_ms=5,
            task_run_id=uuid4(),
            log_entries=["logged before crash"],
        )
        assert result.log_entries == ["logged before crash"]

    def test_log_entries_is_list_of_strings(self):
        """log_entries holds plain strings, not other types."""
        result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data=None,
            error_message=None,
            execution_time_ms=0,
            task_run_id=uuid4(),
            log_entries=["a", "b", "c"],
        )
        assert all(isinstance(entry, str) for entry in result.log_entries)


@pytest.mark.unit
class TestLoadTaskRun:
    """Tests for TaskExecutionService._load_task_run() (mocked session)."""

    @pytest.mark.asyncio
    async def test_load_task_run_success(self):
        """Returns TaskRun when found in the DB."""
        from analysi.services.task_execution import TaskExecutionService

        task_run_id = uuid4()
        tenant_id = "test_tenant"

        mock_task_run = MagicMock()
        mock_task_run.id = task_run_id
        mock_task_run.tenant_id = tenant_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskExecutionService()
        result = await service._load_task_run(mock_session, task_run_id, tenant_id)

        assert result is mock_task_run

    @pytest.mark.asyncio
    async def test_load_task_run_not_found_raises(self):
        """Raises ValueError when task_run_id is not found."""
        from analysi.services.task_execution import TaskExecutionService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskExecutionService()
        with pytest.raises(ValueError, match="not found"):
            await service._load_task_run(mock_session, uuid4(), "test_tenant")
