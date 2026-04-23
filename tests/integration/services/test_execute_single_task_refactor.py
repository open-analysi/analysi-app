"""
Integration tests for the refactored execute_single_task() API.

Verifies:
- New signature (task_run_id, tenant_id) works correctly
- Returns TaskExecutionResult instead of None
- DB writes are NOT performed by execute_single_task() itself
- execute_and_persist() convenience wrapper produces the same DB end-state as before
- Session isolation: no external session needed
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.task_run import TaskRun
from analysi.repositories.task import TaskRepository
from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus
from analysi.services.task_execution import TaskExecutionService
from analysi.services.task_run import TaskRunService

TENANT_ID = "ithaca-test-tenant"


async def _create_task_and_run(
    session: AsyncSession,
    cy_script: str,
    input_data: dict | None = None,
) -> TaskRun:
    """Helper: create a Task + TaskRun in the DB, return the TaskRun."""
    task_repo = TaskRepository(session)
    task = await task_repo.create(
        {
            "tenant_id": TENANT_ID,
            "name": "Task Execution Refactor Test Task",
            "description": "Test task for execute_single_task refactor",
            "script": cy_script,
        }
    )
    await session.commit()

    task_run_service = TaskRunService()
    task_run = await task_run_service.create_execution(
        session=session,
        tenant_id=TENANT_ID,
        task_id=task.component_id,
        cy_script=None,  # loaded from task
        input_data=input_data or {},
        executor_config=None,
    )
    await session.commit()
    return task_run


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteSingleTaskNewSignature:
    """execute_single_task(task_run_id, tenant_id) returns TaskExecutionResult."""

    async def test_returns_task_execution_result(
        self, integration_test_session: AsyncSession
    ):
        """Calling execute_single_task returns a TaskExecutionResult, not None."""
        task_run = await _create_task_and_run(
            integration_test_session, 'return "hello"'
        )
        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)
        assert isinstance(result, TaskExecutionResult)

    async def test_success_result_fields(self, integration_test_session: AsyncSession):
        """Successful Cy script produces correct result fields."""
        task_run = await _create_task_and_run(
            integration_test_session, 'return "hello from ithaca"'
        )
        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.COMPLETED
        assert result.output_data == "hello from ithaca"
        assert result.error_message is None
        assert result.execution_time_ms >= 0

    async def test_failure_result_fields(self, integration_test_session: AsyncSession):
        """Cy script that errors produces a FAILED result with error_message."""
        task_run = await _create_task_and_run(
            integration_test_session,
            "x = undefined_variable_that_does_not_exist\nreturn x",
        )
        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.FAILED
        assert result.output_data is None
        assert result.error_message is not None
        assert len(result.error_message) > 0

    async def test_result_contains_correct_task_run_id(
        self, integration_test_session: AsyncSession
    ):
        """result.task_run_id matches the task_run_id passed in."""
        task_run = await _create_task_and_run(integration_test_session, "return 42")
        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.task_run_id == task_run.id


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteSingleTaskDoesNotPersist:
    """execute_single_task() must NOT write task_run status to DB."""

    async def test_task_run_status_unchanged_after_execute(
        self, integration_test_session: AsyncSession
    ):
        """After execute_single_task(), task_run.status is still 'running' in DB."""
        task_run = await _create_task_and_run(integration_test_session, 'return "done"')
        original_status = task_run.status  # "running"

        service = TaskExecutionService()
        await service.execute_single_task(task_run.id, TENANT_ID)

        # Reload from DB with a fresh query
        stmt = select(TaskRun).where(TaskRun.id == task_run.id)
        db_result = await integration_test_session.execute(stmt)
        reloaded = db_result.scalar_one_or_none()

        assert reloaded is not None
        assert reloaded.status == original_status  # still "running"


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteAndPersist:
    """execute_and_persist() wrapper updates DB status like the old API did."""

    async def test_success_persists_succeeded_status(
        self, integration_test_session: AsyncSession
    ):
        """After execute_and_persist() with a success script, task_run is 'completed'."""
        task_run = await _create_task_and_run(
            integration_test_session, 'return {"ok": True}'
        )
        task_run_id = task_run.id  # capture before expire_all()
        service = TaskExecutionService()
        await service.execute_and_persist(task_run_id, TENANT_ID)

        # execute_and_persist() commits via its own AsyncSessionLocal (separate DB
        # connection). Expire the test session cache so we see those committed writes.
        integration_test_session.expire_all()

        task_run_service = TaskRunService()
        updated = await task_run_service.get_task_run(
            integration_test_session, TENANT_ID, task_run_id
        )
        assert updated is not None
        assert updated.status == "completed"

    async def test_failure_persists_failed_status(
        self, integration_test_session: AsyncSession
    ):
        """After execute_and_persist() with a failing script, task_run is 'failed'."""
        task_run = await _create_task_and_run(
            integration_test_session,
            "x = undefined_xyz\nreturn x",
        )
        task_run_id = task_run.id  # capture before expire_all()
        service = TaskExecutionService()
        await service.execute_and_persist(task_run_id, TENANT_ID)

        # execute_and_persist() commits via its own AsyncSessionLocal (separate DB
        # connection). Expire the test session cache so we see those committed writes.
        integration_test_session.expire_all()

        task_run_service = TaskRunService()
        updated = await task_run_service.get_task_run(
            integration_test_session, TENANT_ID, task_run_id
        )
        assert updated is not None
        assert updated.status == "failed"


@pytest.mark.asyncio
@pytest.mark.integration
class TestSessionIsolation:
    """execute_single_task() manages its own session — no caller session needed."""

    async def test_works_without_external_session(
        self, integration_test_session: AsyncSession
    ):
        """execute_single_task() succeeds with only IDs — no session passed by caller."""
        task_run = await _create_task_and_run(
            integration_test_session, 'return "isolated"'
        )
        # No session argument — service must create its own
        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.COMPLETED
        assert result.output_data == "isolated"

    async def test_two_sequential_tasks_both_succeed(
        self, integration_test_session: AsyncSession
    ):
        """Two sequential execute_single_task() calls both return COMPLETED."""
        task_run_1 = await _create_task_and_run(
            integration_test_session, 'return "task one"'
        )
        task_run_2 = await _create_task_and_run(
            integration_test_session, 'return "task two"'
        )

        service = TaskExecutionService()
        result_1 = await service.execute_single_task(task_run_1.id, TENANT_ID)
        result_2 = await service.execute_single_task(task_run_2.id, TENANT_ID)

        assert result_1.status == TaskExecutionStatus.COMPLETED
        assert result_1.output_data == "task one"
        assert result_2.status == TaskExecutionStatus.COMPLETED
        assert result_2.output_data == "task two"


@pytest.mark.asyncio
@pytest.mark.integration
class TestLogCapture:
    """execute_single_task() captures log() calls from Cy scripts."""

    async def test_log_calls_appear_in_result(
        self, integration_test_session: AsyncSession
    ):
        """Cy script calling log() produces non-empty log_entries in TaskExecutionResult."""
        script = 'log("hello")\nlog("world")\nreturn "done"'
        task_run = await _create_task_and_run(integration_test_session, script)

        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.COMPLETED
        assert result.output_data == "done"
        # Log entries are dicts with {ts, message}
        messages = [
            e["message"] if isinstance(e, dict) else e for e in result.log_entries
        ]
        assert messages == ["hello", "world"]

    async def test_no_log_calls_gives_empty_list(
        self, integration_test_session: AsyncSession
    ):
        """Cy script with no log() calls produces an empty log_entries list."""
        task_run = await _create_task_and_run(
            integration_test_session, 'return "quiet"'
        )

        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.COMPLETED
        assert result.log_entries == []

    async def test_log_entries_captured_even_on_failure(
        self, integration_test_session: AsyncSession
    ):
        """Log entries written before a script failure are still captured."""
        script = 'log("about to fail")\nx = undefined_var\nreturn x'
        task_run = await _create_task_and_run(integration_test_session, script)

        service = TaskExecutionService()
        result = await service.execute_single_task(task_run.id, TENANT_ID)

        assert result.status == TaskExecutionStatus.FAILED
        # Log entries are dicts with {ts, message}
        messages = [
            e["message"] if isinstance(e, dict) else e for e in result.log_entries
        ]
        assert messages == ["about to fail"]
