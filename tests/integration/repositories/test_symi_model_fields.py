"""
Integration tests for model field additions.

Verify new fields on Task (integration_id, origin_type)
and TaskRun (run_context) persist correctly.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind
from analysi.models.task import Task, TaskFunction
from analysi.models.task_run import TaskRun


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskModelAdditions:
    """Test new fields on Task model."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    async def _create_component(self, session: AsyncSession, tenant: str) -> Component:
        component = Component(
            tenant_id=tenant,
            kind=ComponentKind.TASK,
            name=f"Test Task {uuid4().hex[:6]}",
            description="Test task for Symi model fields",
            created_by=str(SYSTEM_USER_ID),
        )
        session.add(component)
        await session.flush()
        return component

    async def test_task_integration_id_persists(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        tenant = f"t-{unique_id}"
        component = await self._create_component(session, tenant)

        task = Task(
            component_id=component.id,
            directive="Pull alerts",
            function=TaskFunction.REASONING,
            integration_id=f"splunk-{unique_id}",
            origin_type="system",
        )
        session.add(task)
        await session.flush()

        # Re-query to verify persistence
        result = await session.execute(
            text("SELECT integration_id FROM tasks WHERE component_id = :cid"),
            {"cid": component.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == f"splunk-{unique_id}"

    async def test_task_origin_type_defaults_to_user(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        tenant = f"t-{unique_id}"
        component = await self._create_component(session, tenant)

        task = Task(
            component_id=component.id,
            directive="Ad-hoc task",
            function=TaskFunction.REASONING,
        )
        session.add(task)
        await session.flush()

        result = await session.execute(
            text("SELECT origin_type FROM tasks WHERE component_id = :cid"),
            {"cid": component.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "user"

    async def test_task_origin_type_accepts_system(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        tenant = f"t-{unique_id}"
        component = await self._create_component(session, tenant)

        task = Task(
            component_id=component.id,
            directive="System task",
            function=TaskFunction.REASONING,
            origin_type="system",
        )
        session.add(task)
        await session.flush()

        result = await session.execute(
            text("SELECT origin_type FROM tasks WHERE component_id = :cid"),
            {"cid": component.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "system"


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunModelAdditions:
    """Test new fields on TaskRun model."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    async def test_task_run_run_context_defaults_to_ad_hoc(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        task_run = TaskRun(
            tenant_id=f"t-{unique_id}",
            status="running",
        )
        session.add(task_run)
        await session.flush()

        result = await session.execute(
            text("SELECT run_context FROM task_runs WHERE id = :id"),
            {"id": task_run.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "ad_hoc"

    async def test_task_run_run_context_accepts_analysis(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        task_run = TaskRun(
            tenant_id=f"t-{unique_id}",
            status="running",
            run_context="analysis",
        )
        session.add(task_run)
        await session.flush()

        result = await session.execute(
            text("SELECT run_context FROM task_runs WHERE id = :id"),
            {"id": task_run.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "analysis"

    async def test_task_run_run_context_accepts_scheduled(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        session = integration_test_session
        task_run = TaskRun(
            tenant_id=f"t-{unique_id}",
            status="running",
            run_context="scheduled",
        )
        session.add(task_run)
        await session.flush()

        result = await session.execute(
            text("SELECT run_context FROM task_runs WHERE id = :id"),
            {"id": task_run.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "scheduled"
