"""Integration test for task validation at the API level."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskValidationAPI:
    """Test task validation error handling at the API level.

    Note: 422 errors use RFC 9457 Problem Details format, NOT the Sifnos
    {data, meta} envelope. Error fields are at top level:
    {"type", "title", "status", "detail", "request_id", "errors": [...]}
    """

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
    async def test_invalid_scope_returns_422(self, client: AsyncClient):
        """Test that invalid scope returns 422 with helpful error message."""
        task_data = {
            "name": "Test Task with Invalid Scope",
            "script": "return 'test'",
            "scope": "playground",  # Invalid scope
        }

        response = await client.post("/v1/default/tasks", json=task_data)

        # Should return 422 Unprocessable Entity
        assert response.status_code == 422

        # RFC 9457 Problem Details — errors list is at top level
        error_response = response.json()
        assert "errors" in error_response

        # Find the scope error
        scope_error = None
        for error in error_response["errors"]:
            if error["loc"] == ["body", "scope"]:
                scope_error = error
                break

        assert scope_error is not None
        assert "Invalid task scope 'playground'" in scope_error["msg"]
        assert "Must be one of: input, processing, output" in scope_error["msg"]

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_422(self, client: AsyncClient):
        """Test that invalid mode returns 422 with helpful error message."""
        task_data = {
            "name": "Test Task with Invalid Mode",
            "script": "return 'test'",
            "mode": "temporary",  # Invalid mode
        }

        response = await client.post("/v1/default/tasks", json=task_data)

        # Should return 422 Unprocessable Entity
        assert response.status_code == 422

        # RFC 9457 Problem Details — errors list is at top level
        error_response = response.json()
        assert "errors" in error_response

        # Find the mode error
        mode_error = None
        for error in error_response["errors"]:
            if error["loc"] == ["body", "mode"]:
                mode_error = error
                break

        assert mode_error is not None
        assert "Invalid task mode 'temporary'" in mode_error["msg"]
        assert "Must be one of: ad_hoc, saved" in mode_error["msg"]

    @pytest.mark.asyncio
    async def test_multiple_validation_errors(self, client: AsyncClient):
        """Test that multiple validation errors are all returned."""
        task_data = {
            "name": "Test Task with Multiple Errors",
            "script": "return 'test'",
            "scope": "playground",  # Invalid
            "mode": "temporary",  # Invalid
        }

        response = await client.post("/v1/default/tasks", json=task_data)

        # Should return 422 Unprocessable Entity
        assert response.status_code == 422

        # RFC 9457 Problem Details — errors list is at top level
        error_response = response.json()
        assert "errors" in error_response

        # Should have 2 errors
        errors = error_response["errors"]
        assert len(errors) == 2

        # Both errors should have helpful messages
        for error in errors:
            assert "Invalid task" in error["msg"]
            assert "Must be one of:" in error["msg"]

    @pytest.mark.asyncio
    async def test_valid_task_creation(self, client: AsyncClient):
        """Test that valid task creation succeeds."""
        task_data = {
            "name": "Valid Test Task",
            "script": "return 'test'",
            "scope": "processing",
            "mode": "saved",
        }

        response = await client.post("/v1/default/tasks", json=task_data)

        # Should succeed
        assert response.status_code == 201

        # Check task was created correctly
        task = response.json()["data"]
        assert task["name"] == "Valid Test Task"
        assert task["scope"] == "processing"
        assert task["mode"] == "saved"

    @pytest.mark.asyncio
    async def test_update_with_invalid_scope(self, client: AsyncClient):
        """Test that updating with invalid scope returns 422."""
        # First create a valid task
        task_data = {
            "name": "Task to Update",
            "script": "return 'test'",
            "scope": "processing",
        }

        create_response = await client.post("/v1/default/tasks", json=task_data)
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Try to update with invalid scope
        update_data = {"scope": "playground"}

        update_response = await client.put(
            f"/v1/default/tasks/{task_id}", json=update_data
        )

        # Should return 422
        assert update_response.status_code == 422

        # RFC 9457 Problem Details — errors list is at top level
        error_response = update_response.json()
        assert "errors" in error_response

        scope_error = error_response["errors"][0]
        assert "Invalid task scope 'playground'" in scope_error["msg"]
