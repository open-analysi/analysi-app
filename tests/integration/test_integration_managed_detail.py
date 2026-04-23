"""Integration tests for integration detail with managed_resources."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.integration import Integration
from analysi.services.task_factory import (
    create_default_schedule,
    create_health_check_task,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationDetailManagedResources:
    """Test GET /integrations/{id} includes managed_resources block."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"echo-edr-{unique_id}"

    @pytest.fixture
    async def client(
        self, integration_test_session
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
    async def integration_with_health_check(
        self, integration_test_session: AsyncSession, tenant_id, integration_id
    ):
        """Create integration with health_check managed resource."""
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
            name="Test Echo EDR",
            settings={"api_url": "http://echo-server:8000"},
            enabled=False,
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()

        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
        )
        await create_default_schedule(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component.id,
            schedule_value="5m",
            integration_id=integration_id,
        )
        await integration_test_session.flush()
        return integration

    async def test_integration_detail_includes_managed_resources(
        self,
        client,
        tenant_id,
        integration_id,
        integration_with_health_check,
    ):
        """GET /integrations/{id} includes managed_resources block."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert "managed_resources" in data

    async def test_integration_detail_managed_resources_has_task_id_and_schedule(
        self,
        client,
        tenant_id,
        integration_id,
        integration_with_health_check,
    ):
        """managed_resources block has the expected structure."""
        http_client, session = client

        response = await http_client.get(
            f"/v1/{tenant_id}/integrations/{integration_id}"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        managed = data.get("managed_resources", {})
        assert "health_check" in managed
        hc = managed["health_check"]
        assert "task_id" in hc
        assert "task_name" in hc
        assert "schedule_id" in hc
        assert "schedule" in hc
