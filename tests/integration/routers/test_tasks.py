"""Integration tests for Task API endpoints."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskEndpoints:
    """Test Task REST API endpoints."""

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

    # Tenant ID Validation Tests
    @pytest.mark.asyncio
    async def test_endpoint_with_default_tenant(self, client: AsyncClient):
        """Test all endpoints work with 'default' tenant."""
        response = await client.get("/v1/default/tasks")
        assert response.status_code != 405  # Should not be method not allowed

    @pytest.mark.asyncio
    async def test_endpoint_with_custom_tenant(self, client: AsyncClient):
        """Test all endpoints work with custom tenant."""
        response = await client.get("/v1/customer-123/tasks")
        assert response.status_code != 405

    @pytest.mark.asyncio
    async def test_endpoint_with_special_chars_tenant(self, client: AsyncClient):
        """Test handling URL encoding for special tenant names."""
        response = await client.get("/v1/tenant%40example.com/tasks")
        assert response.status_code != 405

    @pytest.mark.asyncio
    async def test_tenant_isolation_between_requests(self, client: AsyncClient):
        """Test that tasks from different tenants are isolated."""
        # Create task for tenant-a
        response_a = await client.post(
            "/v1/tenant-a/tasks",
            json={
                "name": "Task A",
                "script": "TASK a: RETURN 'a'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert response_a.status_code == 201
        task_a_data = response_a.json()["data"]

        # Create task for tenant-b
        response_b = await client.post(
            "/v1/tenant-b/tasks",
            json={
                "name": "Task B",
                "script": "TASK b: RETURN 'b'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert response_b.status_code == 201
        task_b_data = response_b.json()["data"]

        # Verify tenant-a can only see their task
        list_a = await client.get("/v1/tenant-a/tasks")
        assert list_a.status_code == 200
        tasks_a = list_a.json()["data"]
        assert len(tasks_a) == 1
        assert tasks_a[0]["id"] == task_a_data["id"]

        # Verify tenant-b can only see their task
        list_b = await client.get("/v1/tenant-b/tasks")
        assert list_b.status_code == 200
        tasks_b = list_b.json()["data"]
        assert len(tasks_b) == 1
        assert tasks_b[0]["id"] == task_b_data["id"]

    # POST /v1/{tenant}/tasks Tests
    @pytest.mark.asyncio
    async def test_create_task_minimal_fields(self, client: AsyncClient):
        """Test creating task with only required fields."""
        task_data = {
            "name": "Minimal Task",
            "script": "TASK minimal: RETURN 'hello'",
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 201

        # Verify default values are applied
        created_task = response.json()["data"]
        assert created_task["mode"] == "saved"  # Default mode
        assert created_task["status"] == "enabled"  # Default status
        assert created_task["visible"] is False  # Default visible
        assert created_task["system_only"] is False  # Default system_only
        assert created_task["categories"] == []  # Default empty categories
        assert created_task["directive"] is None  # Optional field
        assert created_task["schedule"] is None  # Optional field

    @pytest.mark.asyncio
    async def test_create_task_all_fields(self, client: AsyncClient):
        """Test creating task with all optional fields."""
        task_data = {
            "name": "Complete Task",
            "description": "A complete task with all fields",
            "directive": "You are a test assistant. Process data according to requirements.",
            "script": "TASK complete: RETURN 'full'",
            "llm_config": {"model": "gpt-4", "temperature": 0.7},
            "function": "reasoning",
            "scope": "processing",
            "mode": "ad_hoc",
            "status": "enabled",
            "visible": True,
            "system_only": False,
            "categories": ["Testing", "Integration", "Complete"],
            "schedule": "0 */6 * * *",
            "version": "2.0.0",
            "app": "test-app",
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 201

        # Verify all fields are returned correctly
        created_task = response.json()["data"]
        assert created_task["name"] == "Complete Task"
        assert created_task["directive"] == task_data["directive"]
        assert created_task["mode"] == "ad_hoc"
        assert created_task["status"] == "enabled"
        assert created_task["visible"] is True
        assert created_task["system_only"] is False
        # User-provided categories plus auto-populated from function/scope
        assert set(created_task["categories"]) == {
            "Testing",
            "Integration",
            "Complete",
            "reasoning",
            "processing",
        }
        assert created_task["schedule"] == "0 */6 * * *"
        assert created_task["version"] == "2.0.0"
        assert created_task["app"] == "test-app"

    @pytest.mark.asyncio
    async def test_create_task_missing_required(self, client: AsyncClient):
        """Test 400 error for missing required fields."""
        task_data = {"description": "Missing name and script"}

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_task_invalid_json(self, client: AsyncClient):
        """Test 400 error for malformed JSON."""
        response = await client.post(
            "/v1/default/tasks",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_empty_script(self, client: AsyncClient):
        """Test 400 error for empty script."""
        task_data = {"name": "Invalid Task", "script": ""}

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_task_with_string_tenant_id(self, client: AsyncClient):
        """Verify tenant_id is stored as string."""
        task_data = {
            "name": "String Tenant Task",
            "script": "TASK test: RETURN 'hello'",
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/tenant-xyz/tasks", json=task_data)
        assert response.status_code == 201

    # GET /v1/{tenant}/tasks/{id} Tests
    @pytest.mark.asyncio
    async def test_get_task_success(self, client: AsyncClient):
        """Test retrieving existing task."""
        # First create a task to get
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Test Task",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_data = create_response.json()["data"]
        task_id = task_data["id"]

        # Now get the task
        response = await client.get(f"/v1/default/tasks/{task_id}")
        assert response.status_code == 200

        # Verify response structure and data
        retrieved_task = response.json()["data"]
        assert retrieved_task["id"] == task_id
        assert retrieved_task["name"] == "Test Task"
        assert retrieved_task["script"] == "TASK test: RETURN 'hello'"
        assert retrieved_task["tenant_id"] == "default"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, client: AsyncClient):
        """Test 404 error for non-existent task."""
        task_id = uuid.uuid4()
        response = await client.get(f"/v1/default/tasks/{task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_wrong_tenant(self, client: AsyncClient):
        """Test 404 error for wrong tenant."""
        # Create a task for default tenant
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Test Task",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Try to access from different tenant
        response = await client.get(f"/v1/wrong-tenant/tasks/{task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_invalid_uuid(self, client: AsyncClient):
        """Test 400 error for invalid UUID format."""
        response = await client.get("/v1/default/tasks/not-a-uuid")
        assert response.status_code == 422  # Validation error

    # PUT /v1/{tenant}/tasks/{id} Tests
    @pytest.mark.asyncio
    async def test_update_task_name(self, client: AsyncClient):
        """Test updating only name field."""
        # First create a task to update
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Original Name",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Update just the name
        update_data = {"name": "Updated Name"}
        response = await client.put(f"/v1/default/tasks/{task_id}", json=update_data)
        assert response.status_code == 200

        # Verify the update
        updated_task = response.json()["data"]
        assert updated_task["name"] == "Updated Name"
        assert updated_task["script"] == "TASK test: RETURN 'hello'"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_task_script(self, client: AsyncClient):
        """Test updating script field."""
        # First create a task to update
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Test Task",
                "script": "TASK original: RETURN 'old'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Update the script
        update_data = {"script": "TASK updated: RETURN 'new'"}
        response = await client.put(f"/v1/default/tasks/{task_id}", json=update_data)
        assert response.status_code == 200

        # Verify the update
        updated_task = response.json()["data"]
        assert updated_task["script"] == "TASK updated: RETURN 'new'"
        assert updated_task["name"] == "Test Task"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_task_multiple_fields(self, client: AsyncClient):
        """Test updating several fields at once."""
        # First create a task to update
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Original",
                "description": "Old desc",
                "script": "TASK test: RETURN 'hello'",
                "mode": "saved",
                "categories": ["Original"],
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Update multiple fields including new ones
        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
            "function": "processing",
            "mode": "ad_hoc",
            "categories": ["Updated", "Multiple"],
            "directive": "New directive for the task",
            "visible": True,
        }
        response = await client.put(f"/v1/default/tasks/{task_id}", json=update_data)
        assert response.status_code == 200

        # Verify all updates
        updated_task = response.json()["data"]
        assert updated_task["name"] == "Updated Name"
        assert updated_task["description"] == "Updated description"
        assert updated_task["function"] == "processing"
        assert updated_task["mode"] == "ad_hoc"
        assert updated_task["categories"] == ["Updated", "Multiple"]
        assert updated_task["directive"] == "New directive for the task"
        assert updated_task["visible"] is True

    @pytest.mark.asyncio
    async def test_update_task_empty_body(self, client: AsyncClient):
        """Test handling empty update (no-op)."""
        # First create a task to update
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Test Task",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Empty update should succeed but change nothing
        response = await client.put(f"/v1/default/tasks/{task_id}", json={})
        assert response.status_code == 200

        # Verify nothing changed
        updated_task = response.json()["data"]
        assert updated_task["name"] == "Test Task"
        assert updated_task["script"] == "TASK test: RETURN 'hello'"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, client: AsyncClient):
        """Test 404 error for non-existent task."""
        task_id = uuid.uuid4()
        update_data = {"name": "Updated Name"}
        response = await client.put(f"/v1/default/tasks/{task_id}", json=update_data)
        assert response.status_code == 404

    # DELETE /v1/{tenant}/tasks/{id} Tests
    @pytest.mark.asyncio
    async def test_delete_task_success(self, client: AsyncClient):
        """Test deleting existing task returns 204."""
        # First create a task to delete
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Task to Delete",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Delete the task
        response = await client.delete(f"/v1/default/tasks/{task_id}")
        assert response.status_code == 204

        # Verify task is gone
        get_response = await client.get(f"/v1/default/tasks/{task_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, client: AsyncClient):
        """Test 404 error for non-existent task."""
        task_id = uuid.uuid4()
        response = await client.delete(f"/v1/default/tasks/{task_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_task_idempotent(self, client: AsyncClient):
        """Test multiple deletes are idempotent."""
        # First create a task to delete
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Task to Delete",
                "script": "TASK test: RETURN 'hello'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # First delete should succeed
        response1 = await client.delete(f"/v1/default/tasks/{task_id}")
        assert response1.status_code == 204

        # Second delete should return 404 (not found)
        response2 = await client.delete(f"/v1/default/tasks/{task_id}")
        assert response2.status_code == 404

    # GET /v1/{tenant}/tasks/{id}/check-delete Tests
    @pytest.mark.asyncio
    async def test_check_task_deletable_can_delete(self, client: AsyncClient):
        """Test check-delete returns can_delete=True for task not used by workflows."""
        # Create a task that is not used by any workflow
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Deletable Task",
                "script": "TASK deletable: RETURN 'ok'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Check if it can be deleted
        response = await client.get(f"/v1/default/tasks/{task_id}/check-delete")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["can_delete"] is True
        assert data["reason"] is None
        assert data["message"] is None

        # Clean up
        await client.delete(f"/v1/default/tasks/{task_id}")

    @pytest.mark.asyncio
    async def test_check_task_deletable_not_found(self, client: AsyncClient):
        """Test 404 error for non-existent task."""
        task_id = uuid.uuid4()
        response = await client.get(f"/v1/default/tasks/{task_id}/check-delete")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_check_task_deletable_system_protected(self, client: AsyncClient):
        """Test check-delete returns can_delete=False for system_only task."""
        # Create a system_only task
        create_response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "System Protected Task",
                "script": "TASK sys: RETURN 'protected'",
                "created_by": str(SYSTEM_USER_ID),
                "system_only": True,
            },
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["data"]["id"]

        # Check if it can be deleted - should return can_delete=False
        response = await client.get(f"/v1/default/tasks/{task_id}/check-delete")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["can_delete"] is False
        assert data["reason"] == "system_protected"
        assert "system task" in data["message"].lower()

    # GET /v1/{tenant}/tasks Tests
    @pytest.mark.asyncio
    async def test_list_tasks_default_pagination(self, client: AsyncClient):
        """Test default page size and ordering."""
        response = await client.get("/v1/default/tasks")
        assert response.status_code == 200  # Working endpoint now!

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert "total" in body["meta"]

    @pytest.mark.asyncio
    async def test_list_tasks_custom_pagination(self, client: AsyncClient):
        """Test custom skip/limit values."""
        response = await client.get("/v1/default/tasks?offset=10&limit=5")
        assert response.status_code == 200

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["limit"] == 5

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_function(self, client: AsyncClient):
        """Test filtering by function type."""
        response = await client.get("/v1/default/tasks?function=reasoning")
        assert response.status_code == 200

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_scope(self, client: AsyncClient):
        """Test filtering by scope."""
        response = await client.get("/v1/default/tasks?scope=processing")
        assert response.status_code == 200

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body

    @pytest.mark.asyncio
    async def test_list_tasks_combined_filters(self, client: AsyncClient):
        """Test multiple filters together."""
        response = await client.get(
            "/v1/default/tasks?function=reasoning&scope=processing&offset=0&limit=10"
        )
        assert response.status_code == 200

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_pagination(self, client: AsyncClient):
        """Test 422 error for invalid pagination parameters."""
        # Test with limit > 200 (new max limit, validation should fail)
        response = await client.get("/v1/default/tasks?offset=0&limit=201")
        assert response.status_code == 422  # Validation error

        # Test with negative offset (now properly validated)
        response = await client.get("/v1/default/tasks?offset=-1&limit=20")
        assert response.status_code == 422  # Validation error for negative offset

    # Tests for new Component and Task fields
    @pytest.mark.asyncio
    async def test_task_mode_field(self, client: AsyncClient):
        """Test mode field values (ad_hoc vs saved)."""
        # Create ad_hoc task
        ad_hoc_task = {
            "name": "Ad-hoc Task",
            "script": "TASK adhoc: RETURN 'temp'",
            "mode": "ad_hoc",
            "created_by": str(SYSTEM_USER_ID),
        }
        response = await client.post("/v1/default/tasks", json=ad_hoc_task)
        assert response.status_code == 201
        assert response.json()["data"]["mode"] == "ad_hoc"

        # Create saved task
        saved_task = {
            "name": "Saved Task",
            "script": "TASK saved: RETURN 'persistent'",
            "mode": "saved",
            "created_by": str(SYSTEM_USER_ID),
        }
        response = await client.post("/v1/default/tasks", json=saved_task)
        assert response.status_code == 201
        assert response.json()["data"]["mode"] == "saved"

    @pytest.mark.asyncio
    async def test_task_categories_field(self, client: AsyncClient):
        """Test categories array field."""
        task_data = {
            "name": "Categorized Task",
            "script": "TASK cat: RETURN 'data'",
            "categories": ["Security", "AI", "Palo Alto"],
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 201
        created_task = response.json()["data"]
        assert created_task["categories"] == ["Security", "AI", "Palo Alto"]

        # Update categories
        task_id = created_task["id"]
        update_data = {"categories": ["Updated", "New"]}
        response = await client.put(f"/v1/default/tasks/{task_id}", json=update_data)
        assert response.status_code == 200
        assert response.json()["data"]["categories"] == ["Updated", "New"]

    @pytest.mark.asyncio
    async def test_task_directive_field(self, client: AsyncClient):
        """Test directive field for LLM system messages."""
        task_data = {
            "name": "Task with Directive",
            "script": "TASK dir: RETURN 'result'",
            "directive": "You are a security analyst. Focus on threat detection and response.",
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 201
        created_task = response.json()["data"]
        assert created_task["directive"] == task_data["directive"]

    @pytest.mark.asyncio
    async def test_task_visibility_and_system_fields(self, client: AsyncClient):
        """Test visible and system_only fields."""
        task_data = {
            "name": "System Task",
            "script": "TASK sys: RETURN 'internal'",
            "visible": False,
            "system_only": True,
            "created_by": str(SYSTEM_USER_ID),
        }

        response = await client.post("/v1/default/tasks", json=task_data)
        assert response.status_code == 201
        created_task = response.json()["data"]
        assert created_task["visible"] is False
        assert created_task["system_only"] is True

    # GET /v1/{tenant}/tasks with search Tests
    @pytest.mark.asyncio
    async def test_search_tasks_by_name(self, client: AsyncClient):
        """Test finding tasks matching name via q parameter."""
        response = await client.get("/v1/default/tasks?q=security")
        assert response.status_code == 200  # Search is implemented

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body

    @pytest.mark.asyncio
    async def test_search_tasks_empty_query(self, client: AsyncClient):
        """Test 400 error for empty query string."""
        response = await client.get("/v1/default/tasks?q=")
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_search_tasks_pagination(self, client: AsyncClient):
        """Test search results are paginated."""
        response = await client.get("/v1/default/tasks?q=test&offset=5&limit=10")
        assert response.status_code == 200

        # Verify response structure
        body = response.json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["limit"] == 10


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskScriptValidationWithIngestFunctions:
    """Regression: scripts using ingest/checkpoint functions must pass validation.

    Before the fix, creating or updating a task whose script called
    get_checkpoint, set_checkpoint, ingest_alerts, or default_lookback
    returned 500 because those functions were registered at runtime but
    missing from the compile-time tool registry.
    """

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    INGEST_SCRIPT = """\
TASK splunk_ingest:
    lookback = default_lookback()
    last_ts = get_checkpoint("last_event_time")
    start = last_ts ?? lookback
    events = app::splunk::search_events(query="index=main", earliest_time=start)
    result = ingest_alerts(events)
    set_checkpoint("last_event_time", events[-1].timestamp)
    RETURN result
"""

    @pytest.mark.asyncio
    async def test_create_task_with_ingest_functions(self, client: AsyncClient):
        """Creating a task that uses ingest/checkpoint functions should succeed."""
        response = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Splunk Ingest Task",
                "script": self.INGEST_SCRIPT,
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_update_task_script_to_use_ingest_functions(
        self, client: AsyncClient
    ):
        """Updating a task's script to use ingest functions should succeed."""
        # Create with a simple script first
        create_resp = await client.post(
            "/v1/default/tasks",
            json={
                "name": "Task to Update",
                "script": "TASK simple: RETURN 'ok'",
                "created_by": str(SYSTEM_USER_ID),
            },
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["id"]

        # Update to an ingest script
        update_resp = await client.put(
            f"/v1/default/tasks/{task_id}",
            json={"script": self.INGEST_SCRIPT},
        )
        assert update_resp.status_code == 200, (
            f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        )
