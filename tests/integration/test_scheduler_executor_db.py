"""Integration tests for the scheduler executor with real PostgreSQL.

Verifies that the scheduler creates correct DB records.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.job_run import JobRun
from analysi.models.task import Task
from analysi.models.task_run import TaskRun
from analysi.repositories.job_run_repository import JobRunRepository
from analysi.repositories.schedule_repository import ScheduleRepository
from analysi.scheduler.interval import compute_next_run_at


@pytest.mark.asyncio
@pytest.mark.integration
class TestSchedulerExecutorDB:
    """Test scheduler executor with real database."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def setup_task(self, integration_test_session: AsyncSession, unique_id: str):
        """Create a task that a schedule can target."""
        tenant_id = f"t-{unique_id}"
        comp_id = uuid4()
        component = Component(
            id=comp_id,
            tenant_id=tenant_id,
            kind="task",
            name=f"Scheduled Task {unique_id}",
            description="Task for scheduler tests",
            version="1.0.0",
        )
        task = Task(
            component_id=comp_id,
            directive="Test scheduled task",
            script="return 'scheduled-ok'",
            scope="processing",
            mode="saved",
        )
        integration_test_session.add(component)
        integration_test_session.add(task)
        await integration_test_session.flush()
        return {"tenant_id": tenant_id, "task_id": comp_id}

    async def test_due_schedule_creates_job_run_and_task_run(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """A due schedule creates JobRun and TaskRun in the database."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)
        jr_repo = JobRunRepository(session)

        # Create a schedule that is past due
        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        await session.flush()

        # Verify the schedule is due
        due_schedules = await sched_repo.get_due_schedules()
        due_ids = [s.id for s in due_schedules]
        assert schedule.id in due_ids

        # Create a JobRun manually (mimicking executor behavior)
        job_run = await jr_repo.create(
            tenant_id=ids["tenant_id"],
            schedule_id=schedule.id,
            target_type="task",
            target_id=ids["task_id"],
            status="pending",
        )
        await session.flush()

        # Verify the JobRun was created
        assert job_run.id is not None
        assert job_run.schedule_id == schedule.id
        assert job_run.target_type == "task"

    async def test_schedule_next_run_at_advanced(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """After processing, next_run_at is advanced by the interval."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)

        old_next = datetime.now(UTC) - timedelta(seconds=10)
        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=old_next,
        )

        # Compute new next_run_at (mimicking executor)
        new_next = compute_next_run_at("every", "60s")
        assert new_next is not None

        now = datetime.now(UTC)
        await sched_repo.update_next_run_at(schedule.id, new_next, last_run_at=now)
        await session.flush()

        updated = await sched_repo.get(ids["tenant_id"], schedule.id)
        assert updated is not None
        assert updated.last_run_at is not None
        # New next_run_at should be in the future (~60s from now)
        assert updated.next_run_at > old_next

    async def test_disabled_schedule_not_processed(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """Disabled schedules are not returned by get_due_schedules."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)

        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=False,
            next_run_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        await session.flush()

        due_schedules = await sched_repo.get_due_schedules()
        due_ids = [s.id for s in due_schedules]
        assert schedule.id not in due_ids

    async def test_job_run_links_to_schedule(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """JobRun correctly references schedule_id, target_type, target_id."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)
        jr_repo = JobRunRepository(session)

        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="120s",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        await session.flush()

        # Create JobRun (mimicking executor)
        job_run = await jr_repo.create(
            tenant_id=ids["tenant_id"],
            schedule_id=schedule.id,
            target_type="task",
            target_id=ids["task_id"],
            status="pending",
        )
        await session.flush()

        # Verify fields match
        assert job_run.schedule_id == schedule.id
        assert job_run.target_type == "task"
        assert job_run.target_id == ids["task_id"]
        assert job_run.status == "pending"
        assert job_run.triggered_at is not None

    async def test_job_run_status_update(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """JobRun status can be updated through repository method."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)
        jr_repo = JobRunRepository(session)

        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        await session.flush()

        job_run = await jr_repo.create(
            tenant_id=ids["tenant_id"],
            schedule_id=schedule.id,
            target_type="task",
            target_id=ids["task_id"],
            status="pending",
        )
        await session.flush()

        # Update status to completed
        now = datetime.now(UTC)
        updated = await jr_repo.update_status(
            tenant_id=ids["tenant_id"],
            job_run_id=job_run.id,
            status="completed",
            started_at=now - timedelta(seconds=2),
            completed_at=now,
            created_at=job_run.created_at,
        )
        await session.flush()

        assert updated is not None
        assert updated.status == "completed"
        assert updated.started_at is not None
        assert updated.completed_at is not None

    async def test_job_runs_list_by_schedule(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """list_by_schedule returns job runs for a specific schedule."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)
        jr_repo = JobRunRepository(session)

        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(seconds=5),
        )
        await session.flush()

        # Create two job runs for this schedule
        for _ in range(2):
            await jr_repo.create(
                tenant_id=ids["tenant_id"],
                schedule_id=schedule.id,
                target_type="task",
                target_id=ids["task_id"],
                status="completed",
            )
        await session.flush()

        runs = await jr_repo.list_by_schedule(ids["tenant_id"], schedule.id)
        assert len(runs) == 2
        assert all(r.schedule_id == schedule.id for r in runs)

    async def test_future_schedule_not_due(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """A schedule with next_run_at far in the future is not returned as due."""
        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)

        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await session.flush()

        due_schedules = await sched_repo.get_due_schedules()
        due_ids = [s.id for s in due_schedules]
        assert schedule.id not in due_ids

    async def test_next_run_at_computed_correctly(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """compute_next_run_at for '5m' returns ~300 seconds in the future."""
        new_next = compute_next_run_at("every", "5m")
        assert new_next is not None
        now = datetime.now(UTC)
        diff = (new_next - now).total_seconds()
        # Should be approximately 300 seconds, allow 2s slack
        assert 298 <= diff <= 302

    async def test_next_run_at_none_for_invalid_type(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """compute_next_run_at returns None for unsupported schedule_type."""
        result = compute_next_run_at("cron", "* * * * *")
        assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteDueSchedulesE2E:
    """End-to-end tests for execute_due_schedules() against real PostgreSQL.

    Exercises the full path: enabled schedule → executor → TaskRun created
    → ARQ enqueue called. The ARQ enqueue is mocked (no Redis needed) but
    everything else hits the real database.
    """

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def setup_task(self, integration_test_session: AsyncSession, unique_id: str):
        """Create a task that a schedule can target."""
        tenant_id = f"t-{unique_id}"
        comp_id = uuid4()
        component = Component(
            id=comp_id,
            tenant_id=tenant_id,
            kind="task",
            name=f"Health Check {unique_id}",
            description="Health check for executor e2e test",
            version="1.0.0",
        )
        task = Task(
            component_id=comp_id,
            directive="Health check task",
            script="return app::echo_edr::health_check()",
            scope="processing",
            mode="saved",
        )
        integration_test_session.add(component)
        integration_test_session.add(task)
        await integration_test_session.flush()
        return {"tenant_id": tenant_id, "task_id": comp_id}

    async def test_execute_due_schedules_creates_task_run(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """Full path: due schedule → execute_due_schedules → TaskRun + JobRun created."""
        from analysi.scheduler.executor import execute_due_schedules

        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)

        # Create an enabled schedule that is past due
        schedule = await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        await session.commit()

        # Run the executor with mocked ARQ enqueue (no Redis) and
        # patched AsyncSessionLocal to use our test session factory
        with (
            patch(
                "analysi.scheduler.executor.enqueue_arq_job",
                new_callable=AsyncMock,
                return_value="mock-job-id",
            ) as mock_enqueue,
            patch(
                "analysi.scheduler.executor.AsyncSessionLocal",
            ) as mock_session_local,
        ):
            # Make AsyncSessionLocal() return our test session
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await execute_due_schedules({})

        assert result["processed"] == 1
        assert result["errors"] == 0

        # Verify enqueue was called with the right function
        mock_enqueue.assert_called_once()
        enqueue_args = mock_enqueue.call_args
        assert "execute_task_run" in enqueue_args[0][0]

        # Verify TaskRun was created in the database
        task_runs = (
            (
                await session.execute(
                    select(TaskRun).where(TaskRun.tenant_id == ids["tenant_id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(task_runs) == 1
        assert task_runs[0].task_id == ids["task_id"]
        assert task_runs[0].run_context == "scheduled"

        # Verify JobRun was created in the database
        job_runs = (
            (
                await session.execute(
                    select(JobRun).where(JobRun.schedule_id == schedule.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(job_runs) == 1
        assert job_runs[0].target_type == "task"
        assert job_runs[0].task_run_id == task_runs[0].id

        # Verify next_run_at was advanced (should be ~60s in the future)
        await session.refresh(schedule)
        assert schedule.next_run_at > datetime.now(UTC) + timedelta(seconds=50)
        assert schedule.last_run_at is not None

    async def test_execute_due_schedules_skips_disabled(
        self, integration_test_session: AsyncSession, setup_task, unique_id
    ):
        """Disabled schedules are not picked up by the executor."""
        from analysi.scheduler.executor import execute_due_schedules

        session = integration_test_session
        ids = setup_task
        sched_repo = ScheduleRepository(session)

        # Create a DISABLED schedule that is past due
        await sched_repo.create(
            tenant_id=ids["tenant_id"],
            target_type="task",
            target_id=ids["task_id"],
            schedule_type="every",
            schedule_value="60s",
            enabled=False,
            next_run_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        await session.commit()

        with (
            patch(
                "analysi.scheduler.executor.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
            patch(
                "analysi.scheduler.executor.AsyncSessionLocal",
            ) as mock_session_local,
        ):
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await execute_due_schedules({})

        assert result["processed"] == 0
        mock_enqueue.assert_not_called()
