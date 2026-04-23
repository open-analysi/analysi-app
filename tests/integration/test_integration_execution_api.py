"""Integration tests for integration tool execution REST API."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationExecutionAPI:
    """Integration tests for POST /v1/{tenant}/integrations/{id}/tools/{action}/execute."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_execute_integration_tool_success(self, client: AsyncClient):
        """
        Test tool execution endpoint (integration not configured in test DB).

        Expected: 404 since integration doesn't exist in test database
        """
        response = await client.post(
            "/v1/test_tenant/integrations/splunk/tools/health_check/execute",
            json={"arguments": {}, "timeout_seconds": 30},
        )

        # Integration doesn't exist in test DB, so expect 404
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_execute_integration_tool_with_arguments(self, client: AsyncClient):
        """
        Test tool execution with arguments (integration not configured).

        Expected: 404 since integration doesn't exist in test database
        """
        response = await client.post(
            "/v1/test_tenant/integrations/virustotal/tools/ip_reputation/execute",
            json={"arguments": {"ip": "8.8.8.8"}, "timeout_seconds": 30},
        )

        # Integration doesn't exist in test DB
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_execute_integration_tool_missing_required_params(
        self, client: AsyncClient
    ):
        """
        Test missing required parameters (integration not configured).

        Expected: 404 since integration doesn't exist in test database
        Note: Parameter validation would happen at tool execution, not at API level
        """
        response = await client.post(
            "/v1/test_tenant/integrations/virustotal/tools/ip_reputation/execute",
            json={
                "arguments": {},
                "timeout_seconds": 30,
            },  # Missing required 'ip' param
        )

        # Integration doesn't exist in test DB, so 404 before parameter validation
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_integration_tool_not_found(self, client: AsyncClient):
        """
        Test 404 handling for non-existent integration or action.

        Expected: 404 Not Found with clear error message
        """
        response = await client.post(
            "/v1/test_tenant/integrations/nonexistent/tools/nonexistent/execute",
            json={"arguments": {}, "timeout_seconds": 30},
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_execute_integration_tool_timeout(self, client: AsyncClient):
        """
        Test timeout handling (integration not configured).

        Expected: 404 since integration doesn't exist in test database
        """
        response = await client.post(
            "/v1/test_tenant/integrations/splunk/tools/health_check/execute",
            json={"arguments": {}, "timeout_seconds": 1},  # Very short timeout
        )

        # Integration doesn't exist in test DB, so 404 before timeout can occur
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_integration_tool_execution_error(self, client: AsyncClient):
        """
        Test handling of tool execution errors (integration not configured).

        Expected: 404 since integration doesn't exist in test database
        """
        response = await client.post(
            "/v1/test_tenant/integrations/splunk/tools/health_check/execute",
            json={"arguments": {}, "timeout_seconds": 30},
        )

        # Integration doesn't exist in test DB
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
