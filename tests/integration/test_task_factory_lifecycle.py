"""
Integration tests for Task Factory + Integration Lifecycle.

Tests task/schedule creation from factory functions and lifecycle cascades
(create/enable/disable/delete) against PostgreSQL.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.schedule import Schedule
from analysi.models.task import Task
from analysi.services.task_factory import (
    cascade_disable_schedules,
    cascade_enable_schedules,
    cleanup_integration_tasks,
    create_action_task,
    create_alert_ingestion_task,
    create_default_schedule,
    create_health_check_task,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskFactoryDB:
    """Test task factory functions against PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    async def test_create_alert_ingestion_task_creates_component_and_task(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Factory creates a Component + Task pair."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        assert task is not None
        assert task.component is not None
        assert task.component.kind == "task"
        assert task.component.tenant_id == tenant_id
        assert task.script is not None
        assert len(task.script) > 0

    async def test_create_alert_ingestion_task_sets_origin_type_system(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Alert ingestion task has origin_type='system'."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        assert task.origin_type == "system"

    async def test_create_alert_ingestion_task_sets_integration_id(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Alert ingestion task is linked to its integration."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        assert task.integration_id == integration_id

    async def test_create_alert_ingestion_task_script_is_valid(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Generated script contains the key function calls."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        assert "app::splunk::pull_alerts" in task.script
        assert "app::splunk::alerts_to_ocsf" in task.script
        assert "ingest_alerts" in task.script

    async def test_create_health_check_task_creates_component_and_task(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Factory creates a health check Task with Component."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        assert task is not None
        assert task.component is not None
        assert task.component.kind == "task"
        assert task.component.tenant_id == tenant_id

    async def test_create_health_check_task_sets_origin_type_system(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Health check task has origin_type='system'."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        assert task.origin_type == "system"

    async def test_create_default_schedule_creates_disabled_schedule(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Default schedule starts disabled."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            integration_id=integration_id,
        )

        assert schedule is not None
        assert schedule.enabled is False
        assert schedule.target_type == "task"
        assert schedule.target_id == task.component.id

    async def test_create_default_schedule_sets_origin_type_system(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Default schedule has origin_type='system'."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            integration_id=integration_id,
        )

        assert schedule.origin_type == "system"

    async def test_create_default_schedule_sets_integration_id(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Default schedule is linked to its integration."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            integration_id=integration_id,
        )

        assert schedule.integration_id == integration_id


@pytest.mark.asyncio
@pytest.mark.integration
class TestLifecycleCascadesDB:
    """Test integration lifecycle cascade operations against PostgreSQL."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"echo-edr-{unique_id}"

    async def _create_task_with_schedule(
        self, session, tenant_id, integration_id
    ) -> tuple[Task, Schedule]:
        """Helper: create a health check task + disabled schedule."""
        task = await create_health_check_task(
            session=session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )
        schedule = await create_default_schedule(
            session=session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            integration_id=integration_id,
        )
        return task, schedule

    async def test_cascade_enable_schedules(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Enabling an integration enables its system-managed schedules."""
        _, schedule = await self._create_task_with_schedule(
            integration_test_session, tenant_id, integration_id
        )
        assert schedule.enabled is False

        count = await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        assert count >= 1

        # Verify the schedule is now enabled
        refreshed = await integration_test_session.get(Schedule, schedule.id)
        assert refreshed.enabled is True
        assert refreshed.next_run_at is not None

    async def test_cascade_disable_schedules(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Disabling an integration disables its system-managed schedules."""
        _, schedule = await self._create_task_with_schedule(
            integration_test_session, tenant_id, integration_id
        )

        # First enable
        await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        # Then disable
        count = await cascade_disable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        assert count >= 1
        refreshed = await integration_test_session.get(Schedule, schedule.id)
        assert refreshed.enabled is False

    async def test_cascade_enable_no_schedules_returns_zero(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
    ):
        """When there are no schedules for the integration, returns 0."""
        count = await cascade_enable_schedules(
            integration_test_session, tenant_id, "nonexistent-integration"
        )
        assert count == 0

    async def test_cleanup_integration_tasks(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Cleanup archives tasks and disables schedules."""
        task, schedule = await self._create_task_with_schedule(
            integration_test_session, tenant_id, integration_id
        )
        # Enable the schedule first
        await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        result = await cleanup_integration_tasks(
            integration_test_session, tenant_id, integration_id
        )

        assert result["schedules_disabled"] >= 1
        assert result["tasks_archived"] >= 1

        # Verify schedule is disabled
        refreshed_schedule = await integration_test_session.get(Schedule, schedule.id)
        assert refreshed_schedule.enabled is False

        # Verify task component is disabled
        await integration_test_session.refresh(task, ["component"])
        assert task.component.status == "disabled"

    async def test_create_alert_ingestion_task_invalid_type(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Factory handles unknown integration type gracefully (still creates task)."""
        # Unknown types should still generate a script — the integration
        # type is just a string used in the app:: prefix
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="unknown_type",
        )

        assert task is not None
        assert "app::unknown_type::pull_alerts" in task.script

    # ── Scope and categories ───────────────────────────────────────

    async def test_alert_ingestion_task_scope_is_input(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Alert ingestion task has scope='input' — it brings data into the system."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        assert task.scope == "input"

    async def test_alert_ingestion_task_has_domain_categories(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Alert ingestion task categories include domain, scope, and function."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )

        cats = task.component.categories
        assert "alert_ingestion" in cats
        assert "integration" in cats
        assert "scheduled" in cats
        # Auto-merged from scope + function
        assert "input" in cats
        assert "data_conversion" in cats

    async def test_health_check_task_has_domain_categories(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Health check task categories include health_monitoring."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        cats = task.component.categories
        assert "health_monitoring" in cats
        assert "integration" in cats
        assert "scheduled" in cats

    async def test_health_check_task_scope_is_processing(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Health check task uses scope='processing'."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )

        assert task.scope == "processing"


@pytest.mark.asyncio
@pytest.mark.integration
class TestCreateActionTask:
    """Test create_action_task() — generic action task factory."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    async def test_creates_component_and_task(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Factory creates a Component + Task pair for a generic action."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert task is not None
        assert task.component is not None
        assert task.component.kind == "task"
        assert task.component.tenant_id == tenant_id

    async def test_sets_origin_type_system(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Action task has origin_type='system'."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert task.origin_type == "system"

    async def test_sets_integration_id(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Action task is linked to its integration."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert task.integration_id == integration_id

    async def test_sets_managed_resource_key_to_action_id(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """managed_resource_key is set to the action's id."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert task.managed_resource_key == "sourcetype_discovery"

    async def test_task_name_follows_convention(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Task name is '{action_name} for {integration_id}'."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert task.component.name == f"Sourcetype Discovery for {integration_id}"

    async def test_script_calls_action(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Generated script calls app::{type}::{cy_name}."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
        )

        assert "app::splunk::sourcetype_discovery" in task.script

    async def test_uses_action_categories(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Task categories include the action's categories + integration + scheduled."""
        task = await create_action_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
            categories=["knowledge_building"],
        )

        cats = task.component.categories
        assert "knowledge_building" in cats
        assert "integration" in cats
        assert "scheduled" in cats


@pytest.mark.asyncio
@pytest.mark.integration
class TestActionTaskLifecycleCascades:
    """Test that custom action tasks participate in enable/disable/cleanup cascades."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    async def _create_full_managed_set(
        self, session, tenant_id, integration_id
    ) -> dict:
        """Create health_check + custom action task, each with a schedule."""
        health_task = await create_health_check_task(
            session=session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        health_schedule = await create_default_schedule(
            session=session,
            tenant_id=tenant_id,
            task_id=health_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )

        action_task = await create_action_task(
            session=session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            action_id="sourcetype_discovery",
            action_name="Sourcetype Discovery",
            cy_name="sourcetype_discovery",
            categories=["knowledge_building"],
        )
        action_schedule = await create_default_schedule(
            session=session,
            tenant_id=tenant_id,
            task_id=action_task.component.id,
            schedule_value="24h",
            integration_id=integration_id,
        )

        await session.flush()
        return {
            "health_task": health_task,
            "health_schedule": health_schedule,
            "action_task": action_task,
            "action_schedule": action_schedule,
        }

    async def test_cascade_enable_includes_action_task_schedules(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """cascade_enable_schedules enables both health and custom action schedules."""
        resources = await self._create_full_managed_set(
            integration_test_session, tenant_id, integration_id
        )
        assert resources["health_schedule"].enabled is False
        assert resources["action_schedule"].enabled is False

        count = await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        assert count == 2

        health_sched = await integration_test_session.get(
            Schedule, resources["health_schedule"].id
        )
        action_sched = await integration_test_session.get(
            Schedule, resources["action_schedule"].id
        )
        assert health_sched.enabled is True
        assert health_sched.next_run_at is not None
        assert action_sched.enabled is True
        assert action_sched.next_run_at is not None

    async def test_cascade_disable_includes_action_task_schedules(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """cascade_disable_schedules disables both health and custom action schedules."""
        resources = await self._create_full_managed_set(
            integration_test_session, tenant_id, integration_id
        )

        # Enable first
        await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        # Then disable
        count = await cascade_disable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        assert count == 2

        health_sched = await integration_test_session.get(
            Schedule, resources["health_schedule"].id
        )
        action_sched = await integration_test_session.get(
            Schedule, resources["action_schedule"].id
        )
        assert health_sched.enabled is False
        assert action_sched.enabled is False

    async def test_cleanup_archives_action_tasks(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """cleanup_integration_tasks archives both health and custom action tasks."""
        resources = await self._create_full_managed_set(
            integration_test_session, tenant_id, integration_id
        )

        # Enable schedules first (so disable has something to do)
        await cascade_enable_schedules(
            integration_test_session, tenant_id, integration_id
        )

        result = await cleanup_integration_tasks(
            integration_test_session, tenant_id, integration_id
        )

        assert result["schedules_disabled"] == 2
        assert result["tasks_archived"] == 2

        # Verify action task component is disabled
        await integration_test_session.refresh(resources["action_task"], ["component"])
        assert resources["action_task"].component.status == "disabled"

        # Verify action schedule is disabled
        action_sched = await integration_test_session.get(
            Schedule, resources["action_schedule"].id
        )
        assert action_sched.enabled is False
