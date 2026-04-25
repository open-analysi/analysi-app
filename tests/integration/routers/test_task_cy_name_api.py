"""Test that task API accepts cy_name field."""

import uuid

import pytest
from httpx import AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskCyNameAPI:
    """Test cy_name handling in Task API."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def client(self, integration_test_session):
        """Create test client with session override."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        from httpx import ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_task_with_explicit_cy_name(self, client, tenant_id):
        """Test creating a task with explicitly provided cy_name."""
        task_data = {
            "name": "My Complex Task Name",
            "cy_name": "my_custom_cy_name",
            "script": "return 'Hello from task'",
            "description": "Test task with custom cy_name",
        }

        response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)

        assert response.status_code == 201
        created_task = response.json()["data"]
        assert created_task["cy_name"] == "my_custom_cy_name"
        assert created_task["name"] == "My Complex Task Name"

    @pytest.mark.asyncio
    async def test_create_task_without_cy_name_auto_generates(self, client, tenant_id):
        """Test that cy_name is auto-generated when not provided."""
        task_data = {
            "name": "Another Task With Spaces",
            "script": "return 'Auto-generated cy_name'",
            "description": "Test task without cy_name",
        }

        response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)

        assert response.status_code == 201
        created_task = response.json()["data"]
        # Auto-generated from name
        assert created_task["cy_name"] == "another_task_with_spaces"
        assert created_task["name"] == "Another Task With Spaces"

    @pytest.mark.asyncio
    async def test_create_task_duplicate_cy_name_fails(self, client, tenant_id):
        """Test that duplicate cy_name results in conflict."""
        task_data1 = {
            "name": "First Task",
            "cy_name": "unique_task_name",
            "script": "return 'First'",
        }

        # Create first task
        response1 = await client.post(f"/v1/{tenant_id}/tasks", json=task_data1)
        assert response1.status_code == 201

        # Try to create second task with same cy_name
        task_data2 = {
            "name": "Second Task",
            "cy_name": "unique_task_name",  # Same cy_name
            "script": "return 'Second'",
        }

        response2 = await client.post(f"/v1/{tenant_id}/tasks", json=task_data2)
        assert response2.status_code == 409  # Conflict
        error = response2.json()
        detail = error["detail"]
        detail_str = detail["error"] if isinstance(detail, dict) else detail
        assert "already exists" in detail_str

    @pytest.mark.asyncio
    async def test_update_task_cy_name(self, client, tenant_id):
        """Test updating a task's cy_name."""
        # Create task
        task_data = {
            "name": "Original Task",
            "cy_name": "original_cy_name",
            "script": "return 'Original'",
        }

        response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)
        assert response.status_code == 201
        task_id = response.json()["data"]["id"]

        # Update cy_name
        update_data = {"cy_name": "updated_cy_name"}

        response = await client.put(
            f"/v1/{tenant_id}/tasks/{task_id}", json=update_data
        )
        assert response.status_code == 200
        updated_task = response.json()["data"]
        assert updated_task["cy_name"] == "updated_cy_name"
        assert updated_task["name"] == "Original Task"  # Name unchanged

    @pytest.mark.asyncio
    async def test_invalid_cy_name_format_rejected(self, client, tenant_id):
        """Test that invalid cy_name format is rejected."""
        invalid_cy_names = [
            "CamelCase",  # Must be lowercase
            "with-dashes",  # Only underscores allowed
            "123_starts_with_number",  # Must start with letter
            "has spaces",  # No spaces
            "",  # Empty string
        ]

        for invalid_name in invalid_cy_names:
            task_data = {
                "name": "Test Task",
                "cy_name": invalid_name,
                "script": "return 'test'",
            }

            response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)
            assert response.status_code == 422, f"Should reject cy_name: {invalid_name}"

    @pytest.mark.asyncio
    async def test_query_task_by_cy_name(self, client, tenant_id):
        """Test querying tasks by cy_name."""
        # Create task with specific cy_name
        task_data = {
            "name": "Queryable Task",
            "cy_name": "test_query_task",
            "script": "return 'Found me!'",
        }

        response = await client.post(f"/v1/{tenant_id}/tasks", json=task_data)
        assert response.status_code == 201

        # Query by cy_name
        response = await client.get(
            f"/v1/{tenant_id}/tasks", params={"cy_name": "test_query_task"}
        )
        assert response.status_code == 200
        tasks = response.json()["data"]
        assert len(tasks) == 1
        assert tasks[0]["cy_name"] == "test_query_task"
        assert tasks[0]["name"] == "Queryable Task"
