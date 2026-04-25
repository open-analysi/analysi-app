"""
Task Execution API Tests

Tests for task execution endpoints and async processing.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskExecutionEndpoints:
    """Test task execution API endpoints."""

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
    async def test_execute_existing_task_returns_202_with_headers(
        self, client: AsyncClient
    ):
        """Test that executing an existing task returns 202 with proper headers."""
        # First create a task to execute
        task_data = {
            "name": "Test Execution Task",
            "description": "A task for testing execution",
            "directive": "Test system message",
            "script": "return 'Hello from execution'",
            "function": "testing",
            "scope": "processing",
        }

        task_response = await client.post("/v1/test_tenant/tasks", json=task_data)
        assert task_response.status_code == 201
        task_id = task_response.json()["data"]["id"]

        # Execute the task
        execution_response = await client.post(
            f"/v1/test_tenant/tasks/{task_id}/run",
            json={"input": {"message": "test input"}},
        )

        # Should return 202 Accepted for async operation
        assert execution_response.status_code == 202

        body = execution_response.json()
        assert "data" in body, "Response should be wrapped in {data, meta} envelope"
        response_data = body["data"]
        assert "trid" in response_data, "Response should include task run ID (trid)"

        # Check required headers for async operation
        headers = execution_response.headers
        assert "Location" in headers, (
            "Response should include Location header for polling"
        )
        assert "Retry-After" in headers, "Response should include Retry-After header"

        # Location header should point to status endpoint
        trid = response_data["trid"]
        expected_location = f"/v1/test_tenant/task-runs/{trid}"
        assert expected_location in headers["Location"]

    @pytest.mark.asyncio
    async def test_ad_hoc_execution_with_cy_script(self, client: AsyncClient):
        """Test ad-hoc execution: POST with task_id=null and cy_script in body."""
        # Execute ad-hoc Cy script
        execution_data = {
            "cy_script": "return 'Ad-hoc execution result'",
            "input": {"test": "data"},
            "executor_config": {"executor_type": "default", "timeout_seconds": 30},
        }

        response = await client.post(
            "/v1/test_tenant/tasks/run",
            json=execution_data,  # No task_id in URL
        )

        # Should return 202 Accepted
        assert response.status_code == 202

        body = response.json()
        assert "data" in body
        response_data = body["data"]
        assert "trid" in response_data
        assert "Location" in response.headers
        assert "Retry-After" in response.headers
