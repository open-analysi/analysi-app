"""
Integration tests for ScheduleRepository.

Schedule CRUD and due-schedule polling.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.schedule_repository import ScheduleRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestScheduleRepository:
    """Test ScheduleRepository with PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    async def repo(self, integration_test_session: AsyncSession):
        return ScheduleRepository(integration_test_session)

    # ── Positive tests ──────────────────────────────────────────────

    async def test_create_schedule_persists_all_fields(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        target_id = uuid4()

        schedule = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=target_id,
            schedule_type="every",
            schedule_value="60s",
            timezone="America/New_York",
            enabled=True,
            params={"lookback": 300},
            origin_type="system",
            integration_id=f"splunk-{unique_id}",
            next_run_at=datetime.now(UTC) + timedelta(seconds=60),
        )

        assert schedule.id is not None
        assert schedule.tenant_id == tenant
        assert schedule.target_type == "task"
        assert schedule.target_id == target_id
        assert schedule.schedule_type == "every"
        assert schedule.schedule_value == "60s"
        assert schedule.timezone == "America/New_York"
        assert schedule.enabled is True
        assert schedule.params == {"lookback": 300}
        assert schedule.origin_type == "system"
        assert schedule.integration_id == f"splunk-{unique_id}"
        assert schedule.next_run_at is not None
        assert schedule.created_at is not None

    async def test_get_schedule_returns_by_tenant_and_id(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        created = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="5m",
        )

        found = await repo.get(tenant, created.id)
        assert found is not None
        assert found.id == created.id
        assert found.schedule_value == "5m"

    async def test_list_by_tenant_returns_matching(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        for _ in range(3):
            await repo.create(
                tenant_id=tenant,
                target_type="task",
                target_id=uuid4(),
                schedule_type="every",
                schedule_value="60s",
            )

        results = await repo.list_by_tenant(tenant)
        assert len(results) == 3

    async def test_list_by_tenant_filters_by_target_type(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
        )
        await repo.create(
            tenant_id=tenant,
            target_type="workflow",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="1h",
        )

        tasks_only = await repo.list_by_tenant(tenant, target_type="task")
        assert len(tasks_only) == 1
        assert tasks_only[0].target_type == "task"

    async def test_list_by_tenant_filters_by_integration_id(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        int_id = f"splunk-{unique_id}"
        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            integration_id=int_id,
        )
        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="5m",
        )

        filtered = await repo.list_by_tenant(tenant, integration_id=int_id)
        assert len(filtered) == 1
        assert filtered[0].integration_id == int_id

    async def test_list_by_tenant_filters_by_enabled(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
        )
        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="5m",
            enabled=False,
        )

        enabled_only = await repo.list_by_tenant(tenant, enabled=True)
        assert len(enabled_only) == 1
        assert enabled_only[0].enabled is True

    async def test_update_schedule_modifies_fields(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        created = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=False,
        )

        updated = await repo.update(
            tenant, created.id, schedule_value="120s", enabled=True
        )
        assert updated is not None
        assert updated.schedule_value == "120s"
        assert updated.enabled is True

    async def test_delete_schedule_removes_row(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        created = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
        )

        deleted = await repo.delete(tenant, created.id)
        assert deleted is True

        found = await repo.get(tenant, created.id)
        assert found is None

    async def test_get_due_schedules_returns_enabled_past_next_run(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        past = datetime.now(UTC) - timedelta(seconds=30)

        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=past,
        )

        due = await repo.get_due_schedules()
        assert len(due) >= 1
        assert any(s.tenant_id == tenant for s in due)

    async def test_get_due_schedules_skips_disabled(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-disabled-{unique_id}"
        past = datetime.now(UTC) - timedelta(seconds=30)

        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=False,
            next_run_at=past,
        )

        due = await repo.get_due_schedules()
        assert not any(s.tenant_id == tenant for s in due)

    async def test_get_due_schedules_skips_future(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-future-{unique_id}"
        future = datetime.now(UTC) + timedelta(hours=1)

        await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=future,
        )

        due = await repo.get_due_schedules()
        assert not any(s.tenant_id == tenant for s in due)

    async def test_update_next_run_at_updates_timing(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        created = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
            enabled=True,
            next_run_at=datetime.now(UTC),
        )

        new_next = datetime.now(UTC) + timedelta(seconds=60)
        now = datetime.now(UTC)
        await repo.update_next_run_at(created.id, new_next, last_run_at=now)

        found = await repo.get(tenant, created.id)
        assert found is not None
        assert found.next_run_at is not None
        # Timestamps may lose microsecond precision in DB, so compare within 1 second
        assert abs((found.next_run_at - new_next).total_seconds()) < 1
        assert found.last_run_at is not None

    # ── Negative tests ──────────────────────────────────────────────

    async def test_get_schedule_wrong_tenant_returns_none(
        self, repo: ScheduleRepository, unique_id: str
    ):
        tenant = f"t-{unique_id}"
        created = await repo.create(
            tenant_id=tenant,
            target_type="task",
            target_id=uuid4(),
            schedule_type="every",
            schedule_value="60s",
        )

        found = await repo.get("wrong-tenant", created.id)
        assert found is None

    async def test_delete_nonexistent_returns_false(
        self, repo: ScheduleRepository, unique_id: str
    ):
        deleted = await repo.delete(f"t-{unique_id}", uuid4())
        assert deleted is False

    async def test_update_nonexistent_returns_none(
        self, repo: ScheduleRepository, unique_id: str
    ):
        updated = await repo.update(f"t-{unique_id}", uuid4(), enabled=True)
        assert updated is None
