"""Integration tests for registry actions endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestRegistryActionsAPI:
    """Test GET /registry/{type}/actions endpoints."""

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

    async def test_get_actions_for_integration_type(self, client):
        """GET /registry/{type}/actions returns all actions."""
        http_client, session = client
        tenant = "test-tenant"

        response = await http_client.get(
            f"/v1/{tenant}/integrations/registry/splunk/actions"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        # Splunk has multiple actions
        assert len(data) >= 1
        # Each action should have id, name, categories
        for action in data:
            assert "action_id" in action
            assert "name" in action
            assert "categories" in action

    async def test_get_specific_action(self, client):
        """GET /registry/{type}/actions/{action_id} returns action details."""
        http_client, session = client
        tenant = "test-tenant"

        response = await http_client.get(
            f"/v1/{tenant}/integrations/registry/splunk/actions/health_check"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["action_id"] == "health_check"
        assert "name" in data
        assert "description" in data

    async def test_get_actions_unknown_type_returns_404(self, client):
        """GET /registry/bogus/actions returns 404."""
        http_client, session = client
        tenant = "test-tenant"

        response = await http_client.get(
            f"/v1/{tenant}/integrations/registry/bogus_nonexistent/actions"
        )

        assert response.status_code == 404

    async def test_get_specific_action_unknown_returns_404(self, client):
        """GET /registry/{type}/actions/bogus returns 404."""
        http_client, session = client
        tenant = "test-tenant"

        response = await http_client.get(
            f"/v1/{tenant}/integrations/registry/splunk/actions/bogus_nonexistent"
        )

        assert response.status_code == 404
