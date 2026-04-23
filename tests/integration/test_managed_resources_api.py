"""Integration tests for Managed Resources REST API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.integration import Integration
from analysi.services.task_factory import (
    create_alert_ingestion_task,
    create_default_schedule,
    create_health_check_task,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestManagedResourcesAPI:
    """Test managed resources REST endpoints."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        app.dependency_overrides.clear()

    @pytest.fixture
    async def integration_with_resources(
        self, integration_test_session: AsyncSession, tenant_id, integration_id
    ):
        """Create integration with both alert_ingestion and health_check resources."""
        # Create the Integration row
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            name="Test Splunk",
            description="Test instance",
            settings={"host": "localhost", "port": 8089},
            enabled=True,
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()

        # Create alert ingestion task + schedule
        ingestion_task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        ingestion_schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=ingestion_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )

        # Create health check task + schedule
        health_task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        health_schedule = await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=health_task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )

        await integration_test_session.flush()

        return {
            "ingestion_task": ingestion_task,
            "ingestion_schedule": ingestion_schedule,
            "health_task": health_task,
            "health_schedule": health_schedule,
        }

    async def test_get_managed_resources_list(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed returns both resources for an AlertSource integration."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "alert_ingestion" in data
        assert "health_check" in data

    async def test_get_managed_task(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/health_check/task returns task details."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/task"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "task_id" in data
        assert "name" in data
        assert "script" in data

    async def test_get_managed_task_unknown_key_returns_404(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/bogus/task returns 404."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/bogus/task"
        )

        assert response.status_code == 404

    async def test_update_managed_task(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """PUT /managed/health_check/task updates the task script."""
        http_client, session = client

        new_script = "return app::splunk::health_check(verbose=true)"
        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/task",
            json={"script": new_script},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["script"] == new_script

    async def test_get_managed_schedule(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/health_check/schedule returns the schedule."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/schedule"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "schedule_id" in data
        assert "schedule_value" in data

    async def test_update_managed_schedule(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """PUT /managed/health_check/schedule updates the interval."""
        http_client, session = client

        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/schedule",
            json={"schedule_value": "120s", "enabled": True},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["schedule_value"] == "120s"
        assert data["enabled"] is True

    async def test_noop_schedule_update_preserves_next_run_at(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """PUT with empty body does not reset next_run_at."""
        http_client, session = client

        # First enable the schedule so next_run_at gets set
        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/schedule",
            json={"enabled": True},
        )
        assert response.status_code == 200
        original_next = response.json()["data"]["next_run_at"]
        assert original_next is not None

        # Now send an empty update (no fields changed)
        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/schedule",
            json={},
        )
        assert response.status_code == 200
        after_noop_next = response.json()["data"]["next_run_at"]

        # next_run_at should not have been reset
        assert after_noop_next == original_next

    async def test_list_managed_runs(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/health_check/runs returns TaskRuns (empty initially)."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/runs"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)

    async def test_trigger_managed_run(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """POST /managed/health_check/run creates an ad-hoc TaskRun."""
        http_client, session = client

        response = await http_client.post(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/run",
            json={},
        )

        assert response.status_code == 202
        data = response.json()["data"]
        assert "task_run_id" in data
        assert data["status"] == "running"

    # ── Error path tests ──────────────────────────────────────────────

    async def test_list_managed_resources_nonexistent_integration(
        self, client, tenant_id
    ):
        """GET /managed with non-existent integration returns empty dict."""
        http_client, _ = client
        fake_integration = f"nonexistent-{uuid4().hex[:8]}"

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{fake_integration}/managed"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # No system tasks exist for a nonexistent integration, so result is empty
        assert data == {}

    async def test_get_managed_task_invalid_resource_key(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/{invalid_key}/task returns 404."""
        http_client, _ = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/nonexistent_key/task"
        )

        assert response.status_code == 404

    async def test_get_managed_schedule_invalid_resource_key(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/{invalid_key}/schedule returns 404."""
        http_client, _ = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/nonexistent_key/schedule"
        )

        assert response.status_code == 404

    async def test_update_managed_schedule_invalid_interval(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """PUT /managed/{key}/schedule with invalid interval returns 400."""
        http_client, _ = client

        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/schedule",
            json={"schedule_value": "bad-interval"},
        )

        assert response.status_code == 400

    async def test_update_managed_task_with_empty_body(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """PUT /managed/{key}/task with empty body is a no-op (returns current state)."""
        http_client, _ = client

        response = await http_client.put(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/health_check/task",
            json={},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        # Should still return the task data unchanged
        assert "task_id" in data
        assert "script" in data

    async def test_trigger_managed_run_invalid_resource_key(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """POST /managed/{invalid_key}/run returns 404."""
        http_client, _ = client

        response = await http_client.post(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/bogus_key/run",
            json={},
        )

        assert response.status_code == 404

    async def test_list_managed_runs_invalid_resource_key(
        self, client, tenant_id, integration_id, integration_with_resources
    ):
        """GET /managed/{invalid_key}/runs returns 404."""
        http_client, _ = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}/managed/bogus_key/runs"
        )

        assert response.status_code == 404

    async def test_get_managed_task_nonexistent_integration(self, client, tenant_id):
        """GET /managed/health_check/task with nonexistent integration returns 404."""
        http_client, _ = client
        fake_int = f"no-such-int-{uuid4().hex[:8]}"

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{fake_int}/managed/health_check/task"
        )

        assert response.status_code == 404
