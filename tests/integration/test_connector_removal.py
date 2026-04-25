"""Integration tests for connector endpoint removal.

Verifies that old connector-specific REST endpoints are gone and that
core integration endpoints still work after the cleanup.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

pytestmark = [pytest.mark.integration]


@pytest.mark.asyncio
class TestConnectorEndpointsRemoved:
    """Test that old connector endpoints no longer respond."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def test_connector_runs_post_returns_404(self, client: AsyncClient):
        """POST connector-runs endpoint is gone."""
        response = await client.post(
            "/v1/test-tenant/integrations/splunk-dev/connectors/pull_alerts/connector-runs",
            json={"params": {}},
        )
        # Should be 404 (no route matches) or 405
        assert response.status_code in (404, 405)

    async def test_connector_runs_get_returns_404(self, client: AsyncClient):
        """GET connector-runs endpoint is gone."""
        response = await client.get(
            "/v1/test-tenant/integrations/splunk-dev/connectors/pull_alerts/connector-runs",
        )
        assert response.status_code in (404, 405)

    async def test_connector_schedules_post_returns_404(self, client: AsyncClient):
        """POST connector schedules endpoint is gone."""
        response = await client.post(
            "/v1/test-tenant/integrations/splunk-dev/connectors/pull_alerts/schedules",
            json={"schedule_type": "every", "schedule_value": "5m"},
        )
        assert response.status_code in (404, 405)

    async def test_connector_schedules_get_returns_404(self, client: AsyncClient):
        """GET connector schedules endpoint is gone."""
        response = await client.get(
            "/v1/test-tenant/integrations/splunk-dev/connectors/pull_alerts/schedules",
        )
        assert response.status_code in (404, 405)

    async def test_connectors_list_returns_404(self, client: AsyncClient):
        """GET connectors list endpoint is gone."""
        response = await client.get(
            "/v1/test-tenant/integrations/splunk-dev/connectors",
        )
        assert response.status_code in (404, 405)

    async def test_connector_registry_detail_returns_404(self, client: AsyncClient):
        """GET connector registry detail endpoint is gone."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/splunk/connectors/pull_alerts",
        )
        assert response.status_code in (404, 405)

    async def test_legacy_runs_list_returns_404(self, client: AsyncClient):
        """GET /{id}/runs (legacy IntegrationRun-based) is gone."""
        response = await client.get(
            "/v1/test-tenant/integrations/splunk-dev/runs",
        )
        assert response.status_code in (404, 405)


@pytest.mark.asyncio
class TestCoreEndpointsStillWork:
    """Test that core integration endpoints still function after cleanup."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    async def test_list_integrations_works(self, client: AsyncClient):
        """GET /integrations still works."""
        response = await client.get("/v1/test-tenant/integrations")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body

    async def test_registry_list_works(self, client: AsyncClient):
        """GET /integrations/registry still works."""
        response = await client.get("/v1/test-tenant/integrations/registry")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body

    async def test_actions_endpoint_works(self, client: AsyncClient):
        """GET /integrations/registry/{type}/actions still works."""
        response = await client.get(
            "/v1/test-tenant/integrations/registry/splunk/actions"
        )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body

    async def test_integration_health_works(self, client: AsyncClient):
        """GET /integrations/{id}/health still works."""
        # First create an integration
        create_resp = await client.post(
            "/v1/test-tenant/integrations",
            json={
                "integration_type": "echo_edr",
                "name": "Test Echo",
                "enabled": True,
            },
        )
        if create_resp.status_code == 201:
            integration_id = create_resp.json()["data"]["integration_id"]
            response = await client.get(
                f"/v1/test-tenant/integrations/{integration_id}/health"
            )
            assert response.status_code == 200
