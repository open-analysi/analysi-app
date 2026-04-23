"""Integration tests for the Schedules REST API.

Generic CRUD, task convenience, and workflow convenience.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.models.workflow import Workflow


def _make_component(tenant_id: str) -> tuple[Component, Task]:
    """Create a Component + Task pair for testing."""
    comp_id = uuid4()
    component = Component(
        id=comp_id,
        tenant_id=tenant_id,
        kind="task",
        name=f"Test Task {comp_id.hex[:6]}",
        description="Test task for scheduler",
        version="1.0.0",
    )
    task = Task(
        component_id=comp_id,
        directive="Test directive",
        script="return 'ok'",
        scope="processing",
        mode="saved",
    )
    return component, task


def _make_workflow(tenant_id: str) -> Workflow:
    """Create a minimal Workflow for testing."""
    return Workflow(
        id=uuid4(),
        tenant_id=tenant_id,
        name=f"Test Workflow {uuid4().hex[:6]}",
        description="Test workflow for scheduler",
        io_schema={},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestSchedulesGenericAPI:
    """Tests for the generic schedules CRUD endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.fixture
    async def setup_task(self, client) -> dict:
        """Create a task and return IDs for schedule tests."""
        _, session = client
        tenant_id = f"t-{uuid4().hex[:8]}"
        component, task = _make_component(tenant_id)
        session.add(component)
        session.add(task)
        await session.flush()
        return {"tenant_id": tenant_id, "task_id": str(component.id)}

    async def test_create_schedule(self, client, setup_task):
        http_client, session = client
        ids = setup_task
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["target_type"] == "task"
        assert data["schedule_value"] == "5m"
        assert data["enabled"] is True
        # next_run_at should be computed on creation
        assert data["next_run_at"] is not None

    async def test_create_schedule_invalid_interval(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "xyz-bad",
                "enabled": True,
            },
        )
        assert response.status_code == 400

    async def test_list_schedules(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        # Create two schedules
        for val in ["5m", "10m"]:
            await http_client.post(
                f"/v1/{ids['tenant_id']}/schedules",
                json={
                    "target_type": "task",
                    "target_id": ids["task_id"],
                    "schedule_type": "every",
                    "schedule_value": val,
                },
            )
        response = await http_client.get(f"/v1/{ids['tenant_id']}/schedules")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 2

    async def test_list_schedules_filter_target_type(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
            },
        )
        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/schedules?target_type=workflow"
        )
        assert response.status_code == 200
        # Should not include our task schedule
        data = response.json()["data"]
        assert all(s["target_type"] != "task" for s in data)

    async def test_update_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        create_resp = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
                "enabled": False,
            },
        )
        schedule_id = create_resp.json()["data"]["id"]

        patch_resp = await http_client.patch(
            f"/v1/{ids['tenant_id']}/schedules/{schedule_id}",
            json={"schedule_value": "10m", "enabled": True},
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()["data"]
        assert data["schedule_value"] == "10m"
        assert data["enabled"] is True

    async def test_delete_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        create_resp = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
            },
        )
        schedule_id = create_resp.json()["data"]["id"]

        del_resp = await http_client.delete(
            f"/v1/{ids['tenant_id']}/schedules/{schedule_id}"
        )
        assert del_resp.status_code == 204

    async def test_delete_schedule_not_found(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        del_resp = await http_client.delete(
            f"/v1/{ids['tenant_id']}/schedules/{uuid4()}"
        )
        assert del_resp.status_code == 404

    async def test_update_schedule_not_found(self, client, setup_task):
        """PATCH /schedules/{id} with non-existent ID returns 404."""
        http_client, _ = client
        ids = setup_task
        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/schedules/{uuid4()}",
            json={"schedule_value": "10m"},
        )
        assert response.status_code == 404

    async def test_update_schedule_invalid_interval(self, client, setup_task):
        """PATCH /schedules/{id} with unparseable interval returns 400."""
        http_client, _ = client
        ids = setup_task
        # Create a valid schedule first
        create_resp = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
            },
        )
        schedule_id = create_resp.json()["data"]["id"]

        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/schedules/{schedule_id}",
            json={"schedule_value": "abc"},
        )
        assert response.status_code == 400

    async def test_create_schedule_invalid_schedule_type(self, client, setup_task):
        """POST /schedules with unsupported schedule_type returns 400."""
        http_client, _ = client
        ids = setup_task
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "cron",
                "schedule_value": "5m",
                "enabled": True,
            },
        )
        assert response.status_code == 400

    async def test_create_schedule_missing_required_fields(self, client, setup_task):
        """POST /schedules with missing required fields returns 422."""
        http_client, _ = client
        ids = setup_task
        # Missing target_type, target_id, and schedule_value
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={"enabled": True},
        )
        assert response.status_code == 422

    async def test_list_schedules_filter_enabled_true(self, client, setup_task):
        """GET /schedules?enabled=true returns only enabled schedules."""
        http_client, _ = client
        ids = setup_task
        # Create one enabled and one disabled schedule
        await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
                "enabled": True,
            },
        )
        # Create a second task for a separate schedule
        _, session = client
        component2, task2 = _make_component(ids["tenant_id"])
        session.add(component2)
        session.add(task2)
        await session.flush()
        await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": str(component2.id),
                "schedule_type": "every",
                "schedule_value": "10m",
                "enabled": False,
            },
        )

        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/schedules?enabled=true"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(s["enabled"] is True for s in data)

    async def test_list_schedules_filter_enabled_false(self, client, setup_task):
        """GET /schedules?enabled=false returns only disabled schedules."""
        http_client, _ = client
        ids = setup_task
        # Create both an enabled and disabled schedule
        await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": ids["task_id"],
                "schedule_type": "every",
                "schedule_value": "5m",
                "enabled": True,
            },
        )
        _, session = client
        component2, task2 = _make_component(ids["tenant_id"])
        session.add(component2)
        session.add(task2)
        await session.flush()
        await http_client.post(
            f"/v1/{ids['tenant_id']}/schedules",
            json={
                "target_type": "task",
                "target_id": str(component2.id),
                "schedule_type": "every",
                "schedule_value": "10m",
                "enabled": False,
            },
        )

        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/schedules?enabled=false"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert all(s["enabled"] is False for s in data)


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskScheduleConvenience:
    """Tests for task convenience endpoints: POST/GET/PATCH/DELETE /tasks/{id}/schedule."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.fixture
    async def setup_task(self, client) -> dict:
        _, session = client
        tenant_id = f"t-{uuid4().hex[:8]}"
        component, task = _make_component(tenant_id)
        session.add(component)
        session.add(task)
        await session.flush()
        return {"tenant_id": tenant_id, "task_id": str(component.id)}

    async def test_create_task_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={
                "schedule_type": "every",
                "schedule_value": "10m",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["target_type"] == "task"
        assert data["target_id"] == ids["task_id"]
        assert data["schedule_value"] == "10m"

    async def test_get_task_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        # Create schedule first
        await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "5m"},
        )
        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["target_type"] == "task"

    async def test_get_task_schedule_not_found(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule"
        )
        assert response.status_code == 404

    async def test_update_task_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "5m"},
        )
        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_value": "15m", "enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["data"]["schedule_value"] == "15m"

    async def test_delete_task_schedule(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "5m"},
        )
        response = await http_client.delete(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule"
        )
        assert response.status_code == 204

    async def test_create_task_schedule_duplicate(self, client, setup_task):
        http_client, _ = client
        ids = setup_task
        await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "5m"},
        )
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "10m"},
        )
        assert response.status_code == 409

    async def test_create_task_schedule_nonexistent_task(self, client, setup_task):
        """POST /tasks/{task_id}/schedule where task doesn't exist still creates (no FK check)."""
        http_client, _ = client
        ids = setup_task
        fake_task_id = uuid4()
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{fake_task_id}/schedule",
            json={"schedule_type": "every", "schedule_value": "5m", "enabled": True},
        )
        # The schedules table has no FK to components -- the schedule is created
        # (target_id is just stored, not validated against a component table).
        # This is by design: the scheduler fires and the executor validates.
        assert response.status_code == 201

    async def test_create_task_schedule_invalid_interval(self, client, setup_task):
        """POST /tasks/{task_id}/schedule with invalid interval returns 400."""
        http_client, _ = client
        ids = setup_task
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "not-a-duration"},
        )
        assert response.status_code == 400

    async def test_update_task_schedule_no_schedule_exists(self, client, setup_task):
        """PATCH /tasks/{task_id}/schedule when no schedule exists returns 404."""
        http_client, _ = client
        ids = setup_task
        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule",
            json={"schedule_value": "10m"},
        )
        assert response.status_code == 404

    async def test_delete_task_schedule_no_schedule_exists(self, client, setup_task):
        """DELETE /tasks/{task_id}/schedule when no schedule exists returns 404."""
        http_client, _ = client
        ids = setup_task
        response = await http_client.delete(
            f"/v1/{ids['tenant_id']}/tasks/{ids['task_id']}/schedule"
        )
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestWorkflowScheduleConvenience:
    """Tests for workflow convenience endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.fixture
    async def setup_workflow(self, client) -> dict:
        _, session = client
        tenant_id = f"t-{uuid4().hex[:8]}"
        workflow = _make_workflow(tenant_id)
        session.add(workflow)
        await session.flush()
        return {"tenant_id": tenant_id, "workflow_id": str(workflow.id)}

    async def test_create_workflow_schedule(self, client, setup_workflow):
        http_client, _ = client
        ids = setup_workflow
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "1h", "enabled": True},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["target_type"] == "workflow"
        assert data["target_id"] == ids["workflow_id"]

    async def test_get_workflow_schedule(self, client, setup_workflow):
        http_client, _ = client
        ids = setup_workflow
        await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "30m"},
        )
        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule"
        )
        assert response.status_code == 200

    async def test_get_workflow_schedule_not_found(self, client, setup_workflow):
        http_client, _ = client
        ids = setup_workflow
        response = await http_client.get(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule"
        )
        assert response.status_code == 404

    async def test_update_workflow_schedule(self, client, setup_workflow):
        http_client, _ = client
        ids = setup_workflow
        await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "30m"},
        )
        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["data"]["enabled"] is True

    async def test_delete_workflow_schedule(self, client, setup_workflow):
        http_client, _ = client
        ids = setup_workflow
        await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "30m"},
        )
        response = await http_client.delete(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule"
        )
        assert response.status_code == 204

    async def test_create_workflow_schedule_invalid_interval(
        self, client, setup_workflow
    ):
        """POST /workflows/{id}/schedule with invalid interval returns 400."""
        http_client, _ = client
        ids = setup_workflow
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "xyz-bad"},
        )
        assert response.status_code == 400

    async def test_create_workflow_schedule_duplicate(self, client, setup_workflow):
        """POST /workflows/{id}/schedule when schedule already exists returns 409."""
        http_client, _ = client
        ids = setup_workflow
        await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "30m"},
        )
        response = await http_client.post(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"schedule_type": "every", "schedule_value": "1h"},
        )
        assert response.status_code == 409

    async def test_update_workflow_schedule_no_schedule_exists(
        self, client, setup_workflow
    ):
        """PATCH /workflows/{id}/schedule when no schedule exists returns 404."""
        http_client, _ = client
        ids = setup_workflow
        response = await http_client.patch(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule",
            json={"enabled": True},
        )
        assert response.status_code == 404

    async def test_delete_workflow_schedule_no_schedule_exists(
        self, client, setup_workflow
    ):
        """DELETE /workflows/{id}/schedule when no schedule exists returns 404."""
        http_client, _ = client
        ids = setup_workflow
        response = await http_client.delete(
            f"/v1/{ids['tenant_id']}/workflows/{ids['workflow_id']}/schedule"
        )
        assert response.status_code == 404
