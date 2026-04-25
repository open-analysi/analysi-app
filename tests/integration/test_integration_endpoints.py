"""Integration tests for Integration REST API endpoints."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.integration import Integration


@pytest.mark.integration
class TestIntegrationCRUDEndpoints:
    """Test Integration CRUD operations via REST API."""

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

    @pytest.fixture
    async def sample_integration(self, integration_test_session):
        """Create a sample integration for testing."""
        integration = Integration(
            tenant_id="test-tenant",
            integration_id="splunk-test",
            integration_type="splunk",
            name="Test Splunk",
            description="Test Splunk instance",
            settings={"host": "localhost", "port": 8089},
            enabled=True,
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()
        return integration

    @pytest.mark.asyncio
    async def test_create_integration_endpoint(self, client):
        """Test POST /v1/{tenant}/integrations creates integration."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_data = {
            "integration_id": "splunk-prod",
            "integration_type": "splunk",
            "name": "Production Splunk",
            "description": "Production Splunk instance",
            "enabled": True,
            "settings": {"host": "splunk.example.com", "port": 8089},
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
        assert data["integration_id"] == integration_data["integration_id"]
        assert data["integration_type"] == integration_data["integration_type"]
        assert data["name"] == integration_data["name"]
        assert data["enabled"] is True
        assert "created_at" in data
        assert "health" in data

    @pytest.mark.asyncio
    async def test_create_duplicate_integration_returns_409(
        self, client, sample_integration
    ):
        """Test creating duplicate integration returns 409 Conflict."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_data = {
            "integration_id": "splunk-test",  # Same as sample_integration
            "integration_type": "splunk",
            "name": "Duplicate Splunk",
        }

        # Act
        response = await http_client.post(
            f"/v1/{tenant}/integrations", json=integration_data
        )

        # Assert
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "already exists" in detail

    @pytest.mark.asyncio
    async def test_create_integration_with_invalid_type_returns_409(self, client):
        """Test creating integration with unsupported integration_type returns 409."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_data = {
            "integration_id": "invalid-test",
            "integration_type": "nonexistent_integration",  # Invalid type
            "name": "Invalid Integration",
            "description": "Integration with unsupported type",
            "enabled": True,
            "settings": {},
        }

        # Act
        response = await http_client.post(
            f"/v1/{tenant}/integrations", json=integration_data
        )

        # Assert
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail == "Integration type not supported"

    @pytest.mark.asyncio
    async def test_list_integrations_endpoint(self, client, sample_integration):
        """Test GET /v1/{tenant}/integrations returns list."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(f"/v1/{tenant}/integrations")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1
        # Find our sample integration
        found = False
        for integration in data:
            if integration["integration_id"] == "splunk-test":
                found = True
                assert integration["name"] == "Test Splunk"
                assert "health" in integration
        assert found, "Sample integration not found in list"

    @pytest.mark.asyncio
    async def test_get_integration_endpoint(self, client, sample_integration):
        """Test GET /v1/{tenant}/integrations/{id} returns integration."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-test"

        # Act
        response = await http_client.get(f"/v1/{tenant}/integrations/{integration_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["integration_id"] == integration_id
        assert data["name"] == "Test Splunk"
        assert data["settings"]["host"] == "localhost"
        assert "health" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_integration_returns_404(self, client):
        """Test GET for non-existent integration returns 404."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(f"/v1/{tenant}/integrations/non-existent")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_integration_endpoint(self, client, sample_integration):
        """Test PATCH /v1/{tenant}/integrations/{id} updates integration."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-test"
        update_data = {
            "name": "Updated Splunk Name",
            "enabled": False,
            "settings": {"host": "new-host.example.com", "port": 9000},
        }

        # Act
        response = await http_client.patch(
            f"/v1/{tenant}/integrations/{integration_id}", json=update_data
        )

        # Commit changes
        await session.commit()

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "Updated Splunk Name"
        assert data["enabled"] is False
        assert data["settings"]["host"] == "new-host.example.com"

    @pytest.mark.asyncio
    async def test_delete_integration_endpoint(self, client, sample_integration):
        """Test DELETE /v1/{tenant}/integrations/{id} removes integration."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-test"

        # Act
        response = await http_client.delete(
            f"/v1/{tenant}/integrations/{integration_id}"
        )

        # Commit deletion
        await session.commit()

        # Assert
        assert response.status_code == 204

        # Verify it's deleted
        get_response = await http_client.get(
            f"/v1/{tenant}/integrations/{integration_id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_integration_health_endpoint(self, client, sample_integration):
        """Test GET /v1/{tenant}/integrations/{id}/health returns health status."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-test"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/integrations/{integration_id}/health"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert "status" in data
        assert "message" in data
        assert "recent_failure_rate" in data
        # With no health check runs, status is unknown
        assert data["status"] == "unknown"
        assert "No health check data" in data["message"]

    @pytest.mark.asyncio
    async def test_get_integration_connectors_endpoint_removed(
        self, client, sample_integration
    ):
        """Connectors endpoint was removed — verify 404."""
        http_client, session = client
        tenant = "test-tenant"
        integration_id = "splunk-test"

        response = await http_client.get(
            f"/v1/{tenant}/integrations/{integration_id}/connectors"
        )
        assert response.status_code == 404


@pytest.mark.skip(
    reason="Connector-based schedule endpoints removed. Use /schedules API instead."
)
@pytest.mark.integration
class TestScheduleEndpoints:
    """Test Schedule management endpoints via REST API (REMOVED)."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
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
    async def integration_with_schedule(self, integration_test_session):
        """Create an integration with a schedule for testing."""
        # Create integration
        integration = Integration(
            tenant_id="test-tenant",
            integration_id="splunk-scheduled",
            integration_type="splunk",
            name="Scheduled Splunk",
            enabled=True,
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()

        return integration

    @pytest.mark.asyncio
    async def test_create_schedule_endpoint(self, client, integration_with_schedule):
        """Test POST schedule endpoint creates a new schedule."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-scheduled"
        connector = "pull_alerts"
        schedule_data = {
            "integration_id": integration_id,
            "integration_type": "splunk",
            "connector": connector,
            "schedule_type": "every",
            "schedule_value": "1m",
            "enabled": True,
            "params": {"lookback_seconds": 120},
        }

        # Act
        response = await http_client.post(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules",
            json=schedule_data,
        )

        # Commit
        await session.commit()

        # Assert
        assert response.status_code == 201
        data = response.json()["data"]
        assert "schedule_id" in data
        assert data["schedule_type"] == "every"
        assert data["schedule_value"] == "1m"
        assert data["enabled"] is True

    @pytest.mark.asyncio
    async def test_list_schedules_endpoint(self, client, integration_with_schedule):
        """Test GET schedules endpoint returns list."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-scheduled"
        connector = "pull_alerts"

        # Create a schedule first
        schedule_data = {
            "integration_id": integration_id,
            "integration_type": "splunk",
            "connector": connector,
            "schedule_type": "every",
            "schedule_value": "5m",
            "enabled": True,
        }
        await http_client.post(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules",
            json=schedule_data,
        )
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_update_schedule_endpoint(self, client, integration_with_schedule):
        """Test PATCH schedule endpoint updates schedule."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-scheduled"
        connector = "pull_alerts"

        # Create a schedule first
        schedule_data = {
            "integration_id": integration_id,
            "integration_type": "splunk",
            "connector": connector,
            "schedule_type": "every",
            "schedule_value": "10m",
            "enabled": True,
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules",
            json=schedule_data,
        )
        await session.commit()
        schedule_id = create_response.json()["data"]["schedule_id"]

        # Update data
        update_data = {"enabled": False, "schedule_value": "30m"}

        # Act
        response = await http_client.patch(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}",
            json=update_data,
        )
        await session.commit()

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["enabled"] is False
        assert data["schedule_value"] == "30m"

    @pytest.mark.asyncio
    async def test_delete_schedule_endpoint(self, client, integration_with_schedule):
        """Test DELETE schedule endpoint removes schedule."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        integration_id = "splunk-scheduled"
        connector = "pull_alerts"

        # Create a schedule first
        schedule_data = {
            "integration_id": integration_id,
            "integration_type": "splunk",
            "connector": connector,
            "schedule_type": "every",
            "schedule_value": "1h",
            "enabled": True,
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules",
            json=schedule_data,
        )
        await session.commit()
        schedule_id = create_response.json()["data"]["schedule_id"]

        # Act
        response = await http_client.delete(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}"
        )
        await session.commit()

        # Assert
        assert response.status_code == 204

        # Verify schedule is deleted by trying to update it
        update_response = await http_client.patch(
            f"/v1/{tenant}/integrations/{integration_id}/connectors/{connector}/schedules/{schedule_id}",
            json={"enabled": True},
        )
        assert update_response.status_code == 404


@pytest.mark.integration
class TestRegistryEndpoints:
    """Test Registry endpoints via REST API."""

    @pytest.fixture
    async def client(self) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_list_integration_types_registry(self, client):
        """Test GET /v1/{tenant}/integrations/registry returns all integration types."""
        # Arrange
        tenant = "test-tenant"

        # Act
        response = await client.get(f"/v1/{tenant}/integrations/registry")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert isinstance(data, list)
        # Should have integration types
        integration_types = [i["integration_type"] for i in data]
        assert "splunk" in integration_types
        assert "echo_edr" in integration_types

    @pytest.mark.asyncio
    async def test_get_integration_type_registry(self, client):
        """Test GET /v1/{tenant}/integrations/registry/{type} returns integration details."""
        tenant = "test-tenant"

        response = await client.get(f"/v1/{tenant}/integrations/registry/splunk")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["integration_type"] == "splunk"
        # "connectors" renamed to "actions"
        assert "actions" in data
        action_ids = [a["action_id"] for a in data["actions"]]
        assert "health_check" in action_ids
        assert "pull_alerts" in action_ids

    @pytest.mark.asyncio
    async def test_get_action_details_registry(self, client):
        """Test GET /v1/{tenant}/integrations/registry/{type}/actions/{action_id}."""
        tenant = "test-tenant"

        response = await client.get(
            f"/v1/{tenant}/integrations/registry/splunk/actions/pull_alerts"
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["action_id"] == "pull_alerts"
        assert data["name"] == "Pull Alerts"
        assert "params_schema" in data
        assert "result_schema" in data
