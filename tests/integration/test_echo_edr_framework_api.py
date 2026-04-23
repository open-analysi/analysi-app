"""
Integration test for Echo EDR via Framework and REST API.

Verifies that Echo EDR works end-to-end via the framework:
- Create integration via API
- Get integration details via API
- List actions via registry API
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.integration
class TestEchoEDRFrameworkAPI:
    """Test Echo EDR integration via framework and REST API."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_echo_edr_integration(self, client):
        """Test creating Echo EDR integration via API."""
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_data = {
            "integration_id": "echo-edr-test",
            "integration_type": "echo_edr",
            "name": "Test Echo EDR",
            "description": "Test Echo EDR instance",
            "enabled": True,
            "settings": {"api_url": "http://test-echo:8000"},
        }

        # Act
        response = await http_client.post(
            f"/v1/{tenant}/integrations", json=integration_data
        )

        # Commit to ensure data persists
        await session.commit()

        # Assert
        if response.status_code != 201:
            print(f"Error: {response.json()}")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["integration_id"] == "echo-edr-test"
        assert data["integration_type"] == "echo_edr"
        assert data["name"] == "Test Echo EDR"
        assert data["enabled"] is True
        assert "health" in data

    @pytest.mark.asyncio
    async def test_echo_edr_in_registry_list(self, client):
        """Test that Echo EDR appears in integration types registry."""
        http_client, session = client

        # Act
        response = await http_client.get("/v1/test-tenant/integrations/registry")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]

        # Find echo_edr
        integration_types = [i["integration_type"] for i in data]
        assert "echo_edr" in integration_types

        # Verify echo_edr details
        echo_edr = next(i for i in data if i["integration_type"] == "echo_edr")
        assert echo_edr["display_name"] == "Echo EDR"
        assert echo_edr["action_count"] == 9

    @pytest.mark.asyncio
    async def test_get_echo_edr_integration_type_details(self, client):
        """Test getting Echo EDR integration type details from registry."""
        http_client, session = client

        # Act
        response = await http_client.get(
            "/v1/test-tenant/integrations/registry/echo_edr"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["integration_type"] == "echo_edr"
        assert data["display_name"] == "Echo EDR"
        assert "actions" in data
        assert isinstance(data["actions"], list)

        # Verify health_check action details
        health_check = next(
            a for a in data["actions"] if a["action_id"] == "health_check"
        )
        assert health_check["name"] == "Health Check"
        assert "categories" in health_check
        assert "params_schema" in health_check

    @pytest.mark.asyncio
    async def test_get_echo_edr_action_details(self, client):
        """Test getting specific Echo EDR action details."""
        http_client, session = client

        # Act
        response = await http_client.get(
            "/v1/test-tenant/integrations/registry/echo_edr/actions/health_check"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["action_id"] == "health_check"
        assert data["name"] == "Health Check"
        assert "categories" in data
        assert "params_schema" in data
        assert "result_schema" in data
