"""Integration tests for managed resources service."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.services.managed_resources import (
    list_managed_resources,
    resolve_managed_resource,
)
from analysi.services.task_factory import (
    cleanup_integration_tasks,
    create_action_task,
    create_alert_ingestion_task,
    create_default_schedule,
    create_health_check_task,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestResolveManagedResource:
    """Test resolve_managed_resource against PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    async def test_resolve_alert_ingestion_resource(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Resolves alert_ingestion to the correct Task + Schedule."""
        # Create alert ingestion task + schedule via factory
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        # Resolve
        result = await resolve_managed_resource(
            integration_test_session, tenant_id, integration_id, "alert_ingestion"
        )

        assert result is not None
        assert result.resource_key == "alert_ingestion"
        assert result.task_id == task.component.id
        assert result.schedule_id == schedule.id

    async def test_resolve_health_check_resource(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Resolves health_check to the correct Task + Schedule."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        result = await resolve_managed_resource(
            integration_test_session, tenant_id, integration_id, "health_check"
        )

        assert result is not None
        assert result.resource_key == "health_check"
        assert result.task_id == task.component.id
        assert result.schedule_id == schedule.id

    async def test_resolve_custom_action_resource(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Resolves a custom action task (e.g. sourcetype_discovery) by resource key."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )
        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            schedule_value="24h",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        result = await resolve_managed_resource(
            integration_test_session,
            tenant_id,
            integration_id,
            "sourcetype_discovery",
        )

        assert result is not None
        assert result.resource_key == "sourcetype_discovery"
        assert result.task_id == task.component.id
        assert result.schedule_id == schedule.id

    async def test_resolve_unknown_resource_key_returns_none(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Resource key with no matching system task returns None."""
        result = await resolve_managed_resource(
            integration_test_session, tenant_id, integration_id, "nonexistent_action"
        )

        assert result is None

    async def test_resolve_with_no_tasks_returns_none(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Integration with no system tasks returns None."""
        result = await resolve_managed_resource(
            integration_test_session, tenant_id, integration_id, "health_check"
        )

        assert result is None

    async def test_resolve_after_delete_recreate_finds_only_active_task(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """After delete + recreate, resolve finds only the new (active) task."""
        # Create first generation
        task_v1 = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task_v1.component.id,
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        # Archive (simulates integration deletion)
        await cleanup_integration_tasks(
            integration_test_session, tenant_id, integration_id
        )

        # Create second generation (simulates integration recreation)
        task_v2 = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task_v2.component.id,
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        # Resolve should find only the new task, not the archived one
        result = await resolve_managed_resource(
            integration_test_session, tenant_id, integration_id, "health_check"
        )

        assert result is not None
        assert result.task_id == task_v2.component.id
        assert result.task_id != task_v1.component.id


@pytest.mark.asyncio
@pytest.mark.integration
class TestListManagedResources:
    """Test list_managed_resources against PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    async def test_list_managed_resources_alert_source_integration(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """AlertSource integration has both alert_ingestion and health_check."""
        # Create both tasks + schedules
        ingestion_task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=ingestion_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )

        health_task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=health_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        resources = await list_managed_resources(
            integration_test_session, tenant_id, integration_id
        )

        assert "alert_ingestion" in resources
        assert "health_check" in resources
        assert len(resources) == 2

    async def test_list_managed_resources_non_alert_source(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Non-AlertSource integration has only health_check."""
        health_task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=health_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        resources = await list_managed_resources(
            integration_test_session, tenant_id, integration_id
        )

        assert "health_check" in resources
        assert "alert_ingestion" not in resources

    async def test_list_managed_resources_includes_custom_action_tasks(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """list_managed_resources includes custom action tasks alongside well-known ones."""
        # Create health check (well-known)
        health_task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=health_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )

        # Create custom action task
        action_task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=action_task.component.id,
            schedule_value="24h",
            integration_id=integration_id,
        )
        await integration_test_session.flush()

        resources = await list_managed_resources(
            integration_test_session, tenant_id, integration_id
        )

        assert "health_check" in resources
        assert "sourcetype_discovery" in resources
        assert len(resources) == 2

    async def test_list_managed_resources_empty_for_no_tasks(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Integration with no factory tasks returns empty dict."""
        resources = await list_managed_resources(
            integration_test_session, tenant_id, integration_id
        )

        assert resources == {}
