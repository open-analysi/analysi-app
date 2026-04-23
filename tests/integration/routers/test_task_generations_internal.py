"""Integration tests for Task Generations Internal API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.kea_coordination import AnalysisGroup, WorkflowGeneration


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskGenerationsInternalEndpoints:
    """Test Task Generations Internal REST API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    async def test_workflow_generation(
        self, integration_test_session: AsyncSession
    ) -> WorkflowGeneration:
        """Create a workflow generation for FK reference."""
        # Create analysis group first
        group = AnalysisGroup(
            tenant_id="test-tenant",
            title=f"Test Group {uuid.uuid4().hex[:8]}",
        )
        integration_test_session.add(group)
        await integration_test_session.flush()

        # Create workflow generation
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=group.id,
            status="running",
            is_active=True,
        )
        integration_test_session.add(generation)
        await integration_test_session.commit()

        return generation

    @pytest.mark.asyncio
    async def test_create_task_generation(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test creating a task generation."""
        response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {
                    "proposal": {"name": "IP Reputation Check", "designation": "new"},
                    "alert": {"title": "Suspicious IP"},
                    "runbook": "## Investigation Steps\n1. Check IP reputation",
                },
            },
        )
        assert response.status_code == 201

        data = response.json()["data"]
        assert data["tenant_id"] == "test-tenant"
        assert data["workflow_generation_id"] == str(test_workflow_generation.id)
        assert data["status"] == "pending"
        assert data["input_context"]["proposal"]["name"] == "IP Reputation Check"
        assert data["created_by"] == str(SYSTEM_USER_ID)
        assert data["progress_messages"] == []
        assert data["result"] is None
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_task_generation(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test retrieving a task generation by ID."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "Test Task"}},
            },
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["data"]["id"]

        # Get by ID
        get_response = await client.get(
            f"/v1/test-tenant/task-generations-internal/{run_id}"
        )
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        assert data["id"] == run_id
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_task_generation_not_found(self, client: AsyncClient):
        """Test getting non-existent task generation returns 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/v1/test-tenant/task-generations-internal/{fake_id}"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_task_generation_tenant_isolation(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test that runs are isolated by tenant."""
        # Create run for test-tenant
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "Tenant Isolated Task"}},
            },
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["data"]["id"]

        # Try to access from other-tenant (should not find it)
        get_response = await client.get(
            f"/v1/other-tenant/task-generations-internal/{run_id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_task_generations_by_generation(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test listing task generations filtered by workflow generation."""
        # Create multiple runs
        for i in range(3):
            await client.post(
                "/v1/test-tenant/task-generations-internal",
                json={
                    "workflow_generation_id": str(test_workflow_generation.id),
                    "input_context": {"proposal": {"name": f"Task {i}"}},
                },
            )

        # List by generation
        response = await client.get(
            f"/v1/test-tenant/task-generations-internal?workflow_generation_id={test_workflow_generation.id}"
        )
        assert response.status_code == 200

        body = response.json()
        assert len(body["data"]) == 3
        assert body["meta"]["total"] == 3

    @pytest.mark.asyncio
    async def test_list_task_generations_returns_paginated_results(
        self, client: AsyncClient
    ):
        """Test that listing without filter returns paginated results."""
        response = await client.get("/v1/test-tenant/task-generations-internal")
        assert response.status_code == 200

        body = response.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]

    @pytest.mark.asyncio
    async def test_update_status_to_in_progress(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test updating status to in_progress."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "In Progress Task"}},
            },
        )
        run_id = create_response.json()["data"]["id"]

        # Update status
        update_response = await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={"status": "running"},
        )
        assert update_response.status_code == 200

        data = update_response.json()["data"]
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_update_status_to_completed_with_result(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test updating status to completed with result."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "Completed Task"}},
            },
        )
        run_id = create_response.json()["data"]["id"]

        # Update to in_progress first
        await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={"status": "running"},
        )

        # Update to completed with result
        update_response = await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={
                "status": "completed",
                "result": {
                    "task_id": str(uuid.uuid4()),
                    "cy_name": "ip_reputation_check",
                    "recovered": False,
                },
            },
        )
        assert update_response.status_code == 200

        data = update_response.json()["data"]
        assert data["status"] == "completed"
        assert data["result"]["cy_name"] == "ip_reputation_check"
        assert data["result"]["recovered"] is False

    @pytest.mark.asyncio
    async def test_update_status_to_failed_with_error(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test updating status to failed with error details."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "Failed Task"}},
            },
        )
        run_id = create_response.json()["data"]["id"]

        # Update to failed
        update_response = await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={
                "status": "failed",
                "result": {
                    "error": "Agent execution failed: timeout",
                    "error_type": "TimeoutError",
                    "recovered": False,
                },
            },
        )
        assert update_response.status_code == 200

        data = update_response.json()["data"]
        assert data["status"] == "failed"
        assert data["result"]["error"] == "Agent execution failed: timeout"

    @pytest.mark.asyncio
    async def test_append_progress_messages(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test appending progress messages."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "Progress Task"}},
            },
        )
        run_id = create_response.json()["data"]["id"]

        # Append progress messages
        now = datetime.now(UTC).isoformat()
        progress_response = await client.post(
            f"/v1/test-tenant/task-generations-internal/{run_id}/progress",
            json={
                "messages": [
                    {
                        "timestamp": now,
                        "message": "Starting task building",
                        "level": "info",
                        "details": {},
                    },
                    {
                        "timestamp": now,
                        "message": "Loading agent",
                        "level": "info",
                        "details": {"agent": "cybersec-task-builder.md"},
                    },
                ]
            },
        )
        assert progress_response.status_code == 200

        data = progress_response.json()["data"]
        assert len(data["progress_messages"]) == 2
        assert data["progress_messages"][0]["message"] == "Starting task building"
        assert (
            data["progress_messages"][1]["details"]["agent"]
            == "cybersec-task-builder.md"
        )

    @pytest.mark.asyncio
    async def test_progress_messages_fifo_limit(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test that progress_messages respects 100 message FIFO limit."""
        # Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {"proposal": {"name": "FIFO Test Task"}},
            },
        )
        run_id = create_response.json()["data"]["id"]

        now = datetime.now(UTC).isoformat()

        # Append 120 messages in batches (exceeds 100 limit)
        for batch in range(12):
            messages = [
                {
                    "timestamp": now,
                    "message": f"Message batch-{batch}-{i}",
                    "level": "info",
                    "details": {"batch": batch, "index": i},
                }
                for i in range(10)
            ]
            await client.post(
                f"/v1/test-tenant/task-generations-internal/{run_id}/progress",
                json={"messages": messages},
            )

        # Get the run and verify only last 100 messages are kept
        get_response = await client.get(
            f"/v1/test-tenant/task-generations-internal/{run_id}"
        )
        assert get_response.status_code == 200

        data = get_response.json()["data"]
        assert len(data["progress_messages"]) == 100

        # First message should be from batch 2 (batches 0-1 were dropped)
        # 120 messages - 100 kept = 20 dropped = 2 batches dropped
        assert data["progress_messages"][0]["message"].startswith("Message batch-2-")

        # Last message should be from batch 11
        assert data["progress_messages"][-1]["message"].startswith("Message batch-11-")

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, client: AsyncClient, test_workflow_generation: WorkflowGeneration
    ):
        """Test full lifecycle: create -> in_progress -> progress -> completed."""
        now = datetime.now(UTC).isoformat()

        # 1. Create run
        create_response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "workflow_generation_id": str(test_workflow_generation.id),
                "input_context": {
                    "proposal": {"name": "Lifecycle Test", "designation": "new"},
                    "alert": {"title": "Test Alert"},
                    "runbook": "Test runbook content",
                },
            },
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["data"]["id"]
        assert create_response.json()["data"]["status"] == "pending"

        # 2. Update to in_progress
        await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={"status": "running"},
        )

        # 3. Append progress messages
        await client.post(
            f"/v1/test-tenant/task-generations-internal/{run_id}/progress",
            json={
                "messages": [
                    {
                        "timestamp": now,
                        "message": "Starting agent",
                        "level": "info",
                        "details": {},
                    },
                    {
                        "timestamp": now,
                        "message": "Agent running",
                        "level": "info",
                        "details": {},
                    },
                ]
            },
        )

        # 4. Update to completed with result
        task_id = str(uuid.uuid4())
        update_response = await client.patch(
            f"/v1/test-tenant/task-generations-internal/{run_id}/status",
            json={
                "status": "completed",
                "result": {
                    "task_id": task_id,
                    "cy_name": "lifecycle_test_task",
                    "recovered": False,
                },
            },
        )
        assert update_response.status_code == 200

        # 5. Verify final state
        final_response = await client.get(
            f"/v1/test-tenant/task-generations-internal/{run_id}"
        )
        assert final_response.status_code == 200

        final_data = final_response.json()["data"]
        assert final_data["status"] == "completed"
        assert final_data["result"]["task_id"] == task_id
        assert final_data["result"]["cy_name"] == "lifecycle_test_task"
        assert len(final_data["progress_messages"]) == 2
        assert final_data["input_context"]["proposal"]["name"] == "Lifecycle Test"

    @pytest.mark.asyncio
    async def test_cascade_delete_on_workflow_generation(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        test_workflow_generation: WorkflowGeneration,
    ):
        """Test FK cascade: deleting workflow_generation deletes task_generations."""
        # Create task generations
        for i in range(3):
            response = await client.post(
                "/v1/test-tenant/task-generations-internal",
                json={
                    "workflow_generation_id": str(test_workflow_generation.id),
                    "input_context": {"proposal": {"name": f"Cascade Test {i}"}},
                },
            )
            assert response.status_code == 201

        # Verify runs exist
        list_response = await client.get(
            f"/v1/test-tenant/task-generations-internal?workflow_generation_id={test_workflow_generation.id}"
        )
        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 3

        # Delete the workflow generation (via session, not API)
        await integration_test_session.delete(test_workflow_generation)
        await integration_test_session.commit()

        # Verify runs are also deleted (cascade)
        list_response_after = await client.get(
            f"/v1/test-tenant/task-generations-internal?workflow_generation_id={test_workflow_generation.id}"
        )
        assert list_response_after.status_code == 200
        assert len(list_response_after.json()["data"]) == 0

    @pytest.mark.asyncio
    async def test_create_rejects_null_workflow_generation_id(
        self, client: AsyncClient
    ):
        """Test POST rejects requests without workflow_generation_id.

        Standalone builds must use POST /task-generations instead.
        """
        response = await client.post(
            "/v1/test-tenant/task-generations-internal",
            json={
                "input_context": {"description": "Should be rejected"},
            },
        )
        assert response.status_code == 400
        assert "workflow_generation_id is required" in response.json()["detail"]
