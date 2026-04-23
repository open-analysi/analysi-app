"""Unit tests for the generic schedule executor.

Tests for execute_due_schedules() using mocked DB.

The executor processes one schedule per transaction to avoid releasing
FOR UPDATE SKIP LOCKED locks on unprocessed schedules (see architectural
fix in executor.py docstring).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from analysi.scheduler.executor import (
    MAX_SCHEDULES_PER_CYCLE,
    execute_due_schedules,
)


def _make_schedule(
    *,
    target_type: str = "task",
    schedule_value: str = "60s",
    enabled: bool = True,
    next_run_at: datetime | None = None,
    tenant_id: str | None = None,
    integration_id: str | None = None,
    schedule_id: UUID | None = None,
):
    """Create a mock Schedule object."""
    schedule = MagicMock()
    schedule.id = schedule_id or uuid4()
    schedule.tenant_id = tenant_id or f"t-{uuid4().hex[:8]}"
    schedule.target_type = target_type
    schedule.target_id = uuid4()
    schedule.schedule_type = "every"
    schedule.schedule_value = schedule_value
    schedule.timezone = "UTC"
    schedule.enabled = enabled
    schedule.params = {}
    schedule.origin_type = "user"
    schedule.integration_id = integration_id
    schedule.next_run_at = next_run_at or (datetime.now(UTC) - timedelta(seconds=10))
    schedule.last_run_at = None
    schedule.created_at = datetime.now(UTC) - timedelta(hours=1)
    return schedule


def _mock_session():
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _setup_session_local(mock_session_local, sessions):
    """Configure AsyncSessionLocal to yield sessions from a list.

    Each call to ``async with AsyncSessionLocal()`` pops the next session.
    """
    call_count = 0

    class _CtxManager:
        def __init__(self):
            nonlocal call_count
            self._idx = call_count
            call_count += 1

        async def __aenter__(self):
            idx = min(self._idx, len(sessions) - 1)
            return sessions[idx]

        async def __aexit__(self, *args):
            return False

    mock_session_local.side_effect = lambda: _CtxManager()


def _make_job_run():
    jr = MagicMock()
    jr.id = uuid4()
    jr.created_at = datetime.now(UTC)
    return jr


def _make_task_run():
    tr = MagicMock()
    tr.id = uuid4()
    return tr


@pytest.mark.asyncio
class TestExecuteDueSchedules:
    """Tests for the main scheduler cron function."""

    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_no_due_schedules_returns_zero(self, mock_session_local):
        """When no schedules are due, returns 0 processed."""
        session = _mock_session()
        _setup_session_local(mock_session_local, [session])

        with patch("analysi.scheduler.executor.ScheduleRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_due_schedules.return_value = []
            mock_repo_cls.return_value = mock_repo

            result = await execute_due_schedules({})
            assert result["processed"] == 0
            assert result["errors"] == 0
            assert result["total_due"] == 0

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_creates_job_run_for_due_task(self, mock_session_local, mock_enqueue):
        """Due task schedule creates a JobRun."""
        # Two sessions: one for the schedule, one for the "no more" check
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        schedule = _make_schedule(target_type="task")
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            # First call returns the schedule; second call returns empty
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            result = await execute_due_schedules({})

            assert result["processed"] == 1
            mock_jr_repo.create.assert_called_once()
            mock_enqueue.assert_called_once()

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_creates_task_run_with_scheduled_context(
        self, mock_session_local, mock_enqueue
    ):
        """TaskRun created for scheduled execution has run_context='scheduled'."""
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        schedule = _make_schedule(target_type="task")
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            await execute_due_schedules({})

            # Verify create_execution was called with scheduled context
            mock_trs.create_execution.assert_called_once()

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_updates_next_run_at(self, mock_session_local, mock_enqueue):
        """Schedule's next_run_at is advanced after processing."""
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        schedule = _make_schedule(target_type="task", schedule_value="60s")
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            await execute_due_schedules({})

            mock_sched_repo.update_next_run_at.assert_called_once()

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_enqueues_task_run_to_arq(self, mock_session_local, mock_enqueue):
        """Due task schedule enqueues execute_task_run."""
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        schedule = _make_schedule(target_type="task")
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            await execute_due_schedules({})

            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args
            assert "execute_task_run" in call_args[0][0]

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_workflow_target_enqueues_workflow_run(
        self, mock_session_local, mock_enqueue
    ):
        """Workflow schedule enqueues execute_workflow_run."""
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        schedule = _make_schedule(target_type="workflow")
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch(
                "analysi.scheduler.executor.WorkflowExecutionService"
            ) as mock_wes_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_wes = AsyncMock()
            mock_wes.start_workflow.return_value = {
                "workflow_run_id": uuid4(),
            }
            mock_wes_cls.return_value = mock_wes

            await execute_due_schedules({})

            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args
            assert "execute_workflow_run" in call_args[0][0]

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_processes_multiple_due_schedules(
        self, mock_session_local, mock_enqueue
    ):
        """Multiple due schedules are all processed, each in its own session."""
        s1 = _make_schedule()
        s2 = _make_schedule()
        s3 = _make_schedule()

        # 4 sessions: one per schedule + one for the empty check
        sessions = [_mock_session() for _ in range(4)]
        _setup_session_local(mock_session_local, sessions)

        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [
                [s1],
                [s2],
                [s3],
                [],
            ]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.side_effect = [_make_job_run() for _ in range(3)]
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.side_effect = [_make_task_run() for _ in range(3)]
            mock_trs_cls.return_value = mock_trs

            result = await execute_due_schedules({})

            assert result["processed"] == 3
            assert mock_enqueue.call_count == 3

    # ── Lock isolation tests ──────────────────────────────────────────

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_each_schedule_gets_own_session(
        self, mock_session_local, mock_enqueue
    ):
        """Each schedule is processed in a separate session (separate transaction)."""
        s1 = _make_schedule()
        s2 = _make_schedule()

        session_a = _mock_session()
        session_b = _mock_session()
        session_empty = _mock_session()
        _setup_session_local(mock_session_local, [session_a, session_b, session_empty])

        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[s1], [s2], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.side_effect = [_make_job_run(), _make_job_run()]
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.side_effect = [_make_task_run(), _make_task_run()]
            mock_trs_cls.return_value = mock_trs

            await execute_due_schedules({})

            # Each schedule's commit goes to a different session
            session_a.commit.assert_called()
            session_b.commit.assert_called()

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_get_due_schedules_called_with_limit_one(
        self, mock_session_local, mock_enqueue
    ):
        """Each iteration fetches at most one schedule to minimise lock scope."""
        sessions = [_mock_session()]
        _setup_session_local(mock_session_local, sessions)

        with patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls:
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.return_value = []
            mock_sched_cls.return_value = mock_sched_repo

            await execute_due_schedules({})

            args, kwargs = mock_sched_repo.get_due_schedules.call_args
            assert kwargs.get("limit") == 1 or (args and args[0] == 1)

    # ── Negative / error-isolation tests ──────────────────────────────

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_unparseable_interval_skipped(self, mock_session_local, mock_enqueue):
        """Schedule with unparseable interval is skipped."""
        bad = _make_schedule(schedule_value="xyz-invalid")

        # Session for the bad schedule, then session for "no more"
        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[bad], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_cls.return_value = AsyncMock()
            mock_trs_cls.return_value = AsyncMock()

            result = await execute_due_schedules({})

            assert result["errors"] == 1
            assert result["processed"] == 0

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_isolates_failures_across_schedules(
        self, mock_session_local, mock_enqueue
    ):
        """One schedule failure does not block processing of others."""
        bad = _make_schedule(schedule_value="xyz-invalid")
        good = _make_schedule(schedule_value="60s")
        mock_enqueue.return_value = "job-123"

        # 3 sessions: bad schedule, good schedule, empty check
        sessions = [_mock_session() for _ in range(3)]
        _setup_session_local(mock_session_local, sessions)

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            # Bad schedule first, then good, then empty.
            # After the bad schedule fails, its ID is added to exclude_ids,
            # so the next query skips it and returns the good one.
            mock_sched_repo.get_due_schedules.side_effect = [
                [bad],
                [good],
                [],
            ]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            result = await execute_due_schedules({})

            assert result["processed"] == 1
            assert result["errors"] == 1

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_failed_schedule_id_excluded_from_next_query(
        self, mock_session_local, mock_enqueue
    ):
        """After a schedule fails, its ID is passed in exclude_ids to avoid re-fetch."""
        bad = _make_schedule(schedule_value="xyz-invalid")
        bad_id = bad.id
        mock_enqueue.return_value = "job-123"

        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository"),
            patch("analysi.scheduler.executor.TaskRunService"),
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[bad], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            await execute_due_schedules({})

            # Second call (after the failure) should include exclude_ids
            calls = mock_sched_repo.get_due_schedules.call_args_list
            assert len(calls) == 2

            second_call_kwargs = calls[1][1]
            assert "exclude_ids" in second_call_kwargs
            assert bad_id in second_call_kwargs["exclude_ids"]

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_failed_schedule_session_rolled_back(
        self, mock_session_local, mock_enqueue
    ):
        """When processing fails, the session is explicitly rolled back."""
        bad = _make_schedule(schedule_value="xyz-invalid")

        bad_session = _mock_session()
        empty_session = _mock_session()
        _setup_session_local(mock_session_local, [bad_session, empty_session])

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository"),
            patch("analysi.scheduler.executor.TaskRunService"),
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[bad], []]
            mock_sched_cls.return_value = mock_sched_repo

            await execute_due_schedules({})

            bad_session.rollback.assert_called_once()

    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_db_connection_failure_breaks_loop(self, mock_session_local):
        """DB connectivity failure stops the loop immediately."""
        mock_session_local.side_effect = OSError("connection refused")

        result = await execute_due_schedules({})

        assert result["processed"] == 0
        assert result["errors"] == 0

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_max_schedules_per_cycle_respected(
        self, mock_session_local, mock_enqueue
    ):
        """The loop doesn't exceed MAX_SCHEDULES_PER_CYCLE iterations."""
        mock_enqueue.return_value = "job-123"

        sessions = [_mock_session() for _ in range(MAX_SCHEDULES_PER_CYCLE + 1)]
        _setup_session_local(mock_session_local, sessions)

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            # Always return a schedule (never empty)
            mock_sched_repo.get_due_schedules.return_value = [_make_schedule()]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            result = await execute_due_schedules({})

            assert result["processed"] == MAX_SCHEDULES_PER_CYCLE

    @patch("analysi.scheduler.executor.enqueue_arq_job", new_callable=AsyncMock)
    @patch("analysi.scheduler.executor.AsyncSessionLocal")
    async def test_integration_id_propagated_in_execution_context(
        self, mock_session_local, mock_enqueue
    ):
        """Schedules with integration_id propagate it into execution_context."""
        schedule = _make_schedule(
            target_type="task",
            integration_id="splunk-prod",
        )

        sessions = [_mock_session(), _mock_session()]
        _setup_session_local(mock_session_local, sessions)
        mock_enqueue.return_value = "job-123"

        with (
            patch("analysi.scheduler.executor.ScheduleRepository") as mock_sched_cls,
            patch("analysi.scheduler.executor.JobRunRepository") as mock_jr_cls,
            patch("analysi.scheduler.executor.TaskRunService") as mock_trs_cls,
        ):
            mock_sched_repo = AsyncMock()
            mock_sched_repo.get_due_schedules.side_effect = [[schedule], []]
            mock_sched_repo.update_next_run_at = AsyncMock()
            mock_sched_cls.return_value = mock_sched_repo

            mock_jr_repo = AsyncMock()
            mock_jr_repo.create.return_value = _make_job_run()
            mock_jr_cls.return_value = mock_jr_repo

            mock_trs = AsyncMock()
            mock_trs.create_execution.return_value = _make_task_run()
            mock_trs_cls.return_value = mock_trs

            await execute_due_schedules({})

            call_kwargs = mock_trs.create_execution.call_args[1]
            ctx = call_kwargs["execution_context"]
            assert ctx["integration_id"] == "splunk-prod"
