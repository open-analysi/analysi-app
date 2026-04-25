"""
API Field Completeness Tests

Tests for new Component fields and include_relationships functionality.
These tests should FAIL initially since the functionality isn't implemented yet (TDD).
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestComponentFieldCompleteness:
    """Test all Task/KU endpoints return new Component fields."""

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
    async def test_task_endpoints_return_new_component_fields(
        self, client: AsyncClient
    ):
        """Test that Task endpoints return created_by, version, last_used_at, system_only."""
        # Create a task
        task_data = {
            "name": "Field Test Task",
            "description": "Testing new Component fields",
            "directive": "Test directive",
            "script": "return 'field test'",
            "function": "testing",
            "scope": "processing",
            "created_by": str(SYSTEM_USER_ID),
            "version": "1.0.0",
            "system_only": False,
        }

        # Create task
        create_response = await client.post("/v1/test_tenant/tasks", json=task_data)
        if create_response.status_code != 201:
            print(f"Error response: {create_response.json()}")
        assert create_response.status_code == 201

        created_task = create_response.json()["data"]
        task_id = created_task["id"]

        # Verify new fields are present in creation response
        assert "created_by" in created_task
        assert "version" in created_task
        assert "last_used_at" in created_task
        assert "system_only" in created_task
        assert created_task["created_by"] == str(SYSTEM_USER_ID)
        assert created_task["version"] == "1.0.0"
        assert created_task["system_only"] is False

        # Test GET single task
        get_response = await client.get(f"/v1/test_tenant/tasks/{task_id}")
        assert get_response.status_code == 200

        task_details = get_response.json()["data"]
        assert "created_by" in task_details
        assert "version" in task_details
        assert "last_used_at" in task_details
        assert "system_only" in task_details

        # Test GET task list
        list_response = await client.get("/v1/test_tenant/tasks")
        assert list_response.status_code == 200

        tasks_list = list_response.json()["data"]
        found_task = next((t for t in tasks_list if t["id"] == task_id), None)
        assert found_task is not None
        assert "created_by" in found_task
        assert "version" in found_task
        assert "last_used_at" in found_task
        assert "system_only" in found_task

    @pytest.mark.asyncio
    async def test_ku_endpoints_return_new_component_fields(self, client: AsyncClient):
        """Test that Knowledge Unit endpoints return new Component fields."""
        # Test Table KU
        table_data = {
            "name": "Field Test Table",
            "description": "Testing new Component fields in KU",
            "content": {"data": [{"id": 1, "name": "test"}]},
            "schema": {"type": "object"},
            "created_by": str(SYSTEM_USER_ID),
            "version": "2.0.0",
            "system_only": True,
        }

        # Create table KU
        create_response = await client.post(
            "/v1/test_tenant/knowledge-units/tables", json=table_data
        )
        if create_response.status_code != 201:
            print(f"KU Error response: {create_response.json()}")
        assert create_response.status_code == 201

        created_ku = create_response.json()["data"]
        ku_id = created_ku["id"]

        # Verify new fields are present
        assert "created_by" in created_ku
        assert "version" in created_ku
        assert "last_used_at" in created_ku
        assert "system_only" in created_ku
        assert created_ku["created_by"] == str(SYSTEM_USER_ID)
        assert created_ku["version"] == "2.0.0"
        assert created_ku["system_only"] is True

        # Test KU search endpoint
        search_response = await client.get("/v1/test_tenant/knowledge-units")
        assert search_response.status_code == 200

        kus_list = search_response.json()["data"]
        found_ku = next((ku for ku in kus_list if ku["id"] == ku_id), None)
        assert found_ku is not None
        assert "created_by" in found_ku
        assert "version" in found_ku
        assert "system_only" in found_ku

    @pytest.mark.asyncio
    async def test_last_used_at_field_updates(self, client: AsyncClient):
        """Test that last_used_at field gets updated when components are used."""
        # Create a task
        task_data = {
            "name": "Usage Tracking Task",
            "script": "return 'usage test'",
            "function": "testing",
            "scope": "processing",
            "created_by": str(SYSTEM_USER_ID),
        }

        create_response = await client.post("/v1/test_tenant/tasks", json=task_data)
        task_id = create_response.json()["data"]["id"]

        # Get initial last_used_at (should be None)
        get_response = await client.get(f"/v1/test_tenant/tasks/{task_id}")
        initial_task = get_response.json()["data"]
        initial_last_used = initial_task["last_used_at"]

        # Execute the task (this should update last_used_at)
        execution_response = await client.post(
            f"/v1/test_tenant/tasks/{task_id}/run", json={}
        )
        assert execution_response.status_code == 202

        # Wait a moment for processing
        import asyncio

        await asyncio.sleep(0.1)

        # Check that last_used_at was updated
        updated_response = await client.get(f"/v1/test_tenant/tasks/{task_id}")
        updated_task = updated_response.json()["data"]
        updated_last_used = updated_task["last_used_at"]

        # last_used_at should be updated after execution
        assert updated_last_used != initial_last_used
        assert updated_last_used is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRelationships:
    """Test Task endpoints with include_relationships=true parameter."""

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
    async def test_task_get_with_relationships(self, client: AsyncClient):
        """Test GET task with include_relationships returns knowledge_units array."""
        # Create a knowledge unit
        ku_data = {
            "name": "Relationship Test KU",
            "description": "KU for testing relationships",
            "content": {"rows": [{"test": "data"}]},
            "schema": {"type": "object"},
        }

        ku_response = await client.post(
            "/v1/test_tenant/knowledge-units/tables", json=ku_data
        )
        if ku_response.status_code != 201:
            print(
                f"KU creation failed: {ku_response.status_code} - {ku_response.json()}"
            )
        assert ku_response.status_code == 201
        ku_id = ku_response.json()["data"]["id"]

        # Create a task
        task_data = {
            "name": "Relationship Test Task",
            "description": "Task for testing relationships",
            "script": "return 'relationship test'",
            "function": "testing",
            "scope": "processing",
        }

        task_response = await client.post("/v1/test_tenant/tasks", json=task_data)
        task_id = task_response.json()["data"]["id"]

        # Create a KDG relationship (task uses KU)
        edge_data = {
            "source_id": task_id,
            "target_id": ku_id,
            "relationship_type": "uses",
            "is_required": True,
        }

        edge_response = await client.post("/v1/test_tenant/kdg/edges", json=edge_data)
        assert edge_response.status_code == 201

        # Get task — include_relationships was removed to avoid N+1 queries.
        # Relationships are now accessed via the KDG API.
        get_response = await client.get(f"/v1/test_tenant/tasks/{task_id}")
        assert get_response.status_code == 200
        task_data = get_response.json()["data"]
        assert "knowledge_units" not in task_data

        # Verify KDG edge exists via KDG API
        edges_response = await client.get(f"/v1/test_tenant/kdg/nodes/{task_id}/edges")
        assert edges_response.status_code == 200
        edges = edges_response.json()["data"]
        assert len(edges) >= 1

    @pytest.mark.asyncio
    async def test_task_list_no_relationships(self, client: AsyncClient):
        """Test GET tasks list never includes relationships (removed to avoid N+1)."""
        # Get tasks list
        list_response = await client.get("/v1/test_tenant/tasks")
        assert list_response.status_code == 200
        tasks = list_response.json()["data"]

        # Verify no knowledge_units arrays — relationships accessed via KDG API
        for task in tasks:
            assert "knowledge_units" not in task

    @pytest.mark.asyncio
    async def test_kdg_edges_contain_relationship_types(self, client: AsyncClient):
        """Test that KDG edges include different relationship types."""
        # Create KUs and Task
        ku1_response = await client.post(
            "/v1/test_tenant/knowledge-units/tables",
            json={"name": "Used KU", "content": {}, "schema": {"type": "object"}},
        )
        assert ku1_response.status_code == 201
        ku1_id = ku1_response.json()["data"]["id"]

        ku2_response = await client.post(
            "/v1/test_tenant/knowledge-units/tables",
            json={"name": "Generated KU", "content": {}, "schema": {"type": "object"}},
        )
        assert ku2_response.status_code == 201
        ku2_id = ku2_response.json()["data"]["id"]

        task_response = await client.post(
            "/v1/test_tenant/tasks",
            json={
                "name": "Filter Test Task",
                "script": "return 'test'",
                "function": "testing",
                "scope": "processing",
            },
        )
        assert task_response.status_code == 201
        task_id = task_response.json()["data"]["id"]

        # Create 'uses' relationship
        await client.post(
            "/v1/test_tenant/kdg/edges",
            json={
                "source_id": task_id,
                "target_id": ku1_id,
                "relationship_type": "uses",
            },
        )

        # Create 'generates' relationship
        await client.post(
            "/v1/test_tenant/kdg/edges",
            json={
                "source_id": task_id,
                "target_id": ku2_id,
                "relationship_type": "generates",
            },
        )

        # Verify edges via KDG API (include_relationships removed from tasks)
        edges_response = await client.get(f"/v1/test_tenant/kdg/nodes/{task_id}/edges")
        assert edges_response.status_code == 200
        edges = edges_response.json()["data"]
        assert len(edges) >= 2


@pytest.mark.asyncio
@pytest.mark.integration
class TestSystemOnlyFieldProtection:
    """Test system_only field prevents unauthorized modifications."""

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
    async def test_system_only_task_cannot_be_modified(self, client: AsyncClient):
        """Test that tasks with system_only=true cannot be modified by users."""
        # Create a system-only task
        system_task_data = {
            "name": "System Only Task",
            "description": "This task cannot be modified",
            "script": "return 'system task'",
            "function": "system",
            "scope": "processing",
            "system_only": True,
            "created_by": str(SYSTEM_USER_ID),
        }

        create_response = await client.post(
            "/v1/test_tenant/tasks", json=system_task_data
        )
        assert create_response.status_code == 201

        task_id = create_response.json()["data"]["id"]

        # Attempt to update the system-only task
        update_data = {
            "name": "Modified System Task",
            "description": "Attempting to modify system task",
        }

        update_response = await client.put(
            f"/v1/test_tenant/tasks/{task_id}", json=update_data
        )

        # Should be forbidden
        assert update_response.status_code == 403
        response_data = update_response.json()
        # Error responses use RFC 7807 format: detail_data holds structured error info
        error_text = str(
            response_data.get("detail_data", response_data.get("detail", ""))
        )
        assert "system_only" in error_text

        # Attempt to delete the system-only task
        delete_response = await client.delete(f"/v1/test_tenant/tasks/{task_id}")

        # Should also be forbidden
        assert delete_response.status_code == 403
        delete_data = delete_response.json()
        error_text = str(delete_data.get("detail_data", delete_data.get("detail", "")))
        assert "system_only" in error_text

    @pytest.mark.asyncio
    async def test_regular_task_can_be_modified(self, client: AsyncClient):
        """Test that regular tasks (system_only=false) can be modified."""
        # Create a regular task
        regular_task_data = {
            "name": "Regular Task",
            "description": "This task can be modified",
            "script": "return 'regular task'",
            "function": "user",
            "scope": "processing",
            "system_only": False,
            "created_by": str(SYSTEM_USER_ID),
        }

        create_response = await client.post(
            "/v1/test_tenant/tasks", json=regular_task_data
        )
        assert create_response.status_code == 201

        task_id = create_response.json()["data"]["id"]

        # Update the regular task (should succeed)
        update_data = {
            "name": "Modified Regular Task",
            "description": "Successfully modified task",
        }

        update_response = await client.put(
            f"/v1/test_tenant/tasks/{task_id}", json=update_data
        )

        assert update_response.status_code == 200

        updated_task = update_response.json()["data"]
        assert updated_task["name"] == "Modified Regular Task"
        assert updated_task["description"] == "Successfully modified task"

        # Delete the regular task (should also succeed)
        delete_response = await client.delete(f"/v1/test_tenant/tasks/{task_id}")
        assert delete_response.status_code == 204
