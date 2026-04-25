"""
Integration tests for JobRunRepository.

JobRun CRUD on partitioned table.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.job_run_repository import JobRunRepository
from analysi.repositories.schedule_repository import ScheduleRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestJobRunRepository:
    """Test JobRunRepository with partitioned PostgreSQL table."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def repo(self, integration_test_session: AsyncSession):
        return JobRunRepository(integration_test_session)

    @pytest.fixture
    async def schedule_repo(self, integration_test_session: AsyncSession):
        return ScheduleRepository(integration_test_session)

    @pytest.fixture
    async def sample_schedule(self, schedule_repo: ScheduleRepository, unique_id: str):
        """Create a schedule to reference in job runs."""
        return await schedule_repo.create(
            tenant_id=f"t-{unique_id}",
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
        )

    # ── Positive tests ──────────────────────────────────────────────

    async def test_create_job_run_persists_to_partitioned_table(
        self, repo: JobRunRepository, sample_schedule, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        target_id = uuid4()

        job_run = await repo.create(
            tenant_id=tenant,
            schedule_id=sample_schedule.id,
            target_type="task",
            target_id=target_id,
            integration_id=f"splunk-{unique_id}",
            action_id="pull_alerts",
        )

        assert job_run.id is not None
        assert job_run.tenant_id == tenant
        assert job_run.schedule_id == sample_schedule.id
        assert job_run.target_type == "task"
        assert job_run.target_id == target_id
        assert job_run.integration_id == f"splunk-{unique_id}"
        assert job_run.action_id == "pull_alerts"
        assert job_run.status == "pending"
        assert job_run.created_at is not None
        assert job_run.triggered_at is not None

    async def test_update_status_transitions(
        self, repo: JobRunRepository, sample_schedule, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        job_run = await repo.create(
            tenant_id=tenant,
            schedule_id=sample_schedule.id,
            target_type="task",
            target_id=uuid4(),
        )
        assert job_run.status == "pending"

        now = datetime.now(UTC)
        updated = await repo.update_status(
            tenant,
            job_run.id,
            "running",
            started_at=now,
            created_at=job_run.created_at,
        )
        assert updated is not None
        assert updated.status == "running"
        assert updated.started_at is not None

        completed = await repo.update_status(
            tenant,
            job_run.id,
            "completed",
            completed_at=datetime.now(UTC),
            created_at=job_run.created_at,
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.completed_at is not None

    async def test_list_by_schedule_returns_matching(
        self, repo: JobRunRepository, sample_schedule, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        for _ in range(3):
            await repo.create(
                tenant_id=tenant,
                schedule_id=sample_schedule.id,
                target_type="task",
                target_id=uuid4(),
            )

        results = await repo.list_by_schedule(tenant, sample_schedule.id)
        assert len(results) == 3

    async def test_list_by_integration_returns_matching(
        self, repo: JobRunRepository, sample_schedule, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        int_id = f"splunk-{unique_id}"

        await repo.create(
            tenant_id=tenant,
            schedule_id=sample_schedule.id,
            target_type="task",
            target_id=uuid4(),
            integration_id=int_id,
        )
        await repo.create(
            tenant_id=tenant,
            schedule_id=sample_schedule.id,
            target_type="task",
            target_id=uuid4(),
            integration_id="other",
        )

        results = await repo.list_by_integration(tenant, int_id)
        assert len(results) == 1
        assert results[0].integration_id == int_id

    async def test_list_by_schedule_ordered_by_created_at_desc(
        self, repo: JobRunRepository, sample_schedule, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        for _ in range(3):
            await repo.create(
                tenant_id=tenant,
                schedule_id=sample_schedule.id,
                target_type="task",
                target_id=uuid4(),
            )

        results = await repo.list_by_schedule(tenant, sample_schedule.id)
        created_times = [r.created_at for r in results]
        assert created_times == sorted(created_times, reverse=True)

    # ── Negative tests ──────────────────────────────────────────────

    async def test_update_status_nonexistent_returns_none(
        self, repo: JobRunRepository, unique_id: str
    ):
        updated = await repo.update_status(
            f"t-{unique_id}",
            uuid4(),
            "running",
            created_at=datetime.now(UTC),
        )
        assert updated is None

    async def test_list_by_schedule_empty_for_unknown_schedule(
        self, repo: JobRunRepository, unique_id: str
    ):
        results = await repo.list_by_schedule(f"t-{unique_id}", uuid4())
        assert results == []
