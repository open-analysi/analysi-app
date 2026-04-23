"""Integration tests for Packs API endpoints.

Tests GET /v1/{tenant}/packs and DELETE /v1/{tenant}/packs/{name}.
Also tests the `app` query filter on tasks/workflows list endpoints.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.models.workflow import Workflow

_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _unique_id() -> str:
    return f"test-{uuid4().hex[:8]}"


def _owner_user(tenant_id: str) -> CurrentUser:
    return CurrentUser(
        user_id="owner-test-user",
        email="owner@test.local",
        tenant_id=tenant_id,
        roles=["owner"],
        actor_type="user",
        db_user_id=_SYSTEM_USER_ID,
    )


async def _seed_component(
    session: AsyncSession,
    tenant_id: str,
    app_name: str,
    kind: str = "task",
    name: str | None = None,
) -> Component:
    """Seed a component with a specific app value."""
    comp = Component(
        tenant_id=tenant_id,
        kind=kind,
        name=name or f"Test {kind} {uuid4().hex[:6]}",
        description="Test component",
        app=app_name,
        created_by=_SYSTEM_USER_ID,
    )
    session.add(comp)
    await session.flush()
    return comp


async def _seed_workflow(
    session: AsyncSession,
    tenant_id: str,
    app_name: str,
    name: str | None = None,
) -> Workflow:
    """Seed a workflow with a specific app value."""
    wf = Workflow(
        tenant_id=tenant_id,
        name=name or f"Test WF {uuid4().hex[:6]}",
        io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
        app=app_name,
        created_by=_SYSTEM_USER_ID,
    )
    session.add(wf)
    await session.flush()
    return wf


@pytest.mark.integration
class TestListPacks:
    """Tests for GET /v1/{tenant}/packs."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_list_packs_empty(self, client: AsyncClient, tenant: str):
        """No packs installed returns empty list."""
        response = await client.get(f"/v1/{tenant}/packs")
        assert response.status_code == 200
        assert response.json()["data"] == []
        assert response.json()["meta"]["total"] == 0

    async def test_list_packs_with_components(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Packs list shows component counts grouped by app."""
        await _seed_component(integration_test_session, tenant, "foundation", "task")
        await _seed_component(integration_test_session, tenant, "foundation", "ku")
        await _seed_workflow(integration_test_session, tenant, "foundation")
        await _seed_component(integration_test_session, tenant, "examples", "task")
        await integration_test_session.commit()

        response = await client.get(f"/v1/{tenant}/packs")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 2

        pack_names = {p["name"] for p in data}
        assert "foundation" in pack_names
        assert "examples" in pack_names

        # Foundation should have tasks, ku, and workflows
        foundation = next(p for p in data if p["name"] == "foundation")
        assert foundation["components"].get("task", 0) >= 1
        assert foundation["components"].get("ku", 0) >= 1
        assert foundation["components"].get("workflows", 0) >= 1

    async def test_list_packs_excludes_default(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Packs list excludes 'default' app (not a pack)."""
        await _seed_component(integration_test_session, tenant, "default", "task")
        await integration_test_session.commit()

        response = await client.get(f"/v1/{tenant}/packs")
        data = response.json()["data"]
        assert not any(p["name"] == "default" for p in data)


@pytest.mark.integration
class TestUninstallPack:
    """Tests for DELETE /v1/{tenant}/packs/{pack_name}."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_uninstall_pack_success(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Uninstall removes all components with matching app."""
        await _seed_component(integration_test_session, tenant, "to-remove", "task")
        await _seed_component(integration_test_session, tenant, "to-remove", "ku")
        await _seed_workflow(integration_test_session, tenant, "to-remove")
        await integration_test_session.commit()

        response = await client.delete(f"/v1/{tenant}/packs/to-remove")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["pack_name"] == "to-remove"
        assert data["components_deleted"] >= 2
        assert data["workflows_deleted"] >= 1

        # Verify pack is gone
        list_response = await client.get(f"/v1/{tenant}/packs")
        pack_names = {p["name"] for p in list_response.json()["data"]}
        assert "to-remove" not in pack_names

    async def test_uninstall_pack_not_found(self, client: AsyncClient, tenant: str):
        """Uninstall nonexistent pack returns 404."""
        response = await client.delete(f"/v1/{tenant}/packs/nonexistent-pack")
        assert response.status_code == 404

    async def test_uninstall_pack_force(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Force uninstall works even with modified components."""
        from datetime import timedelta

        now = datetime.now(UTC)
        comp = await _seed_component(
            integration_test_session, tenant, "modified-pack", "task"
        )
        # Explicitly set timestamps so the modification check can detect the diff
        comp.created_at = now - timedelta(hours=2)
        comp.updated_at = now  # 2 hours after created_at — clearly modified
        await integration_test_session.commit()

        # Without force, should be rejected
        response = await client.delete(f"/v1/{tenant}/packs/modified-pack")
        assert response.status_code == 409
        assert "user-modified" in response.json()["detail"]

        # With force, should succeed
        response = await client.delete(
            f"/v1/{tenant}/packs/modified-pack", params={"force": True}
        )
        assert response.status_code == 200


@pytest.mark.integration
class TestAppFilterOnListEndpoints:
    """Tests for the `app` query filter on tasks/workflows list endpoints."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_tasks_app_filter(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Tasks list can be filtered by app."""
        # Seed proper Task + Component pairs (Task joins Component)
        comp_a = Component(
            tenant_id=tenant,
            kind="task",
            name="Task A",
            description="",
            app="pack-a",
            created_by=_SYSTEM_USER_ID,
        )
        integration_test_session.add(comp_a)
        await integration_test_session.flush()
        task_a = Task(component_id=comp_a.id, script="return 1", directive="test")
        integration_test_session.add(task_a)

        comp_b = Component(
            tenant_id=tenant,
            kind="task",
            name="Task B",
            description="",
            app="pack-b",
            created_by=_SYSTEM_USER_ID,
        )
        integration_test_session.add(comp_b)
        await integration_test_session.flush()
        task_b = Task(component_id=comp_b.id, script="return 2", directive="test")
        integration_test_session.add(task_b)
        await integration_test_session.commit()

        # No filter — both appear
        response = await client.get(f"/v1/{tenant}/tasks")
        assert response.status_code == 200
        all_names = {t["name"] for t in response.json()["data"]}
        assert "Task A" in all_names
        assert "Task B" in all_names

        # Filter by pack-a
        response = await client.get(f"/v1/{tenant}/tasks", params={"app": "pack-a"})
        assert response.status_code == 200
        filtered_names = {t["name"] for t in response.json()["data"]}
        assert "Task A" in filtered_names
        assert "Task B" not in filtered_names

    async def test_workflows_app_filter(
        self,
        client: AsyncClient,
        tenant: str,
        integration_test_session: AsyncSession,
    ):
        """Workflows list can be filtered by app."""
        await _seed_workflow(integration_test_session, tenant, "pack-x", name="WF X")
        await _seed_workflow(integration_test_session, tenant, "pack-y", name="WF Y")
        await integration_test_session.commit()

        # Filter by pack-x
        response = await client.get(f"/v1/{tenant}/workflows", params={"app": "pack-x"})
        assert response.status_code == 200
        names = {w["name"] for w in response.json()["data"]}
        assert "WF X" in names
        assert "WF Y" not in names
